"""Servicio de domicilios (HU-06): cobertura, solicitud antes de pagar y asignación manual.

Contra Postgres, con "hoy" y "ahora" fijos.
"""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.comun.errores import PermisoDenegado
from app.comun.paginacion import ParametrosPagina
from app.modulos.alquileres import servicio as alquileres
from app.modulos.alquileres.excepciones import (
    AlquilerNoCancelable,
    AlquilerNoEncontrado,
    ReservaExpirada,
)
from app.modulos.alquileres.modelos import EstadoAlquiler
from app.modulos.domicilios import servicio
from app.modulos.domicilios.excepciones import (
    DomiciliarioNoDisponible,
    DomicilioNoEncontrado,
    DomicilioSinPagar,
    FueraDeCobertura,
    OperacionNoAdmiteDomicilio,
    TransicionDeDomicilioInvalida,
    VehiculoDeTransporteNoDisponible,
    YaTieneDomicilio,
)
from app.modulos.domicilios.modelos import EstadoDomicilio, HistorialEstadoDomicilio
from app.modulos.inventario import servicio as inventario
from app.modulos.inventario.esquemas import NovedadCrear
from app.modulos.inventario.modelos import EstadoVehiculo, TipoNovedad
from app.modulos.pagos import procesamiento
from app.modulos.pagos.esquemas import PagoCrear
from app.modulos.pagos.excepciones import PagoEnCurso
from app.modulos.pagos.modelos import EstadoPago, MetodoPago
from app.modulos.pagos.pasarela import PasarelaFalsa
from app.modulos.usuarios.modelos import Rol
from app.modulos.ventas import servicio as ventas
from app.modulos.ventas.esquemas import VentaCrear
from app.modulos.ventas.modelos import EstadoVenta

HOY = date(2026, 11, 2)
MOMENTO = datetime(2026, 11, 2, 15, 0, tzinfo=UTC)
TARIFA_DIARIA = 30_000
# Dentro de la zona de prueba de la fábrica (centro de Bucaramanga).
DENTRO = (Decimal("7.119300"), Decimal("-73.122700"))
FUERA = (Decimal("7.050000"), Decimal("-73.200000"))


def cuadrado(lat_min, lat_max, lng_min, lng_max) -> dict:
    return {
        "type": "Polygon",
        "coordinates": [
            [
                [lng_min, lat_max],
                [lng_max, lat_max],
                [lng_max, lat_min],
                [lng_min, lat_min],
                [lng_min, lat_max],
            ]
        ],
    }


@pytest.fixture(autouse=True)
def metodos_pago(sesion) -> None:
    sesion.add(MetodoPago(codigo="tarjeta", nombre="Tarjeta"))
    sesion.flush()


@pytest.fixture
def zona(fabrica):
    return fabrica.zona(tarifa_envio=5_000)


@pytest.fixture
def cliente(fabrica):
    return fabrica.cliente()


@pytest.fixture
def modelo(fabrica):
    modelo = fabrica.modelo(tarifa_diaria=TARIFA_DIARIA)
    fabrica.vehiculo(modelo)
    return modelo


@pytest.fixture
def alquiler(sesion, modelo, cliente):
    inicio = HOY + timedelta(days=2)
    return alquileres.crear_alquiler(
        sesion, cliente, modelo.id, inicio, inicio + timedelta(days=1), hoy=HOY, momento=MOMENTO
    )


def _solicitar(sesion, cliente, *, alquiler=None, venta=None, punto=DENTRO, momento=MOMENTO):
    return servicio.solicitar_domicilio(
        sesion,
        cliente,
        alquiler_id=alquiler.id if alquiler else None,
        venta_id=venta.id if venta else None,
        direccion="Calle 36 # 19-20",
        indicaciones=None,
        latitud=punto[0],
        longitud=punto[1],
        momento=momento,
    )


def _pagar(sesion, cliente, alquiler, pasarela=None):
    return procesamiento.pagar(
        sesion,
        cliente,
        PagoCrear(metodo_pago="tarjeta"),
        pasarela or PasarelaFalsa(),
        alquiler_id=alquiler.id,
        momento=MOMENTO,
    )


# --- Cobertura ----------------------------------------------------------------------------


def test_la_zona_del_punto(sesion, zona) -> None:
    assert servicio.zona_para_punto(sesion, *DENTRO).id == zona.id


def test_fuera_de_cobertura_se_bloquea(sesion, zona) -> None:
    with pytest.raises(FueraDeCobertura):
        servicio.zona_para_punto(sesion, *FUERA)


