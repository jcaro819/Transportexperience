"""Servicio de alquileres (HU-03): reservar, pagar, cancelar, entregar, recibir, reasignar.

Contra Postgres. "Hoy" y "ahora" son fijos para que los tests no dependan del día en que
se corren. La concurrencia se prueba aparte, en ``test_concurrencia.py``.
"""

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select

from app.auditoria import RegistroAuditoria
from app.comun.errores import PermisoDenegado
from app.comun.paginacion import ParametrosPagina
from app.modulos.alquileres import servicio
from app.modulos.alquileres.excepciones import (
    AlquilerNoCancelable,
    AlquilerNoEncontrado,
    DuracionExcedida,
    FueraDeLasFechasDelAlquiler,
    ReasignacionInvalida,
    ReservaExpirada,
    SinUnidadesDisponibles,
    TransicionDeAlquilerInvalida,
    VehiculoNoListoParaEntrega,
)
from app.modulos.alquileres.modelos import Alquiler, EstadoAlquiler
from app.modulos.inventario import servicio as inventario
from app.modulos.inventario.esquemas import NovedadCrear
from app.modulos.inventario.excepciones import ModeloNoSeAlquila
from app.modulos.inventario.modelos import EstadoVehiculo, TipoNovedad
from app.modulos.pagos import procesamiento
from app.modulos.pagos.esquemas import PagoCrear
from app.modulos.pagos.excepciones import MetodoDePagoNoDisponible
from app.modulos.pagos.modelos import EstadoPago, MetodoPago, Pago
from app.modulos.pagos.pasarela import PasarelaFalsa
from app.modulos.usuarios.modelos import Rol
from app.parametros import MAX_DIAS_ALQUILER, ParametroSistema

HOY = date(2026, 11, 2)
MOMENTO = datetime(2026, 11, 2, 15, 0, tzinfo=UTC)
INICIO = HOY + timedelta(days=3)
FIN = HOY + timedelta(days=5)  # 3 días
TARIFA = 40_000


@pytest.fixture(autouse=True)
def metodos_pago(sesion) -> None:
    sesion.add_all(
        [
            MetodoPago(codigo="tarjeta", nombre="Tarjeta"),
            MetodoPago(codigo="pse", nombre="PSE", activo=False),
        ]
    )
    sesion.flush()


@pytest.fixture
def modelo(fabrica):
    return fabrica.modelo(tarifa_diaria=TARIFA)


@pytest.fixture
def cliente(fabrica):
    return fabrica.cliente()


@pytest.fixture
def operador(crear_usuario):
    return crear_usuario(Rol.OPERADOR)


@pytest.fixture
def administrador(crear_usuario):
    return crear_usuario(Rol.ADMINISTRADOR)


def _reservar(sesion, cliente, modelo, inicio=INICIO, fin=FIN, momento=MOMENTO) -> Alquiler:
    return servicio.crear_alquiler(
        sesion, cliente, modelo.id, inicio, fin, hoy=HOY, momento=momento
    )


def _pagar(sesion, alquiler, cliente, *, aprueba=True, metodo="tarjeta", momento=MOMENTO):
    pasarela = PasarelaFalsa(EstadoPago.APROBADO if aprueba else EstadoPago.RECHAZADO)
    return procesamiento.pagar(
        sesion,
        cliente,
        PagoCrear(metodo_pago=metodo),
        pasarela,
        alquiler_id=alquiler.id,
        momento=momento,
    )


def _auditoria(sesion, alquiler: Alquiler) -> list[RegistroAuditoria]:
    return list(
        sesion.scalars(
            select(RegistroAuditoria)
            .where(
                RegistroAuditoria.entidad == "alquileres",
                RegistroAuditoria.entidad_id == str(alquiler.id),
            )
            .order_by(RegistroAuditoria.id)
        )
    )


# --- Reservar ---------------------------------------------------------------------------


