"""Inactivación, novedades y regreso a servicio de las unidades (HU-09, SRS 3.1.8).

Contra Postgres. "Hoy" es fijo para que los tests no dependan del día en que se corren.
"""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.auditoria import RegistroAuditoria
from app.comun.errores import PermisoDenegado
from app.comun.paginacion import ParametrosPagina
from app.modulos.alquileres.modelos import EstadoAlquiler
from app.modulos.domicilios.modelos import Domicilio, ZonaCobertura
from app.modulos.inventario import servicio
from app.modulos.inventario.esquemas import CierreNovedad, FiltrosCatalogo, NovedadCrear
from app.modulos.inventario.excepciones import (
    NoPuedeVolverAServicio,
    NovedadNoEncontrada,
    NovedadYaCerrada,
    TransicionInvalida,
    VehiculoNoEncontrado,
    VehiculoVendido,
)
from app.modulos.inventario.modelos import (
    EstadoNovedad,
    EstadoVehiculo,
    NovedadVehiculo,
    TipoNovedad,
)
from app.modulos.usuarios.modelos import Rol

HOY = date(2026, 10, 1)
MOMENTO = datetime(2026, 10, 1, 15, 0, tzinfo=UTC)
MOTIVO = "Cambio de rodamientos de la rueda delantera."


@pytest.fixture
def operador(crear_usuario):
    return crear_usuario(Rol.OPERADOR)


def _inactivar(sesion, vehiculo, usuario):
    return servicio.inactivar_vehiculo(
        sesion, vehiculo.id, MOTIVO, usuario, hoy=HOY, momento=MOMENTO
    )


def _reportar(sesion, vehiculo, usuario, *, critica: bool, tipo=TipoNovedad.DANO):
    datos = NovedadCrear(tipo=tipo, descripcion="Rayón en el manubrio.", es_critica=critica)
    return servicio.reportar_novedad(sesion, vehiculo.id, datos, usuario, hoy=HOY, momento=MOMENTO)


def _cerrar(sesion, vehiculo, novedad, usuario, *, devolver: bool):
    datos = CierreNovedad(solucion="Reparado y probado en ruta.", devolver_a_servicio=devolver)
    return servicio.cerrar_novedad(sesion, vehiculo.id, novedad.id, datos, usuario)


def _cambios_de_estado(sesion, vehiculo) -> list[RegistroAuditoria]:
    consulta = (
        select(RegistroAuditoria)
        .filter_by(entidad="vehiculos", entidad_id=str(vehiculo.id), accion="cambiar_estado")
        .order_by(RegistroAuditoria.id)
    )
    return list(sesion.scalars(consulta))


def _disponibles_hoy(sesion, modelo) -> int:
    pagina = servicio.listar_modelos(
        sesion, ParametrosPagina(), FiltrosCatalogo(), hoy=HOY, momento=MOMENTO
    )
    return next(e.disponibles_hoy for e in pagina.elementos if e.modelo.id == modelo.id)


# --- Inactivación (HU-09) -------------------------------------------------------------


def test_inactivar_pasa_a_mantenimiento_con_novedad_abierta_y_motivo(
    sesion, fabrica, operador
) -> None:
    vehiculo = fabrica.vehiculo()

    resultado = _inactivar(sesion, vehiculo, operador)

    assert vehiculo.estado == EstadoVehiculo.MANTENIMIENTO
    novedad = resultado.novedad
    assert novedad.tipo == TipoNovedad.MANTENIMIENTO
    assert novedad.es_critica
    assert novedad.estado == EstadoNovedad.ABIERTA
    assert novedad.descripcion == MOTIVO
    assert novedad.reportada_por_id == operador.id


def test_inactivar_la_saca_del_catalogo_al_instante(sesion, fabrica, operador) -> None:
    modelo = fabrica.modelo()
    vehiculo = fabrica.vehiculo(modelo, codigo="MON-0001")
    fabrica.vehiculo(modelo, codigo="MON-0002")
    assert _disponibles_hoy(sesion, modelo) == 2

    _inactivar(sesion, vehiculo, operador)

    assert _disponibles_hoy(sesion, modelo) == 1
    detalle = servicio.obtener_modelo(sesion, modelo.id, hoy=HOY, momento=MOMENTO)
    assert [u.codigo for u in detalle.unidades] == ["MON-0002"]


