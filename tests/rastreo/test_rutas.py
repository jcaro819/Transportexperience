"""Rutas del rastreo y el simulador de punta a punta (HU-08).

El simulador se prueba contra la API real a través del cliente de pruebas de FastAPI: inicia
sesión, emite claves y envía posiciones por el mismo endpoint que un GPS real.
"""

import pytest

from app.modulos.inventario.modelos import EstadoVehiculo
from app.modulos.rastreo.modelos import FuenteGps
from app.modulos.usuarios.modelos import Rol
from simulador_gps.simulador import ErrorDelSimulador, Simulador
from tests.conftest import CONTRASENA_PRUEBAS, encabezado_de

POSICION = {"latitud": "7.119300", "longitud": "-73.122700", "precision_metros": "4.20"}


@pytest.fixture
def administrador(crear_usuario):
    return crear_usuario(Rol.ADMINISTRADOR)


@pytest.fixture
def clave(cliente_api, fabrica, administrador) -> str:
    vehiculo = fabrica.vehiculo(codigo="MON-0001")
    respuesta = cliente_api.post(
        f"/rastreo/vehiculos/{vehiculo.id}/clave",
        json={"fuente": "simulador"},
        headers=encabezado_de(administrador),
    )
    assert respuesta.status_code == 201
    return respuesta.json()["clave"]


def test_el_dispositivo_reporta_con_su_clave_sin_jwt(cliente_api, clave) -> None:
    respuesta = cliente_api.post(
        "/rastreo/posiciones", json=POSICION, headers={"X-Clave-Gps": clave}
    )
    assert respuesta.status_code == 201
    assert respuesta.json()["vehiculo_codigo"] == "MON-0001"


@pytest.mark.parametrize("encabezados", [{}, {"X-Clave-Gps": "gps_falsa"}], ids=["sin", "falsa"])
def test_sin_clave_valida_no_se_reporta(cliente_api, clave, encabezados) -> None:
    respuesta = cliente_api.post("/rastreo/posiciones", json=POSICION, headers=encabezados)
    assert respuesta.status_code == 401
    assert respuesta.json()["error"]["codigo"] == "clave_gps_invalida"


def test_un_jwt_de_usuario_no_sirve_para_reportar(cliente_api, clave, administrador) -> None:
    respuesta = cliente_api.post(
        "/rastreo/posiciones", json=POSICION, headers=encabezado_de(administrador)
    )
    assert respuesta.status_code == 401


def test_el_mapa_es_solo_del_administrador_y_el_operador(cliente_api, crear_usuario, clave) -> None:
    for rol, esperado in [
        (Rol.ADMINISTRADOR, 200),
        (Rol.OPERADOR, 200),
        (Rol.CLIENTE, 403),
        (Rol.DOMICILIARIO, 403),
    ]:
        encabezado = encabezado_de(crear_usuario(rol))
        assert cliente_api.get("/rastreo/flota", headers=encabezado).status_code == esperado, rol


def test_solo_el_administrador_emite_claves(cliente_api, fabrica, crear_usuario) -> None:
    respuesta = cliente_api.post(
        f"/rastreo/vehiculos/{fabrica.vehiculo().id}/clave",
        json={"fuente": "dispositivo"},
        headers=encabezado_de(crear_usuario(Rol.OPERADOR)),
    )
    assert respuesta.status_code == 403


# --- El simulador de punta a punta --------------------------------------------------------


def _simulador(cliente_api, administrador) -> Simulador:
    simulador = Simulador(cliente_api, intervalo=5, semilla=1, dormir=lambda _: None)
    simulador.iniciar_sesion(administrador.correo, CONTRASENA_PRUEBAS)
    return simulador


def test_el_simulador_mueve_la_flota_y_aparece_en_el_mapa(
    cliente_api, sesion, fabrica, administrador
) -> None:
    cicla = fabrica.modelo(nombre="Cicla urbana")
    monopatin = fabrica.modelo(nombre="Monopatín eléctrico")
    fabrica.vehiculo(cicla, codigo="CIC-0001")
    fabrica.vehiculo(monopatin, codigo="MON-0001", nivel_bateria=90)
    fabrica.vehiculo(monopatin, EstadoVehiculo.VENDIDO, codigo="MON-0009")  # se ignora
    simulador = _simulador(cliente_api, administrador)

    simulador.preparar(cantidad=5)
    envios = []
    simulador.correr(ciclos=3, al_enviar=envios.append)

    assert {v.codigo for v in simulador.vehiculos} == {"CIC-0001", "MON-0001"}
    assert all(r.estado_http == 201 for ciclo in envios for r in ciclo)
    flota = cliente_api.get("/rastreo/flota", headers=encabezado_de(administrador)).json()
    por_codigo = {v["codigo"]: v for v in flota["elementos"]}
    assert por_codigo["MON-0001"]["senal"] == "en_linea"
    assert por_codigo["MON-0001"]["posicion"]["nivel_bateria"] is not None
    assert por_codigo["CIC-0001"]["posicion"]["nivel_bateria"] is None
    recorrido = cliente_api.get(
        f"/rastreo/vehiculos/{por_codigo['MON-0001']['vehiculo_id']}/recorrido",
        headers=encabezado_de(administrador),
    ).json()
    assert recorrido["total"] == 3


def test_el_simulador_emite_claves_de_fuente_simulador(
    cliente_api, sesion, fabrica, administrador
) -> None:
    vehiculo = fabrica.vehiculo(codigo="MON-0001")
    _simulador(cliente_api, administrador).preparar(["MON-0001"])
    sesion.refresh(vehiculo)
    assert vehiculo.fuente_gps == FuenteGps.SIMULADOR


def test_el_simulador_avisa_si_el_vehiculo_no_existe(cliente_api, administrador) -> None:
    with pytest.raises(ErrorDelSimulador, match="MON-9999"):
        _simulador(cliente_api, administrador).preparar(["MON-9999"])


def test_el_simulador_avisa_si_la_contrasena_es_incorrecta(cliente_api, administrador) -> None:
    simulador = Simulador(cliente_api)
    with pytest.raises(ErrorDelSimulador, match="iniciar sesión"):
        simulador.iniciar_sesion(administrador.correo, "otra-contrasena")


def test_el_simulador_no_arranca_si_gps_fuente_es_dispositivo(monkeypatch) -> None:
    from simulador_gps import __main__ as programa

    class Configuracion:
        gps_fuente = "dispositivo"

    monkeypatch.setattr(programa, "obtener_configuracion", lambda: Configuracion())
    assert programa.main(["--ciclos", "1"]) == 1
