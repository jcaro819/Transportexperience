"""Asignaciones simultáneas de domicilios (SRS 3.3.3, HU-06).

Un vehículo de transporte no puede quedar en dos entregas, ni un domiciliario con dos
entregas en ruta, aunque dos personas del despacho asignen al mismo tiempo. Varios hilos
con su propia conexión; los datos se confirman de verdad y se borran al final.
"""

import threading
from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.auditoria import RegistroAuditoria
from app.comun import fechas
from app.db import motor
from app.modulos.alquileres.modelos import Alquiler, EstadoAlquiler
from app.modulos.domicilios import servicio
from app.modulos.domicilios.excepciones import (
    DomiciliarioNoDisponible,
    VehiculoDeTransporteNoDisponible,
)
from app.modulos.domicilios.modelos import (
    Domicilio,
    EstadoDomicilio,
    HistorialEstadoDomicilio,
    ZonaCobertura,
)
from app.modulos.inventario.modelos import ModeloVehiculo, TipoVehiculo, Vehiculo
from app.modulos.usuarios.modelos import Rol, Usuario
from tests.fabricas import ZONA_DE_PRUEBA

ENTREGAS = 4


def _usuario(nombre: str, rol: Rol) -> Usuario:
    return Usuario(
        nombre_completo=nombre,
        correo=f"{nombre.lower().replace(' ', '.')}@prueba.co",
        hash_contrasena="no-se-usa",
        rol=rol,
    )


@pytest.fixture
def escenario(base_datos_pruebas):
    """Confirma 4 domicilios pagados, 4 domiciliarios, un operador y una moto; luego borra."""
    with Session(motor) as sesion:
        tipo = TipoVehiculo(nombre="Tipo concurrencia domicilios", usa_bateria=True)
        modelo = ModeloVehiculo(tipo=tipo, nombre="Modelo domicilios", tarifa_diaria=10_000)
        moto = Vehiculo(codigo="DCON-MOTO", modelo=modelo)
        unidades = [Vehiculo(codigo=f"DCON-{n:04d}", modelo=modelo) for n in range(ENTREGAS)]
        cliente = _usuario("Cliente domicilios", Rol.CLIENTE)
        operador = _usuario("Operador domicilios", Rol.OPERADOR)
        domiciliarios = [_usuario(f"Domiciliario {n}", Rol.DOMICILIARIO) for n in range(ENTREGAS)]
        zona = ZonaCobertura(
            nombre="Zona concurrencia", tarifa_envio=5_000, poligono=ZONA_DE_PRUEBA
        )
        sesion.add_all([moto, *unidades, cliente, operador, *domiciliarios, zona])
        sesion.flush()
        inicio = fechas.hoy() + timedelta(days=3)
        domicilios = []
        for n, unidad in enumerate(unidades):
            alquiler = Alquiler(
                cliente_id=cliente.id,
                vehiculo_id=unidad.id,
                fecha_inicio=inicio,
                fecha_fin=inicio,
                tarifa_diaria=10_000,
                subtotal=10_000,
                valor_envio=5_000,
                total=15_000,
                estado=EstadoAlquiler.CONFIRMADO,
            )
            sesion.add(alquiler)
            sesion.flush()
            domicilios.append(
                Domicilio(
                    codigo_rastreo=f"TX-DCON{n:04d}",
                    cliente_id=cliente.id,
                    alquiler_id=alquiler.id,
                    zona_id=zona.id,
                    direccion="Calle 36 # 19-20",
                    latitud=Decimal("7.1193"),
                    longitud=Decimal("-73.1227"),
                )
            )
        sesion.add_all(domicilios)
        sesion.commit()
        ids = {
            "tipo": tipo.id,
            "modelo": modelo.id,
            "vehiculos": [moto.id, *(u.id for u in unidades)],
            "moto": moto.id,
            "usuarios": [cliente.id, operador.id, *(d.id for d in domiciliarios)],
            "operador": operador.id,
            "domiciliarios": [d.id for d in domiciliarios],
            "domicilios": [d.id for d in domicilios],
            "zona": zona.id,
        }

    yield ids

    with Session(motor) as sesion:
        sesion.execute(
            delete(RegistroAuditoria).where(RegistroAuditoria.usuario_id.in_(ids["usuarios"]))
        )
        sesion.execute(
            delete(HistorialEstadoDomicilio).where(
                HistorialEstadoDomicilio.domicilio_id.in_(ids["domicilios"])
            )
        )
        sesion.execute(delete(Domicilio).where(Domicilio.id.in_(ids["domicilios"])))
        sesion.execute(delete(Alquiler).where(Alquiler.cliente_id.in_(ids["usuarios"])))
        sesion.execute(delete(Vehiculo).where(Vehiculo.id.in_(ids["vehiculos"])))
        sesion.execute(delete(Usuario).where(Usuario.id.in_(ids["usuarios"])))
        sesion.execute(delete(ZonaCobertura).where(ZonaCobertura.id == ids["zona"]))
        sesion.execute(delete(ModeloVehiculo).where(ModeloVehiculo.id == ids["modelo"]))
        sesion.execute(delete(TipoVehiculo).where(TipoVehiculo.id == ids["tipo"]))
        sesion.commit()


def _a_la_vez(asignaciones: list[tuple[int, int, int | None]], operador_id: int):
    """Cada asignación es (domicilio, domiciliario, vehículo); todas salen a la vez."""
    barrera = threading.Barrier(len(asignaciones))
    exitos, errores, candado = [], [], threading.Lock()

    def _asignar(domicilio_id, domiciliario_id, vehiculo_id) -> None:
        with Session(motor) as sesion:
            operador = sesion.get(Usuario, operador_id)
            barrera.wait()
            try:
                servicio.asignar_domiciliario(
                    sesion, domicilio_id, operador, domiciliario_id, vehiculo_id
                )
                with candado:
                    exitos.append(domicilio_id)
            except Exception as error:
                sesion.rollback()
                with candado:
                    errores.append(error)

    hilos = [threading.Thread(target=_asignar, args=a) for a in asignaciones]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join(timeout=30)
    assert not any(h.is_alive() for h in hilos), "Un hilo quedó colgado: posible deadlock"
    return exitos, errores


def _en_ruta(condicion) -> int:
    with Session(motor) as sesion:
        return sesion.scalar(
            select(func.count()).where(condicion, Domicilio.estado == EstadoDomicilio.ASIGNADO)
        )


def test_la_misma_moto_en_cuatro_entregas_a_la_vez_solo_queda_en_una(escenario) -> None:
    asignaciones = [
        (domicilio, domiciliario, escenario["moto"])
        for domicilio, domiciliario in zip(
            escenario["domicilios"], escenario["domiciliarios"], strict=True
        )
    ]

    exitos, errores = _a_la_vez(asignaciones, escenario["operador"])

    assert len(exitos) == 1
    assert all(isinstance(e, VehiculoDeTransporteNoDisponible) for e in errores), errores
    assert _en_ruta(Domicilio.vehiculo_transporte_id == escenario["moto"]) == 1


def test_el_mismo_domiciliario_en_cuatro_entregas_a_la_vez_solo_queda_en_una(escenario) -> None:
    domiciliario = escenario["domiciliarios"][0]
    asignaciones = [(domicilio, domiciliario, None) for domicilio in escenario["domicilios"]]

    exitos, errores = _a_la_vez(asignaciones, escenario["operador"])

    assert len(exitos) == 1
    assert all(isinstance(e, DomiciliarioNoDisponible) for e in errores), errores
    assert _en_ruta(Domicilio.domiciliario_id == domiciliario) == 1
