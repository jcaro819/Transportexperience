"""Recorridos por calles de Bucaramanga para el simulador (HU-08).

Cada recorrido es una lista de puntos ``(latitud, longitud)`` que siguen calles y carreras
reales. Son **aproximados** (tomados a ojo sobre el mapa, con unos metros de error): bastan
para que en el mapa se vea a los vehículos moverse por la ciudad. El simulador los recorre
de ida y vuelta.

Recordatorio de Bucaramanga: las carreras van de norte a sur y aumentan hacia el oriente;
las calles van de occidente a oriente y aumentan hacia el sur.
"""

RECORRIDOS: dict[str, list[tuple[float, float]]] = {
    # Del Parque Santander (Cra 19 con Cl 36) hacia Cabecera por la Calle 36 y la Carrera 33.
    "Centro a Cabecera": [
        (7.119300, -73.122700),
        (7.119000, -73.119800),
        (7.118700, -73.116300),
        (7.118400, -73.113000),
        (7.118100, -73.110300),
        (7.115800, -73.110000),
        (7.113400, -73.109700),
        (7.111000, -73.109400),
    ],
    # La Carrera 27 de norte a sur, de la Calle 14 a la Calle 56.
    "Carrera 27": [
        (7.130500, -73.116500),
        (7.126300, -73.116200),
        (7.122000, -73.115900),
        (7.117800, -73.115700),
        (7.113600, -73.115400),
        (7.109400, -73.115100),
        (7.105200, -73.114800),
    ],
    # Vuelta por el Parque San Pío y Sotomayor (Cl 45, Cra 35, Cl 51, Cra 29).
    "San Pío y Sotomayor": [
        (7.114800, -73.112700),
        (7.114500, -73.108300),
        (7.112200, -73.106200),
        (7.109300, -73.106500),
        (7.109600, -73.110900),
        (7.110000, -73.113800),
        (7.112500, -73.114000),
        (7.114800, -73.112700),
    ],
    # La Carrera 33 hacia el sur, hasta la Calle 56 (sector de La Aurora).
    "Carrera 33 al sur": [
        (7.122600, -73.110800),
        (7.118200, -73.110400),
        (7.113800, -73.110000),
        (7.109400, -73.109600),
        (7.105500, -73.109300),
    ],
    # Por la Calle 56 de occidente a oriente, de la Carrera 17 a la Carrera 33.
    "Calle 56": [
        (7.104700, -73.124600),
        (7.105000, -73.120200),
        (7.105200, -73.116000),
        (7.105400, -73.112600),
        (7.105500, -73.109300),
    ],
}