def test_en_el_borde_entre_dos_zonas_se_cobra_la_tarifa_mas_baja(sesion, fabrica) -> None:
    fabrica.zona(tarifa_envio=7_000, poligono=cuadrado(7.10, 7.12, -73.14, -73.12))
    barata = fabrica.zona(tarifa_envio=4_000, poligono=cuadrado(7.10, 7.12, -73.12, -73.10))
    borde = (Decimal("7.110000"), Decimal("-73.120000"))
    assert servicio.zona_para_punto(sesion, *borde).id == barata.id


def test_una_zona_inactiva_no_cubre(sesion, zona) -> None:
    zona.activa = False
    sesion.flush()
    with pytest.raises(FueraDeCobertura):
        servicio.zona_para_punto(sesion, *DENTRO)


# --- Solicitar el domicilio antes de pagar (decisión 1) -----------------------------------


def test_el_domicilio_suma_la_tarifa_de_la_zona_al_total(sesion, zona, alquiler, cliente) -> None:
    resultado = _solicitar(sesion, cliente, alquiler=alquiler)

    domicilio = resultado.domicilio
    assert domicilio.estado == EstadoDomicilio.PENDIENTE
    assert domicilio.codigo_rastreo.startswith("TX-") and len(domicilio.codigo_rastreo) == 11
    assert domicilio.zona_id == zona.id
    assert (alquiler.subtotal, alquiler.valor_envio, alquiler.total) == (60_000, 5_000, 65_000)
    assert (resultado.valor_envio, resultado.total) == (5_000, 65_000)
    [historial] = sesion.scalars(
        select(HistorialEstadoDomicilio).where(
            HistorialEstadoDomicilio.domicilio_id == domicilio.id
        )
    ).all()
    assert (historial.estado_anterior, historial.estado_nuevo) == (None, EstadoDomicilio.PENDIENTE)


def test_el_pago_cubre_el_total_con_el_envio(sesion, zona, alquiler, cliente) -> None:
    _solicitar(sesion, cliente, alquiler=alquiler)
    assert _pagar(sesion, cliente, alquiler).pago.monto == 65_000


def test_domicilio_para_una_compra(sesion, fabrica, zona, cliente) -> None:
    casco = fabrica.producto(precio_venta=120_000)
    venta = ventas.crear_venta(
        sesion, cliente, VentaCrear(productos=[{"producto_id": casco.id}]), momento=MOMENTO
    )
    _solicitar(sesion, cliente, venta=venta)
    assert (venta.valor_envio, venta.total) == (5_000, 125_000)


def test_fuera_de_cobertura_no_cambia_el_total(sesion, zona, alquiler, cliente) -> None:
    with pytest.raises(FueraDeCobertura):
        _solicitar(sesion, cliente, alquiler=alquiler, punto=FUERA)
    assert alquiler.total == 60_000


def test_un_solo_domicilio_por_operacion(sesion, zona, alquiler, cliente) -> None:
    _solicitar(sesion, cliente, alquiler=alquiler)
    with pytest.raises(YaTieneDomicilio):
        _solicitar(sesion, cliente, alquiler=alquiler)


def test_despues_de_pagar_no_se_agrega_domicilio(sesion, zona, alquiler, cliente) -> None:
    _pagar(sesion, cliente, alquiler)
    with pytest.raises(OperacionNoAdmiteDomicilio):
        _solicitar(sesion, cliente, alquiler=alquiler)


def test_con_un_pago_en_curso_no_cambia_el_total(sesion, zona, alquiler, cliente) -> None:
    _pagar(sesion, cliente, alquiler, PasarelaFalsa(EstadoPago.PENDIENTE))
    with pytest.raises(PagoEnCurso):
        _solicitar(sesion, cliente, alquiler=alquiler)
    assert alquiler.total == 60_000


def test_no_se_agrega_a_una_reserva_vencida(sesion, zona, alquiler, cliente) -> None:
    with pytest.raises(ReservaExpirada):
        _solicitar(sesion, cliente, alquiler=alquiler, momento=MOMENTO + timedelta(minutes=16))


def test_otro_cliente_no_agrega_domicilio(sesion, zona, alquiler, crear_usuario) -> None:
    with pytest.raises(AlquilerNoEncontrado):
        _solicitar(sesion, crear_usuario(Rol.CLIENTE), alquiler=alquiler)


def test_quitar_el_domicilio_resta_el_envio_y_permite_otro(sesion, zona, alquiler, cliente) -> None:
    domicilio = _solicitar(sesion, cliente, alquiler=alquiler).domicilio

    servicio.cancelar_domicilio(sesion, domicilio.id, cliente, momento=MOMENTO)

    assert domicilio.estado == EstadoDomicilio.CANCELADO
    assert (alquiler.valor_envio, alquiler.total) == (0, 60_000)
    _solicitar(sesion, cliente, alquiler=alquiler)  # se puede pedir otra dirección


