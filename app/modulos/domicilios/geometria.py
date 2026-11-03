"""¿Está un punto dentro de una zona de cobertura? Función propia, sin PostGIS (HU-06).

Decisión del 29/09/2026: las zonas se guardan como GeoJSON en ``jsonb`` y la validación es
una función propia con tests, sin dependencias nuevas.

Formato GeoJSON (RFC 7946): las coordenadas van como ``[longitud, latitud]``. Un
``Polygon`` es una lista de anillos: el primero es el borde exterior y los demás son huecos.
Un ``MultiPolygon`` es una lista de polígonos.

Algoritmo: **trazado de rayos** (*ray casting*). Desde el punto se traza una línea
horizontal hacia la derecha y se cuentan los bordes del anillo que cruza: impar, adentro;
par, afuera. Un punto **sobre el borde** cuenta como adentro (una dirección en el límite
de la zona sí se atiende). Para las distancias de una ciudad, tratar latitud y longitud
como un plano es exacto de sobra.

Estos números son coordenadas, no dinero: aquí ``float`` está bien (CLAUDE.md 7.3 prohíbe
``float`` solo para plata).
"""

from collections.abc import Sequence
from typing import Any

Punto = tuple[float, float]  # (longitud, latitud), en el orden de GeoJSON
Anillo = Sequence[Sequence[float]]

# ~1 cm en grados: dos coordenadas más cercanas que esto se consideran la misma.
_TOLERANCIA = 1e-7


class PoligonoInvalido(ValueError):
    """El GeoJSON no es un Polygon o MultiPolygon bien formado."""


def _sobre_el_segmento(punto: Punto, a: Sequence[float], b: Sequence[float]) -> bool:
    x, y = punto
    (x1, y1), (x2, y2) = a[:2], b[:2]
    producto_cruz = (x - x1) * (y2 - y1) - (y - y1) * (x2 - x1)
    if abs(producto_cruz) > _TOLERANCIA * max(abs(x2 - x1), abs(y2 - y1), 1.0):
        return False  # no es colineal
    return (
        min(x1, x2) - _TOLERANCIA <= x <= max(x1, x2) + _TOLERANCIA
        and min(y1, y2) - _TOLERANCIA <= y <= max(y1, y2) + _TOLERANCIA
    )


def _en_anillo(punto: Punto, anillo: Anillo) -> tuple[bool, bool]:
    """Devuelve ``(adentro, sobre_el_borde)`` respecto a un anillo cerrado o no."""
    x, y = punto
    adentro = False
    n = len(anillo)
    for i in range(n):
        a, b = anillo[i], anillo[(i + 1) % n]
        if _sobre_el_segmento(punto, a, b):
            return True, True
        (x1, y1), (x2, y2) = a[:2], b[:2]
        # ¿El rayo horizontal hacia la derecha cruza el lado a-b?
        if (y1 > y) != (y2 > y):
            x_cruce = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x < x_cruce:
                adentro = not adentro
    return adentro, False


def _en_poligono(punto: Punto, anillos: Sequence[Anillo]) -> bool:
    if not anillos or len(anillos[0]) < 3:
        raise PoligonoInvalido("Un polígono necesita un anillo exterior de al menos 3 puntos.")
    adentro, borde = _en_anillo(punto, anillos[0])
    if not adentro:
        return False
    if borde:
        return True
    for hueco in anillos[1:]:
        en_hueco, borde_hueco = _en_anillo(punto, hueco)
        if en_hueco and not borde_hueco:
            return False  # dentro de un hueco (el borde del hueco sí es de la zona)
    return True


def punto_en_poligono(latitud: float, longitud: float, geojson: dict[str, Any]) -> bool:
    """``True`` si el punto está dentro (o sobre el borde) del Polygon o MultiPolygon."""
    punto = (float(longitud), float(latitud))
    tipo = geojson.get("type") if isinstance(geojson, dict) else None
    coordenadas = geojson.get("coordinates") if tipo else None
    if tipo == "Polygon" and isinstance(coordenadas, list):
        return _en_poligono(punto, coordenadas)
    if tipo == "MultiPolygon" and isinstance(coordenadas, list):
        return any(_en_poligono(punto, poligono) for poligono in coordenadas)
    raise PoligonoInvalido(f"Se esperaba un GeoJSON Polygon o MultiPolygon, no '{tipo}'.")
