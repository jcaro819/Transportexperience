"""Importa todos los modelos para registrarlos en ``Base.metadata``.

Lo usan Alembic (para ``--autogenerate``) y los tests. Si creas un modelo nuevo,
agrégalo aquí.
"""

from app.auditoria import RegistroAuditoria
from app.modulos.alquileres.modelos import Alquiler
from app.modulos.domicilios.modelos import Domicilio, HistorialEstadoDomicilio, ZonaCobertura
from app.modulos.inventario.modelos import (
    ModeloVehiculo,
    NovedadVehiculo,
    Producto,
    TipoVehiculo,
    Vehiculo,
)
from app.modulos.pagos.modelos import EventoPago, MetodoPago, Pago
from app.modulos.portal.modelos import ContenidoPortal, HorarioAtencion
from app.modulos.rastreo.modelos import PosicionGps
from app.modulos.reportes.modelos import Acta
from app.modulos.usuarios.modelos import Usuario
from app.modulos.ventas.modelos import ItemVenta, Venta

__all__ = [
    "Acta",
    "Alquiler",
    "ContenidoPortal",
    "Domicilio",
    "EventoPago",
    "HistorialEstadoDomicilio",
    "HorarioAtencion",
    "ItemVenta",
    "MetodoPago",
    "ModeloVehiculo",
    "NovedadVehiculo",
    "Pago",
    "PosicionGps",
    "Producto",
    "RegistroAuditoria",
    "TipoVehiculo",
    "Usuario",
    "Vehiculo",
    "Venta",
    "ZonaCobertura",
]
