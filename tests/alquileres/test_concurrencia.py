"""Un vehículo no se reserva dos veces, aunque los pedidos lleguen al mismo tiempo (SRS 3.3.3).

Este es el test de la sustentación (CLAUDE.md 7.1). Varios hilos, cada uno con su propia
conexión a Postgres, piden la misma unidad en el mismo instante (una barrera los suelta a
la vez). Debe ganar exactamente uno; los demás reciben ``SinUnidadesDisponibles``.

Aquí no sirve la sesión de prueba que se revierte: cada hilo necesita ver lo que los otros
confirman. Por eso los datos se confirman de verdad y se borran al final.
"""

import threading
from datetime import timedelta

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.auditoria import RegistroAuditoria
from app.comun import fechas
from app.db import motor
from app.modulos.alquileres import servicio
from app.modulos.alquileres.excepciones import SinUnidadesDisponibles
from app.modulos.alquileres.modelos import ESTADOS_ACTIVOS, Alquiler
from app.modulos.inventario.modelos import ModeloVehiculo, TipoVehiculo, Vehiculo
from app.modulos.usuarios.modelos import Rol, Usuario

PEDIDOS_SIMULTANEOS = 8


@pytest.fixture
def escenario(base_datos_pruebas):
    """Crea y confirma un modelo, sus unidades y un cliente por hilo; al final borra todo."""
    creados: dict[str, list[int]] = {}

    def _crear(unidades: int) -> tuple[int, list[int]]:
        with Session(motor) as sesion:
            tipo = TipoVehiculo(nombre="Tipo prueba de concurrencia", usa_bateria=True)
            modelo = ModeloVehiculo(tipo=tipo, nombre="Modelo concurrencia", tarifa_diaria=40_000)
            vehiculos = [
                Vehiculo(codigo=f"CONC-{n:04d}", modelo=modelo) for n in range(1, unidades + 1)
            ]
            clientes = [
                Usuario(
                    nombre_completo=f"Cliente concurrente {n}",
                    correo=f"concurrente{n}@prueba.co",
                    hash_contrasena="no-se-usa",
                    rol=Rol.CLIENTE,
                )
                for n in range(PEDIDOS_SIMULTANEOS)
            ]
            sesion.add_all([*vehiculos, *clientes])
            sesion.commit()
            creados.update(
                tipo=[tipo.id],
                modelo=[modelo.id],
                vehiculos=[v.id for v in vehiculos],
                clientes=[c.id for c in clientes],
            )
            return modelo.id, creados["clientes"]

    yield _crear

    with Session(motor) as sesion:
        clientes, vehiculos = creados.get("clientes", []), creados.get("vehiculos", [])
        # Aquí solo audita la creación de cada reserva, hecha por su cliente.
        sesion.execute(delete(RegistroAuditoria).where(RegistroAuditoria.usuario_id.in_(clientes)))
        sesion.execute(delete(Alquiler).where(Alquiler.vehiculo_id.in_(vehiculos)))
        sesion.execute(delete(Vehiculo).where(Vehiculo.id.in_(vehiculos)))
        sesion.execute(delete(Usuario).where(Usuario.id.in_(clientes)))
        sesion.execute(
            delete(ModeloVehiculo).where(ModeloVehiculo.id.in_(creados.get("modelo", [])))
        )
        sesion.execute(delete(TipoVehiculo).where(TipoVehiculo.id.in_(creados.get("tipo", []))))
        sesion.commit()


def _reservar_a_la_vez(modelo_id: int, clientes: list[int]) -> tuple[list[int], list[Exception]]:
    """Lanza una reserva por cliente, todas a la vez, para las mismas fechas."""
    inicio = fechas.hoy() + timedelta(days=10)
    fin = inicio + timedelta(days=2)
    barrera = threading.Barrier(len(clientes))
    ganadores: list[int] = []
    errores: list[Exception] = []
    candado = threading.Lock()

    def _pedir(cliente_id: int) -> None:
        with Session(motor) as sesion:
            cliente = sesion.get(Usuario, cliente_id)
            barrera.wait()  # todos salen al mismo tiempo
            try:
                alquiler = servicio.crear_alquiler(sesion, cliente, modelo_id, inicio, fin)
                with candado:
                    ganadores.append(alquiler.vehiculo_id)
            except Exception as error:  # se clasifican abajo
                sesion.rollback()
                with candado:
                    errores.append(error)

    hilos = [threading.Thread(target=_pedir, args=(c,)) for c in clientes]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join(timeout=30)
    assert not any(h.is_alive() for h in hilos), "Un hilo quedó colgado: posible deadlock"
    return ganadores, errores


def _activos(vehiculo_ids: list[int]) -> int:
    with Session(motor) as sesion:
        return sesion.scalar(
            select(func.count()).where(
                Alquiler.vehiculo_id.in_(vehiculo_ids), Alquiler.estado.in_(ESTADOS_ACTIVOS)
            )
        )


def test_dos_reservas_simultaneas_del_mismo_vehiculo_exactamente_una_gana(escenario) -> None:
    modelo_id, clientes = escenario(unidades=1)

    ganadores, errores = _reservar_a_la_vez(modelo_id, clientes[:2])

    assert len(ganadores) == 1
    assert len(errores) == 1
    assert isinstance(errores[0], SinUnidadesDisponibles)
    assert _activos(ganadores) == 1


def test_ocho_reservas_simultaneas_de_la_ultima_unidad_exactamente_una_gana(escenario) -> None:
    modelo_id, clientes = escenario(unidades=1)

    ganadores, errores = _reservar_a_la_vez(modelo_id, clientes)

    assert len(ganadores) == 1
    assert len(errores) == PEDIDOS_SIMULTANEOS - 1
    assert all(isinstance(e, SinUnidadesDisponibles) for e in errores), errores
    assert _activos(ganadores) == 1


def test_con_tres_unidades_ganan_tres_y_cada_una_con_unidad_distinta(escenario) -> None:
    modelo_id, clientes = escenario(unidades=3)

    ganadores, errores = _reservar_a_la_vez(modelo_id, clientes)

    assert len(ganadores) == 3
    assert len(set(ganadores)) == 3, "Dos clientes recibieron la misma unidad"
    assert len(errores) == PEDIDOS_SIMULTANEOS - 3
    assert all(isinstance(e, SinUnidadesDisponibles) for e in errores), errores
