"""Fábrica de datos de prueba del inventario y los alquileres. Úsala con el fixture ``fabrica``."""

from datetime import date, datetime
from itertools import count

from sqlalchemy.orm import Session

from app.modulos.alquileres.modelos import Alquiler, EstadoAlquiler
from app.modulos.inventario.modelos import EstadoVehiculo, ModeloVehiculo, TipoVehiculo, Vehiculo
from app.modulos.usuarios.modelos import Rol, Usuario


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
