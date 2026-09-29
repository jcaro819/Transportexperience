"""Catálogo público y disponibilidad (HU-02), contra Postgres.

Fecha fija para que los tests no dependan del día en que se corren: "hoy" es el 1 de
octubre de 2026 a las 3 p. m. (UTC).
"""

from datetime import UTC, date, datetime, timedelta

import pytest

from app.comun.paginacion import ParametrosPagina
from app.modulos.alquileres.modelos import EstadoAlquiler
from app.modulos.inventario import servicio
from app.modulos.inventario.esquemas import FiltrosCatalogo, Modalidad
from app.modulos.inventario.excepciones import (
    FechasInvalidas,
    ModeloNoEncontrado,
    ModeloNoSeAlquila,
    RangoDeTarifaInvalido,
)
from app.modulos.inventario.modelos import EstadoVehiculo

HOY = date(2026, 10, 1)
MOMENTO = datetime(2026, 10, 1, 15, 0, tzinfo=UTC)
TODO = ParametrosPagina(tamano=100)


def _dia(n: int) -> date:
    return HOY + timedelta(days=n)


def _listar(sesion, filtros: FiltrosCatalogo | None = None, parametros=TODO):
    return servicio.listar_modelos(
        sesion, parametros, filtros or FiltrosCatalogo(), hoy=HOY, momento=MOMENTO
    )


def _disponibles_hoy(sesion, modelo) -> int:
    [elemento] = [e for e in _listar(sesion).elementos if e.modelo.id == modelo.id]
    return elemento.disponibles_hoy


def _libres(sesion, modelo, inicio: date, fin: date) -> int:
    resultado = servicio.consultar_disponibilidad(
        sesion, modelo.id, inicio, fin, hoy=HOY, momento=MOMENTO
    )
    return resultado.unidades_libres


# --- Disponibles hoy ------------------------------------------------------------------


def test_solo_cuentan_las_unidades_fisicamente_disponibles(sesion, fabrica) -> None:
    modelo = fabrica.modelo()
    for estado in EstadoVehiculo:
        fabrica.vehiculo(modelo, estado)

    assert _disponibles_hoy(sesion, modelo) == 1


def test_un_alquiler_que_cubre_hoy_ocupa_la_unidad_aunque_no_se_haya_entregado(
    sesion, fabrica
) -> None:
    modelo = fabrica.modelo()
    comprometida = fabrica.vehiculo(modelo)
    fabrica.alquiler(comprometida, HOY, _dia(2))
    fabrica.vehiculo(modelo)

    assert _disponibles_hoy(sesion, modelo) == 1


def test_alquileres_futuros_o_terminados_no_ocupan_hoy(sesion, fabrica) -> None:
    modelo = fabrica.modelo()
    vehiculo = fabrica.vehiculo(modelo)
    fabrica.alquiler(vehiculo, _dia(-5), _dia(-2), EstadoAlquiler.FINALIZADO)
    fabrica.alquiler(vehiculo, _dia(-1), _dia(1), EstadoAlquiler.CANCELADO)
    fabrica.alquiler(vehiculo, _dia(3), _dia(4))

    assert _disponibles_hoy(sesion, modelo) == 1


def test_un_pago_pendiente_vigente_ocupa_y_uno_vencido_libera(sesion, fabrica) -> None:
    modelo = fabrica.modelo()
    vigente = fabrica.vehiculo(modelo)
    vencido = fabrica.vehiculo(modelo)
    pendiente = EstadoAlquiler.PENDIENTE_PAGO
    fabrica.alquiler(vigente, HOY, HOY, pendiente, expira_en=MOMENTO + timedelta(minutes=10))
    fabrica.alquiler(vencido, HOY, HOY, pendiente, expira_en=MOMENTO - timedelta(minutes=1))

    assert _disponibles_hoy(sesion, modelo) == 1


# --- Listado y filtros ----------------------------------------------------------------


