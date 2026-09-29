"""Los seeds cargan datos coherentes con las reglas del modelo y son idempotentes."""

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modulos.alquileres.modelos import Alquiler, EstadoAlquiler
from app.modulos.domicilios.modelos import ZonaCobertura
from app.modulos.inventario.modelos import (
    EstadoNovedad,
    EstadoVehiculo,
    NovedadVehiculo,
    Producto,
    Vehiculo,
)
from app.modulos.pagos.modelos import MetodoPago
from app.modulos.usuarios.modelos import Rol, Usuario
from app.modulos.ventas.modelos import EstadoVenta, ItemVenta, Venta
from app.seguridad import verificar_contrasena
from seeds import datos
from seeds.cargar import CargaDeSemillas, main


@pytest.fixture
def sesion_con_seeds(sesion: Session) -> Session:
    CargaDeSemillas(sesion).cargar()
    return sesion


def _contar(sesion: Session, modelo) -> int:
    return sesion.scalar(select(func.count()).select_from(modelo))


def test_correr_dos_veces_no_duplica_nada(sesion_con_seeds: Session) -> None:
    tablas = [Usuario, Vehiculo, Producto, ZonaCobertura, MetodoPago, Alquiler, Venta]
    antes = {m.__tablename__: _contar(sesion_con_seeds, m) for m in tablas}

    creados = CargaDeSemillas(sesion_con_seeds).cargar()

    assert not creados
    assert {m.__tablename__: _contar(sesion_con_seeds, m) for m in tablas} == antes


def test_un_usuario_por_rol_con_la_contrasena_documentada(sesion_con_seeds: Session) -> None:
    usuarios = sesion_con_seeds.scalars(select(Usuario)).all()

    assert sorted(u.rol for u in usuarios) == sorted(Rol)
    assert all(
        verificar_contrasena(datos.CONTRASENA_DESARROLLO, u.hash_contrasena) for u in usuarios
    )


def test_hay_productos_en_bajo_stock_para_la_alerta_de_hu10(sesion_con_seeds: Session) -> None:
    bajo_stock = sesion_con_seeds.scalars(
        select(Producto).where(Producto.stock <= Producto.stock_minimo)
    ).all()
    assert bajo_stock


def test_cada_estado_distinto_de_disponible_tiene_su_operacion(sesion_con_seeds: Session) -> None:
    s = sesion_con_seeds
    vehiculos = s.scalars(select(Vehiculo)).all()
    assert len(vehiculos) == 15

    for v in vehiculos:
        if v.estado == EstadoVehiculo.MANTENIMIENTO:
            assert s.scalars(
                select(NovedadVehiculo).filter_by(vehiculo_id=v.id, estado=EstadoNovedad.ABIERTA)
            ).first(), f"{v.codigo} en mantenimiento sin novedad abierta"
        elif v.estado == EstadoVehiculo.ALQUILADO:
            assert s.scalars(
                select(Alquiler).filter_by(vehiculo_id=v.id, estado=EstadoAlquiler.EN_CURSO)
            ).first(), f"{v.codigo} alquilado sin alquiler en curso"
        elif v.estado == EstadoVehiculo.VENDIDO:
            assert s.scalars(
                select(ItemVenta)
                .join(Venta)
                .where(ItemVenta.vehiculo_id == v.id, Venta.estado == EstadoVenta.PAGADA)
            ).first(), f"{v.codigo} vendido sin venta pagada"


def test_zonas_son_poligonos_geojson_cerrados(sesion_con_seeds: Session) -> None:
    zonas = sesion_con_seeds.scalars(select(ZonaCobertura)).all()

    assert len(zonas) == 3
    for zona in zonas:
        anillo = zona.poligono["coordinates"][0]
        assert zona.poligono["type"] == "Polygon"
        assert anillo[0] == anillo[-1]
        assert len(anillo) >= 4


def test_se_niega_a_correr_fuera_de_desarrollo() -> None:
    # conftest fija ENTORNO=pruebas.
    with pytest.raises(SystemExit, match="ENTORNO=desarrollo"):
        main()
