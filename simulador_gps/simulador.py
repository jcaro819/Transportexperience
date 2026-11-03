"""El simulador como cliente HTTP de la API (HU-08, CLAUDE.md sección 8).

Hace exactamente lo que haría un despliegue con GPS reales, sin tocar la base de datos:

1. Inicia sesión como administrador.
2. Para cada vehículo, emite una clave GPS con fuente ``simulador``
   (``POST /rastreo/vehiculos/{id}/clave``).
3. Cada ``intervalo`` segundos, cada vehículo avanza por su recorrido y envía su posición a
   ``POST /rastreo/posiciones`` con su clave en ``X-Clave-Gps``: **el mismo endpoint que
   usaría un GPS real**.

Recibe un ``httpx.Client`` ya configurado: en los tests se le pasa el cliente de pruebas de
FastAPI, sin red ni servidor.
"""

import random
import time
from collections.abc import Callable
from dataclasses import dataclass

import httpx

from simulador_gps.movimiento import Recorrido, VehiculoSimulado
from simulador_gps.rutas import RECORRIDOS


class ErrorDelSimulador(RuntimeError):
    """Algo impide simular (credenciales, vehículos inexistentes, API caída...)."""


@dataclass(frozen=True)
class ResultadoEnvio:
    codigo: str
    estado_http: int
    detalle: str


def _verificar(respuesta: httpx.Response, que: str) -> dict:
    if respuesta.status_code >= 400:
        try:
            error = respuesta.json()["error"]
            detalle = f"{error['mensaje']} {error['accion']}"
        except (ValueError, KeyError, TypeError):
            detalle = respuesta.text[:200]
        raise ErrorDelSimulador(f"No se pudo {que} (HTTP {respuesta.status_code}): {detalle}")
    return respuesta.json()


class Simulador:
    def __init__(
        self,
        cliente: httpx.Client,
        *,
        intervalo: float = 5.0,
        semilla: int | None = None,
        dormir: Callable[[float], None] = time.sleep,
    ) -> None:
        self.cliente = cliente
        self.intervalo = intervalo
        self.azar = random.Random(semilla)
        self.dormir = dormir
        self.vehiculos: list[VehiculoSimulado] = []

    def iniciar_sesion(self, correo: str, contrasena: str) -> None:
        respuesta = self.cliente.post(
            "/autenticacion/token", data={"username": correo, "password": contrasena}
        )
        token = _verificar(respuesta, "iniciar sesión como administrador")["access_token"]
        self.cliente.headers["Authorization"] = f"Bearer {token}"

    def _buscar_vehiculos(self, codigos: list[str] | None, cantidad: int) -> list[dict]:
        if codigos:
            encontrados = []
            for codigo in codigos:
                pagina = _verificar(
                    self.cliente.get("/vehiculos", params={"codigo": codigo, "tamano": 100}),
                    f"buscar el vehículo {codigo}",
                )
                exacto = [v for v in pagina["elementos"] if v["codigo"] == codigo]
                if not exacto:
                    raise ErrorDelSimulador(f"No existe el vehículo {codigo}.")
                encontrados.append(exacto[0])
            return encontrados
        pagina = _verificar(
            self.cliente.get("/vehiculos", params={"tamano": 100}), "listar la flota"
        )
        flota = [v for v in pagina["elementos"] if v["estado"] != "vendido"]
        if not flota:
            raise ErrorDelSimulador("No hay vehículos en la flota. Corre: python -m seeds.cargar")
        return flota[:cantidad]

    def preparar(self, codigos: list[str] | None = None, cantidad: int = 5) -> None:
        """Emite una clave GPS (fuente simulador) para cada vehículo y le asigna un recorrido."""
        recorridos = [Recorrido(nombre, puntos) for nombre, puntos in RECORRIDOS.items()]
        for i, vehiculo in enumerate(self._buscar_vehiculos(codigos, cantidad)):
            emitida = _verificar(
                self.cliente.post(
                    f"/rastreo/vehiculos/{vehiculo['id']}/clave", json={"fuente": "simulador"}
                ),
                f"emitir la clave GPS de {vehiculo['codigo']}",
            )
            recorrido = recorridos[i % len(recorridos)]
            self.vehiculos.append(
                VehiculoSimulado(
                    codigo=vehiculo["codigo"],
                    clave=emitida["clave"],
                    recorrido=recorrido,
                    descripcion=vehiculo["modelo"]["nombre"],
                    usa_bateria=vehiculo["nivel_bateria"] is not None,
                    # Cada uno arranca en un punto distinto del recorrido.
                    distancia_m=self.azar.uniform(0, recorrido.longitud_m),
                    bateria=float(vehiculo["nivel_bateria"] or 100),
                    azar=random.Random(self.azar.random()),
                )
            )

    def enviar_posiciones(self) -> list[ResultadoEnvio]:
        """Un ciclo: cada vehículo avanza ``intervalo`` segundos y reporta su posición."""
        resultados = []
        for vehiculo in self.vehiculos:
            cuerpo = vehiculo.avanzar(self.intervalo)
            respuesta = self.cliente.post(
                "/rastreo/posiciones",
                json=cuerpo,
                # Solo la clave del vehículo: la sesión del administrador no se envía aquí.
                headers={"X-Clave-Gps": vehiculo.clave, "Authorization": ""},
            )
            detalle = (
                f"{cuerpo['latitud']}, {cuerpo['longitud']} a {cuerpo['velocidad_kmh']} km/h"
                if respuesta.status_code < 400
                else respuesta.text[:200]
            )
            resultados.append(ResultadoEnvio(vehiculo.codigo, respuesta.status_code, detalle))
        return resultados

    def correr(self, ciclos: int = 0, al_enviar: Callable[[list[ResultadoEnvio]], None] = print):
        """Envía posiciones cada ``intervalo`` segundos. ``ciclos=0``: hasta Ctrl+C."""
        hechos = 0
        while ciclos == 0 or hechos < ciclos:
            al_enviar(self.enviar_posiciones())
            hechos += 1
            if ciclos == 0 or hechos < ciclos:
                self.dormir(self.intervalo)
