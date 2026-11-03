"""Estado de la entrega, cancelación por el despacho y rastreo público (HU-07).

Contra Postgres, con "hoy" y "ahora" fijos.
"""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.comun.errores import PermisoDenegado
from app.modulos.alquileres import servicio as alquileres
from app.modulos.alquileres.excepciones import (
    FueraDeLasFechasDelAlquiler,
    VehiculoNoListoParaEntrega,
)
from app.modulos.alquileres.modelos import EstadoAlquiler
from app.modulos.domicilios import servicio
from app.modulos.domicilios.excepciones import (
    DomicilioNoEncontrado,
    OperacionNoAdmiteDomicilio,
    TransicionDeDomicilioInvalida,
)
from app.modulos.domicilios.modelos import EstadoDomicilio
from app.modulos.inventario import servicio as inventario
from app.modulos.inventario.esquemas import NovedadCrear
from app.modulos.inventario.modelos import EstadoVehiculo, TipoNovedad
from app.modulos.pagos import procesamiento
from app.modulos.pagos.esquemas import PagoCrear
from app.modulos.pagos.modelos import MetodoPago, Pago, TipoPago
from app.modulos.pagos.pasarela import PasarelaFalsa
from app.modulos.usuarios.modelos import Rol
from app.modulos.ventas import servicio as ventas
from app.modulos.ventas.esquemas import VentaCrear
from app.modulos.ventas.modelos import EstadoVenta

HOY = date(2026, 11, 2)
MOMENTO = datetime(2026, 11, 2, 15, 0, tzinfo=UTC)
PUNTO = (Decimal("7.119300"), Decimal("-73.122700"))
E = EstadoDomicilio


@pytest.fixture(autouse=True)
def base(sesion, fabrica) -> None:
    sesion.add(MetodoPago(codigo="tarjeta", nombre="Tarjeta"))
    fabrica.zona(tarifa_envio=5_000)


@pytest.fixture
def cliente(fabrica):
    return fabrica.cliente()


@pytest.fixture
def operador(crear_usuario):
    return crear_usuario(Rol.OPERADOR)


@pytest.fixture
def domiciliario(crear_usuario):
    return crear_usuario(Rol.DOMICILIARIO)


@pytest.fixture
def moto(fabrica):
    return fabrica.vehiculo(codigo="TRA-0001")


def _domicilio_pagado(sesion, cliente, *, alquiler=None, venta=None):
    resultado = servicio.solicitar_domicilio(
        sesion,
        cliente,
        alquiler_id=alquiler.id if alquiler else None,
        venta_id=venta.id if venta else None,
        direccion="Calle 36 # 19-20",
        indicaciones="Apto 301",
        latitud=PUNTO[0],
        longitud=PUNTO[1],
        momento=MOMENTO,
    )
    procesamiento.pagar(
        sesion,
        cliente,
        PagoCrear(metodo_pago="tarjeta"),
        PasarelaFalsa(),
        alquiler_id=alquiler.id if alquiler else None,
        venta_id=venta.id if venta else None,
        momento=MOMENTO,
    )
    return resultado.domicilio


@pytest.fixture
def alquiler(sesion, fabrica, cliente):
    modelo = fabrica.modelo(tarifa_diaria=30_000)
    fabrica.vehiculo(modelo, codigo="ALQ-0001")
    return alquileres.crear_alquiler(sesion, cliente, modelo.id, HOY, HOY, hoy=HOY, momento=MOMENTO)


@pytest.fixture
def asignado(sesion, alquiler, cliente, operador, domiciliario, moto):
    """Domicilio de un alquiler que empieza hoy, pagado y asignado con moto."""
    domicilio = _domicilio_pagado(sesion, cliente, alquiler=alquiler)
    servicio.asignar_domiciliario(
        sesion, domicilio.id, operador, domiciliario.id, moto.id, hoy=HOY, momento=MOMENTO
    )
    return domicilio


def _avanzar(sesion, domicilio, usuario, *estados, hoy=HOY):
    for estado in estados:
        servicio.avanzar_estado(sesion, domicilio.id, usuario, estado, hoy=hoy, momento=MOMENTO)


# --- Avance del estado (decisiones 1 y 2) -------------------------------------------------