def test_el_cambio_de_estado_queda_en_auditoria(sesion, fabrica, operador) -> None:
    vehiculo = fabrica.vehiculo()

    resultado = _inactivar(sesion, vehiculo, operador)

    [registro] = _cambios_de_estado(sesion, vehiculo)
    assert registro.usuario_id == operador.id
    assert registro.datos_anteriores == {"estado": "disponible"}
    assert registro.datos_nuevos == {
        "estado": "mantenimiento",
        "motivo": f"Novedad crítica #{resultado.novedad.id} (mantenimiento)",
    }


def test_no_se_puede_inactivar_una_unidad_vendida(sesion, fabrica, operador) -> None:
    vehiculo = fabrica.vehiculo(estado=EstadoVehiculo.VENDIDO)

    with pytest.raises(VehiculoVendido):
        _inactivar(sesion, vehiculo, operador)


def test_unidad_inexistente(sesion, operador) -> None:
    with pytest.raises(VehiculoNoEncontrado):
        servicio.inactivar_vehiculo(sesion, 999_999, MOTIVO, operador, hoy=HOY, momento=MOMENTO)


@pytest.mark.parametrize("rol", [Rol.CLIENTE, Rol.DOMICILIARIO])
def test_solo_administrador_u_operador(sesion, fabrica, crear_usuario, rol: Rol) -> None:
    vehiculo = fabrica.vehiculo()

    with pytest.raises(PermisoDenegado):
        _inactivar(sesion, vehiculo, crear_usuario(rol))

    assert vehiculo.estado == EstadoVehiculo.DISPONIBLE


def test_los_alquileres_vigentes_se_informan_y_no_se_cancelan(sesion, fabrica, operador) -> None:
    vehiculo = fabrica.vehiculo()
    fabrica.alquiler(vehiculo, HOY - timedelta(10), HOY - timedelta(8), EstadoAlquiler.FINALIZADO)
    fabrica.alquiler(vehiculo, HOY + timedelta(3), HOY + timedelta(5), EstadoAlquiler.CANCELADO)
    futuro = fabrica.alquiler(vehiculo, HOY + timedelta(3), HOY + timedelta(5))

    resultado = _inactivar(sesion, vehiculo, operador)

    assert [a.id for a in resultado.alquileres_afectados] == [futuro.id]
    assert futuro.estado == EstadoAlquiler.CONFIRMADO


# --- Novedades (SRS 3.1.8) ------------------------------------------------------------


def test_una_novedad_no_critica_no_cambia_el_estado(sesion, fabrica, operador) -> None:
    vehiculo = fabrica.vehiculo()

    resultado = _reportar(sesion, vehiculo, operador, critica=False)

    assert vehiculo.estado == EstadoVehiculo.DISPONIBLE
    assert resultado.novedad.estado == EstadoNovedad.ABIERTA
    assert _cambios_de_estado(sesion, vehiculo) == []


@pytest.mark.parametrize(
    "estado",
    [EstadoVehiculo.DISPONIBLE, EstadoVehiculo.ALQUILADO, EstadoVehiculo.ASIGNADO_A_DOMICILIO],
)
def test_una_novedad_critica_pasa_a_mantenimiento_automaticamente(
    sesion, fabrica, operador, estado: EstadoVehiculo
) -> None:
    vehiculo = fabrica.vehiculo(estado=estado)

    _reportar(sesion, vehiculo, operador, critica=True, tipo=TipoNovedad.FALLA)

    assert vehiculo.estado == EstadoVehiculo.MANTENIMIENTO