def test_reserva_queda_pendiente_15_minutos_con_el_precio_por_dias(
    sesion, fabrica, modelo, cliente
) -> None:
    unidad = fabrica.vehiculo(modelo)

    alquiler = _reservar(sesion, cliente, modelo)

    assert alquiler.vehiculo_id == unidad.id
    assert alquiler.estado == EstadoAlquiler.PENDIENTE_PAGO
    assert alquiler.expira_en == MOMENTO + timedelta(minutes=15)
    assert alquiler.dias == 3
    assert (alquiler.tarifa_diaria, alquiler.subtotal, alquiler.total) == (TARIFA, 120_000, 120_000)
    assert [r.accion for r in _auditoria(sesion, alquiler)] == ["crear"]


def test_reservar_no_cambia_el_estado_fisico_de_la_unidad(sesion, fabrica, modelo, cliente) -> None:
    unidad = fabrica.vehiculo(modelo)
    _reservar(sesion, cliente, modelo)
    assert unidad.estado == EstadoVehiculo.DISPONIBLE  # la ocupación sale de alquileres


def test_asigna_otra_unidad_si_la_primera_esta_ocupada(sesion, fabrica, modelo, cliente) -> None:
    ocupada = fabrica.vehiculo(modelo)
    libre = fabrica.vehiculo(modelo)
    fabrica.alquiler(ocupada, INICIO, FIN)

    assert _reservar(sesion, cliente, modelo).vehiculo_id == libre.id


def test_sin_unidades_libres_en_esas_fechas(sesion, fabrica, modelo, cliente) -> None:
    unidad = fabrica.vehiculo(modelo)
    fabrica.alquiler(unidad, FIN, FIN + timedelta(days=2))  # se cruza solo en un día

    with pytest.raises(SinUnidadesDisponibles):
        _reservar(sesion, cliente, modelo)


def test_al_dia_siguiente_del_fin_ya_se_puede_reservar(sesion, fabrica, modelo, cliente) -> None:
    unidad = fabrica.vehiculo(modelo)
    fabrica.alquiler(unidad, HOY, INICIO - timedelta(days=1))

    assert _reservar(sesion, cliente, modelo).vehiculo_id == unidad.id


def test_expira_los_pendientes_vencidos_antes_de_reservar(sesion, fabrica, modelo, cliente) -> None:
    unidad = fabrica.vehiculo(modelo)
    abandonado = fabrica.alquiler(
        unidad, INICIO, FIN, EstadoAlquiler.PENDIENTE_PAGO, expira_en=MOMENTO - timedelta(seconds=1)
    )

    nuevo = _reservar(sesion, cliente, modelo)

    assert nuevo.vehiculo_id == unidad.id
    assert abandonado.estado == EstadoAlquiler.EXPIRADO
    assert abandonado.expira_en is None
    registro = _auditoria(sesion, abandonado)[-1]
    assert registro.usuario_id is None  # lo hizo el sistema
    assert registro.datos_nuevos["estado"] == "expirado"


def test_un_pendiente_vigente_si_bloquea(sesion, fabrica, modelo, cliente) -> None:
    unidad = fabrica.vehiculo(modelo)
    fabrica.alquiler(
        unidad, INICIO, FIN, EstadoAlquiler.PENDIENTE_PAGO, expira_en=MOMENTO + timedelta(minutes=1)
    )
    with pytest.raises(SinUnidadesDisponibles):
        _reservar(sesion, cliente, modelo)


@pytest.mark.parametrize(
    "estado",
    [EstadoVehiculo.VENDIDO, EstadoVehiculo.RESERVADO, EstadoVehiculo.MANTENIMIENTO],
)
def test_no_alquila_unidades_vendidas_reservadas_ni_en_mantenimiento(
    sesion, fabrica, modelo, cliente, estado
) -> None:
    fabrica.vehiculo(modelo, estado)
    with pytest.raises(SinUnidadesDisponibles):
        _reservar(sesion, cliente, modelo)


def test_una_unidad_alquilada_hoy_se_puede_reservar_para_despues(
    sesion, fabrica, modelo, cliente
) -> None:
    unidad = fabrica.vehiculo(modelo, EstadoVehiculo.ALQUILADO)
    fabrica.alquiler(unidad, HOY, INICIO - timedelta(days=1), EstadoAlquiler.EN_CURSO)
    assert _reservar(sesion, cliente, modelo).vehiculo_id == unidad.id


