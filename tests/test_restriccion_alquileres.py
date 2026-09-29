"""La base de datos impide dos alquileres activos del mismo vehículo en fechas solapadas.

Prueba la restricción de exclusión ``ex_alquileres_sin_solapamiento`` (CLAUDE.md 7.1 y
7.2) directamente contra Postgres, sin pasar por el servicio: aunque el código de Python
tuviera un error, la base rechaza la segunda reserva.
"""

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modulos.alquileres.modelos import Alquiler, EstadoAlquiler
from app.modulos.inventario.modelos import ModeloVehiculo, TipoVehiculo, Vehiculo
from app.modulos.usuarios.modelos import Rol, Usuario

TARIFA_DIARIA = 30_000


def _crear_vehiculo(sesion: Session, codigo: str) -> Vehiculo:
    tipo = sesion.query(TipoVehiculo).filter_by(nombre="Monopatín eléctrico").one_or_none()
    if tipo is None:
        tipo = TipoVehiculo(nombre="Monopatín eléctrico", usa_bateria=True)
        modelo = ModeloVehiculo(tipo=tipo, nombre="Urbano 350", tarifa_diaria=TARIFA_DIARIA)
    else:
        modelo = sesion.query(ModeloVehiculo).filter_by(nombre="Urbano 350").one()
    vehiculo = Vehiculo(codigo=codigo, modelo=modelo)
    sesion.add(vehiculo)
    sesion.flush()
    return vehiculo


def _crear_cliente(sesion: Session) -> Usuario:
    cliente = Usuario(
        nombre_completo="Cliente de Prueba",
        correo="cliente@prueba.co",
        hash_contrasena="no-es-un-hash-real",
        rol=Rol.CLIENTE,
    )
    sesion.add(cliente)
    sesion.flush()
    return cliente


def _alquiler(
    cliente: Usuario,
    vehiculo: Vehiculo,
    inicio: date,
    fin: date,
    estado: EstadoAlquiler = EstadoAlquiler.CONFIRMADO,
) -> Alquiler:
    subtotal = ((fin - inicio).days + 1) * TARIFA_DIARIA
    pendiente = estado == EstadoAlquiler.PENDIENTE_PAGO
    return Alquiler(
        cliente_id=cliente.id,
        vehiculo_id=vehiculo.id,
        fecha_inicio=inicio,
        fecha_fin=fin,
        tarifa_diaria=TARIFA_DIARIA,
        subtotal=subtotal,
        valor_envio=0,
        total=subtotal,
        estado=estado,
        expira_en=datetime.now(UTC) + timedelta(minutes=15) if pendiente else None,
    )


@pytest.fixture
def cliente(sesion: Session) -> Usuario:
    return _crear_cliente(sesion)


@pytest.fixture
def vehiculo(sesion: Session) -> Vehiculo:
    return _crear_vehiculo(sesion, "MON-0001")


def test_rechaza_segundo_alquiler_activo_con_fechas_solapadas(
    sesion: Session, cliente: Usuario, vehiculo: Vehiculo
) -> None:
    sesion.add(_alquiler(cliente, vehiculo, date(2026, 10, 5), date(2026, 10, 7)))
    sesion.flush()

    with pytest.raises(IntegrityError) as error, sesion.begin_nested():
        sesion.add(
            _alquiler(
                cliente,
                vehiculo,
                date(2026, 10, 7),
                date(2026, 10, 9),
                EstadoAlquiler.PENDIENTE_PAGO,
            )
        )
        sesion.flush()

    assert error.value.orig.diag.constraint_name == "ex_alquileres_sin_solapamiento"
    assert sesion.query(Alquiler).filter_by(vehiculo_id=vehiculo.id).count() == 1


def test_el_siguiente_cliente_puede_recoger_al_dia_siguiente_del_fin(
    sesion: Session, cliente: Usuario, vehiculo: Vehiculo
) -> None:
    # Fechas inclusivas: del 5 al 7 son 3 días; el siguiente puede empezar el 8.
    sesion.add(_alquiler(cliente, vehiculo, date(2026, 10, 5), date(2026, 10, 7)))
    sesion.add(_alquiler(cliente, vehiculo, date(2026, 10, 8), date(2026, 10, 10)))
    sesion.flush()

    assert sesion.query(Alquiler).filter_by(vehiculo_id=vehiculo.id).count() == 2


def test_un_alquiler_cancelado_no_bloquea_las_fechas(
    sesion: Session, cliente: Usuario, vehiculo: Vehiculo
) -> None:
    inicio, fin = date(2026, 10, 5), date(2026, 10, 7)
    sesion.add(_alquiler(cliente, vehiculo, inicio, fin, EstadoAlquiler.CANCELADO))
    sesion.add(_alquiler(cliente, vehiculo, inicio, fin))
    sesion.flush()

    assert sesion.query(Alquiler).filter_by(vehiculo_id=vehiculo.id).count() == 2


def test_otro_vehiculo_puede_alquilarse_en_las_mismas_fechas(
    sesion: Session, cliente: Usuario, vehiculo: Vehiculo
) -> None:
    otro = _crear_vehiculo(sesion, "MON-0002")
    inicio, fin = date(2026, 10, 5), date(2026, 10, 7)
    sesion.add(_alquiler(cliente, vehiculo, inicio, fin))
    sesion.add(_alquiler(cliente, otro, inicio, fin))
    sesion.flush()

    assert sesion.query(Alquiler).count() == 2