def test_novedad_critica_sobre_unidad_ya_en_mantenimiento_solo_se_agrega(
    sesion, fabrica, operador
) -> None:
    vehiculo = fabrica.vehiculo()
    _inactivar(sesion, vehiculo, operador)

    _reportar(sesion, vehiculo, operador, critica=True)

    assert vehiculo.estado == EstadoVehiculo.MANTENIMIENTO
    assert len(_cambios_de_estado(sesion, vehiculo)) == 1
    abiertas = sesion.scalars(
        select(NovedadVehiculo).filter_by(vehiculo_id=vehiculo.id, estado=EstadoNovedad.ABIERTA)
    ).all()
    assert len(abiertas) == 2


# --- Cierre y regreso a servicio ------------------------------------------------------


def test_cerrar_y_devolver_a_servicio(sesion, fabrica, operador, crear_usuario) -> None:
    modelo = fabrica.modelo()
    vehiculo = fabrica.vehiculo(modelo)
    novedad = _inactivar(sesion, vehiculo, operador).novedad
    administrador = crear_usuario(Rol.ADMINISTRADOR)

    _cerrar(sesion, vehiculo, novedad, administrador, devolver=True)

    assert vehiculo.estado == EstadoVehiculo.DISPONIBLE
    assert novedad.estado == EstadoNovedad.CERRADA
    assert novedad.cerrada_por_id == administrador.id
    assert novedad.solucion == "Reparado y probado en ruta."
    assert _disponibles_hoy(sesion, modelo) == 1
    salida, regreso = _cambios_de_estado(sesion, vehiculo)
    assert regreso.usuario_id == administrador.id
    assert regreso.datos_anteriores == {"estado": "mantenimiento"}
    assert regreso.datos_nuevos["estado"] == "disponible"


def test_cerrar_sin_devolver_deja_la_unidad_en_mantenimiento(sesion, fabrica, operador) -> None:
    vehiculo = fabrica.vehiculo()
    novedad = _inactivar(sesion, vehiculo, operador).novedad

    _cerrar(sesion, vehiculo, novedad, operador, devolver=False)

    assert novedad.estado == EstadoNovedad.CERRADA
    assert vehiculo.estado == EstadoVehiculo.MANTENIMIENTO


def test_no_vuelve_con_otra_novedad_abierta_y_no_cierra_nada(sesion, fabrica, operador) -> None:
    vehiculo = fabrica.vehiculo()
    novedad = _inactivar(sesion, vehiculo, operador).novedad
    _reportar(sesion, vehiculo, operador, critica=False)

    with pytest.raises(NoPuedeVolverAServicio, match="1 novedad"):
        _cerrar(sesion, vehiculo, novedad, operador, devolver=True)

    # Todo o nada: la novedad sigue abierta y la unidad sigue en mantenimiento.
    sesion.refresh(novedad)
    sesion.refresh(vehiculo)
    assert novedad.estado == EstadoNovedad.ABIERTA
    assert vehiculo.estado == EstadoVehiculo.MANTENIMIENTO


def test_cerrando_primero_las_demas_si_vuelve(sesion, fabrica, operador) -> None:
    vehiculo = fabrica.vehiculo()
    principal = _inactivar(sesion, vehiculo, operador).novedad
    menor = _reportar(sesion, vehiculo, operador, critica=False).novedad

    _cerrar(sesion, vehiculo, menor, operador, devolver=False)
    _cerrar(sesion, vehiculo, principal, operador, devolver=True)

    assert vehiculo.estado == EstadoVehiculo.DISPONIBLE


def test_no_vuelve_si_tiene_un_alquiler_en_curso(sesion, fabrica, operador) -> None:
    vehiculo = fabrica.vehiculo(estado=EstadoVehiculo.ALQUILADO)
    fabrica.alquiler(vehiculo, HOY - timedelta(1), HOY + timedelta(1), EstadoAlquiler.EN_CURSO)
    novedad = _reportar(sesion, vehiculo, operador, critica=True, tipo=TipoNovedad.FALLA).novedad

    with pytest.raises(NoPuedeVolverAServicio, match="alquiler en curso"):
        _cerrar(sesion, vehiculo, novedad, operador, devolver=True)