def test_el_maximo_de_dias_se_lee_de_la_base(sesion, fabrica, modelo, cliente) -> None:
    fabrica.vehiculo(modelo)
    sesion.get(ParametroSistema, MAX_DIAS_ALQUILER).valor = 2
    sesion.flush()

    with pytest.raises(DuracionExcedida, match="3 días.*2"):
        _reservar(sesion, cliente, modelo)


def test_el_maximo_inicial_es_30_dias(sesion, fabrica, modelo, cliente) -> None:
    fabrica.vehiculo(modelo)
    _reservar(sesion, cliente, modelo, INICIO, INICIO + timedelta(days=29))
    with pytest.raises(DuracionExcedida):
        _reservar(sesion, cliente, modelo, INICIO + timedelta(days=30), INICIO + timedelta(days=60))


def test_modelo_solo_de_venta_no_se_alquila(sesion, fabrica, cliente) -> None:
    modelo = fabrica.modelo(tarifa_diaria=None, precio_venta=900_000)
    fabrica.vehiculo(modelo)
    with pytest.raises(ModeloNoSeAlquila):
        _reservar(sesion, cliente, modelo)


def test_solo_un_cliente_reserva(sesion, fabrica, modelo, operador) -> None:
    fabrica.vehiculo(modelo)
    with pytest.raises(PermisoDenegado):
        _reservar(sesion, operador, modelo)


# --- Pagar ------------------------------------------------------------------------------


def test_pago_aprobado_confirma_el_alquiler(sesion, fabrica, modelo, cliente) -> None:
    fabrica.vehiculo(modelo)
    alquiler = _reservar(sesion, cliente, modelo)

    resultado = _pagar(sesion, alquiler, cliente)

    assert alquiler.estado == EstadoAlquiler.CONFIRMADO
    assert alquiler.expira_en is None
    pago = resultado.pago
    assert (pago.estado, pago.monto, pago.proveedor) == (EstadoPago.APROBADO, 120_000, "falso")
    assert pago.alquiler_id == alquiler.id
    assert pago.aprobado_en == MOMENTO


def test_pago_rechazado_deja_la_reserva_pendiente_y_se_puede_reintentar(
    sesion, fabrica, modelo, cliente
) -> None:
    fabrica.vehiculo(modelo)
    alquiler = _reservar(sesion, cliente, modelo)

    rechazo = _pagar(sesion, alquiler, cliente, aprueba=False)
    assert rechazo.pago.estado == EstadoPago.RECHAZADO
    assert alquiler.estado == EstadoAlquiler.PENDIENTE_PAGO

    _pagar(sesion, alquiler, cliente)
    assert alquiler.estado == EstadoAlquiler.CONFIRMADO
    assert sesion.scalars(select(Pago.estado).where(Pago.alquiler_id == alquiler.id)).all() == [
        EstadoPago.RECHAZADO,
        EstadoPago.APROBADO,
    ]


def test_pagar_despues_de_los_15_minutos_expira_la_reserva(
    sesion, fabrica, modelo, cliente
) -> None:
    fabrica.vehiculo(modelo)
    alquiler = _reservar(sesion, cliente, modelo)

    with pytest.raises(ReservaExpirada):
        _pagar(sesion, alquiler, cliente, momento=MOMENTO + timedelta(minutes=15))

    assert alquiler.estado == EstadoAlquiler.EXPIRADO
    assert not sesion.scalars(select(Pago).where(Pago.alquiler_id == alquiler.id)).all()


def test_un_alquiler_ya_pagado_no_se_cobra_dos_veces(sesion, fabrica, modelo, cliente) -> None:
    fabrica.vehiculo(modelo)
    alquiler = _reservar(sesion, cliente, modelo)
    _pagar(sesion, alquiler, cliente)

    with pytest.raises(TransicionDeAlquilerInvalida):
        _pagar(sesion, alquiler, cliente)