def test_si_la_reserva_expira_su_domicilio_se_cancela(
    sesion, zona, alquiler, cliente, modelo, crear_usuario
) -> None:
    domicilio = _solicitar(sesion, cliente, alquiler=alquiler).domicilio
    alquileres.crear_alquiler(  # otro cliente reserva: barre la reserva vencida
        sesion,
        crear_usuario(Rol.CLIENTE),
        modelo.id,
        alquiler.fecha_inicio,
        alquiler.fecha_fin,
        hoy=HOY,
        momento=MOMENTO + timedelta(minutes=16),
    )
    assert alquiler.estado == EstadoAlquiler.EXPIRADO
    assert domicilio.estado == EstadoDomicilio.CANCELADO
    assert "expirado" in domicilio.motivo_cancelacion


def test_si_la_compra_se_cancela_su_domicilio_tambien(sesion, fabrica, zona, cliente) -> None:
    casco = fabrica.producto()
    venta = ventas.crear_venta(
        sesion, cliente, VentaCrear(productos=[{"producto_id": casco.id}]), momento=MOMENTO
    )
    domicilio = _solicitar(sesion, cliente, venta=venta).domicilio
    ventas.cancelar_venta(sesion, venta.id, cliente, momento=MOMENTO)
    assert venta.estado == EstadoVenta.CANCELADA
    assert domicilio.estado == EstadoDomicilio.CANCELADO


# --- Asignación manual (decisión 2) --------------------------------------------------------


@pytest.fixture
def operador(crear_usuario):
    return crear_usuario(Rol.OPERADOR)


@pytest.fixture
def domiciliario(crear_usuario):
    return crear_usuario(Rol.DOMICILIARIO)


@pytest.fixture
def pagado(sesion, zona, alquiler, cliente):
    """Un domicilio pendiente de un alquiler ya pagado."""
    domicilio = _solicitar(sesion, cliente, alquiler=alquiler).domicilio
    _pagar(sesion, cliente, alquiler)
    return domicilio


def _asignar(sesion, domicilio, usuario, domiciliario, vehiculo=None):
    return servicio.asignar_domiciliario(
        sesion,
        domicilio.id,
        usuario,
        domiciliario.id,
        vehiculo.id if vehiculo else None,
        hoy=HOY,
        momento=MOMENTO,
    )


def test_el_operador_asigna_un_domiciliario_con_su_vehiculo(
    sesion, fabrica, pagado, operador, domiciliario
) -> None:
    moto = fabrica.vehiculo(codigo="TRA-0001")

    resultado = _asignar(sesion, pagado, operador, domiciliario, moto)

    assert pagado.estado == EstadoDomicilio.ASIGNADO
    assert pagado.domiciliario_id == domiciliario.id
    assert resultado.domicilio.vehiculo_transporte.codigo == "TRA-0001"
    assert moto.estado == EstadoVehiculo.ASIGNADO_A_DOMICILIO


def test_sin_vehiculo_tambien_se_asigna(sesion, pagado, operador, domiciliario) -> None:
    _asignar(sesion, pagado, operador, domiciliario)
    assert pagado.vehiculo_transporte_id is None


def test_no_se_asigna_sin_pagar(sesion, zona, alquiler, cliente, operador, domiciliario) -> None:
    domicilio = _solicitar(sesion, cliente, alquiler=alquiler).domicilio
    with pytest.raises(DomicilioSinPagar):
        _asignar(sesion, domicilio, operador, domiciliario)


def test_un_domiciliario_ocupado_no_esta_disponible(
    sesion, fabrica, pagado, operador, domiciliario
) -> None:
    otro_alquiler = fabrica.alquiler(fabrica.vehiculo(), HOY, HOY)
    fabrica.domicilio(otro_alquiler, EstadoDomicilio.EN_CAMINO, domiciliario=domiciliario)

    disponibles = servicio.listar_domiciliarios_disponibles(sesion, ParametrosPagina())

    assert domiciliario.id not in [u.id for u in disponibles.elementos]
    with pytest.raises(DomiciliarioNoDisponible):
        _asignar(sesion, pagado, operador, domiciliario)


def test_solo_se_asigna_a_un_domiciliario(sesion, pagado, operador, crear_usuario) -> None:
    with pytest.raises(DomiciliarioNoDisponible):
        _asignar(sesion, pagado, operador, crear_usuario(Rol.CLIENTE))
    inactivo = crear_usuario(Rol.DOMICILIARIO, activo=False)
    with pytest.raises(DomiciliarioNoDisponible):
        _asignar(sesion, pagado, operador, inactivo)


