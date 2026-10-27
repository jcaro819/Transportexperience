"""Reglas de negocio del rastreo GPS (HU-08, CLAUDE.md sección 8).

Decisiones de HU-08:

1. Las posiciones llegan por HTTP, autenticadas con una **clave propia de cada vehículo**
   (no con el JWT de usuarios). En la base solo queda su hash.
2. El simulador (``python -m simulador_gps``) usa **el mismo endpoint** que un GPS real.
   ``GPS_FUENTE`` decide qué fuente se acepta: cada clave se emite para una fuente.
3. El mapa de la flota es solo para administrador y operador.
4. Un vehículo que no reporta hace más de ``segundos_sin_senal`` (30, en base de datos)
   aparece "sin señal".
5. Se guardan 7 días de historial (``scripts/limpiar_posiciones_gps.py``); la "última
   posición de cada vehículo" usa el índice ``(vehiculo_id, registrado_en DESC)``.
6. El frontend consulta cada 5 segundos (sin WebSocket).
"""

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import case, delete, select, true
from sqlalchemy.orm import Session, aliased, joinedload

from app.auditoria import registrar_auditoria
from app.comun import fechas
from app.comun.errores import PermisoDenegado
from app.comun.paginacion import ParametrosPagina, ResultadoPagina, paginar
from app.modulos.inventario.excepciones import VehiculoNoEncontrado
from app.modulos.inventario.modelos import Vehiculo
from app.modulos.inventario.servicio import bloquear_vehiculo
from app.modulos.rastreo.esquemas import PosicionCrear
from app.modulos.rastreo.excepciones import (
    ClaveGpsInvalida,
    FuenteGpsDesactivada,
    PosicionFueraDeTiempo,
    RangoDeRecorridoInvalido,
)
from app.modulos.rastreo.modelos import FuenteGps, PosicionGps
from app.modulos.usuarios.modelos import Rol, Usuario
from app.parametros import SEGUNDOS_SIN_SENAL, obtener_entero

DIAS_DE_HISTORIAL = 7  # decisión 5 de HU-08
# Tolerancia al reloj del dispositivo: una posición "del futuro" de hasta 1 minuto se acepta.
_TOLERANCIA_RELOJ = timedelta(minutes=1)
_SEIS_DECIMALES = Decimal("0.000001")


@dataclass(frozen=True)
class VehiculoRastreado:
    vehiculo: Vehiculo
    posicion: PosicionGps | None
    senal: str
    segundos_sin_reportar: int | None


# --- Claves de los dispositivos ---------------------------------------------------------------


def hash_clave(clave: str) -> str:
    """SHA-256 en hexadecimal. La clave es aleatoria de 256 bits: no hace falta bcrypt."""
    return hashlib.sha256(clave.encode()).hexdigest()


def emitir_clave(
    sesion: Session,
    vehiculo_id: int,
    administrador: Usuario,
    fuente: FuenteGps,
    *,
    momento: datetime | None = None,
) -> tuple[Vehiculo, str]:
    """Genera una clave nueva para el GPS del vehículo y devuelve la clave en claro.

    Es la única vez que se ve: en la base queda solo su hash. Emitir otra invalida la
    anterior (así se revoca una clave perdida).
    """
    if administrador.rol != Rol.ADMINISTRADOR:
        raise PermisoDenegado()
    vehiculo = bloquear_vehiculo(sesion, vehiculo_id)
    clave = "gps_" + secrets.token_urlsafe(32)
    vehiculo.hash_clave_gps = hash_clave(clave)
    vehiculo.fuente_gps = fuente
    vehiculo.clave_gps_emitida_en = momento or fechas.ahora()
    registrar_auditoria(  # sin la clave ni su hash
        sesion,
        usuario_id=administrador.id,
        accion="emitir_clave_gps",
        entidad="vehiculos",
        entidad_id=vehiculo.id,
        despues={"fuente_gps": fuente.value},
    )
    sesion.commit()
    return vehiculo, clave


def vehiculo_por_clave(sesion: Session, clave: str | None) -> Vehiculo:
    """El vehículo dueño de la clave. Lanza ``ClaveGpsInvalida`` si no corresponde a ninguno."""
    if not clave:
        raise ClaveGpsInvalida()
    # Se busca por el hash (columna única con índice). Un atacante no gana nada midiendo
    # tiempos: tendría que adivinar un hash SHA-256 de una clave aleatoria de 256 bits.
    vehiculo = sesion.scalars(
        select(Vehiculo).where(Vehiculo.hash_clave_gps == hash_clave(clave))
    ).one_or_none()
    if vehiculo is None:
        raise ClaveGpsInvalida()
    return vehiculo


# --- Recepción de posiciones -----------------------------------------------------------------


def _seis_decimales(valor: Decimal) -> Decimal:
    return valor.quantize(_SEIS_DECIMALES, rounding=ROUND_HALF_UP)


