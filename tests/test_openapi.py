"""El OpenAPI exportado para el frontend debe coincidir con las rutas (sin base de datos)."""

from scripts.exportar_openapi import ARCHIVO, generar_openapi


def test_openapi_exportado_esta_actualizado() -> None:
    assert ARCHIVO.read_text(encoding="utf-8") == generar_openapi(), (
        "docs/api/openapi.json está desactualizado. Ejecuta: python -m scripts.exportar_openapi"
    )
