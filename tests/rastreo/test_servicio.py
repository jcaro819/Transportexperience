"""Servicio de rastreo GPS (HU-08): claves, posiciones, mapa de la flota, recorrido, limpieza.

Contra Postgres, con "ahora" fijo.
"""

import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select, text

from app.comun.errores import PermisoDenegado
from app.comun.paginacion import ParametrosPagina
from app.modulos.rastreo import servicio
from app.modulos.rastreo.esquemas import PosicionCrear
from app.modulos.rastreo.excepciones import (
    ClaveGpsInvalida,
    FuenteGpsDesactivada,
    PosicionFueraDeTiempo,
    RangoDeRecorridoInvalido,
)
from app.modulos.rastreo.modelos import FuenteGps, PosicionGps
from app.modulos.usuarios.modelos import Rol
from app.parametros import SEGUNDOS_SIN_SENAL, ParametroSistema

AHORA = datetime(2026, 11, 2, 15, 0, tzinfo=UTC)
CENTRO = PosicionCrear(latitud=Decimal("7.119300"), longitud=Decimal("-73.122700"))


@pytest.fixture
def administrador(crear_usuario):
    return crear_usuario(Rol.ADMINISTRADOR)


@pytest.fixture
def con_gps(sesion, fabrica, administrador):
    """Un vehículo con clave GPS de simulador. Devuelve (vehículo, clave)."""
    vehiculo = fabrica.vehiculo(codigo="MON-0001")
    return servicio.emitir_clave(
        sesion, vehiculo.id, administrador, FuenteGps.SIMULADOR, momento=AHORA
    )


def _reportar(sesion, vehiculo, datos=CENTRO, *, en=AHORA, fuente="simulador"):
    return servicio.registrar_posicion(sesion, vehiculo, datos, fuente, momento=en)


# --- Claves -------------------------------------------------------------------------------


def test_la_clave_se_entrega_una_vez_y_solo_se_guarda_su_hash(sesion, con_gps) -> None:
    vehiculo, clave = con_gps

    assert clave.startswith("gps_") and len(clave) > 40
    assert vehiculo.hash_clave_gps == servicio.hash_clave(clave)
    assert clave not in vehiculo.hash_clave_gps
    assert servicio.vehiculo_por_clave(sesion, clave).id == vehiculo.id


def test_emitir_otra_clave_invalida_la_anterior(sesion, con_gps, administrador) -> None:
    vehiculo, vieja = con_gps
    _, nueva = servicio.emitir_clave(sesion, vehiculo.id, administrador, FuenteGps.SIMULADOR)

    assert servicio.vehiculo_por_clave(sesion, nueva).id == vehiculo.id
    with pytest.raises(ClaveGpsInvalida):
        servicio.vehiculo_por_clave(sesion, vieja)


@pytest.mark.parametrize("clave", [None, "", "gps_inventada"])
def test_clave_ausente_o_inventada(sesion, con_gps, clave) -> None:
    with pytest.raises(ClaveGpsInvalida):
        servicio.vehiculo_por_clave(sesion, clave)


def test_solo_el_administrador_emite_claves(sesion, fabrica, crear_usuario) -> None:
    with pytest.raises(PermisoDenegado):
        servicio.emitir_clave(
            sesion, fabrica.vehiculo().id, crear_usuario(Rol.OPERADOR), FuenteGps.DISPOSITIVO
        )


# --- Posiciones ---------------------------------------------------------------------------


def test_la_posicion_se_guarda_con_6_decimales(sesion, con_gps) -> None:
    vehiculo, _ = con_gps
    datos = PosicionCrear(
        latitud=Decimal("7.11930049"),  # 8 decimales: se redondea
        longitud=Decimal("-73.1227"),
        precision_metros=Decimal("4.5"),
        velocidad_kmh=Decimal("18"),
        nivel_bateria=80,
    )

    posicion = _reportar(sesion, vehiculo, datos)

    assert posicion.latitud == Decimal("7.119300")
    assert posicion.longitud == Decimal("-73.122700")
    assert posicion.fuente == FuenteGps.SIMULADOR
    assert (posicion.registrado_en, posicion.recibido_en) == (AHORA, AHORA)


def test_solo_se_aceptan_posiciones_de_la_fuente_activa(sesion, con_gps) -> None:
    vehiculo, _ = con_gps
    with pytest.raises(FuenteGpsDesactivada):
        _reportar(sesion, vehiculo, fuente="dispositivo")


@pytest.mark.parametrize(
    "registrado_en",
    [AHORA + timedelta(minutes=2), AHORA - timedelta(days=8)],
    ids=["futuro", "vieja"],
)
def test_posiciones_fuera_de_tiempo(sesion, con_gps, registrado_en) -> None:
    vehiculo, _ = con_gps
    datos = CENTRO.model_copy(update={"registrado_en": registrado_en})
    with pytest.raises(PosicionFueraDeTiempo):
        _reportar(sesion, vehiculo, datos)


def test_reportar_no_bloquea_la_fila_del_vehiculo(sesion, con_gps) -> None:
    # Si registrar_posicion tocara el vehículo, competiría con las reservas cada 5 s.
    vehiculo, _ = con_gps
    actualizado = vehiculo.actualizado_en
    _reportar(sesion, vehiculo)
    sesion.refresh(vehiculo)
    assert vehiculo.actualizado_en == actualizado


# --- Mapa de la flota (decisiones 3 y 4) --------------------------------------------------


