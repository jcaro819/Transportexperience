"""Tiempos de respuesta del catálogo (SRS 3.4.1 y 3.4.2) con un volumen mayor al real.

Se cargan 60 modelos, 1.200 unidades y 3.600 alquileres, y se mide cada consulta del
servicio contra Postgres. Los límites son los del SRS: disponibilidad < 3 s (3.4.1) y
catálogo < 4 s (3.4.2). Se mide el servicio con la base, sin la red.
"""

import time
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import insert

from app.comun.paginacion import ParametrosPagina
from app.modulos.alquileres.modelos import Alquiler, EstadoAlquiler
from app.modulos.inventario import servicio
from app.modulos.inventario.esquemas import FiltrosCatalogo
from app.modulos.inventario.modelos import EstadoVehiculo, ModeloVehiculo, TipoVehiculo, Vehiculo

HOY = date(2026, 10, 1)
MOMENTO = datetime(2026, 10, 1, 15, 0, tzinfo=UTC)
LIMITE_DISPONIBILIDAD_S = 3.0  # SRS 3.4.1
LIMITE_CATALOGO_S = 4.0  # SRS 3.4.2

MODELOS = 60
UNIDADES_POR_MODELO = 20
TARIFA = 40_000


@pytest.fixture
def flota_grande(sesion, fabrica) -> list[int]:
    """Carga masiva en pocas sentencias; devuelve los ids de los modelos."""
    tipos = sesion.scalars(
        insert(TipoVehiculo).returning(TipoVehiculo.id),
        [{"nombre": f"Tipo {i}", "usa_bateria": True} for i in range(3)],
    ).all()
    modelos = sesion.scalars(
        insert(ModeloVehiculo).returning(ModeloVehiculo.id),
        [
            {"tipo_vehiculo_id": tipos[i % 3], "nombre": f"Modelo {i:03d}", "tarifa_diaria": TARIFA}
            for i in range(MODELOS)
        ],
    ).all()
    estados = [EstadoVehiculo.DISPONIBLE] * 7 + [
        EstadoVehiculo.ALQUILADO,
        EstadoVehiculo.MANTENIMIENTO,
        EstadoVehiculo.VENDIDO,
    ]
    vehiculos = sesion.scalars(
        insert(Vehiculo).returning(Vehiculo.id),
        [
            {
                "codigo": f"R-{m:03d}-{u:03d}",
                "modelo_id": modelo_id,
                "estado": estados[u % len(estados)],
            }
            for m, modelo_id in enumerate(modelos)
            for u in range(UNIDADES_POR_MODELO)
        ],
    ).all()

    cliente_id = fabrica.cliente().id
    tramos = [  # (desde, hasta, estado): pasado, presente y futuro, sin solaparse
        (-20, -15, EstadoAlquiler.FINALIZADO),
        (-1, 2, EstadoAlquiler.CONFIRMADO),
        (10, 14, EstadoAlquiler.CONFIRMADO),
    ]
    alquileres = []
    for vehiculo_id in vehiculos:
        for desde, hasta, estado in tramos:
            dias = hasta - desde + 1
            alquileres.append(
                {
                    "cliente_id": cliente_id,
                    "vehiculo_id": vehiculo_id,
                    "fecha_inicio": HOY + timedelta(days=desde),
                    "fecha_fin": HOY + timedelta(days=hasta),
                    "tarifa_diaria": TARIFA,
                    "subtotal": dias * TARIFA,
                    "valor_envio": 0,
                    "total": dias * TARIFA,
                    "estado": estado,
                }
            )
    sesion.execute(insert(Alquiler), alquileres)
    sesion.flush()
    return list(modelos)


def _medir(funcion) -> float:
    inicio = time.perf_counter()
    funcion()
    return time.perf_counter() - inicio


def test_catalogo_responde_dentro_del_limite_del_srs(sesion, flota_grande) -> None:
    def consultar():
        servicio.listar_modelos(
            sesion, ParametrosPagina(), FiltrosCatalogo(), hoy=HOY, momento=MOMENTO
        )

    def consultar_filtrado():
        filtros = FiltrosCatalogo(tarifa_min=10_000, tarifa_max=50_000, solo_disponibles=True)
        servicio.listar_modelos(sesion, ParametrosPagina(), filtros, hoy=HOY, momento=MOMENTO)

    for nombre, funcion in [("sin filtros", consultar), ("con filtros", consultar_filtrado)]:
        segundos = _medir(funcion)
        assert segundos < LIMITE_CATALOGO_S, f"Catálogo {nombre}: {segundos:.2f} s"


def test_disponibilidad_responde_dentro_del_limite_del_srs(sesion, flota_grande) -> None:
    modelo_id = flota_grande[0]

    def detalle():
        servicio.obtener_modelo(sesion, modelo_id, hoy=HOY, momento=MOMENTO)

    def rango():
        servicio.consultar_disponibilidad(
            sesion,
            modelo_id,
            HOY + timedelta(days=5),
            HOY + timedelta(days=12),
            hoy=HOY,
            momento=MOMENTO,
        )

    for nombre, funcion in [("detalle", detalle), ("rango de fechas", rango)]:
        segundos = _medir(funcion)
        assert segundos < LIMITE_DISPONIBILIDAD_S, f"Disponibilidad {nombre}: {segundos:.2f} s"


def test_los_numeros_de_la_flota_grande_son_coherentes(sesion, flota_grande) -> None:
    """Comprueba que la carga masiva sí ejercita la disponibilidad (no es una base vacía)."""
    pagina = servicio.listar_modelos(
        sesion, ParametrosPagina(tamano=100), FiltrosCatalogo(), hoy=HOY, momento=MOMENTO
    )
    assert pagina.total == MODELOS
    # Por modelo: 14 unidades disponibles (7 de cada 10), todas con un alquiler que cubre hoy.
    assert {e.disponibles_hoy for e in pagina.elementos} == {0}

    rango = servicio.consultar_disponibilidad(
        sesion,
        flota_grande[0],
        HOY + timedelta(days=5),
        HOY + timedelta(days=8),
        hoy=HOY,
        momento=MOMENTO,
    )
    # Del día 5 al 8 nada las ocupa: cuentan disponibles y alquiladas (16 de 20).
    assert rango.unidades_libres == 16
