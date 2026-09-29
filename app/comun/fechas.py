"""Fecha y hora de negocio: siempre la de Colombia, no la del servidor.

Colombia no tiene horario de verano, así que UTC-5 fijo es exacto y no depende de la base
de zonas horarias del sistema (que Windows no trae).
"""

from datetime import date, datetime, timedelta, timezone

ZONA_COLOMBIA = timezone(timedelta(hours=-5), "America/Bogota")


def ahora() -> datetime:
    """Instante actual en hora de Colombia.

    Postgres guarda el instante absoluto; la zona solo afecta cómo se muestra. Se usa la de
    Colombia para que la API responda siempre ``-05:00``, igual que lo que lee de la base.
    """
    return datetime.now(ZONA_COLOMBIA)


def hoy() -> date:
    """Fecha de hoy en Colombia. A las 8 p. m. en Bucaramanga ya es mañana en UTC."""
    return datetime.now(ZONA_COLOMBIA).date()