def test_metodo_de_pago_deshabilitado(sesion, fabrica, modelo, cliente) -> None:
    fabrica.vehiculo(modelo)
    alquiler = _reservar(sesion, cliente, modelo)
    with pytest.raises(MetodoDePagoNoDisponible):
        _pagar(sesion, alquiler, cliente, metodo="pse")


def test_otro_cliente_no_puede_pagar_ni_ver_el_alquiler(
    sesion, fabrica, modelo, cliente, crear_usuario
) -> None:
    fabrica.vehiculo(modelo)
    alquiler = _reservar(sesion, cliente, modelo)
    intruso = crear_usuario(Rol.CLIENTE)

    with pytest.raises(AlquilerNoEncontrado):
        _pagar(sesion, alquiler, intruso)
    with pytest.raises(AlquilerNoEncontrado):
        servicio.obtener_alquiler(sesion, alquiler.id, intruso)


# --- Cancelar ---------------------------------------------------------------------------


def test_el_cliente_cancela_una_reserva_pendiente_y_libera_las_fechas(
    sesion, fabrica, modelo, cliente
) -> None:
    fabrica.vehiculo(modelo)
    alquiler = _reservar(sesion, cliente, modelo)

    servicio.cancelar_alquiler(sesion, alquiler.id, cliente, "Cambié de planes.", momento=MOMENTO)

    assert alquiler.estado == EstadoAlquiler.CANCELADO
    assert alquiler.motivo_cancelacion == "Cambié de planes."
    assert _auditoria(sesion, alquiler)[-1].usuario_id == cliente.id
    _reservar(sesion, cliente, modelo)  # las fechas quedaron libres


def test_un_alquiler_pagado_no_lo_cancela_el_cliente(sesion, fabrica, modelo, cliente) -> None:
    fabrica.vehiculo(modelo)
    alquiler = _reservar(sesion, cliente, modelo)
    _pagar(sesion, alquiler, cliente)

    with pytest.raises(AlquilerNoCancelable):
        servicio.cancelar_alquiler(sesion, alquiler.id, cliente, momento=MOMENTO)
    assert alquiler.estado == EstadoAlquiler.CONFIRMADO


# --- Entregar y recibir -----------------------------------------------------------------


@pytest.fixture
def confirmado(sesion, fabrica, modelo, cliente) -> Alquiler:
    fabrica.vehiculo(modelo)
    alquiler = _reservar(sesion, cliente, modelo)
    _pagar(sesion, alquiler, cliente)
    return alquiler


def test_entrega_pasa_a_en_curso_y_la_unidad_a_alquilado(sesion, confirmado, operador) -> None:
    servicio.entregar_vehiculo(sesion, confirmado.id, operador, hoy=INICIO)

    assert confirmado.estado == EstadoAlquiler.EN_CURSO
    assert confirmado.vehiculo.estado == EstadoVehiculo.ALQUILADO


def test_no_se_entrega_antes_de_la_fecha_de_inicio(sesion, confirmado, operador) -> None:
    with pytest.raises(FueraDeLasFechasDelAlquiler):
        servicio.entregar_vehiculo(sesion, confirmado.id, operador, hoy=INICIO - timedelta(days=1))
    assert confirmado.estado == EstadoAlquiler.CONFIRMADO


def test_no_se_entrega_un_alquiler_sin_pagar(sesion, fabrica, modelo, cliente, operador) -> None:
    fabrica.vehiculo(modelo)
    alquiler = _reservar(sesion, cliente, modelo)
    with pytest.raises(TransicionDeAlquilerInvalida):
        servicio.entregar_vehiculo(sesion, alquiler.id, operador, hoy=INICIO)


def test_no_se_entrega_una_unidad_en_mantenimiento(sesion, confirmado, operador) -> None:
    inventario.inactivar_vehiculo(sesion, confirmado.vehiculo_id, "Freno trasero suelto.", operador)

    with pytest.raises(VehiculoNoListoParaEntrega, match="Reasigna"):
        servicio.entregar_vehiculo(sesion, confirmado.id, operador, hoy=INICIO)
    assert confirmado.estado == EstadoAlquiler.CONFIRMADO


