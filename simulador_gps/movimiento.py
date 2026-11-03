"""Cómo se mueve un vehículo simulado (HU-08). Lógica pura, sin red ni base de datos.

Un ``Recorrido`` es una línea de puntos por calles reales. Un ``VehiculoSimulado`` avanza
sobre él a una velocidad realista para su tipo (una cicla urbana va a 12-18 km/h), con
pequeñas variaciones, paradas ocasionales (semáforos) y el error típico de un GPS de
3-8 m. Al llegar al final, se devuelve (ida y vuelta).

Las coordenadas son ``float`` a propósito: son geometría, no dinero.
"""

import math
import random
from dataclasses import dataclass, field

RADIO_TIERRA_M = 6_371_000

# Velocidades de crucero (km/h) según una palabra del nombre del modelo, en este orden:
# "monopatín" va antes que "patín" porque lo contiene. Si no hay coincidencia, monopatín.
VELOCIDADES_KMH = (
    ("monopatín", (15.0, 25.0)),
    ("patín", (8.0, 12.0)),
    ("cicla", (12.0, 18.0)),
)
_VELOCIDAD_POR_DEFECTO = (15.0, 25.0)
_PROBABILIDAD_DE_PARADA = 0.08  # por intervalo: un semáforo, un cruce
_METROS_POR_GRADO = math.pi * RADIO_TIERRA_M / 180


def rango_de_velocidad(descripcion: str) -> tuple[float, float]:
    """Rango de velocidad (km/h) para un modelo, p. ej. "Cicla urbana 7 cambios" → cicla."""
    texto = descripcion.lower()
    for palabra, rango in VELOCIDADES_KMH:
        if palabra in texto:
            return rango
    return _VELOCIDAD_POR_DEFECTO


def distancia_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Distancia en metros entre dos puntos (latitud, longitud), con la fórmula de haversine."""
    lat1, lng1, lat2, lng2 = map(math.radians, (*a, *b))
    h = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lng2 - lng1) / 2) ** 2
    )
    return 2 * RADIO_TIERRA_M * math.asin(math.sqrt(h))


class Recorrido:
    """Una línea de puntos que se recorre de ida y vuelta."""

    def __init__(self, nombre: str, puntos: list[tuple[float, float]]) -> None:
        if len(puntos) < 2:
            raise ValueError("Un recorrido necesita al menos dos puntos.")
        self.nombre = nombre
        self.puntos = puntos
        self.tramos = [distancia_m(a, b) for a, b in zip(puntos, puntos[1:], strict=False)]
        self.longitud_m = sum(self.tramos)

    def posicion(self, distancia: float) -> tuple[float, float]:
        """El punto a ``distancia`` metros del inicio, yendo y volviendo sin fin."""
        vuelta = distancia % (2 * self.longitud_m)
        if vuelta > self.longitud_m:  # de regreso
            vuelta = 2 * self.longitud_m - vuelta
        pares = zip(self.puntos, self.puntos[1:], strict=False)
        for (a, b), tramo in zip(pares, self.tramos, strict=True):
            if tramo > 0 and vuelta <= tramo:
                f = vuelta / tramo
                return (a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f)
            vuelta -= tramo
        return self.puntos[-1]


@dataclass
class VehiculoSimulado:
    codigo: str
    clave: str
    recorrido: Recorrido
    descripcion: str = "Monopatín eléctrico"  # nombre del modelo: decide la velocidad
    usa_bateria: bool = True
    distancia_m: float = 0.0
    bateria: float = 100.0
    azar: random.Random = field(default_factory=random.Random)

    def __post_init__(self) -> None:
        minima, maxima = rango_de_velocidad(self.descripcion)
        self.velocidad_crucero = self.azar.uniform(minima, maxima)

    def avanzar(self, segundos: float) -> dict:
        """Mueve el vehículo ``segundos`` y devuelve la posición a reportar (cuerpo del POST)."""
        if self.azar.random() < _PROBABILIDAD_DE_PARADA:
            velocidad = 0.0
        else:
            velocidad = max(0.0, self.velocidad_crucero * self.azar.uniform(0.8, 1.15))
        self.distancia_m += velocidad / 3.6 * segundos
        latitud, longitud = self.recorrido.posicion(self.distancia_m)

        precision = self.azar.uniform(3.0, 8.0)  # HU-08: < 10 m
        # Error del GPS: un desplazamiento aleatorio dentro de la precisión reportada.
        angulo = self.azar.uniform(0, 2 * math.pi)
        error = self.azar.uniform(0, precision) / _METROS_POR_GRADO
        latitud += error * math.sin(angulo)
        longitud += error * math.cos(angulo) / math.cos(math.radians(latitud))

        cuerpo = {
            "latitud": f"{latitud:.6f}",
            "longitud": f"{longitud:.6f}",
            "precision_metros": f"{precision:.2f}",
            "velocidad_kmh": f"{velocidad:.2f}",
        }
        if self.usa_bateria:
            # ~1 % cada 2 km; nunca baja de 5 % para que la demo no se quede sin batería.
            self.bateria = max(5.0, self.bateria - velocidad / 3.6 * segundos / 2000)
            cuerpo["nivel_bateria"] = round(self.bateria)
        return cuerpo