def test_la_flota_muestra_la_ultima_posicion_y_la_senal(
    sesion, fabrica, con_gps, administrador
) -> None:
    en_linea, _ = con_gps
    callado = fabrica.vehiculo(codigo="MON-0002")
    nuevo = fabrica.vehiculo(codigo="MON-0003")
    fabrica.vehiculo(codigo="MON-0004")  # sin clave GPS: no aparece
    for v in (callado, nuevo):
        servicio.emitir_clave(sesion, v.id, administrador, FuenteGps.SIMULADOR)
    lejos = CENTRO.model_copy(update={"latitud": Decimal("7.100000")})
    _reportar(sesion, en_linea, lejos, en=AHORA - timedelta(seconds=10))
    _reportar(sesion, en_linea, en=AHORA - timedelta(seconds=5))  # la última
    _reportar(sesion, callado, en=AHORA - timedelta(seconds=31))

    flota = servicio.listar_flota(sesion, ParametrosPagina(), momento=AHORA)

    por_codigo = {r.vehiculo.codigo: r for r in flota.elementos}
    assert set(por_codigo) == {"MON-0001", "MON-0002", "MON-0003"}
    assert por_codigo["MON-0001"].senal == "en_linea"
    assert por_codigo["MON-0001"].posicion.latitud == Decimal("7.119300")
    assert por_codigo["MON-0001"].segundos_sin_reportar == 5
    assert por_codigo["MON-0002"].senal == "sin_senal"
    assert por_codigo["MON-0003"].senal == "sin_datos"
    assert por_codigo["MON-0003"].posicion is None


def test_el_umbral_de_sin_senal_se_lee_de_la_base(sesion, con_gps) -> None:
    vehiculo, _ = con_gps
    _reportar(sesion, vehiculo, en=AHORA - timedelta(seconds=20))
    sesion.get(ParametroSistema, SEGUNDOS_SIN_SENAL).valor = 10
    sesion.flush()

    [rastreado] = servicio.listar_flota(sesion, ParametrosPagina(), momento=AHORA).elementos

    assert rastreado.senal == "sin_senal"


def test_filtro_por_senal(sesion, fabrica, con_gps, administrador) -> None:
    servicio.emitir_clave(sesion, fabrica.vehiculo().id, administrador, FuenteGps.SIMULADOR)
    _reportar(sesion, con_gps[0])
    sin_datos = servicio.listar_flota(sesion, ParametrosPagina(), senal="sin_datos", momento=AHORA)
    assert sin_datos.total == 1


# --- Recorrido y limpieza (decisión 5) ----------------------------------------------------


def test_recorrido_en_orden_y_dentro_del_rango(sesion, con_gps) -> None:
    vehiculo, _ = con_gps
    for minutos in (90, 50, 30, 10):
        _reportar(sesion, vehiculo, en=AHORA - timedelta(minutes=minutos))

    ultima_hora = servicio.recorrido(sesion, vehiculo.id, ParametrosPagina(), momento=AHORA)

    horas = [p.registrado_en for p in ultima_hora.elementos]
    assert horas == sorted(horas) and len(horas) == 3


def test_recorrido_con_rango_invalido(sesion, con_gps) -> None:
    vehiculo, _ = con_gps
    with pytest.raises(RangoDeRecorridoInvalido):
        servicio.recorrido(
            sesion, vehiculo.id, ParametrosPagina(), desde=AHORA, hasta=AHORA, momento=AHORA
        )
    with pytest.raises(RangoDeRecorridoInvalido, match="7 días"):
        servicio.recorrido(
            sesion, vehiculo.id, ParametrosPagina(), desde=AHORA - timedelta(days=8), momento=AHORA
        )


def test_la_limpieza_borra_solo_lo_de_mas_de_7_dias(sesion, con_gps) -> None:
    vehiculo, _ = con_gps
    for dias in (10, 8, 6, 0):
        sesion.add(
            PosicionGps(
                vehiculo_id=vehiculo.id,
                latitud=Decimal("7.1193"),
                longitud=Decimal("-73.1227"),
                fuente=FuenteGps.SIMULADOR,
                registrado_en=AHORA - timedelta(days=dias),
            )
        )
    sesion.flush()

    borradas = servicio.limpiar_historial(sesion, momento=AHORA)

    assert borradas == 2
    assert sesion.scalar(select(func.count()).select_from(PosicionGps)) == 2


# --- Rendimiento: la última posición de cada vehículo (decisión 5) -------------------------


def test_la_ultima_posicion_de_la_flota_es_rapida_con_mucho_historial(
    sesion, fabrica, administrador
) -> None:
    # 20 vehículos con un día entero de posiciones cada 5 s: 345.600 filas.
    vehiculos = [fabrica.vehiculo() for _ in range(20)]
    for vehiculo in vehiculos:
        servicio.emitir_clave(sesion, vehiculo.id, administrador, FuenteGps.SIMULADOR)
    sesion.execute(
        text(
            """
            INSERT INTO posiciones_gps (vehiculo_id, latitud, longitud, fuente, registrado_en)
            SELECT v, 7.1193, -73.1227, 'simulador', :ahora - (s * interval '5 seconds')
            FROM unnest(CAST(:ids AS integer[])) AS v, generate_series(1, 17280) AS s
            """
        ),
        {"ids": [v.id for v in vehiculos], "ahora": AHORA},
    )
    sesion.execute(text("ANALYZE posiciones_gps"))

    inicio = time.perf_counter()
    flota = servicio.listar_flota(sesion, ParametrosPagina(tamano=100), momento=AHORA)
    duracion = time.perf_counter() - inicio

    assert flota.total == 20
    assert all(r.segundos_sin_reportar is not None for r in flota.elementos)
    assert duracion < 0.5, f"La flota tardó {duracion:.2f} s (se consulta cada 5 s)"
