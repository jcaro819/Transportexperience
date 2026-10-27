"""El mismo aviso de pago llegando varias veces a la vez se aplica una sola vez (CLAUDE.md 7.3).

Caso real: el webhook de Wompi, su reintento y la consulta de respaldo dicen "aprobado" al
mismo tiempo. Debe quedar un solo cambio de estado y ninguna devolución. Varios hilos con
su propia conexión; los datos se confirman de verdad y se borran al final.
"""

import threading
from datetime import timedelta

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.auditoria import RegistroAuditoria
from app.comun import fechas
from app.db import motor
from app.modulos.alquileres import servicio as alquileres
from app.modulos.alquileres.modelos import Alquiler, EstadoAlquiler
from app.modulos.inventario.modelos import ModeloVehiculo, TipoVehiculo, Vehiculo
from app.modulos.pagos import procesamiento
from app.modulos.pagos.esquemas import PagoCrear
from app.modulos.pagos.modelos import EstadoPago, MetodoPago, Pago, TipoPago
from app.modulos.pagos.pasarela import PasarelaFalsa, ResultadoCobro
from app.modulos.usuarios.modelos import Rol, Usuario

AVISOS_SIMULTANEOS = 6


@pytest.fixture
def pago_pendiente(base_datos_pruebas):
    """Confirma una reserva con un pago PSE pendiente; al final borra todo."""
    with Session(motor) as sesion:
        tipo = TipoVehiculo(nombre="Tipo concurrencia de pagos", usa_bateria=False)
        modelo = ModeloVehiculo(tipo=tipo, nombre="Modelo pagos", tarifa_diaria=20_000)
        unidad = Vehiculo(codigo="PCON-0001", modelo=modelo)
        cliente = Usuario(
            nombre_completo="Cliente pagos concurrentes",
            correo="pagos.concurrentes@prueba.co",
            hash_contrasena="no-se-usa",
            rol=Rol.CLIENTE,
        )
        metodo = sesion.scalars(select(MetodoPago).where(MetodoPago.codigo == "pse")).first()
        nuevo_metodo = metodo is None
        if nuevo_metodo:
            metodo = MetodoPago(codigo="pse", nombre="PSE")
        sesion.add_all([unidad, cliente, metodo])
        sesion.commit()
        inicio = fechas.hoy() + timedelta(days=4)
        alquiler = alquileres.crear_alquiler(sesion, cliente, modelo.id, inicio, inicio)
        pago = procesamiento.pagar(
            sesion,
            cliente,
            PagoCrear(metodo_pago="pse"),
            PasarelaFalsa(EstadoPago.PENDIENTE),
            alquiler_id=alquiler.id,
        ).pago
        ids = (pago.id, alquiler.id, unidad.id, modelo.id, tipo.id, cliente.id, metodo.id)

    yield ids

    pago_id, alquiler_id, unidad_id, modelo_id, tipo_id, cliente_id, metodo_id = ids
    with Session(motor) as sesion:
        sesion.execute(
            delete(RegistroAuditoria).where(
                (RegistroAuditoria.usuario_id == cliente_id)
                | (
                    (RegistroAuditoria.entidad == "alquileres")
                    & (RegistroAuditoria.entidad_id == str(alquiler_id))
                )
            )
        )
        sesion.execute(delete(Pago).where(Pago.alquiler_id == alquiler_id))
        sesion.execute(delete(Alquiler).where(Alquiler.id == alquiler_id))
        sesion.execute(delete(Vehiculo).where(Vehiculo.id == unidad_id))
        sesion.execute(delete(ModeloVehiculo).where(ModeloVehiculo.id == modelo_id))
        sesion.execute(delete(TipoVehiculo).where(TipoVehiculo.id == tipo_id))
        sesion.execute(delete(Usuario).where(Usuario.id == cliente_id))
        if nuevo_metodo:
            sesion.execute(delete(MetodoPago).where(MetodoPago.id == metodo_id))
        sesion.commit()


def test_seis_avisos_de_aprobado_a_la_vez_se_aplican_una_sola_vez(pago_pendiente) -> None:
    pago_id, alquiler_id = pago_pendiente[:2]
    barrera = threading.Barrier(AVISOS_SIMULTANEOS)
    errores: list[Exception] = []

    def _avisar() -> None:
        with Session(motor) as sesion:
            barrera.wait()
            try:
                procesamiento.aplicar_resultado(
                    sesion, pago_id, ResultadoCobro(EstadoPago.APROBADO, "tx-1"), fechas.ahora()
                )
            except Exception as error:
                errores.append(error)

    hilos = [threading.Thread(target=_avisar) for _ in range(AVISOS_SIMULTANEOS)]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join(timeout=30)

    assert not any(h.is_alive() for h in hilos), "Un hilo quedó colgado: posible deadlock"
    assert not errores, errores
    with Session(motor) as sesion:
        assert sesion.get(Pago, pago_id).estado == EstadoPago.APROBADO
        assert sesion.get(Alquiler, alquiler_id).estado == EstadoAlquiler.CONFIRMADO
        devoluciones = sesion.scalar(
            select(func.count()).where(
                Pago.alquiler_id == alquiler_id, Pago.tipo == TipoPago.COMPENSACION
            )
        )
        confirmaciones = sesion.scalar(
            select(func.count()).where(
                RegistroAuditoria.entidad == "alquileres",
                RegistroAuditoria.entidad_id == str(alquiler_id),
                RegistroAuditoria.datos_nuevos["estado"].astext == "confirmado",
            )
        )
    assert devoluciones == 0
    assert confirmaciones == 1
