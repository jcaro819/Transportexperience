"""Ajustes de stock y compras al mismo tiempo no pierden actualizaciones (HU-10).

Si el administrador ajusta el stock mientras los clientes compran, cada operación debe
sumar o restar sobre el valor más reciente. Varios hilos con su propia conexión; los datos
se confirman de verdad y se borran al final.
"""

import threading

import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.auditoria import RegistroAuditoria
from app.db import motor
from app.modulos.inventario import gestion
from app.modulos.inventario.esquemas_gestion import AjusteStock
from app.modulos.inventario.modelos import CategoriaProducto, Producto
from app.modulos.usuarios.modelos import Rol, Usuario
from app.modulos.ventas import servicio as ventas
from app.modulos.ventas.esquemas import VentaCrear
from app.modulos.ventas.modelos import ItemVenta, Venta

AJUSTES = 6  # cada uno suma 1
COMPRAS = 6  # cada una resta 1
STOCK_INICIAL = 10


@pytest.fixture
def escenario(base_datos_pruebas):
    with Session(motor) as sesion:
        producto = Producto(
            codigo="GCON-CASCO",
            nombre="Casco concurrencia",
            categoria=CategoriaProducto.ACCESORIO,
            precio_venta=100_000,
            stock=STOCK_INICIAL,
        )
        admin = Usuario(
            nombre_completo="Admin concurrencia",
            correo="admin.concurrencia@prueba.co",
            hash_contrasena="no-se-usa",
            rol=Rol.ADMINISTRADOR,
        )
        clientes = [
            Usuario(
                nombre_completo=f"Cliente concurrencia {n}",
                correo=f"cliente.gcon{n}@prueba.co",
                hash_contrasena="no-se-usa",
                rol=Rol.CLIENTE,
            )
            for n in range(COMPRAS)
        ]
        sesion.add_all([producto, admin, *clientes])
        sesion.commit()
        ids = {
            "producto": producto.id,
            "admin": admin.id,
            "clientes": [c.id for c in clientes],
        }
    yield ids
    with Session(motor) as sesion:
        usuarios = [ids["admin"], *ids["clientes"]]
        sesion.execute(delete(RegistroAuditoria).where(RegistroAuditoria.usuario_id.in_(usuarios)))
        ventas_ids = select(Venta.id).where(Venta.cliente_id.in_(ids["clientes"]))
        sesion.execute(delete(ItemVenta).where(ItemVenta.venta_id.in_(ventas_ids)))
        sesion.execute(delete(Venta).where(Venta.cliente_id.in_(ids["clientes"])))
        sesion.execute(delete(Producto).where(Producto.id == ids["producto"]))
        sesion.execute(delete(Usuario).where(Usuario.id.in_(usuarios)))
        sesion.commit()


def test_ajustes_y_compras_simultaneos_no_pierden_ninguna_actualizacion(escenario) -> None:
    producto_id = escenario["producto"]
    barrera = threading.Barrier(AJUSTES + COMPRAS)
    errores: list[Exception] = []

    def _ajustar() -> None:
        with Session(motor) as sesion:
            admin = sesion.get(Usuario, escenario["admin"])
            barrera.wait()
            try:
                gestion.ajustar_stock(
                    sesion, producto_id, AjusteStock(cantidad=1, motivo="Entrada de prueba."), admin
                )
            except Exception as error:
                errores.append(error)

    def _comprar(cliente_id: int) -> None:
        with Session(motor) as sesion:
            cliente = sesion.get(Usuario, cliente_id)
            barrera.wait()
            try:
                ventas.crear_venta(
                    sesion, cliente, VentaCrear(productos=[{"producto_id": producto_id}])
                )
            except Exception as error:
                errores.append(error)

    hilos = [threading.Thread(target=_ajustar) for _ in range(AJUSTES)]
    hilos += [threading.Thread(target=_comprar, args=(c,)) for c in escenario["clientes"]]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join(timeout=30)

    assert not any(h.is_alive() for h in hilos), "Un hilo quedó colgado: posible deadlock"
    assert not errores, errores
    with Session(motor) as sesion:
        assert sesion.get(Producto, producto_id).stock == STOCK_INICIAL + AJUSTES - COMPRAS
