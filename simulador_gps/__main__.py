"""Simulador de GPS sobre Bucaramanga (HU-08). Programa aparte de la API.

Uso (con la API corriendo en otra terminal):

    python -m simulador_gps                         # 5 vehículos de la flota
    python -m simulador_gps --vehiculos MON-0001,CIC-0001
    python -m simulador_gps --cantidad 8 --intervalo 5

Requiere ``GPS_FUENTE=simulador`` en el ``.env``: con ``dispositivo``, el simulador no
arranca (y la API rechazaría sus posiciones). Inicia sesión con el administrador de los
seeds de desarrollo; otro se indica con ``SIMULADOR_ADMIN_CORREO`` y
``SIMULADOR_ADMIN_CONTRASENA``.
"""

import argparse
import os
import sys

import httpx

from app.config import obtener_configuracion
from seeds.datos import CONTRASENA_DESARROLLO
from simulador_gps.simulador import ErrorDelSimulador, ResultadoEnvio, Simulador

# Solo existen en bases de desarrollo (seeds). Nunca se usan en otro entorno.
_ADMIN_DE_DESARROLLO = "admin@transportexperience.test"


def _mostrar(resultados: list[ResultadoEnvio]) -> None:
    for r in resultados:
        marca = "ok " if r.estado_http < 400 else f"{r.estado_http}"
        print(f"  [{marca}] {r.codigo}: {r.detalle}")
    print(flush=True)


def main(argumentos: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m simulador_gps", description=__doc__.split("\n")[0]
    )
    parser.add_argument("--api", default="http://127.0.0.1:8000", help="URL de la API.")
    parser.add_argument(
        "--vehiculos", help="Códigos separados por comas (p. ej. MON-0001,CIC-0001)."
    )
    parser.add_argument("--cantidad", type=int, default=5, help="Sin --vehiculos: cuántos tomar.")
    parser.add_argument("--intervalo", type=float, default=5.0, help="Segundos entre posiciones.")
    parser.add_argument("--ciclos", type=int, default=0, help="0: hasta Ctrl+C.")
    args = parser.parse_args(argumentos)

    if obtener_configuracion().gps_fuente != "simulador":
        print("GPS_FUENTE no es 'simulador' en el .env: el simulador no se usa.", file=sys.stderr)
        return 1

    correo = os.environ.get("SIMULADOR_ADMIN_CORREO", _ADMIN_DE_DESARROLLO)
    contrasena = os.environ.get("SIMULADOR_ADMIN_CONTRASENA", CONTRASENA_DESARROLLO)
    codigos = [c.strip() for c in args.vehiculos.split(",")] if args.vehiculos else None
    try:
        with httpx.Client(base_url=args.api, timeout=10) as cliente:
            simulador = Simulador(cliente, intervalo=args.intervalo)
            simulador.iniciar_sesion(correo, contrasena)
            simulador.preparar(codigos, args.cantidad)
            nombres = ", ".join(f"{v.codigo} ({v.recorrido.nombre})" for v in simulador.vehiculos)
            cuantos = len(simulador.vehiculos)
            print(f"Simulando {cuantos} vehículos cada {args.intervalo:g} s: {nombres}")
            print("Detén el simulador con Ctrl+C.\n", flush=True)
            simulador.correr(args.ciclos, _mostrar)
    except ErrorDelSimulador as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    except httpx.ConnectError:
        print(
            f"No hay API en {args.api}. Arráncala con: uvicorn app.main:app --reload",
            file=sys.stderr,
        )
        return 1
    except KeyboardInterrupt:
        print("\nSimulador detenido.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