def registrar_posicion(
    sesion: Session,
    vehiculo: Vehiculo,
    datos: PosicionCrear,
    fuente_activa: str,
    *,
    momento: datetime | None = None,
) -> PosicionGps:
    """Guarda una posición del vehículo.

    Solo se aceptan posiciones de la fuente activa (``GPS_FUENTE``). No toca la fila del
    vehículo: así un reporte cada 5 s nunca compite con los bloqueos de reservas y ventas.
    """
    if vehiculo.fuente_gps != fuente_activa:
        raise FuenteGpsDesactivada()
    momento = momento or fechas.ahora()
    registrado_en = datos.registrado_en or momento
    if registrado_en > momento + _TOLERANCIA_RELOJ:
        raise PosicionFueraDeTiempo("La hora de la posición está en el futuro.")
    if registrado_en < momento - timedelta(days=DIAS_DE_HISTORIAL):
        raise PosicionFueraDeTiempo("La posición tiene más de 7 días.")
    posicion = PosicionGps(
        vehiculo_id=vehiculo.id,
        latitud=_seis_decimales(datos.latitud),
        longitud=_seis_decimales(datos.longitud),
        precision_metros=datos.precision_metros,
        velocidad_kmh=datos.velocidad_kmh,
        nivel_bateria=datos.nivel_bateria,
        fuente=vehiculo.fuente_gps,
        registrado_en=registrado_en,
        recibido_en=momento,
    )
    sesion.add(posicion)
    sesion.commit()
    return posicion


# --- Mapa de la flota y recorridos -----------------------------------------------------------


def listar_flota(
    sesion: Session,
    parametros: ParametrosPagina,
    *,
    senal: str | None = None,
    momento: datetime | None = None,
) -> ResultadoPagina:
    """Cada vehículo con GPS, su última posición y el estado de la señal.

    La última posición sale de un ``LATERAL ... ORDER BY registrado_en DESC LIMIT 1`` por
    vehículo: con el índice ``(vehiculo_id, registrado_en DESC)`` es una sola lectura de
    índice por vehículo, sin importar cuántas posiciones haya guardadas.
    """
    momento = momento or fechas.ahora()
    umbral = momento - timedelta(seconds=obtener_entero(sesion, SEGUNDOS_SIN_SENAL))
    ultima_sql = (
        select(PosicionGps)
        .where(PosicionGps.vehiculo_id == Vehiculo.id)
        .order_by(PosicionGps.registrado_en.desc())
        .limit(1)
        .lateral("ultima")
    )
    ultima = aliased(PosicionGps, ultima_sql)
    # La señal se mide con la hora de llegada al servidor, no con el reloj del dispositivo.
    estado_senal = case(
        (ultima.id.is_(None), "sin_datos"),
        (ultima.recibido_en >= umbral, "en_linea"),
        else_="sin_senal",
    )
    consulta = (
        select(Vehiculo, ultima, estado_senal)
        .outerjoin(ultima_sql, true())
        .where(Vehiculo.hash_clave_gps.is_not(None))
        .options(joinedload(Vehiculo.modelo))
        .order_by(Vehiculo.codigo)
    )
    if senal is not None:
        consulta = consulta.where(estado_senal == senal)
    pagina = paginar(sesion, consulta, parametros, filas=True)
    elementos = [
        VehiculoRastreado(
            vehiculo,
            posicion,
            estado,
            int((momento - posicion.recibido_en).total_seconds()) if posicion else None,
        )
        for vehiculo, posicion, estado in pagina.elementos
    ]
    return ResultadoPagina(elementos, pagina.total, pagina.pagina, pagina.tamano)


def recorrido(
    sesion: Session,
    vehiculo_id: int,
    parametros: ParametrosPagina,
    *,
    desde: datetime | None = None,
    hasta: datetime | None = None,
    momento: datetime | None = None,
) -> ResultadoPagina:
    """Posiciones del vehículo entre ``desde`` y ``hasta`` (por defecto, la última hora)."""
    momento = momento or fechas.ahora()
    hasta = hasta or momento
    desde = desde or hasta - timedelta(hours=1)
    if desde >= hasta:
        raise RangoDeRecorridoInvalido("`desde` debe ser anterior a `hasta`.")
    if desde < momento - timedelta(days=DIAS_DE_HISTORIAL):
        raise RangoDeRecorridoInvalido("Solo se guardan los últimos 7 días.")
    if sesion.get(Vehiculo, vehiculo_id) is None:
        raise VehiculoNoEncontrado()
    consulta = (
        select(PosicionGps)
        .where(
            PosicionGps.vehiculo_id == vehiculo_id,
            PosicionGps.registrado_en >= desde,
            PosicionGps.registrado_en <= hasta,
        )
        .order_by(PosicionGps.registrado_en)
    )
    return paginar(sesion, consulta, parametros)


def limpiar_historial(
    sesion: Session, *, dias: int = DIAS_DE_HISTORIAL, momento: datetime | None = None
) -> int:
    """Borra las posiciones de más de ``dias`` días. Devuelve cuántas borró."""
    limite = (momento or fechas.ahora()) - timedelta(days=dias)
    resultado = sesion.execute(delete(PosicionGps).where(PosicionGps.registrado_en < limite))
    sesion.commit()
    return resultado.rowcount or 0