def test_el_cliente_no_entrega_vehiculos(sesion, confirmado, cliente) -> None:
    with pytest.raises(PermisoDenegado):
        servicio.entregar_vehiculo(sesion, confirmado.id, cliente, hoy=INICIO)


def test_devolucion_finaliza_y_la_unidad_vuelve_a_disponible(sesion, confirmado, operador) -> None:
    servicio.entregar_vehiculo(sesion, confirmado.id, operador, hoy=INICIO)

    servicio.recibir_vehiculo(sesion, confirmado.id, operador)

    assert confirmado.estado == EstadoAlquiler.FINALIZADO
    assert confirmado.vehiculo.estado == EstadoVehiculo.DISPONIBLE


def test_devolucion_de_una_unidad_que_entro_en_mantenimiento_la_deja_en_mantenimiento(
    sesion, confirmado, operador
) -> None:
    servicio.entregar_vehiculo(sesion, confirmado.id, operador, hoy=INICIO)
    novedad = NovedadCrear(
        tipo=TipoNovedad.FALLA, descripcion="Se apagó el motor.", es_critica=True
    )
    inventario.reportar_novedad(sesion, confirmado.vehiculo_id, novedad, operador)

    servicio.recibir_vehiculo(sesion, confirmado.id, operador)

    assert confirmado.estado == EstadoAlquiler.FINALIZADO
    assert confirmado.vehiculo.estado == EstadoVehiculo.MANTENIMIENTO


def test_no_se_recibe_lo_que_no_se_entrego(sesion, confirmado, operador) -> None:
    with pytest.raises(TransicionDeAlquilerInvalida):
        servicio.recibir_vehiculo(sesion, confirmado.id, operador)


# --- Alquileres en riesgo y reasignación ------------------------------------------------


def test_en_riesgo_lista_los_no_entregados_de_unidades_en_mantenimiento(
    sesion, fabrica, modelo, operador
) -> None:
    rota, sana, rota_en_curso = (fabrica.vehiculo(modelo) for _ in range(3))
    en_riesgo = fabrica.alquiler(rota, INICIO, FIN)
    fabrica.alquiler(sana, INICIO, FIN)
    fabrica.alquiler(
        rota, FIN + timedelta(days=1), FIN + timedelta(days=2), EstadoAlquiler.CANCELADO
    )
    fabrica.alquiler(rota_en_curso, HOY, FIN, EstadoAlquiler.EN_CURSO)
    vencido = fabrica.alquiler(
        rota,
        FIN + timedelta(days=5),
        FIN + timedelta(days=6),
        EstadoAlquiler.PENDIENTE_PAGO,
        expira_en=MOMENTO - timedelta(minutes=1),
    )
    for unidad in (rota, rota_en_curso):
        inventario.inactivar_vehiculo(sesion, unidad.id, "Revisión general.", operador)

    resultado = servicio.listar_en_riesgo(sesion, ParametrosPagina(), momento=MOMENTO)

    assert [a.id for a in resultado.elementos] == [en_riesgo.id]
    assert vencido.id not in [a.id for a in resultado.elementos]


def test_reasigna_a_otra_unidad_libre_del_mismo_modelo_con_el_mismo_precio(
    sesion, fabrica, modelo, operador, administrador
) -> None:
    rota, ocupada, libre = (fabrica.vehiculo(modelo) for _ in range(3))
    alquiler = fabrica.alquiler(rota, INICIO, FIN)
    fabrica.alquiler(ocupada, INICIO, INICIO)
    inventario.inactivar_vehiculo(sesion, rota.id, "Revisión general.", operador)
    total = alquiler.total

    servicio.reasignar_alquiler(sesion, alquiler.id, administrador, hoy=HOY, momento=MOMENTO)

    assert alquiler.vehiculo_id == libre.id
    assert (alquiler.total, alquiler.fecha_inicio, alquiler.fecha_fin) == (total, INICIO, FIN)
    registro = _auditoria(sesion, alquiler)[-1]
    assert (registro.accion, registro.datos_anteriores, registro.datos_nuevos) == (
        "reasignar",
        {"vehiculo_id": rota.id},
        {"vehiculo_id": libre.id},
    )
    assert not servicio.listar_en_riesgo(sesion, ParametrosPagina(), momento=MOMENTO).elementos


