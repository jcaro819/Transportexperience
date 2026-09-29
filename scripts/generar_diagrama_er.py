"""Genera el diagrama entidad-relación (Mermaid) desde los modelos de SQLAlchemy.

Uso:  python -m scripts.generar_diagrama_er

Reescribe solo el bloque entre los marcadores de ``docs/uml/modelo-datos.md``; el texto
explicativo alrededor se edita a mano. El test ``tests/test_diagrama_er.py`` falla si
alguien cambia un modelo y olvida regenerar el diagrama.
"""

import re
from pathlib import Path

from sqlalchemy import Enum, Table
from sqlalchemy.dialects import postgresql

from app import modelos as _modelos  # noqa: F401  registra todas las tablas
from app.db import Base

ARCHIVO = Path(__file__).resolve().parent.parent / "docs" / "uml" / "modelo-datos.md"
INICIO = "<!-- inicio:diagrama (generado por scripts/generar_diagrama_er.py; no editar) -->"
FIN = "<!-- fin:diagrama -->"

_DIALECTO = postgresql.dialect()


def _tipo(columna) -> str:
    """Nombre corto del tipo en Postgres, apto para Mermaid (sin espacios ni comas)."""
    if isinstance(columna.type, Enum):
        return "varchar"
    tipo = columna.type.compile(dialect=_DIALECTO).lower()
    tipo = tipo.replace("timestamp with time zone", "timestamptz")
    tipo = tipo.replace("time without time zone", "time")
    return re.sub(r"\(.*\)", "", tipo)


def _claves(tabla: Table, columna) -> str:
    claves = []
    if columna.primary_key:
        claves.append("PK")
    if columna.foreign_keys:
        claves.append("FK")
    unicas = {c.name for c in tabla.columns if c.unique} | {
        next(iter(r.columns)).name
        for r in tabla.constraints
        if r.__class__.__name__ == "UniqueConstraint" and len(r.columns) == 1
    }
    if columna.name in unicas:
        claves.append("UK")
    return ", ".join(claves)


def _comentario(columna) -> str:
    """Valores permitidos de las columnas de estado."""
    if isinstance(columna.type, Enum):
        return '"' + " | ".join(columna.type.enums) + '"'
    return ""


def generar_mermaid() -> str:
    """Devuelve el bloque Mermaid ``erDiagram`` con todas las tablas y relaciones."""
    lineas = ["```mermaid", "erDiagram"]
    tablas = sorted(Base.metadata.tables.values(), key=lambda t: t.name)

    for tabla in tablas:
        lineas.append(f"    {tabla.name} {{")
        for columna in tabla.columns:
            partes = [_tipo(columna), columna.name, _claves(tabla, columna), _comentario(columna)]
            lineas.append("        " + " ".join(p for p in partes if p))
        lineas.append("    }")

    relaciones = []
    for tabla in tablas:
        for columna in tabla.columns:
            for fk in columna.foreign_keys:
                padre = fk.column.table.name
                # ||--o{ : obligatoria;  |o--o{ : opcional (la FK admite nulo)
                lado_padre = "|o" if columna.nullable else "||"
                relaciones.append(f'    {padre} {lado_padre}--o{{ {tabla.name} : "{columna.name}"')
    lineas.extend(sorted(relaciones))
    lineas.append("```")
    return "\n".join(lineas)


def contenido_actualizado(texto_actual: str) -> str:
    """Reemplaza el bloque entre marcadores por el diagrama recién generado."""
    inicio = texto_actual.index(INICIO) + len(INICIO)
    fin = texto_actual.index(FIN)
    return texto_actual[:inicio] + "\n" + generar_mermaid() + "\n" + texto_actual[fin:]


def main() -> None:
    texto = ARCHIVO.read_text(encoding="utf-8")
    ARCHIVO.write_text(contenido_actualizado(texto), encoding="utf-8", newline="\n")
    print(f"Diagrama actualizado en {ARCHIVO}")


if __name__ == "__main__":
    main()