def test_el_domiciliario_entrega_y_el_alquiler_queda_en_curso(
    sesion, asignado, alquiler, domiciliario, moto
) -> None:
    _avanzar(sesion, asignado, domiciliario, E.RECOGIDO, E.EN_CAMINO, E.ENTREGADO)

    assert asignado.estado == E.ENTREGADO
    assert asignado.entregado_en == MOMENTO
    assert alquiler.estado == EstadoAlquiler.EN_CURSO
    assert alquiler.vehiculo.estado == EstadoVehiculo.ALQUILADO
    assert moto.estado == EstadoVehiculo.DISPONIBLE  # la moto vuelve a la flota


def test_no_se_saltan_pasos(sesion, asignado, domiciliario) -> None:
    with pytest.raises(TransicionDeDomicilioInvalida):
        _avanzar(sesion, asignado, domiciliario, E.ENTREGADO)
    with pytest.raises(TransicionDeDomicilioInvalida):
        _avanzar(sesion, asignado, domiciliario, E.CANCELADO)  # cancelar va por otro camino


def test_el_operador_puede_corregir_el_estado(sesion, asignado, operador) -> None:
    _avanzar(sesion, asignado, operador, E.RECOGIDO)
    assert asignado.estado == E.RECOGIDO


def test_otro_domiciliario_ni_el_cliente_cambian_el_estado(
    sesion, asignado, cliente, crear_usuario
) -> None:
    with pytest.raises(DomicilioNoEncontrado):
        _avanzar(sesion, asignado, crear_usuario(Rol.DOMICILIARIO), E.RECOGIDO)
    with pytest.raises(PermisoDenegado):
        _avanzar(sesion, asignado, cliente, E.RECOGIDO)
    assert asignado.estado == E.ASIGNADO


def test_fuera_de_las_fechas_del_alquiler_no_se_entrega_y_nada_cambia(
    sesion, fabrica, cliente, operador, domiciliario, moto
) -> None:
    modelo = fabrica.modelo(tarifa_diaria=30_000)
    fabrica.vehiculo(modelo)
    manana = HOY + timedelta(days=1)
    alquiler = alquileres.crear_alquiler(
        sesion, cliente, modelo.id, manana, manana, hoy=HOY, momento=MOMENTO
    )
    domicilio = _domicilio_pagado(sesion, cliente, alquiler=alquiler)
    servicio.asignar_domiciliario(
        sesion, domicilio.id, operador, domiciliario.id, moto.id, hoy=HOY, momento=MOMENTO
    )
    _avanzar(sesion, domicilio, domiciliario, E.RECOGIDO, E.EN_CAMINO)

    with pytest.raises(FueraDeLasFechasDelAlquiler):
        _avanzar(sesion, domicilio, domiciliario, E.ENTREGADO)

    assert domicilio.estado == E.EN_CAMINO
    assert alquiler.estado == EstadoAlquiler.CONFIRMADO
    assert moto.estado == EstadoVehiculo.ASIGNADO_A_DOMICILIO


def test_la_entrega_de_una_compra_no_toca_la_venta(
    sesion, fabrica, cliente, operador, domiciliario
) -> None:
    venta = ventas.crear_venta(
        sesion,
        cliente,
        VentaCrear(productos=[{"producto_id": fabrica.producto().id}]),
        momento=MOMENTO,
    )
    domicilio = _domicilio_pagado(sesion, cliente, venta=venta)
    servicio.asignar_domiciliario(
        sesion, domicilio.id, operador, domiciliario.id, hoy=HOY, momento=MOMENTO
    )

    _avanzar(sesion, domicilio, domiciliario, E.RECOGIDO, E.EN_CAMINO, E.ENTREGADO)

    assert domicilio.estado == E.ENTREGADO
    assert venta.estado == EstadoVenta.PAGADA


def test_si_la_moto_se_dano_en_la_ruta_se_queda_en_mantenimiento(
    sesion, asignado, domiciliario, moto
) -> None:
    _avanzar(sesion, asignado, domiciliario, E.RECOGIDO, E.EN_CAMINO)
    novedad = NovedadCrear(
        tipo=TipoNovedad.FALLA, descripcion="Se partió la cadena.", es_critica=True
    )
    inventario.reportar_novedad(sesion, moto.id, novedad, domiciliario)

    _avanzar(sesion, asignado, domiciliario, E.ENTREGADO)

    assert moto.estado == EstadoVehiculo.MANTENIMIENTO


def test_con_domicilio_vigente_no_se_entrega_en_el_local(
    sesion, asignado, alquiler, operador
) -> None:
    with pytest.raises(VehiculoNoListoParaEntrega, match="domicilio"):
        alquileres.entregar_vehiculo(sesion, alquiler.id, operador, hoy=HOY)


# --- Cancelación por el despacho (decisiones 3 y 4) ---------------------------------------


