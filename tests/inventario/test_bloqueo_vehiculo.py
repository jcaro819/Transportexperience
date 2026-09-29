"""El servicio bloquea la fila del vehículo mientras opera (CLAUDE.md 7.1, regla 1).

Aquí sí hacen falta dos conexiones reales y datos confirmados, porque se prueba lo que ve
una transacción mientras otra tiene la fila bloqueada. Los datos se borran al final.
"""

import pytest
from sqlalchemy import delete, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.db import motor
from app.modulos.inventario.modelos import ModeloVehiculo, TipoVehiculo, Vehiculo
from app.modulos.inventario.servicio import bloquear_vehiculo

_BLOQUEO_SIN_ESPERA = text("SELECT id FROM vehiculos WHERE id = :id FOR UPDATE NOWAIT")


@pytest.fixture
def vehiculo_confirmado(base_datos_pruebas) -> int:
    with Session(motor) as sesion:
        tipo = TipoVehiculo(nombre="Tipo prueba de bloqueo", usa_bateria=True)
        modelo = ModeloVehiculo(tipo=tipo, nombre="Modelo prueba de bloqueo", tarifa_diaria=1_000)
        vehiculo = Vehiculo(codigo="BLOQ-0001", modelo=modelo)
        sesion.add(vehiculo)
        sesion.commit()
        ids = (vehiculo.id, modelo.id, tipo.id)
    yield ids[0]
    with Session(motor) as sesion:
        sesion.execute(delete(Vehiculo).where(Vehiculo.id == ids[0]))
        sesion.execute(delete(ModeloVehiculo).where(ModeloVehiculo.id == ids[1]))
        sesion.execute(delete(TipoVehiculo).where(TipoVehiculo.id == ids[2]))
        sesion.commit()


def test_mientras_una_operacion_tiene_la_unidad_nadie_mas_puede_tomarla(
    vehiculo_confirmado: int,
) -> None:
    with Session(motor) as primera, motor.connect() as segunda:
        bloquear_vehiculo(primera, vehiculo_confirmado)  # transacción abierta, sin commit

        with pytest.raises(OperationalError, match="could not obtain lock"):
            segunda.execute(_BLOQUEO_SIN_ESPERA, {"id": vehiculo_confirmado})
        segunda.rollback()

        primera.rollback()  # termina la primera operación
        assert segunda.execute(_BLOQUEO_SIN_ESPERA, {"id": vehiculo_confirmado}).scalar()
        segunda.rollback()
