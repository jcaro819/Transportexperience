"""El diagrama ER de docs/uml debe coincidir con los modelos (no necesita base de datos)."""

from scripts.generar_diagrama_er import ARCHIVO, contenido_actualizado


def test_diagrama_er_esta_actualizado() -> None:
    texto = ARCHIVO.read_text(encoding="utf-8")
    assert texto == contenido_actualizado(texto), (
        "El diagrama está desactualizado. Ejecuta: python -m scripts.generar_diagrama_er"
    )
