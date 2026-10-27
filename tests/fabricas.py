"""Fábrica de datos de prueba: inventario, productos y alquileres. Úsala con ``fabrica``."""

from datetime import date, datetime
from decimal import Decimal
from itertools import count

from sqlalchemy.orm import Session

from app.modulos.alquileres.modelos import Alquiler, EstadoAlquiler
from app.modulos.domicilios.modelos import Domicilio, EstadoDomicilio, ZonaCobertura
from app.modulos.inventario.modelos import (
    CategoriaProducto,
    EstadoVehiculo,
    ModeloVehiculo,
    Producto,
    TipoVehiculo,
    Vehiculo,
)
from app.modulos.usuarios.modelos import Rol, Usuario

# GeoJSON: [longitud, latitud]. Cubre el centro de Bucaramanga.
ZONA_DE_PRUEBA = {
    "type": "Polygon",
    "coordinates": [
        [[-73.14, 7.14], [-73.10, 7.14], [-73.10, 7.10], [-73.14, 7.10], [-73.14, 7.14]]
    ],
}


class Fabrica:
    def __init__(self, sesion: Session) -> None:
        self.sesion = sesion
        self._numeros = count(1)
        self._cliente: Usuario | None = None

    def _guardar(self, objeto):
        self.sesion.add(objeto)
        self.sesion.flush()
        return objeto

    def tipo(self, nombre: str | None = None, *, activo: bool = True) -> TipoVehiculo:
        nombre = nombre or f"Tipo {next(self._numeros)}"
        return self._guardar(TipoVehiculo(nombre=nombre, usa_bateria=True, activo=activo))

    def modelo(
        self,
        tipo: TipoVehiculo | None = None,
        *,
        nombre: str | None = None,
        tarifa_diaria: int | None = 50_000,
        precio_venta: int | None = None,
        activo: bool = True,
    ) -> ModeloVehiculo:
        return self._guardar(
            ModeloVehiculo(
                tipo=tipo or self.tipo(),
                nombre=nombre or f"Modelo {next(self._numeros)}",
                tarifa_diaria=tarifa_diaria,
                precio_venta=precio_venta,
                activo=activo,
            )
        )

    def vehiculo(
        self,
        modelo: ModeloVehiculo | None = None,
        estado: EstadoVehiculo = EstadoVehiculo.DISPONIBLE,
        **datos,
    ) -> Vehiculo:
        codigo = datos.pop("codigo", None) or f"VEH-{next(self._numeros):04d}"
        return self._guardar(
            Vehiculo(codigo=codigo, modelo=modelo or self.modelo(), estado=estado, **datos)
        )

    def producto(
        self,
        *,
        stock: int = 10,
        precio_venta: int = 100_000,
        categoria: CategoriaProducto = CategoriaProducto.ACCESORIO,
        activo: bool = True,
        nombre: str | None = None,
    ) -> Producto:
        n = next(self._numeros)
        return self._guardar(
            Producto(
                codigo=f"PRD-{n:04d}",
                nombre=nombre or f"Producto {n}",
                categoria=categoria,
                precio_venta=precio_venta,
                stock=stock,
                activo=activo,
            )
        )

    def cliente(self) -> Usuario:
        if self._cliente is None:
            self._cliente = self._guardar(
                Usuario(
                    nombre_completo="Cliente de la fábrica",
                    correo=f"fabrica{next(self._numeros)}@prueba.co",
                    hash_contrasena="no-se-usa-en-estos-tests",
                    rol=Rol.CLIENTE,
                )
            )
        return self._cliente

    def alquiler(
        self,
        vehiculo: Vehiculo,
        inicio: date,
        fin: date,
        estado: EstadoAlquiler = EstadoAlquiler.CONFIRMADO,
        *,
        expira_en: datetime | None = None,
    ) -> Alquiler:
        tarifa = vehiculo.modelo.tarifa_diaria or 50_000
        subtotal = ((fin - inicio).days + 1) * tarifa
        return self._guardar(
            Alquiler(
                cliente_id=self.cliente().id,
                vehiculo_id=vehiculo.id,
                fecha_inicio=inicio,
                fecha_fin=fin,
                tarifa_diaria=tarifa,
                subtotal=subtotal,
                valor_envio=0,
                total=subtotal,
                estado=estado,
                expira_en=expira_en,
            )
        )

    def zona(self, *, tarifa_envio: int = 5_000, poligono: dict | None = None) -> ZonaCobertura:
        """Zona cuadrada alrededor del centro de Bucaramanga (lat 7.10-7.14, lng -73.14--73.10)."""
        return self._guardar(
            ZonaCobertura(
                nombre=f"Zona {next(self._numeros)}",
                tarifa_envio=tarifa_envio,
                poligono=poligono or ZONA_DE_PRUEBA,
            )
        )

    def domicilio(
        self,
        alquiler: Alquiler,
        estado: EstadoDomicilio = EstadoDomicilio.PENDIENTE,
        *,
        domiciliario: Usuario | None = None,
        vehiculo_transporte: Vehiculo | None = None,
    ) -> Domicilio:
        """Domicilio de un alquiler, directo en la base (sin pasar por el servicio)."""
        return self._guardar(
            Domicilio(
                codigo_rastreo=f"TXPRUEBA{next(self._numeros):04d}",
                cliente_id=alquiler.cliente_id,
                alquiler_id=alquiler.id,
                zona_id=self.zona().id,
                direccion="Calle 36 # 19-20",
                latitud=Decimal("7.1193"),
                longitud=Decimal("-73.1227"),
                estado=estado,
                domiciliario_id=domiciliario.id if domiciliario else None,
                vehiculo_transporte_id=vehiculo_transporte.id if vehiculo_transporte else None,
            )
        )
