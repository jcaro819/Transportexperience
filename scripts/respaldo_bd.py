"""Respaldo y restauración de la base de datos (SRS 3.3.2).

Uso (con ``docker compose up -d``):

    python -m scripts.respaldo_bd respaldar                    # crea backups/<base>-<fecha>.dump
    python -m scripts.respaldo_bd respaldar --conservar 10     # y borra los más viejos
    python -m scripts.respaldo_bd restaurar backups/ARCHIVO.dump --base transportexperience_prueba
    python -m scripts.respaldo_bd restaurar backups/ARCHIVO.dump --confirmar   # ¡reemplaza la base!

Usa ``pg_dump`` y ``pg_restore`` **dentro del contenedor** de Postgres (``docker compose
exec``): no hace falta instalar las herramientas de Postgres en el equipo. El respaldo usa
el formato propio de Postgres (``-Fc``): comprimido y restaurable de forma selectiva.

Los respaldos quedan en ``backups/``, que **no se sube a git** (contiene datos personales).
La explicación completa está en el README, sección "Respaldo y restauración".
"""

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy.engine import make_url

RAIZ = Path(__file__).resolve().parent.parent
CARPETA = RAIZ / "backups"
SERVICIO = "postgres"  # el servicio de docker-compose.yml
_NOMBRE_VALIDO = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")


@dataclass(frozen=True)
class Conexion:
    usuario: str
    base: str


def conexion_configurada() -> Conexion:
    """Usuario y base de ``DATABASE_URL`` (la contraseña no hace falta dentro del contenedor)."""
    from app.config import obtener_configuracion

    url = make_url(obtener_configuracion().database_url)
    return Conexion(usuario=url.username, base=url.database)


def _validar_nombre(nombre: str) -> str:
    # Los nombres van a un comando y a un CREATE DATABASE: solo letras, números y guiones bajos.
    if not _NOMBRE_VALIDO.match(nombre):
        raise ValueError(f"Nombre de base no válido: {nombre!r}")
    return nombre


def _exec(*comando: str) -> list[str]:
    return ["docker", "compose", "exec", "-T", SERVICIO, *comando]


def comando_respaldo(conexion: Conexion) -> list[str]:
    base = _validar_nombre(conexion.base)
    return _exec("pg_dump", "-U", conexion.usuario, "-d", base, "-Fc", "--no-owner")


def comando_crear_base(conexion: Conexion, base: str) -> list[str]:
    _validar_nombre(base)
    return _exec("createdb", "-U", conexion.usuario, base)


def comando_restauracion(conexion: Conexion, base: str) -> list[str]:
    _validar_nombre(base)
    return _exec(
        "pg_restore",
        "-U",
        conexion.usuario,
        "-d",
        base,
        "--clean",
        "--if-exists",
        "--no-owner",
        "--exit-on-error",
    )


def nombre_de_respaldo(base: str, momento: datetime) -> str:
    return f"{base}-{momento:%Y-%m-%d_%H%M%S}.dump"


def respaldos_a_borrar(archivos: list[Path], conservar: int) -> list[Path]:
    """Los más viejos, dejando los ``conservar`` más recientes (el nombre lleva la fecha)."""
    ordenados = sorted(archivos, key=lambda a: a.name)
    return ordenados[: max(0, len(ordenados) - conservar)]


def _correr(comando: list[str], **kwargs) -> subprocess.CompletedProcess:
    # Los errores siempre se capturan para mostrarlos; la salida va a un archivo si se pide.
    kwargs.setdefault("stdout", subprocess.PIPE)
    resultado = subprocess.run(comando, cwd=RAIZ, stderr=subprocess.PIPE, **kwargs)
    if resultado.returncode != 0:
        error = resultado.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"Falló: {' '.join(comando[4:])}\n{error}")
    return resultado


def respaldar(conexion: Conexion, carpeta: Path = CARPETA, *, conservar: int | None = None) -> Path:
    """Crea el respaldo y devuelve su ruta. Con ``conservar``, borra los más viejos."""
    carpeta.mkdir(parents=True, exist_ok=True)
    destino = carpeta / nombre_de_respaldo(conexion.base, datetime.now())
    temporal = destino.with_suffix(".parcial")
    with temporal.open("wb") as archivo:
        # Se escribe a un .parcial y se renombra al final: nunca queda un respaldo a medias
        # con apariencia de completo.
        _correr(comando_respaldo(conexion), stdout=archivo)
    temporal.replace(destino)
    if conservar is not None:
        for viejo in respaldos_a_borrar(list(carpeta.glob(f"{conexion.base}-*.dump")), conservar):
            viejo.unlink()
    return destino


def restaurar(conexion: Conexion, archivo: Path, base: str, *, crear: bool) -> None:
    """Restaura ``archivo`` en ``base`` (creándola si ``crear``). Reemplaza lo que haya."""
    if crear:
        _correr(comando_crear_base(conexion, base))
    with archivo.open("rb") as entrada:
        _correr(comando_restauracion(conexion, base), stdin=entrada)


def _existe_base(conexion: Conexion, base: str) -> bool:
    consulta = f"SELECT 1 FROM pg_database WHERE datname = '{_validar_nombre(base)}'"
    resultado = _correr(_exec("psql", "-U", conexion.usuario, "-d", "postgres", "-tAc", consulta))
    return resultado.stdout.strip() == b"1"


def main(argumentos: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.respaldo_bd", description=__doc__.split("\n")[0]
    )
    sub = parser.add_subparsers(dest="accion", required=True)
    p_respaldar = sub.add_parser("respaldar", help="Crear un respaldo en backups/.")
    p_respaldar.add_argument("--conservar", type=int, help="Dejar solo los N más recientes.")
    p_restaurar = sub.add_parser("restaurar", help="Restaurar un respaldo.")
    p_restaurar.add_argument("archivo", type=Path)
    p_restaurar.add_argument(
        "--base", help="Base destino (por defecto, la del .env). Si no existe, se crea."
    )
    p_restaurar.add_argument(
        "--confirmar",
        action="store_true",
        help="Necesario para restaurar sobre la base del .env: reemplaza todos sus datos.",
    )
    args = parser.parse_args(argumentos)
    conexion = conexion_configurada()

    try:
        if args.accion == "respaldar":
            if args.conservar is not None and args.conservar < 1:
                parser.error("--conservar debe ser al menos 1.")
            destino = respaldar(conexion, conservar=args.conservar)
            print(
                f"Respaldo creado: {destino.relative_to(RAIZ)} ({destino.stat().st_size:,} bytes)"
            )
            return 0

        if not args.archivo.is_file():
            parser.error(f"No existe el archivo {args.archivo}.")
        base = _validar_nombre(args.base or conexion.base)
        if base == conexion.base and not args.confirmar:
            print(
                f"Esto REEMPLAZA todos los datos de la base '{base}' (la del .env).\n"
                "Si es lo que quieres, repite el comando con --confirmar. Para probar un\n"
                "respaldo sin tocar nada, restáuralo en otra base con --base.",
                file=sys.stderr,
            )
            return 1
        restaurar(conexion, args.archivo, base, crear=not _existe_base(conexion, base))
        print(f"Restaurado {args.archivo} en la base '{base}'.")
        return 0
    except (RuntimeError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    except FileNotFoundError:
        print("No se encontró el comando 'docker'. ¿Está Docker Desktop abierto?", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
