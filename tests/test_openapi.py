"""El contrato para el frontend: OpenAPI exportado y guía docs/api/README.md (sin base de datos)."""

import json
import re
from pathlib import Path

import pytest

from app.comun.errores import ErrorDeNegocio
from scripts.exportar_openapi import ARCHIVO, generar_openapi

GUIA = Path(__file__).resolve().parent.parent / "docs" / "api" / "README.md"

# Lo que el Sprint 1 promete al frontend (HU-12, HU-02, HU-09, HU-01).
RUTAS_SPRINT_1 = {
    ("post", "/autenticacion/token"),
    ("post", "/usuarios/registro"),
    ("get", "/usuarios/yo"),
    ("get", "/usuarios"),
    ("post", "/usuarios"),
    ("get", "/usuarios/{usuario_id}"),
    ("patch", "/usuarios/{usuario_id}"),
    ("get", "/catalogo/tipos"),
    ("get", "/catalogo/modelos"),
    ("get", "/catalogo/modelos/{modelo_id}"),
    ("get", "/catalogo/modelos/{modelo_id}/disponibilidad"),
    ("get", "/vehiculos"),
    ("get", "/vehiculos/{vehiculo_id}/novedades"),
    ("post", "/vehiculos/{vehiculo_id}/novedades"),
    ("post", "/vehiculos/{vehiculo_id}/inactivacion"),
    ("post", "/vehiculos/{vehiculo_id}/novedades/{novedad_id}/cierre"),
    ("get", "/portal"),
    ("put", "/portal/secciones/{seccion}"),
    ("put", "/portal/horarios/{dia}"),
    ("delete", "/portal/horarios/{dia}"),
}

# Códigos que no vienen de una clase ErrorDeNegocio sino de los manejadores globales.
CODIGOS_GENERALES = {
    "datos_invalidos",
    "cuerpo_invalido",
    "recurso_no_encontrado",
    "metodo_no_permitido",
    "error_interno",
}


def _operaciones() -> set[tuple[str, str]]:
    rutas = json.loads(generar_openapi())["paths"]
    return {(metodo, ruta) for ruta, ops in rutas.items() for metodo in ops}


def _codigos_de_error() -> set[str]:
    def subclases(clase):
        for sub in clase.__subclasses__():
            yield sub
            yield from subclases(sub)

    import app.main  # noqa: F401  carga todos los módulos y sus errores

    return {c.codigo for c in subclases(ErrorDeNegocio)} | CODIGOS_GENERALES


def test_openapi_exportado_esta_actualizado() -> None:
    assert ARCHIVO.read_text(encoding="utf-8") == generar_openapi(), (
        "docs/api/openapi.json está desactualizado. Ejecuta: python -m scripts.exportar_openapi"
    )


def test_el_contrato_incluye_todas_las_rutas_del_sprint_1() -> None:
    faltantes = RUTAS_SPRINT_1 - _operaciones()
    assert not faltantes, f"Rutas del Sprint 1 que no están en el contrato: {sorted(faltantes)}"


@pytest.mark.parametrize(("metodo", "ruta"), sorted(_operaciones()))
def test_cada_ruta_esta_en_la_guia_del_frontend(metodo: str, ruta: str) -> None:
    fila = f"| `{metodo.upper()}` | `{ruta}` |"
    assert fila in GUIA.read_text(encoding="utf-8"), (
        f"Falta {metodo.upper()} {ruta} en la tabla de endpoints de docs/api/README.md"
    )


def test_cada_codigo_de_error_esta_en_la_guia_del_frontend() -> None:
    documentados = set(re.findall(r"^\| `([a-z_]+)` \|", GUIA.read_text(encoding="utf-8"), re.M))
    faltantes = _codigos_de_error() - documentados
    assert not faltantes, f"Códigos de error sin documentar en docs/api/README.md: {faltantes}"