def test_no_vuelve_si_participa_en_un_domicilio_sin_finalizar(sesion, fabrica, operador) -> None:
    vehiculo = fabrica.vehiculo()
    alquiler = fabrica.alquiler(fabrica.vehiculo(), HOY, HOY + timedelta(2))
    zona = ZonaCobertura(nombre="Centro", poligono={"type": "Polygon"}, tarifa_envio=4_000)
    sesion.add(zona)
    sesion.flush()
    sesion.add(
        Domicilio(
            codigo_rastreo="TX000001",
            cliente_id=alquiler.cliente_id,
            alquiler_id=alquiler.id,
            zona_id=zona.id,
            direccion="Calle 36 # 20-15",
            latitud=Decimal("7.119300"),
            longitud=Decimal("-73.122700"),
            vehiculo_transporte_id=vehiculo.id,  # el domiciliario usa esta unidad
        )
    )
    novedad = _inactivar(sesion, vehiculo, operador).novedad

    with pytest.raises(NoPuedeVolverAServicio, match="domicilio sin finalizar"):
        _cerrar(sesion, vehiculo, novedad, operador, devolver=True)


def test_devolver_una_unidad_que_no_esta_en_mantenimiento_es_transicion_invalida(
    sesion, fabrica, operador
) -> None:
    vehiculo = fabrica.vehiculo()
    novedad = _reportar(sesion, vehiculo, operador, critica=False).novedad

    with pytest.raises(TransicionInvalida):
        _cerrar(sesion, vehiculo, novedad, operador, devolver=True)

    sesion.refresh(novedad)
    assert novedad.estado == EstadoNovedad.ABIERTA


def test_no_se_cierra_dos_veces(sesion, fabrica, operador) -> None:
    vehiculo = fabrica.vehiculo()
    novedad = _inactivar(sesion, vehiculo, operador).novedad
    _cerrar(sesion, vehiculo, novedad, operador, devolver=False)

    with pytest.raises(NovedadYaCerrada):
        _cerrar(sesion, vehiculo, novedad, operador, devolver=False)


def test_la_novedad_debe_ser_de_esa_unidad(sesion, fabrica, operador) -> None:
    una, otra = fabrica.vehiculo(), fabrica.vehiculo()
    novedad = _inactivar(sesion, una, operador).novedad

    with pytest.raises(NovedadNoEncontrada):
        _cerrar(sesion, otra, novedad, operador, devolver=True)


# --- Listados -------------------------------------------------------------------------


def test_la_flota_muestra_todos_los_estados_y_filtra(sesion, fabrica) -> None:
    fabrica.vehiculo(codigo="MON-0001")
    fabrica.vehiculo(codigo="MON-0002", estado=EstadoVehiculo.MANTENIMIENTO)
    fabrica.vehiculo(codigo="CIC-0001", estado=EstadoVehiculo.VENDIDO)

    todos = servicio.listar_vehiculos(sesion, ParametrosPagina())
    en_taller = servicio.listar_vehiculos(
        sesion, ParametrosPagina(), estado=EstadoVehiculo.MANTENIMIENTO
    )
    monopatines = servicio.listar_vehiculos(sesion, ParametrosPagina(), codigo="mon")

    assert [v.codigo for v in todos.elementos] == ["CIC-0001", "MON-0001", "MON-0002"]
    assert [v.codigo for v in en_taller.elementos] == ["MON-0002"]
    assert monopatines.total == 2


def test_historial_de_novedades_filtrado_por_estado(sesion, fabrica, operador) -> None:
    vehiculo = fabrica.vehiculo()
    novedad = _inactivar(sesion, vehiculo, operador).novedad
    _cerrar(sesion, vehiculo, novedad, operador, devolver=True)
    _reportar(sesion, vehiculo, operador, critica=False)

    todas = servicio.listar_novedades(sesion, vehiculo.id, ParametrosPagina())
    abiertas = servicio.listar_novedades(
        sesion, vehiculo.id, ParametrosPagina(), estado=EstadoNovedad.ABIERTA
    )

    assert todas.total == 2
    assert abiertas.total == 1
