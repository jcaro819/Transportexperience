"""Exporta el contrato de la API a ``docs/api/openapi.json`` (CLAUDE.md sección 9).

Uso:  python -m scripts.exportar_openapi

El test ``tests/test_openapi.py`` falla si alguien cambia una ruta o un esquema y olvida
exportar, para que el frontend nunca trabaje contra un contrato viejo.
"""

import json
from pathlib import Path

from app.main import app

ARCHIVO = Path(__file__).resolve().parent.parent / "docs" / "api" / "openapi.json"


def generar_openapi() -> str:
    return json.dumps(app.openapi(), ensure_ascii=False, indent=2) + "\n"


def main() -> None:
    ARCHIVO.write_text(generar_openapi(), encoding="utf-8", newline="\n")
    print(f"OpenAPI exportado en {ARCHIVO}")


if __name__ == "__main__":
    main()