def test_oculta_modelos_inactivos_y_modelos_de_tipos_inactivos(sesion, fabrica) -> None:
    visible = fabrica.modelo()
    fabrica.modelo(activo=False)
    fabrica.modelo(fabrica.tipo(activo=False))

    assert [e.modelo.id for e in _listar(sesion).elementos] == [visible.id]


def test_filtra_por_tipo(sesion, fabrica) -> None:
    ciclas = fabrica.tipo("Cicla")
    cicla = fabrica.modelo(ciclas)
    fabrica.modelo(fabrica.tipo("Patín"))

    resultado = _listar(sesion, FiltrosCatalogo(tipo_id=ciclas.id))

    assert [e.modelo.id for e in resultado.elementos] == [cicla.id]


def test_filtra_por_rango_de_tarifa_inclusivo(sesion, fabrica) -> None:
    fabrica.modelo(tarifa_diaria=20_000)
    medio = fabrica.modelo(tarifa_diaria=40_000)
    borde = fabrica.modelo(tarifa_diaria=60_000)
    fabrica.modelo(tarifa_diaria=80_000)
    fabrica.modelo(tarifa_diaria=None, precio_venta=1_000_000)  # solo venta: sin tarifa

    resultado = _listar(sesion, FiltrosCatalogo(tarifa_min=30_000, tarifa_max=60_000))

    assert {e.modelo.id for e in resultado.elementos} == {medio.id, borde.id}


def test_filtra_por_modalidad(sesion, fabrica) -> None:
    solo_alquiler = fabrica.modelo(tarifa_diaria=30_000)
    solo_venta = fabrica.modelo(tarifa_diaria=None, precio_venta=900_000)
    ambos = fabrica.modelo(tarifa_diaria=30_000, precio_venta=900_000)

    alquiler = _listar(sesion, FiltrosCatalogo(modalidad=Modalidad.ALQUILER))
    venta = _listar(sesion, FiltrosCatalogo(modalidad=Modalidad.VENTA))

    assert {e.modelo.id for e in alquiler.elementos} == {solo_alquiler.id, ambos.id}
    assert {e.modelo.id for e in venta.elementos} == {solo_venta.id, ambos.id}


def test_solo_disponibles_excluye_modelos_sin_unidades_libres_hoy(sesion, fabrica) -> None:
    con_unidades = fabrica.modelo()
    fabrica.vehiculo(con_unidades)
    en_taller = fabrica.modelo()
    fabrica.vehiculo(en_taller, EstadoVehiculo.MANTENIMIENTO)
    fabrica.modelo()  # sin unidades

    resultado = _listar(sesion, FiltrosCatalogo(solo_disponibles=True))

    assert [e.modelo.id for e in resultado.elementos] == [con_unidades.id]


def test_rango_de_tarifa_invertido_es_un_error(sesion) -> None:
    with pytest.raises(RangoDeTarifaInvalido):
        _listar(sesion, FiltrosCatalogo(tarifa_min=50_000, tarifa_max=10_000))


def test_listado_paginado_y_ordenado_por_tipo_y_nombre(sesion, fabrica) -> None:
    patines, ciclas = fabrica.tipo("Patín"), fabrica.tipo("Cicla")
    fabrica.modelo(patines, nombre="Patín A")
    fabrica.modelo(ciclas, nombre="Cicla B")
    fabrica.modelo(ciclas, nombre="Cicla A")

    primera = _listar(sesion, parametros=ParametrosPagina(pagina=1, tamano=2))
    segunda = _listar(sesion, parametros=ParametrosPagina(pagina=2, tamano=2))

    assert primera.total == 3
    assert primera.paginas == 2
    assert [e.modelo.nombre for e in primera.elementos + segunda.elementos] == [
        "Cicla A",
        "Cicla B",
        "Patín A",
    ]


# --- Detalle --------------------------------------------------------------------------


