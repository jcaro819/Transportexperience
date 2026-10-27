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

# Lo que HU-03 (Sprint 2) promete al frontend.
RUTAS_HU_03 = {
    ("post", "/alquileres"),
    ("get", "/alquileres"),
    ("get", "/alquileres/mios"),
    ("get", "/alquileres/en-riesgo"),
    ("get", "/alquileres/{alquiler_id}"),
    ("post", "/alquileres/{alquiler_id}/pago"),
    ("post", "/alquileres/{alquiler_id}/cancelacion"),
    ("post", "/alquileres/{alquiler_id}/entrega"),
    ("post", "/alquileres/{alquiler_id}/devolucion"),
    ("post", "/alquileres/{alquiler_id}/reasignacion"),
}

# Lo que HU-04 (Sprint 2) promete al frontend.
RUTAS_HU_04 = {
    ("get", "/catalogo/productos"),
    ("post", "/ventas"),
    ("get", "/ventas"),
    ("get", "/ventas/mias"),
    ("get", "/ventas/devoluciones-pendientes"),
    ("get", "/ventas/{venta_id}"),
    ("post", "/ventas/{venta_id}/pago"),
    ("post", "/ventas/{venta_id}/cancelacion"),
    ("get", "/ventas/{venta_id}/comprobante"),
}

# Lo que HU-05 (Sprint 2) promete al frontend.
RUTAS_HU_05 = {
    ("get", "/pagos/configuracion"),
    ("get", "/pagos/pse/bancos"),
    ("get", "/pagos/{referencia}"),
    ("get", "/pagos/{referencia}/comprobante"),
    ("get", "/pagos/devoluciones-pendientes"),
    ("post", "/pagos/{referencia}/devolucion-ejecutada"),
    ("post", "/pagos/webhooks/wompi"),
    ("post", "/alquileres/{alquiler_id}/cancelacion-con-devolucion"),
}

# Lo que HU-06 (Sprint 3) promete al frontend.
RUTAS_HU_06 = {
    ("get", "/domicilios/zonas"),
    ("get", "/domicilios/cobertura"),
    ("post", "/domicilios"),
    ("get", "/domicilios"),
    ("get", "/domicilios/mios"),
    ("get", "/domicilios/asignados"),
    ("get", "/domicilios/domiciliarios-disponibles"),
    ("get", "/domicilios/{domicilio_id}"),
    ("post", "/domicilios/{domicilio_id}/cancelacion"),
    ("post", "/domicilios/{domicilio_id}/asignacion"),
}

# Lo que HU-07 (Sprint 3) promete al frontend.
RUTAS_HU_07 = {
    ("post", "/domicilios/{domicilio_id}/estado"),
    ("post", "/domicilios/{domicilio_id}/cancelacion-por-despacho"),
    ("get", "/domicilios/rastreo/{codigo}"),
}

# Lo que HU-08 (Sprint 3) promete al frontend y a los dispositivos.
RUTAS_HU_08 = {
    ("post", "/rastreo/posiciones"),
    ("get", "/rastreo/flota"),
    ("get", "/rastreo/vehiculos/{vehiculo_id}/recorrido"),
    ("post", "/rastreo/vehiculos/{vehiculo_id}/clave"),
}

# Lo que HU-10 (Sprint 4) promete al frontend.
RUTAS_HU_10 = {
    ("get", "/inventario/resumen"),
    ("get", "/inventario/alertas-stock"),
    ("get", "/inventario/tipos"),
    ("post", "/inventario/tipos"),
    ("patch", "/inventario/tipos/{tipo_id}"),
    ("get", "/inventario/modelos"),
    ("post", "/inventario/modelos"),
    ("patch", "/inventario/modelos/{modelo_id}"),
    ("post", "/inventario/unidades"),
    ("patch", "/inventario/unidades/{vehiculo_id}"),
    ("get", "/inventario/productos"),
    ("post", "/inventario/productos"),
    ("patch", "/inventario/productos/{producto_id}"),
    ("post", "/inventario/productos/{producto_id}/ajustes"),
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


def test_el_contrato_incluye_todas_las_rutas_de_hu_10() -> None:
    faltantes = RUTAS_HU_10 - _operaciones()
    assert not faltantes, f"Rutas de HU-10 que no están en el contrato: {sorted(faltantes)}"


def test_el_contrato_incluye_todas_las_rutas_de_hu_08() -> None:
    faltantes = RUTAS_HU_08 - _operaciones()
    assert not faltantes, f"Rutas de HU-08 que no están en el contrato: {sorted(faltantes)}"


def test_el_contrato_incluye_todas_las_rutas_de_hu_07() -> None:
    faltantes = RUTAS_HU_07 - _operaciones()
    assert not faltantes, f"Rutas de HU-07 que no están en el contrato: {sorted(faltantes)}"


def test_el_contrato_incluye_todas_las_rutas_de_hu_06() -> None:
    faltantes = RUTAS_HU_06 - _operaciones()
    assert not faltantes, f"Rutas de HU-06 que no están en el contrato: {sorted(faltantes)}"


def test_el_contrato_incluye_todas_las_rutas_de_hu_05() -> None:
    faltantes = RUTAS_HU_05 - _operaciones()
    assert not faltantes, f"Rutas de HU-05 que no están en el contrato: {sorted(faltantes)}"


def test_el_contrato_incluye_todas_las_rutas_de_hu_04() -> None:
    faltantes = RUTAS_HU_04 - _operaciones()
    assert not faltantes, f"Rutas de HU-04 que no están en el contrato: {sorted(faltantes)}"


def test_el_contrato_incluye_todas_las_rutas_de_hu_03() -> None:
    faltantes = RUTAS_HU_03 - _operaciones()
    assert not faltantes, f"Rutas de HU-03 que no están en el contrato: {sorted(faltantes)}"


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
