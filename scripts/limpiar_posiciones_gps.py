"""Borra las posiciones GPS de más de 7 días (HU-08, decisión 5).

Uso:  python -m scripts.limpiar_posiciones_gps            # deja los últimos 7 días
      python -m scripts.limpiar_posiciones_gps --dias 3   # o los que se indiquen

Con el simulador corriendo, cada vehículo genera ~17.000 posiciones al día: conviene
correrlo a diario (por ejemplo, con el Programador de tareas de Windows). Es seguro
correrlo varias veces.
"""

import argparse

from app.db import SesionLocal
from app.modulos.rastreo.servicio import DIAS_DE_HISTORIAL, limpiar_historial


def main(argumentos: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m scripts.limpiar_posiciones_gps")
    parser.add_argument(
        "--dias",
        type=int,
        default=DIAS_DE_HISTORIAL,
        help=f"Días de historial que se conservan (por defecto, {DIAS_DE_HISTORIAL}).",
    )
    args = parser.parse_args(argumentos)
    if args.dias < 1:
        parser.error("--dias debe ser al menos 1.")
    with SesionLocal() as sesion:
        borradas = limpiar_historial(sesion, dias=args.dias)
    print(f"Posiciones borradas (más de {args.dias} días): {borradas}")


if __name__ == "__main__":
    main()