def test_reasigna_a_la_unidad_elegida(sesion, fabrica, modelo, administrador) -> None:
    actual, primera, elegida = (fabrica.vehiculo(modelo) for _ in range(3))
    alquiler = fabrica.alquiler(actual, INICIO, FIN)

    servicio.reasignar_alquiler(
        sesion, alquiler.id, administrador, elegida.id, hoy=HOY, momento=MOMENTO
    )
    assert alquiler.vehiculo_id == elegida.id


def test_no_reasigna_a_una_unidad_de_otro_modelo(sesion, fabrica, modelo, administrador) -> None:
    alquiler = fabrica.alquiler(fabrica.vehiculo(modelo), INICIO, FIN)
    de_otro_modelo = fabrica.vehiculo(fabrica.modelo())

    with pytest.raises(ReasignacionInvalida):
        servicio.reasignar_alquiler(
            sesion, alquiler.id, administrador, de_otro_modelo.id, hoy=HOY, momento=MOMENTO
        )


def test_sin_otra_unidad_libre_no_reasigna(sesion, fabrica, modelo, administrador) -> None:
    alquiler = fabrica.alquiler(fabrica.vehiculo(modelo), INICIO, FIN)
    fabrica.alquiler(fabrica.vehiculo(modelo), FIN, FIN)

    with pytest.raises(SinUnidadesDisponibles):
        servicio.reasignar_alquiler(sesion, alquiler.id, administrador, hoy=HOY, momento=MOMENTO)


def test_no_reasigna_un_alquiler_en_curso(sesion, fabrica, modelo, administrador) -> None:
    alquiler = fabrica.alquiler(fabrica.vehiculo(modelo), HOY, FIN, EstadoAlquiler.EN_CURSO)
    fabrica.vehiculo(modelo)
    with pytest.raises(ReasignacionInvalida):
        servicio.reasignar_alquiler(sesion, alquiler.id, administrador, hoy=HOY, momento=MOMENTO)


def test_solo_el_administrador_reasigna(sesion, fabrica, modelo, operador) -> None:
    alquiler = fabrica.alquiler(fabrica.vehiculo(modelo), INICIO, FIN)
    fabrica.vehiculo(modelo)
    with pytest.raises(PermisoDenegado):
        servicio.reasignar_alquiler(sesion, alquiler.id, operador, hoy=HOY, momento=MOMENTO)


# --- Consultas --------------------------------------------------------------------------


def test_mis_alquileres_solo_trae_los_del_cliente(
    sesion, fabrica, modelo, cliente, crear_usuario
) -> None:
    fabrica.vehiculo(modelo)
    fabrica.vehiculo(modelo)
    mio = _reservar(sesion, cliente, modelo)
    _reservar(sesion, crear_usuario(Rol.CLIENTE), modelo)

    resultado = servicio.listar_alquileres(sesion, ParametrosPagina(), cliente_id=cliente.id)

    assert [a.id for a in resultado.elementos] == [mio.id]


def test_el_filtro_expirado_incluye_los_pendientes_vencidos(sesion, fabrica, modelo) -> None:
    unidad = fabrica.vehiculo(modelo)
    vencido = fabrica.alquiler(
        unidad, INICIO, FIN, EstadoAlquiler.PENDIENTE_PAGO, expira_en=MOMENTO - timedelta(minutes=1)
    )
    vigente = fabrica.alquiler(
        unidad,
        FIN + timedelta(days=1),
        FIN + timedelta(days=1),
        EstadoAlquiler.PENDIENTE_PAGO,
        expira_en=MOMENTO + timedelta(minutes=1),
    )

    def _ids(estado):
        pagina = servicio.listar_alquileres(
            sesion, ParametrosPagina(), estado=estado, momento=MOMENTO
        )
        return [a.id for a in pagina.elementos]

    assert _ids(EstadoAlquiler.EXPIRADO) == [vencido.id]
    assert _ids(EstadoAlquiler.PENDIENTE_PAGO) == [vigente.id]
