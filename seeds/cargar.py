"""Carga los datos de ejemplo en la base de DESARROLLO.

Uso:  python -m seeds.cargar

- Se niega a correr si ENTORNO no es "desarrollo".
- Se puede correr varias veces: cada registro se busca por su clave natural (correo,
  código, nombre...) y solo se crea si no existe. Lo que ya está no se modifica.
- Todo va en una sola transacción: si algo falla, no queda nada a medias.
"""

import sys
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import obtener_configuracion
from app.modulos.alquileres.modelos import Alquiler, EstadoAlquiler
from app.modulos.domicilios.modelos import ZonaCobertura
from app.modulos.inventario.modelos import (
    ModeloVehiculo,
    NovedadVehiculo,
    Producto,
    TipoVehiculo,
    Vehiculo,
)
from app.modulos.pagos.modelos import EstadoPago, MetodoPago, Pago
from app.modulos.portal.modelos import ContenidoPortal, HorarioAtencion
from app.modulos.usuarios.modelos import Rol, Usuario
from app.modulos.ventas.modelos import EstadoVenta, ItemVenta, Venta
from app.seguridad import hashear_contrasena
from seeds import datos


class CargaDeSemillas:
    """Crea lo que falte y cuenta cuántos registros creó por tabla."""

    def __init__(self, sesion: Session) -> None:
        self.sesion = sesion
        self.creados: Counter[str] = Counter()

    def asegurar(self, modelo: type, clave: dict[str, Any], **datos: Any):
        """Devuelve el registro con ``clave``; si no existe, lo crea con ``datos``."""
        existente = self.sesion.scalars(select(modelo).filter_by(**clave)).one_or_none()
        if existente is not None:
            return existente
        registro = modelo(**clave, **datos)
        self.sesion.add(registro)
        self.sesion.flush()
        self.creados[modelo.__tablename__] += 1
        return registro

    def cargar(self) -> Counter[str]:
        usuarios = self._usuarios()
        self._catalogo()
        self._productos()
        for zona in datos.ZONAS_COBERTURA:
            self.asegurar(
                ZonaCobertura,
                {"nombre": zona["nombre"]},
                poligono=zona["poligono"],
                tarifa_envio=zona["tarifa_envio"],
            )
        metodos = {
            m["codigo"]: self.asegurar(MetodoPago, {"codigo": m["codigo"]}, nombre=m["nombre"])
            for m in datos.METODOS_PAGO
        }
        for contenido in datos.CONTENIDO_PORTAL:
            self.asegurar(
                ContenidoPortal,
                {"seccion": contenido["seccion"]},
                titulo=contenido["titulo"],
                contenido=contenido["contenido"],
            )
        for horario in datos.HORARIOS_ATENCION:
            self.asegurar(
                HorarioAtencion,
                {"dia_semana": horario["dia_semana"]},
                hora_apertura=horario["hora_apertura"],
                hora_cierre=horario["hora_cierre"],
            )
        self._novedades(usuarios[Rol.OPERADOR])
        self._operaciones(usuarios[Rol.CLIENTE], metodos["tarjeta"])
        return self.creados

    def _usuarios(self) -> dict[Rol, Usuario]:
        usuarios = {}
        hash_comun = None  # los 4 comparten contraseña: se calcula una sola vez
        for u in datos.USUARIOS:
            existente = self.sesion.scalars(
                select(Usuario).filter_by(correo=u["correo"])
            ).one_or_none()
            if existente is not None:
                usuarios[u["rol"]] = existente
                continue
            # bcrypt es lento a propósito: solo se calcula si hay que crear un usuario.
            hash_comun = hash_comun or hashear_contrasena(datos.CONTRASENA_DESARROLLO)
            usuarios[u["rol"]] = self.asegurar(
                Usuario,
                {"correo": u["correo"]},
                nombre_completo=u["nombre_completo"],
                telefono=u["telefono"],
                rol=u["rol"],
                hash_contrasena=hash_comun,
            )
        return usuarios

    def _catalogo(self) -> None:
        tipos = {
            t["nombre"]: self.asegurar(
                TipoVehiculo, {"nombre": t["nombre"]}, usa_bateria=t["usa_bateria"]
            )
            for t in datos.TIPOS_VEHICULO
        }
        modelos = {}
        for m in datos.MODELOS_VEHICULO:
            modelos[m["nombre"]] = self.asegurar(
                ModeloVehiculo,
                {"nombre": m["nombre"]},
                tipo_vehiculo_id=tipos[m["tipo"]].id,
                descripcion=m["descripcion"],
                tarifa_diaria=m["tarifa_diaria"],
                precio_venta=m["precio_venta"],
            )
        for v in datos.VEHICULOS:
            extra = {k: v[k] for k in ("estado", "nivel_bateria") if k in v}
            self.asegurar(
                Vehiculo,
                {"codigo": v["codigo"]},
                modelo_id=modelos[v["modelo"]].id,
                ubicacion=v["ubicacion"],
                **extra,
            )

    def _productos(self) -> None:
        for p in datos.PRODUCTOS:
            self.asegurar(
                Producto, {"codigo": p["codigo"]}, **{k: v for k, v in p.items() if k != "codigo"}
            )

    def _vehiculo(self, codigo: str) -> Vehiculo:
        return self.sesion.scalars(select(Vehiculo).filter_by(codigo=codigo)).one()

    def _novedades(self, operador: Usuario) -> None:
        for n in datos.NOVEDADES:
            vehiculo = self._vehiculo(n["vehiculo"])
            self.asegurar(
                NovedadVehiculo,
                {"vehiculo_id": vehiculo.id, "tipo": n["tipo"]},
                descripcion=n["descripcion"],
                es_critica=n["es_critica"],
                reportada_por_id=operador.id,
            )

    def _ya_existe_pago(self, referencia: str) -> bool:
        consulta = select(Pago.id).filter_by(referencia=referencia)
        return self.sesion.scalars(consulta).first() is not None

    def _pago_aprobado(self, referencia: str, metodo: MetodoPago, monto: int, **operacion):
        self.sesion.add(
            Pago(
                referencia=referencia,
                metodo_pago_id=metodo.id,
                monto=monto,
                estado=EstadoPago.APROBADO,
                proveedor="falso",
                aprobado_en=datetime.now(UTC),
                **operacion,
            )
        )
        self.creados["pagos"] += 1

    def _alquiler_pagado(
        self,
        referencia: str,
        cliente: Usuario,
        metodo: MetodoPago,
        codigo: str,
        inicio: date,
        fin: date,
        estado: EstadoAlquiler,
    ) -> None:
        """Alquiler con su pago aprobado. La referencia del pago es la clave de idempotencia."""
        if self._ya_existe_pago(referencia):
            return
        vehiculo = self._vehiculo(codigo)
        tarifa = vehiculo.modelo.tarifa_diaria
        subtotal = ((fin - inicio).days + 1) * tarifa
        alquiler = Alquiler(
            cliente_id=cliente.id,
            vehiculo_id=vehiculo.id,
            fecha_inicio=inicio,
            fecha_fin=fin,
            tarifa_diaria=tarifa,
            subtotal=subtotal,
            valor_envio=0,
            total=subtotal,
            estado=estado,
        )
        self.sesion.add(alquiler)
        self.sesion.flush()
        self.creados["alquileres"] += 1
        self._pago_aprobado(referencia, metodo, subtotal, alquiler_id=alquiler.id)

    def _operaciones(self, cliente: Usuario, tarjeta: MetodoPago) -> None:
        """Operaciones que respaldan los estados de las unidades, más una reserva futura."""
        hoy = date.today()
        # MON-0003 está "alquilado": su alquiler va de ayer a mañana.
        self._alquiler_pagado(
            "SEED-ALQ-0001",
            cliente,
            tarjeta,
            "MON-0003",
            hoy - timedelta(days=1),
            hoy + timedelta(days=1),
            EstadoAlquiler.EN_CURSO,
        )
        # MON-0001 está "disponible" hoy, pero reservado en unos días: sirve para probar
        # la disponibilidad por fechas (HU-02, HU-03).
        self._alquiler_pagado(
            "SEED-ALQ-0002",
            cliente,
            tarjeta,
            "MON-0001",
            hoy + timedelta(days=3),
            hoy + timedelta(days=5),
            EstadoAlquiler.CONFIRMADO,
        )

        # CIC-0004 está "vendido": su venta pagada.
        if not self._ya_existe_pago("SEED-VEN-0001"):
            vehiculo = self._vehiculo("CIC-0004")
            precio = vehiculo.modelo.precio_venta
            venta = Venta(
                cliente_id=cliente.id,
                estado=EstadoVenta.PAGADA,
                subtotal=precio,
                valor_envio=0,
                total=precio,
            )
            venta.items.append(
                ItemVenta(
                    vehiculo_id=vehiculo.id, cantidad=1, precio_unitario=precio, subtotal=precio
                )
            )
            self.sesion.add(venta)
            self.sesion.flush()
            self.creados["ventas"] += 1
            self._pago_aprobado("SEED-VEN-0001", tarjeta, precio, venta_id=venta.id)
        self.sesion.flush()


def main() -> None:
    config = obtener_configuracion()
    if config.entorno != "desarrollo":
        sys.exit(
            f"Los seeds solo se cargan con ENTORNO=desarrollo (actual: '{config.entorno}'). "
            "Crean usuarios con contraseñas conocidas."
        )

    from app.db import SesionLocal

    with SesionLocal.begin() as sesion:
        creados = CargaDeSemillas(sesion).cargar()

    if not creados:
        print("Nada que cargar: todos los datos de ejemplo ya existían.")
        return
    print("Datos de ejemplo cargados:")
    for tabla, cantidad in sorted(creados.items()):
        print(f"  {tabla:<28} {cantidad:>3} nuevos")
    print(f"\nContraseña de todos los usuarios: {datos.CONTRASENA_DESARROLLO}")


if __name__ == "__main__":
    main()
