"""Consulta de respaldo de todos los pagos pendientes (HU-05).

Uso:  python -m scripts.sincronizar_pagos

Le pregunta a la pasarela configurada (PAGOS_PROVEEDOR) por cada cobro que sigue
``pendiente`` y aplica lo que responda: confirma, rechaza o registra la devolución si el
pago llegó tarde. Sirve en desarrollo, donde el webhook de Wompi no puede llegar a
127.0.0.1, y como red de seguridad si un webhook se pierde. Es seguro correrlo varias veces.
"""

from app.comun import fechas
from app.db import SesionLocal
from app.modulos.pagos import procesamiento
from app.modulos.pagos.modelos import EstadoPago, Pago
from app.modulos.pagos.pasarela import obtener_pasarela


def main() -> None:
    pasarela = obtener_pasarela()
    with SesionLocal() as sesion:
        pendientes = procesamiento.cobros_pendientes(sesion, pasarela.nombre)
        print(f"Cobros pendientes con '{pasarela.nombre}': {len(pendientes)}")
        for pago_id in pendientes:
            pago = procesamiento.sincronizar(
                sesion, sesion.get(Pago, pago_id), pasarela, fechas.ahora()
            )
            cambio = "sin cambios" if pago.estado == EstadoPago.PENDIENTE else pago.estado.value
            print(f"  {pago.referencia}: {cambio}")


if __name__ == "__main__":
    main()