def _devoluciones(sesion, alquiler) -> list[Pago]:
    return list(
        sesion.scalars(
            select(Pago)
            .where(Pago.alquiler_id == alquiler.id, Pago.tipo == TipoPago.COMPENSACION)
            .order_by(Pago.id)
        )
    )


def test_el_despacho_cancela_una_entrega_asignada_y_devuelve_el_envio(
    sesion, asignado, alquiler, operador, moto
) -> None:
    resultado = servicio.cancelar_por_despacho(
        sesion, asignado.id, operador, "El cliente prefirió recoger en el local."
    )

    assert asignado.estado == E.CANCELADO
    assert asignado.motivo_cancelacion == "El cliente prefirió recoger en el local."
    assert moto.estado == EstadoVehiculo.DISPONIBLE
    assert resultado.devolucion.monto == 5_000  # solo el envío
    assert alquiler.estado == EstadoAlquiler.CONFIRMADO  # la reserva sigue vigente
    alquileres.entregar_vehiculo(sesion, alquiler.id, operador, hoy=HOY)  # ahora, en el local
    assert alquiler.estado == EstadoAlquiler.EN_CURSO


def test_nunca_se_devuelve_mas_de_lo_cobrado(
    sesion, asignado, alquiler, operador, crear_usuario
) -> None:
    servicio.cancelar_por_despacho(sesion, asignado.id, operador, "Sin domiciliario hoy.")

    _, devolucion = alquileres.cancelar_con_devolucion(
        sesion, alquiler.id, crear_usuario(Rol.ADMINISTRADOR), "La unidad se dañó."
    )

    assert devolucion.monto == alquiler.total - 5_000
    assert sum(d.monto for d in _devoluciones(sesion, alquiler)) == alquiler.total


def test_tambien_se_cancela_una_entrega_en_camino(sesion, asignado, domiciliario, operador) -> None:
    _avanzar(sesion, asignado, domiciliario, E.RECOGIDO, E.EN_CAMINO)
    servicio.cancelar_por_despacho(sesion, asignado.id, operador, "Dirección inexistente.")
    assert asignado.estado == E.CANCELADO


def test_una_entrega_hecha_no_se_cancela(sesion, asignado, domiciliario, operador) -> None:
    _avanzar(sesion, asignado, domiciliario, E.RECOGIDO, E.EN_CAMINO, E.ENTREGADO)
    with pytest.raises(TransicionDeDomicilioInvalida):
        servicio.cancelar_por_despacho(sesion, asignado.id, operador, "Ya no la quiere.")


def test_solo_el_despacho_cancela_una_entrega_pagada(
    sesion, asignado, cliente, domiciliario
) -> None:
    with pytest.raises(PermisoDenegado):
        servicio.cancelar_por_despacho(sesion, asignado.id, domiciliario, "Motivo cualquiera.")
    with pytest.raises(OperacionNoAdmiteDomicilio):
        servicio.cancelar_domicilio(sesion, asignado.id, cliente, momento=MOMENTO)


def test_antes_de_pagar_el_despacho_no_cancela(sesion, alquiler, cliente, operador) -> None:
    domicilio = servicio.solicitar_domicilio(
        sesion,
        cliente,
        alquiler_id=alquiler.id,
        venta_id=None,
        direccion="Calle 36 # 19-20",
        indicaciones=None,
        latitud=PUNTO[0],
        longitud=PUNTO[1],
        momento=MOMENTO,
    ).domicilio
    with pytest.raises(OperacionNoAdmiteDomicilio, match="el cliente"):
        servicio.cancelar_por_despacho(sesion, domicilio.id, operador, "Motivo cualquiera.")


# --- Rastreo público (decisión 5) ----------------------------------------------------------


def test_rastreo_publico_muestra_cada_cambio(sesion, asignado, domiciliario) -> None:
    _avanzar(sesion, asignado, domiciliario, E.RECOGIDO, E.EN_CAMINO)

    rastreo = servicio.rastreo_publico(sesion, asignado.codigo_rastreo.lower())

    assert rastreo.estado == E.EN_CAMINO
    assert [c.estado_nuevo for c in rastreo.cambios] == [
        E.PENDIENTE,
        E.ASIGNADO,
        E.RECOGIDO,
        E.EN_CAMINO,
    ]


def test_rastreo_de_un_codigo_que_no_existe(sesion) -> None:
    with pytest.raises(DomicilioNoEncontrado):
        servicio.rastreo_publico(sesion, "TX-NOEXISTE")
