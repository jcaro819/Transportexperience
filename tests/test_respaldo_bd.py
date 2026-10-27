"""Respaldo y restauración de la base (SRS 3.3.2).

Las piezas puras se prueban sin Docker. El test de ida y vuelta sí usa el contenedor:
respalda la base de pruebas, la restaura en una base nueva, compara y la borra.
"""

import shutil
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from scripts import respaldo_bd
from scripts.respaldo_bd import Conexion

CONEXION = Conexion(usuario="transport", base="transportexperience")


def test_nombre_del_respaldo_lleva_la_base_y_la_fecha() -> None:
    nombre = respaldo_bd.nombre_de_respaldo("transportexperience", datetime(2026, 11, 2, 7, 5, 9))
    assert nombre == "transportexperience-2026-11-02_070509.dump"


def test_el_respaldo_corre_pg_dump_dentro_del_contenedor() -> None:
    comando = respaldo_bd.comando_respaldo(CONEXION)
    assert comando[:5] == ["docker", "compose", "exec", "-T", "postgres"]
    assert comando[5:] == [
        "pg_dump",
        "-U",
        "transport",
        "-d",
        "transportexperience",
        "-Fc",
        "--no-owner",
    ]


def test_la_restauracion_reemplaza_y_se_detiene_ante_el_primer_error() -> None:
    comando = respaldo_bd.comando_restauracion(CONEXION, "otra_base")
    assert {"--clean", "--if-exists", "--exit-on-error"} <= set(comando)
    assert comando[comando.index("-d") + 1] == "otra_base"


@pytest.mark.parametrize(
    "nombre", ["base; DROP DATABASE x", "con espacio", "1empieza_con_numero", ""]
)
def test_nombres_de_base_peligrosos_se_rechazan(nombre) -> None:
    with pytest.raises(ValueError):
        respaldo_bd.comando_restauracion(CONEXION, nombre)


def test_conservar_borra_solo_los_mas_viejos() -> None:
    archivos = [Path(f"transportexperience-2026-11-0{d}_000000.dump") for d in (3, 1, 4, 2)]
    borrar = respaldo_bd.respaldos_a_borrar(archivos, conservar=2)
    assert [a.name for a in borrar] == [
        "transportexperience-2026-11-01_000000.dump",
        "transportexperience-2026-11-02_000000.dump",
    ]
    assert respaldo_bd.respaldos_a_borrar(archivos, conservar=10) == []


def test_restaurar_sobre_la_base_del_env_exige_confirmar(tmp_path, monkeypatch) -> None:
    archivo = tmp_path / "x.dump"
    archivo.write_bytes(b"no importa")
    monkeypatch.setattr(respaldo_bd, "conexion_configurada", lambda: CONEXION)
    llamado = []
    monkeypatch.setattr(respaldo_bd, "restaurar", lambda *a, **k: llamado.append(a))

    assert respaldo_bd.main(["restaurar", str(archivo)]) == 1
    assert llamado == []  # no tocó nada


# --- Ida y vuelta real con el contenedor -----------------------------------------------------


@pytest.mark.skipif(shutil.which("docker") is None, reason="Necesita Docker")
def test_respaldar_y_restaurar_en_otra_base_conserva_los_datos(
    base_datos_pruebas, tmp_path
) -> None:
    conexion = Conexion(usuario=base_datos_pruebas.username, base=base_datos_pruebas.database)
    copia = "transportexperience_restauracion_pruebas"
    mantenimiento = create_engine(
        base_datos_pruebas.set(database="postgres"), isolation_level="AUTOCOMMIT"
    )

    def _borrar_copia() -> None:
        with mantenimiento.connect() as cx:
            cx.execute(text(f'DROP DATABASE IF EXISTS "{copia}" WITH (FORCE)'))

    def _huella(base: str) -> tuple:
        motor = create_engine(base_datos_pruebas.set(database=base))
        try:
            with motor.connect() as cx:
                return (
                    cx.execute(text("SELECT version_num FROM alembic_version")).scalar(),
                    cx.execute(
                        text(
                            "SELECT count(*) FROM information_schema.tables "
                            "WHERE table_schema = 'public'"
                        )
                    ).scalar(),
                    tuple(
                        cx.execute(
                            text("SELECT clave, valor FROM parametros_sistema ORDER BY clave")
                        ).all()
                    ),
                )
        finally:
            motor.dispose()

    _borrar_copia()
    try:
        archivo = respaldo_bd.respaldar(conexion, tmp_path)
        assert archivo.stat().st_size > 0
        assert not list(tmp_path.glob("*.parcial"))

        respaldo_bd.restaurar(conexion, archivo, copia, crear=True)

        assert _huella(copia) == _huella(conexion.base)
        assert _huella(copia)[2]  # los parámetros del sistema viajaron
    finally:
        _borrar_copia()
        mantenimiento.dispose()
