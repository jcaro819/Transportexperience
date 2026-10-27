"""Una unidad o un producto no se venden dos veces, aunque los pedidos lleguen a la vez.

SRS 3.3.3: un mismo vehículo no puede estar reservado, vendido o asignado en dos
operaciones activas al mismo tiempo. Igual que en ``tests/alquileres/test_concurrencia.py``,
varios hilos con su propia conexión salen a la vez de una barrera; los datos se confirman
de verdad y se borran al final.
"""

import threading
from collections.abc import Callable
from datetime import timedelta

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.auditoria import RegistroAuditoria
from app.comun import fechas
from app.db import motor
from app.modulos.alquileres import servicio as alquileres
from app.modulos.alquileres.excepciones import SinUnidadesDisponibles
from app.modulos.alquileres.modelos import ESTADOS_ACTIVOS, Alquiler
from app.modulos.inventario.modelos import (
    CategoriaProducto,
    EstadoVehiculo,
    ModeloVehiculo,
    Producto,
    TipoVehiculo,
    Vehiculo,
)
from app.modulos.usuarios.modelos import Rol, Usuario
from app.modulos.ventas import servicio as ventas
from app.modulos.ventas.esquemas import VentaCrear
from app.modulos.ventas.excepciones import SinUnidadesParaVenta, StockInsuficiente
from app.modulos.ventas.modelos import ItemVenta, Venta

PEDIDOS_SIMULTANEOS = 8


@pytest.fixture
def escenario(base_datos_pruebas):
    """Confirma un modelo con una unidad, un producto y un cliente por hilo; luego borra todo."""
    with Session(motor) as sesion:
        tipo = TipoVehiculo(nombre="Tipo concurrencia de ventas", usa_bateria=False)
        modelo = ModeloVehiculo(
            tipo=tipo, nombre="Modelo ventas", tarifa_diaria=30_000, precio_venta=900_000
        )
        unidad = Vehiculo(codigo="VCON-0001", modelo=modelo)
        producto = Producto(
            codigo="VCON-CASCO",
            nombre="Casco concurrencia",
            categoria=CategoriaProducto.ACCESORIO,
            precio_venta=100_000,
            stock=3,
        )
        clientes = [
            Usuario(
                nombre_completo=f"Comprador concurrente {n}",
                correo=f"comprador{n}@prueba.co",
                hash_contrasena="no-se-usa",
                rol=Rol.CLIENTE,
            )
            for n in range(PEDIDOS_SIMULTANEOS)
        ]
        sesion.add_all([unidad, producto, *clientes])
        sesion.commit()
        ids = {
            "tipo": tipo.id,
            "modelo": modelo.id,
            "unidad": unidad.id,
            "producto": producto.id,
            "clientes": [c.id for c in clientes],
        }

    yield ids

    with Session(motor) as sesion:
        clientes = ids["clientes"]
        sesion.execute(delete(RegistroAuditoria).where(RegistroAuditoria.usuario_id.in_(clientes)))
        sesion.execute(
            delete(ItemVenta).where(
                ItemVenta.venta_id.in_(select(Venta.id).where(Venta.cliente_id.in_(clientes)))
            )
        )
        sesion.execute(delete(Venta).where(Venta.cliente_id.in_(clientes)))
        sesion.execute(delete(Alquiler).where(Alquiler.cliente_id.in_(clientes)))
        sesion.execute(delete(Vehiculo).where(Vehiculo.id == ids["unidad"]))
        sesion.execute(delete(Producto).where(Producto.id == ids["producto"]))
        sesion.execute(delete(Usuario).where(Usuario.id.in_(clientes)))
        sesion.execute(delete(ModeloVehiculo).where(ModeloVehiculo.id == ids["modelo"]))
        sesion.execute(delete(TipoVehiculo).where(TipoVehiculo.id == ids["tipo"]))
        sesion.commit()


def _a_la_vez(pedidos: list[Callable[[Session, Usuario], object]], clientes: list[int]):
    """Ejecuta cada pedido en su hilo, con su cliente, todos a la vez."""
    barrera = threading.Barrier(len(pedidos))
    exitos: list[object] = []
    errores: list[Exception] = []
    candado = threading.Lock()

    def _correr(pedido, cliente_id: int) -> None:
        with Session(motor) as sesion:
            cliente = sesion.get(Usuario, cliente_id)
            barrera.wait()
            try:
                resultado = pedido(sesion, cliente)
                with candado:
                    exitos.append(resultado)
            except Exception as error:  # se clasifican en cada test
                sesion.rollback()
                with candado:
                    errores.append(error)

    hilos = [
        threading.Thread(target=_correr, args=(p, c))
        for p, c in zip(pedidos, clientes, strict=True)
    ]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join(timeout=30)
    assert not any(h.is_alive() for h in hilos), "Un hilo quedó colgado: posible deadlock"
    return exitos, errores


def _comprar_unidad(modelo_id: int):
    datos = VentaCrear(vehiculos=[{"modelo_id": modelo_id}])
    return lambda sesion, cliente: ventas.crear_venta(sesion, cliente, datos)


def _alquilar(modelo_id: int):
    inicio = fechas.hoy() + timedelta(days=5)
    return lambda sesion, cliente: alquileres.crear_alquiler(
        sesion, cliente, modelo_id, inicio, inicio + timedelta(days=1)
    )


def test_ocho_compras_simultaneas_de_la_ultima_unidad_exactamente_una_gana(escenario) -> None:
    pedidos = [_comprar_unidad(escenario["modelo"])] * PEDIDOS_SIMULTANEOS

    exitos, errores = _a_la_vez(pedidos, escenario["clientes"])

    assert len(exitos) == 1
    assert all(isinstance(e, SinUnidadesParaVenta) for e in errores), errores
    with Session(motor) as sesion:
        assert sesion.get(Vehiculo, escenario["unidad"]).estado == EstadoVehiculo.RESERVADO


def test_ocho_compras_simultaneas_con_stock_de_tres_ganan_exactamente_tres(escenario) -> None:
    datos = VentaCrear(productos=[{"producto_id": escenario["producto"]}])
    pedidos = [lambda s, c: ventas.crear_venta(s, c, datos)] * PEDIDOS_SIMULTANEOS

    exitos, errores = _a_la_vez(pedidos, escenario["clientes"])

    assert len(exitos) == 3
    assert all(isinstance(e, StockInsuficiente) for e in errores), errores
    with Session(motor) as sesion:
        assert sesion.get(Producto, escenario["producto"]).stock == 0


def test_compra_y_alquiler_simultaneos_de_la_misma_unidad_exactamente_uno_gana(
    escenario,
) -> None:
    mitad = PEDIDOS_SIMULTANEOS // 2
    pedidos = [_comprar_unidad(escenario["modelo"])] * mitad + [
        _alquilar(escenario["modelo"])
    ] * mitad

    exitos, errores = _a_la_vez(pedidos, escenario["clientes"])

    assert len(exitos) == 1
    assert all(isinstance(e, SinUnidadesParaVenta | SinUnidadesDisponibles) for e in errores), (
        errores
    )
    with Session(motor) as sesion:
        alquileres_activos = sesion.scalar(
            select(func.count()).where(
                Alquiler.vehiculo_id == escenario["unidad"], Alquiler.estado.in_(ESTADOS_ACTIVOS)
            )
        )
        reservada = sesion.get(Vehiculo, escenario["unidad"]).estado == EstadoVehiculo.RESERVADO
    assert alquileres_activos + reservada == 1  # o se alquiló o se apartó para compra, no ambos
