"""Liberar lo que aparta una venta y expirar las ventas vencidas (CLAUDE.md 7.1, regla 2).

Una venta en ``pendiente_pago`` aparta stock (ya descontado) y unidades (en
``reservado``). Si el cliente no paga en 15 minutos, nadie la marca sola: se expira cuando
otra operación necesita lo que aparta, en la misma transacción. Al expirar o cancelarse,
devuelve el stock y las unidades vuelven a ``disponible``.

Lo usan las ventas y los alquileres, por eso vive aquí y no en ``servicio.py``.
"""

from collections.abc import Iterable
from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.auditoria import registrar_auditoria
from app.modulos.inventario.modelos import EstadoVehiculo, Producto, Vehiculo
from app.modulos.inventario.servicio import bloquear_inventario, cambiar_estado_vehiculo
from app.modulos.usuarios.modelos import Usuario
from app.modulos.ventas.estados import validar_transicion
from app.modulos.ventas.modelos import EstadoVenta, ItemVenta, Venta


def cambiar_estado_venta(
    sesion: Session,
    venta: Venta,
    nuevo: EstadoVenta,
    usuario: Usuario | None,
    motivo: str | None = None,
) -> None:
    """Único camino para cambiar el estado de una venta: valida la transición y la audita."""
    anterior = venta.estado
    validar_transicion(anterior, nuevo)
    venta.estado = nuevo
    if nuevo != EstadoVenta.PENDIENTE_PAGO:
        venta.expira_en = None  # el bloqueo temporal solo existe mientras se paga
    despues = {"estado": nuevo.value}
    if motivo:
        despues["motivo"] = motivo
    registrar_auditoria(
        sesion,
        usuario_id=usuario.id if usuario else None,
        accion="cambiar_estado",
        entidad="ventas",
        entidad_id=venta.id,
        antes={"estado": anterior.value},
        despues=despues,
    )


def liberar_venta(
    sesion: Session,
    venta: Venta,
    nuevo: EstadoVenta,
    usuario: Usuario | None,
    motivo: str,
    vehiculos: dict[int, Vehiculo],
    productos: dict[int, Producto],
) -> None:
    """Cancela o expira la venta y devuelve lo que apartaba. No hace commit.

    ``vehiculos`` y ``productos`` son las filas ya bloqueadas con ``bloquear_inventario``.
    Una unidad que ya no está ``reservado`` (p. ej., entró en mantenimiento) se deja como
    está: el taller decide cuándo vuelve.
    """
    for item in venta.items:
        if item.producto_id is not None:
            productos[item.producto_id].stock += item.cantidad
        elif vehiculos[item.vehiculo_id].estado == EstadoVehiculo.RESERVADO:
            cambiar_estado_vehiculo(
                sesion,
                vehiculos[item.vehiculo_id],
                EstadoVehiculo.DISPONIBLE,
                usuario,
                f"Liberada por la venta #{venta.id} ({nuevo.value})",
            )
    cambiar_estado_venta(sesion, venta, nuevo, usuario, motivo)


def bloquear_y_expirar(
    sesion: Session,
    momento: datetime,
    vehiculo_ids: Iterable[int],
    producto_ids: Iterable[int] = (),
) -> tuple[dict[int, Vehiculo], dict[int, Producto]]:
    """Bloquea lo pedido y, de paso, expira las ventas vencidas que lo apartan.

    Para no romper el orden global de bloqueo (vehículos, luego productos, luego
    operaciones), primero se buscan esas ventas sin bloquear, se suman sus ítems a lo que
    hay que bloquear, y todo se bloquea de una vez. Devuelve las filas bloqueadas, que
    incluyen las de las ventas expiradas.
    """
    vehiculo_ids, producto_ids = set(vehiculo_ids), set(producto_ids)
    vencidas = select(Venta.id).where(
        Venta.estado == EstadoVenta.PENDIENTE_PAGO,
        Venta.expira_en <= momento,
        Venta.items.any(
            or_(ItemVenta.vehiculo_id.in_(vehiculo_ids), ItemVenta.producto_id.in_(producto_ids))
        ),
    )
    ids_vencidas = list(sesion.scalars(vencidas))
    if ids_vencidas:
        for vehiculo_id, producto_id in sesion.execute(
            select(ItemVenta.vehiculo_id, ItemVenta.producto_id).where(
                ItemVenta.venta_id.in_(ids_vencidas)
            )
        ):
            if vehiculo_id is not None:
                vehiculo_ids.add(vehiculo_id)
            else:
                producto_ids.add(producto_id)

    vehiculos, productos = bloquear_inventario(sesion, vehiculo_ids, producto_ids)

    if ids_vencidas:
        # Se vuelve a filtrar: otra transacción pudo expirarlas mientras esperábamos.
        por_expirar = sesion.scalars(
            select(Venta)
            .where(
                Venta.id.in_(ids_vencidas),
                Venta.estado == EstadoVenta.PENDIENTE_PAGO,
                Venta.expira_en <= momento,
            )
            .order_by(Venta.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).all()
        for venta in por_expirar:
            liberar_venta(
                sesion, venta, EstadoVenta.EXPIRADA, None, "Bloqueo vencido", vehiculos, productos
            )
        sesion.flush()
    return vehiculos, productos