@pytest.mark.parametrize(
    "estado", [EstadoVehiculo.MANTENIMIENTO, EstadoVehiculo.ALQUILADO, EstadoVehiculo.RESERVADO]
)
def test_el_vehiculo_de_transporte_debe_estar_disponible(
    sesion, fabrica, pagado, operador, domiciliario, estado
) -> None:
    with pytest.raises(VehiculoDeTransporteNoDisponible):
        _asignar(sesion, pagado, operador, domiciliario, fabrica.vehiculo(estado=estado))
    assert pagado.estado == EstadoDomicilio.PENDIENTE


def test_el_vehiculo_de_transporte_no_puede_tener_alquiler_hoy(
    sesion, fabrica, pagado, operador, domiciliario
) -> None:
    moto = fabrica.vehiculo()
    fabrica.alquiler(moto, HOY, HOY)
    with pytest.raises(VehiculoDeTransporteNoDisponible, match="alquiler hoy"):
        _asignar(sesion, pagado, operador, domiciliario, moto)


def test_la_unidad_que_se_entrega_no_es_el_transporte(
    sesion, pagado, alquiler, operador, domiciliario
) -> None:
    with pytest.raises(VehiculoDeTransporteNoDisponible):
        _asignar(sesion, pagado, operador, domiciliario, alquiler.vehiculo)


def test_no_se_asigna_dos_veces(sesion, pagado, operador, domiciliario, crear_usuario) -> None:
    _asignar(sesion, pagado, operador, domiciliario)
    with pytest.raises(TransicionDeDomicilioInvalida):
        _asignar(sesion, pagado, operador, crear_usuario(Rol.DOMICILIARIO))


def test_el_cliente_no_asigna(sesion, pagado, cliente, domiciliario) -> None:
    with pytest.raises(PermisoDenegado):
        _asignar(sesion, pagado, cliente, domiciliario)


# --- El domiciliario y su vehículo (nota del CLAUDE.md) ------------------------------------


def test_el_domiciliario_ve_su_entrega_y_reporta_sobre_su_vehiculo(
    sesion, fabrica, pagado, operador, domiciliario
) -> None:
    moto = fabrica.vehiculo(codigo="TRA-0002")
    _asignar(sesion, pagado, operador, domiciliario, moto)

    entregas = servicio.listar_domicilios(
        sesion, ParametrosPagina(), domiciliario_id=domiciliario.id, solo_en_ruta=True
    )
    [entrega] = entregas.elementos
    vehiculo_id = entrega.domicilio.vehiculo_transporte_id

    novedad = NovedadCrear(
        tipo=TipoNovedad.FALLA, descripcion="Pinchazo en la ruta.", es_critica=True
    )
    inventario.reportar_novedad(sesion, vehiculo_id, novedad, domiciliario)
    assert moto.estado == EstadoVehiculo.MANTENIMIENTO


def test_cada_quien_ve_solo_sus_domicilios(
    sesion, pagado, operador, domiciliario, cliente, crear_usuario
) -> None:
    _asignar(sesion, pagado, operador, domiciliario)

    assert servicio.obtener_domicilio(sesion, pagado.id, cliente)
    assert servicio.obtener_domicilio(sesion, pagado.id, domiciliario)
    assert servicio.obtener_domicilio(sesion, pagado.id, operador)
    for ajeno in (crear_usuario(Rol.CLIENTE), crear_usuario(Rol.DOMICILIARIO)):
        with pytest.raises(DomicilioNoEncontrado):
            servicio.obtener_domicilio(sesion, pagado.id, ajeno)


def test_no_se_cancela_con_devolucion_un_alquiler_con_entrega_asignada(
    sesion, pagado, alquiler, operador, domiciliario, crear_usuario
) -> None:
    _asignar(sesion, pagado, operador, domiciliario)
    with pytest.raises(AlquilerNoCancelable, match="asignado"):
        alquileres.cancelar_con_devolucion(
            sesion, alquiler.id, crear_usuario(Rol.ADMINISTRADOR), "Motivo de prueba."
        )


def test_cancelar_con_devolucion_cancela_el_domicilio_pendiente(
    sesion, pagado, alquiler, crear_usuario
) -> None:
    alquileres.cancelar_con_devolucion(
        sesion, alquiler.id, crear_usuario(Rol.ADMINISTRADOR), "Motivo de prueba."
    )
    assert pagado.estado == EstadoDomicilio.CANCELADO
