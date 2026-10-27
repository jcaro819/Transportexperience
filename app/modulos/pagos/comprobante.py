"""Comprobante de pago en PDF (HU-05, SRS 3.1.6): valor, fecha, servicio, cliente y estado.

Se arma en dos pasos para poder probarlo: ``datos_comprobante`` reúne la información de la
base, y ``generar_pdf`` (función pura) la dibuja con ReportLab.
"""

from dataclasses import dataclass
from datetime import datetime
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.modulos.alquileres.modelos import Alquiler
from app.modulos.inventario.modelos import Vehiculo
from app.modulos.pagos.modelos import EstadoPago, MetodoPago, Pago, TipoPago
from app.modulos.usuarios.modelos import Usuario
from app.modulos.ventas.modelos import ItemVenta, Venta

_ESTADOS = {
    EstadoPago.PENDIENTE: "Pendiente",
    EstadoPago.APROBADO: "Aprobado",
    EstadoPago.RECHAZADO: "Rechazado",
    EstadoPago.EXPIRADO: "Expirado",
    EstadoPago.ERROR: "Error",
}


@dataclass(frozen=True)
class LineaComprobante:
    descripcion: str
    cantidad: int
    valor: int  # pesos


@dataclass(frozen=True)
class DatosComprobante:
    referencia: str
    tipo: TipoPago
    fecha: datetime
    cliente_nombre: str
    cliente_correo: str
    servicio: str
    lineas: list[LineaComprobante]
    total: int
    metodo: str
    estado: EstadoPago
    id_transaccion: str | None


def pesos(valor: int) -> str:
    """60000 -> "$60.000" (formato colombiano, sin decimales)."""
    return "$" + f"{valor:,}".replace(",", ".")


def datos_comprobante(sesion: Session, pago: Pago) -> DatosComprobante:
    """Reúne lo que va en el comprobante de ``pago`` (alquiler o compra)."""
    metodo = sesion.get(MetodoPago, pago.metodo_pago_id)
    if pago.alquiler_id is not None:
        alquiler = sesion.scalars(
            select(Alquiler)
            .where(Alquiler.id == pago.alquiler_id)
            .options(joinedload(Alquiler.vehiculo).joinedload(Vehiculo.modelo))
        ).one()
        cliente = sesion.get(Usuario, alquiler.cliente_id)
        servicio = f"Alquiler #{alquiler.id}"
        lineas = [
            LineaComprobante(
                f"{alquiler.vehiculo.modelo.nombre} ({alquiler.vehiculo.codigo}), del "
                f"{alquiler.fecha_inicio:%d/%m/%Y} al {alquiler.fecha_fin:%d/%m/%Y}, "
                f"{alquiler.dias} día(s) a {pesos(alquiler.tarifa_diaria)}",
                alquiler.dias,
                alquiler.subtotal,
            )
        ]
        envio = alquiler.valor_envio
    else:
        venta = sesion.scalars(
            select(Venta)
            .where(Venta.id == pago.venta_id)
            .options(
                selectinload(Venta.items)
                .joinedload(ItemVenta.vehiculo)
                .joinedload(Vehiculo.modelo),
                selectinload(Venta.items).joinedload(ItemVenta.producto),
            )
        ).one()
        cliente = sesion.get(Usuario, venta.cliente_id)
        servicio = f"Compra #{venta.id}"
        lineas = [
            LineaComprobante(
                f"{i.vehiculo.modelo.nombre} ({i.vehiculo.codigo})"
                if i.vehiculo
                else f"{i.producto.nombre} ({i.producto.codigo})",
                i.cantidad,
                i.subtotal,
            )
            for i in venta.items
        ]
        envio = venta.valor_envio
    if envio:
        lineas.append(LineaComprobante("Envío a domicilio", 1, envio))
    if pago.tipo == TipoPago.COMPENSACION:
        servicio = f"Devolución de {servicio.lower()}"
    return DatosComprobante(
        referencia=pago.referencia,
        tipo=pago.tipo,
        fecha=pago.aprobado_en or pago.creado_en,
        cliente_nombre=cliente.nombre_completo,
        cliente_correo=cliente.correo,
        servicio=servicio,
        lineas=lineas,
        total=pago.monto,
        metodo=metodo.nombre,
        estado=pago.estado,
        id_transaccion=pago.id_transaccion_pasarela,
    )


def generar_pdf(datos: DatosComprobante) -> bytes:
    """Dibuja el comprobante en PDF (tamaño carta)."""
    salida = BytesIO()
    documento = SimpleDocTemplate(
        salida,
        pagesize=letter,
        title=f"Comprobante {datos.referencia}",
        author="TransportExperience",
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )
    estilos = getSampleStyleSheet()
    normal = estilos["Normal"]
    contenido = [
        Paragraph("TransportExperience", estilos["Title"]),
        Paragraph(f"Comprobante de pago — {datos.servicio}", estilos["Heading2"]),
        Spacer(1, 0.3 * cm),
    ]
    resumen = [
        ["Referencia", datos.referencia],
        ["Fecha", f"{datos.fecha:%d/%m/%Y %H:%M}"],
        ["Cliente", f"{datos.cliente_nombre} ({datos.cliente_correo})"],
        ["Método de pago", datos.metodo],
        ["Estado de la transacción", _ESTADOS[datos.estado]],
        ["Id. en la pasarela", datos.id_transaccion or "—"],
    ]
    tabla_resumen = Table(resumen, colWidths=[5 * cm, 12 * cm])
    tabla_resumen.setStyle(
        TableStyle(
            [("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"), ("VALIGN", (0, 0), (-1, -1), "TOP")]
        )
    )
    contenido += [tabla_resumen, Spacer(1, 0.5 * cm)]

    filas = [["Descripción", "Cant.", "Valor"]]
    filas += [
        [Paragraph(linea.descripcion, normal), str(linea.cantidad), pesos(linea.valor)]
        for linea in datos.lineas
    ]
    filas.append(["", "Total", pesos(datos.total)])
    detalle = Table(filas, colWidths=[11 * cm, 2 * cm, 4 * cm], repeatRows=1)
    detalle.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                ("LINEBELOW", (0, 0), (-1, 0), 0.8, colors.black),
                ("LINEABOVE", (0, -1), (-1, -1), 0.8, colors.black),
                ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    contenido += [detalle, Spacer(1, 0.8 * cm)]

    # Este proyecto solo usa la pasarela falsa o el sandbox de Wompi (CLAUDE.md sección 5).
    notas = ["Valores en pesos colombianos.", "Ambiente de pruebas: no se movió dinero real."]
    if datos.estado != EstadoPago.APROBADO:
        notas.append("Este pago no está aprobado: el documento no prueba un pago.")
    for nota in notas:
        contenido.append(Paragraph(nota, estilos["Italic"]))

    documento.build(contenido)
    return salida.getvalue()