def test_detalle_muestra_solo_unidades_libres_hoy_con_bateria_y_ubicacion(sesion, fabrica) -> None:
    modelo = fabrica.modelo()
    fabrica.vehiculo(modelo, codigo="MON-0002", nivel_bateria=80, ubicacion="Sede Centro")
    fabrica.vehiculo(modelo, codigo="MON-0001", nivel_bateria=95, ubicacion="Sede Cabecera")
    fabrica.vehiculo(modelo, EstadoVehiculo.MANTENIMIENTO, codigo="MON-0003")

    detalle = servicio.obtener_modelo(sesion, modelo.id, hoy=HOY, momento=MOMENTO)

    assert [(u.codigo, u.nivel_bateria) for u in detalle.unidades] == [
        ("MON-0001", 95),
        ("MON-0002", 80),
    ]


@pytest.mark.parametrize("caso", ["inexistente", "inactivo"])
def test_detalle_de_modelo_inexistente_o_inactivo(sesion, fabrica, caso: str) -> None:
    modelo_id = 999_999 if caso == "inexistente" else fabrica.modelo(activo=False).id

    with pytest.raises(ModeloNoEncontrado):
        servicio.obtener_modelo(sesion, modelo_id, hoy=HOY, momento=MOMENTO)


# --- Disponibilidad por rango de fechas -----------------------------------------------


def test_un_alquiler_solapado_quita_la_unidad_del_rango(sesion, fabrica) -> None:
    modelo = fabrica.modelo()
    ocupada = fabrica.vehiculo(modelo)
    fabrica.vehiculo(modelo)
    fabrica.alquiler(ocupada, _dia(5), _dia(7))

    assert _libres(sesion, modelo, _dia(7), _dia(9)) == 1
    assert _libres(sesion, modelo, _dia(8), _dia(10)) == 2  # fechas inclusivas: libre el 8


def test_a_futuro_cuenta_una_unidad_alquilada_hoy_que_se_devuelve_antes(sesion, fabrica) -> None:
    modelo = fabrica.modelo()
    alquilada = fabrica.vehiculo(modelo, EstadoVehiculo.ALQUILADO)
    fabrica.alquiler(alquilada, _dia(-1), _dia(1), EstadoAlquiler.EN_CURSO)

    assert _libres(sesion, modelo, HOY, _dia(3)) == 0
    assert _libres(sesion, modelo, _dia(2), _dia(3)) == 1


def test_una_unidad_en_mantenimiento_nunca_esta_libre(sesion, fabrica) -> None:
    modelo = fabrica.modelo()
    fabrica.vehiculo(modelo, EstadoVehiculo.MANTENIMIENTO)
    fabrica.vehiculo(modelo, EstadoVehiculo.VENDIDO)
    fabrica.vehiculo(modelo, EstadoVehiculo.RESERVADO)

    assert _libres(sesion, modelo, _dia(30), _dia(31)) == 0


def test_resultado_del_rango_trae_los_dias_inclusivos(sesion, fabrica) -> None:
    modelo = fabrica.modelo()
    fabrica.vehiculo(modelo)

    resultado = servicio.consultar_disponibilidad(
        sesion, modelo.id, _dia(5), _dia(7), hoy=HOY, momento=MOMENTO
    )

    assert resultado.dias == 3
    assert resultado.disponible


@pytest.mark.parametrize(
    ("inicio", "fin"),
    [(_dia(-1), _dia(2)), (_dia(5), _dia(4))],
    ids=["inicio_en_el_pasado", "fin_antes_del_inicio"],
)
def test_fechas_invalidas(sesion, fabrica, inicio: date, fin: date) -> None:
    modelo = fabrica.modelo()

    with pytest.raises(FechasInvalidas):
        servicio.consultar_disponibilidad(sesion, modelo.id, inicio, fin, hoy=HOY, momento=MOMENTO)


def test_un_modelo_solo_de_venta_no_tiene_disponibilidad_de_alquiler(sesion, fabrica) -> None:
    modelo = fabrica.modelo(tarifa_diaria=None, precio_venta=1_500_000)

    with pytest.raises(ModeloNoSeAlquila):
        servicio.consultar_disponibilidad(sesion, modelo.id, HOY, HOY, hoy=HOY, momento=MOMENTO)
