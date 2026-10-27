"""Registro de actas de entrega y recepción (HU-11). Pieza de bajo nivel, solo modelos.

La llaman, dentro de su misma transacción, la entrega y la recepción en el local
(alquileres) y la entrega por domicilio (domicilios). Si la operación falla, el acta
tampoco queda. Vive aparte del servicio para no crear imports circulares.
"""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.modulos.inventario.excepciones import BateriaNoAplica
from app.modulos.inventario.modelos import Vehiculo
from app.modulos.reportes.modelos import Acta, TipoActa
from app.modulos.usuarios.modelos import Usuario

SIN_OBSERVACIONES = "Sin observaciones."


@dataclass(frozen=True)
class DatosActa:
    """Lo que anota quien entrega o recibe: el estado de la unidad y su batería."""

    estado_vehiculo: str = SIN_OBSERVACIONES
    nivel_bateria: int | None = None


def registrar_acta(
    sesion: Session,
    tipo: TipoActa,
    vehiculo: Vehiculo,
    usuario: Usuario,
    datos: DatosActa | None = None,
    *,
    alquiler_id: int | None = None,
    venta_id: int | None = None,
    domicilio_id: int | None = None,
) -> Acta:
    """Agrega el acta a la transacción en curso. No hace commit."""
    datos = datos or DatosActa()
    if datos.nivel_bateria is not None and not vehiculo.modelo.tipo.usa_bateria:
        raise BateriaNoAplica(f"La unidad {vehiculo.codigo} no usa batería.")
    acta = Acta(
        tipo=tipo,
        vehiculo_id=vehiculo.id,
        alquiler_id=alquiler_id,
        venta_id=venta_id,
        domicilio_id=domicilio_id,
        estado_vehiculo=datos.estado_vehiculo,
        nivel_bateria=datos.nivel_bateria,
        registrada_por_id=usuario.id,
    )
    sesion.add(acta)
    sesion.flush()
    return acta
