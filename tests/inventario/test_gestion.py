"""Gestión del inventario por el administrador (HU-10): crear, editar, ajustar stock, alertas.

Contra Postgres. Cada cambio debe quedar en auditoría (SRS 3.5.4).
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.auditoria import RegistroAuditoria
from app.comun.errores import PermisoDenegado
from app.comun.paginacion import ParametrosPagina
from app.modulos.alquileres import servicio as alquileres
from app.modulos.inventario import gestion
from app.modulos.inventario import servicio as catalogo
from app.modulos.inventario.esquemas import FiltrosCatalogo
from app.modulos.inventario.esquemas_gestion import (
    AjusteStock,
    ModeloActualizar,
    ModeloCrear,
    ProductoActualizar,
    ProductoCrear,
    TipoVehiculoActualizar,
    TipoVehiculoCrear,
    UnidadActualizar,
    UnidadCrear,
)
from app.modulos.inventario.excepciones import (
    AjusteDeStockInvalido,
    BateriaNoAplica,
    CodigoDuplicado,
    ModeloSinPrecio,
    NombreDuplicado,
    TipoNoEncontrado,
    VehiculoVendido,
)
from app.modulos.inventario.modelos import CategoriaProducto, EstadoVehiculo
from app.modulos.usuarios.modelos import Rol

MOMENTO = datetime(2026, 11, 2, 15, 0, tzinfo=UTC)


@pytest.fixture
def admin(crear_usuario):
    return crear_usuario(Rol.ADMINISTRADOR)


@pytest.fixture
def operador(crear_usuario):
    return crear_usuario(Rol.OPERADOR)


def _auditoria(sesion, entidad: str, entidad_id: int) -> list[RegistroAuditoria]:
    return list(
        sesion.scalars(
            select(RegistroAuditoria)
            .where(
                RegistroAuditoria.entidad == entidad,
                RegistroAuditoria.entidad_id == str(entidad_id),
            )
            .order_by(RegistroAuditoria.id)
        )
    )


# --- Tipos ----------------------------------------------------------------------------------


def test_crear_y_editar_un_tipo_queda_auditado(sesion, admin) -> None:
    tipo = gestion.crear_tipo(sesion, TipoVehiculoCrear(nombre="Scooter", usa_bateria=True), admin)
    gestion.actualizar_tipo(sesion, tipo.id, TipoVehiculoActualizar(activo=False), admin)

    assert tipo.activo is False
    crear, editar = _auditoria(sesion, "tipos_vehiculo", tipo.id)
    assert (crear.accion, crear.usuario_id) == ("crear", admin.id)
    assert (editar.datos_anteriores, editar.datos_nuevos) == ({"activo": True}, {"activo": False})


def test_el_nombre_del_tipo_es_unico_sin_importar_mayusculas(sesion, admin) -> None:
    gestion.crear_tipo(sesion, TipoVehiculoCrear(nombre="Scooter", usa_bateria=True), admin)
    with pytest.raises(NombreDuplicado):
        gestion.crear_tipo(sesion, TipoVehiculoCrear(nombre="scooter", usa_bateria=False), admin)


def test_desactivar_un_tipo_lo_saca_del_catalogo(sesion, fabrica, admin) -> None:
    tipo = fabrica.tipo()
    modelo = fabrica.modelo(tipo)
    fabrica.vehiculo(modelo)

    gestion.actualizar_tipo(sesion, tipo.id, TipoVehiculoActualizar(activo=False), admin)

    pagina = catalogo.listar_modelos(sesion, ParametrosPagina(), FiltrosCatalogo())
    assert modelo.id not in [e.modelo.id for e in pagina.elementos]


def test_editar_sin_cambios_no_audita(sesion, fabrica, admin) -> None:
    tipo = fabrica.tipo("Cicla")
    gestion.actualizar_tipo(sesion, tipo.id, TipoVehiculoActualizar(nombre="Cicla"), admin)
    assert _auditoria(sesion, "tipos_vehiculo", tipo.id) == []


def test_null_en_un_campo_obligatorio_es_invalido() -> None:
    with pytest.raises(ValueError, match="no puede ser null"):
        TipoVehiculoActualizar(nombre=None)


# --- Modelos --------------------------------------------------------------------------------


def test_crear_un_modelo_lo_publica_en_el_catalogo(sesion, fabrica, admin) -> None:
    tipo = fabrica.tipo()
    modelo = gestion.crear_modelo(
        sesion,
        ModeloCrear(tipo_vehiculo_id=tipo.id, nombre="Urbano 500", tarifa_diaria=45_000),
        admin,
    )
    pagina = catalogo.listar_modelos(sesion, ParametrosPagina(), FiltrosCatalogo())
    assert modelo.id in [e.modelo.id for e in pagina.elementos]


def test_un_modelo_sin_tarifa_ni_precio_es_invalido() -> None:
    with pytest.raises(ValueError, match="tarifa diaria, precio de venta"):
        ModeloCrear(tipo_vehiculo_id=1, nombre="Sin precio")


def test_no_se_le_quitan_los_dos_precios(sesion, fabrica, admin) -> None:
    modelo = fabrica.modelo(tarifa_diaria=40_000, precio_venta=None)
    with pytest.raises(ModeloSinPrecio):
        gestion.actualizar_modelo(sesion, modelo.id, ModeloActualizar(tarifa_diaria=None), admin)


def test_cambiar_la_tarifa_queda_auditado_y_no_cambia_alquileres_hechos(
    sesion, fabrica, admin
) -> None:
    modelo = fabrica.modelo(tarifa_diaria=40_000)
    fabrica.vehiculo(modelo)
    cliente = fabrica.cliente()
    hoy = MOMENTO.date()
    alquiler = alquileres.crear_alquiler(
        sesion, cliente, modelo.id, hoy, hoy + timedelta(days=1), hoy=hoy, momento=MOMENTO
    )

    gestion.actualizar_modelo(sesion, modelo.id, ModeloActualizar(tarifa_diaria=55_000), admin)

    assert modelo.tarifa_diaria == 55_000
    assert (alquiler.tarifa_diaria, alquiler.total) == (40_000, 80_000)
    [registro] = _auditoria(sesion, "modelos_vehiculo", modelo.id)
    assert registro.datos_anteriores == {"tarifa_diaria": 40_000}
    assert registro.datos_nuevos == {"tarifa_diaria": 55_000}


def test_modelo_con_un_tipo_inexistente(sesion, admin) -> None:
    with pytest.raises(TipoNoEncontrado):
        gestion.crear_modelo(
            sesion, ModeloCrear(tipo_vehiculo_id=999_999, nombre="Modelo X", tarifa_diaria=1), admin
        )


# --- Unidades -------------------------------------------------------------------------------


def test_registrar_una_unidad_la_deja_disponible_hoy(sesion, fabrica, admin) -> None:
    modelo = fabrica.modelo()

    unidad = gestion.crear_unidad(
        sesion, UnidadCrear(codigo="mon-0100", modelo_id=modelo.id, nivel_bateria=95), admin
    )

    assert unidad.codigo == "MON-0100"  # se guarda en mayúsculas
    assert unidad.estado == EstadoVehiculo.DISPONIBLE
    detalle = catalogo.obtener_modelo(sesion, modelo.id)
    assert [u.codigo for u in detalle.unidades] == ["MON-0100"]


def test_el_codigo_de_la_unidad_es_unico(sesion, fabrica, admin) -> None:
    modelo = fabrica.modelo()
    fabrica.vehiculo(modelo, codigo="MON-0100")
    with pytest.raises(CodigoDuplicado):
        gestion.crear_unidad(sesion, UnidadCrear(codigo="MON-0100", modelo_id=modelo.id), admin)


def test_una_cicla_no_tiene_bateria(sesion, fabrica, admin) -> None:
    cicla = fabrica.modelo(fabrica.tipo("Cicla urbana", usa_bateria=False))
    with pytest.raises(BateriaNoAplica):
        gestion.crear_unidad(
            sesion, UnidadCrear(codigo="CIC-0100", modelo_id=cicla.id, nivel_bateria=50), admin
        )


def test_editar_una_unidad_queda_auditado(sesion, fabrica, admin) -> None:
    unidad = fabrica.vehiculo(ubicacion="Bodega")
    gestion.actualizar_unidad(
        sesion, unidad.id, UnidadActualizar(ubicacion="Sede Cabecera", nivel_bateria=40), admin
    )
    [registro] = _auditoria(sesion, "vehiculos", unidad.id)
    assert registro.datos_nuevos == {"ubicacion": "Sede Cabecera", "nivel_bateria": 40}


def test_una_unidad_vendida_no_se_edita(sesion, fabrica, admin) -> None:
    vendida = fabrica.vehiculo(estado=EstadoVehiculo.VENDIDO)
    with pytest.raises(VehiculoVendido):
        gestion.actualizar_unidad(sesion, vendida.id, UnidadActualizar(ubicacion="X"), admin)


# --- Productos y stock ----------------------------------------------------------------------


def _producto(sesion, admin, **datos):
    base = {
        "codigo": "ACC-CASCO-X",
        "nombre": "Casco X",
        "categoria": CategoriaProducto.ACCESORIO,
        "precio_venta": 120_000,
        "stock": 10,
        "stock_minimo": 3,
    }
    return gestion.crear_producto(sesion, ProductoCrear(**(base | datos)), admin)


def test_crear_y_editar_un_producto(sesion, admin) -> None:
    producto = _producto(sesion, admin)
    gestion.actualizar_producto(
        sesion, producto.id, ProductoActualizar(precio_venta=130_000), admin
    )

    assert producto.precio_venta == 130_000
    crear, editar = _auditoria(sesion, "productos", producto.id)
    assert crear.datos_nuevos["stock"] == 10
    assert editar.datos_nuevos == {"precio_venta": 130_000}


def test_el_codigo_del_producto_es_unico(sesion, admin) -> None:
    _producto(sesion, admin)
    with pytest.raises(CodigoDuplicado):
        _producto(sesion, admin, nombre="Otro casco")


def test_el_stock_no_se_edita_directo() -> None:
    assert "stock" not in ProductoActualizar.model_fields


def test_ajuste_de_stock_suma_y_resta_con_su_motivo(sesion, admin) -> None:
    producto = _producto(sesion, admin)

    gestion.ajustar_stock(
        sesion, producto.id, AjusteStock(cantidad=5, motivo="Llegó el pedido."), admin
    )
    gestion.ajustar_stock(
        sesion, producto.id, AjusteStock(cantidad=-2, motivo="Dos dañados."), admin
    )

    assert producto.stock == 13
    ajustes = [
        r for r in _auditoria(sesion, "productos", producto.id) if r.accion == "ajustar_stock"
    ]
    assert [(r.datos_anteriores["stock"], r.datos_nuevos["stock"]) for r in ajustes] == [
        (10, 15),
        (15, 13),
    ]
    assert ajustes[1].datos_nuevos["motivo"] == "Dos dañados."


def test_el_ajuste_no_deja_el_stock_en_negativo(sesion, admin) -> None:
    producto = _producto(sesion, admin, stock=2)
    with pytest.raises(AjusteDeStockInvalido, match="Hay 2"):
        gestion.ajustar_stock(
            sesion, producto.id, AjusteStock(cantidad=-3, motivo="Pérdida."), admin
        )
    assert producto.stock == 2


def test_un_ajuste_de_cero_es_invalido() -> None:
    with pytest.raises(ValueError, match="no puede ser 0"):
        AjusteStock(cantidad=0, motivo="Nada que hacer.")


# --- Alertas de bajo stock y resumen ----------------------------------------------------------


def test_alertas_de_bajo_stock_mas_urgente_primero(sesion, fabrica, operador) -> None:
    fabrica.producto(nombre="Sobra", stock=10)  # stock_minimo 0: no alerta
    justo = fabrica.producto(nombre="Justo", stock=3)
    agotado = fabrica.producto(nombre="Agotado", stock=0)
    inactivo = fabrica.producto(nombre="Descontinuado", stock=0, activo=False)
    for producto, minimo in ((justo, 3), (agotado, 5), (inactivo, 5)):
        producto.stock_minimo = minimo
    sesion.flush()

    alertas = gestion.alertas_de_stock(sesion, ParametrosPagina(), operador)

    assert [p.nombre for p in alertas.elementos] == ["Agotado", "Justo"]
    assert all(p.bajo_stock for p in alertas.elementos)


def test_una_venta_que_baja_del_minimo_aparece_en_las_alertas(sesion, fabrica, operador) -> None:
    from app.modulos.ventas import servicio as ventas
    from app.modulos.ventas.esquemas import VentaCrear

    casco = fabrica.producto(stock=4)
    casco.stock_minimo = 3
    sesion.flush()
    assert not gestion.alertas_de_stock(sesion, ParametrosPagina(), operador).elementos

    ventas.crear_venta(
        sesion,
        fabrica.cliente(),
        VentaCrear(productos=[{"producto_id": casco.id}]),
        momento=MOMENTO,
    )

    assert [
        p.id for p in gestion.alertas_de_stock(sesion, ParametrosPagina(), operador).elementos
    ] == [casco.id]


def test_resumen_del_inventario(sesion, fabrica, operador) -> None:
    fabrica.vehiculo()
    fabrica.vehiculo(estado=EstadoVehiculo.MANTENIMIENTO)
    fabrica.producto(stock=0)  # stock 0 y mínimo 0: en alerta

    resumen = gestion.resumen(sesion, operador)

    assert resumen["total_unidades"] == 2
    assert resumen["unidades_por_estado"][EstadoVehiculo.MANTENIMIENTO] == 1
    assert resumen["unidades_por_estado"][EstadoVehiculo.VENDIDO] == 0
    assert (resumen["productos_activos"], resumen["productos_bajo_stock"]) == (1, 1)


# --- Permisos -------------------------------------------------------------------------------


def test_el_operador_consulta_pero_no_cambia(sesion, fabrica, operador) -> None:
    gestion.listar_productos(sesion, ParametrosPagina(), operador)
    with pytest.raises(PermisoDenegado):
        gestion.crear_tipo(sesion, TipoVehiculoCrear(nombre="Scooter", usa_bateria=True), operador)
    with pytest.raises(PermisoDenegado):
        gestion.ajustar_stock(
            sesion, fabrica.producto().id, AjusteStock(cantidad=1, motivo="Prueba."), operador
        )


def test_el_cliente_no_consulta_el_inventario(sesion, crear_usuario) -> None:
    with pytest.raises(PermisoDenegado):
        gestion.alertas_de_stock(sesion, ParametrosPagina(), crear_usuario(Rol.CLIENTE))
