"""Reglas de negocio de las actas de entrega y recepción (HU-11, SRS 3.1.9).

Decisión 2 del Sprint 4:

- Las actas se generan **solas** al entregar o recibir un vehículo, en el local y por
  domicilio (``registro.registrar_acta``, dentro de la misma transacción).
- Se exportan a **PDF** (ReportLab) y **Excel** (openpyxl).
- **Firma de conformidad**: el cliente da su conformidad en la plataforma y queda un
  registro con su usuario, la fecha y el **SHA-256 del PDF** del acta (tabla ``actas``).
  *Decidido así y pendiente de confirmación del equipo.*

Quién ve qué: el administrador y el operador, todas las actas; el cliente, las de sus
alquileres y compras.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import Select, or_, select
from sqlalchemy.orm import Session, joinedload

from app.auditoria import registrar_auditoria
from app.comun import fechas
from app.comun.errores import PermisoDenegado
from app.comun.paginacion import ParametrosPagina, ResultadoPagina, paginar
from app.modulos.alquileres.modelos import Alquiler
from app.modulos.inventario.modelos import Vehiculo
from app.modulos.reportes.documentos import huella, pdf_acta
from app.modulos.reportes.excepciones import (
    ActaNoEncontrada,
    ConformidadYaRegistrada,
    RangoDeReporteInvalido,
)
from app.modulos.reportes.modelos import Acta, TipoActa
from app.modulos.usuarios.modelos import Rol, Usuario
from app.modulos.ventas.modelos import Venta

ROLES_DE_MOSTRADOR = frozenset({Rol.ADMINISTRADOR, Rol.OPERADOR})
MAX_DIAS_REPORTE = 92  # un trimestre: los reportes no traen tablas completas (SRS 3.4.6)


@dataclass(frozen=True)
class Reporte:
    actas: list[Acta]
    titulo: str


def _consulta() -> Select:
    """Actas con todo lo que muestran sus documentos ya cargado."""
    return select(Acta).options(
        joinedload(Acta.vehiculo).joinedload(Vehiculo.modelo),
        joinedload(Acta.alquiler).joinedload(Alquiler.cliente),
        joinedload(Acta.venta).joinedload(Venta.cliente),
        joinedload(Acta.registrada_por),
        joinedload(Acta.conforme_por),
    )


def _del_cliente(cliente_id: int):
    return or_(
        Acta.alquiler_id.in_(select(Alquiler.id).where(Alquiler.cliente_id == cliente_id)),
        Acta.venta_id.in_(select(Venta.id).where(Venta.cliente_id == cliente_id)),
    )


def _visible(acta: Acta, usuario: Usuario) -> bool:
    return usuario.rol in ROLES_DE_MOSTRADOR or (
        usuario.rol == Rol.CLIENTE and acta.cliente_id == usuario.id
    )


def listar_actas(
    sesion: Session,
    parametros: ParametrosPagina,
    usuario: Usuario,
    *,
    tipo: TipoActa | None = None,
    vehiculo_id: int | None = None,
    desde: date | None = None,
    hasta: date | None = None,
) -> ResultadoPagina:
    """De la más reciente a la más antigua. El cliente solo recibe las suyas."""
    if usuario.rol not in ROLES_DE_MOSTRADOR | {Rol.CLIENTE}:
        raise PermisoDenegado()
    consulta = _consulta().order_by(Acta.creado_en.desc(), Acta.id.desc())
    if usuario.rol == Rol.CLIENTE:
        consulta = consulta.where(_del_cliente(usuario.id))
    if tipo is not None:
        consulta = consulta.where(Acta.tipo == tipo)
    if vehiculo_id is not None:
        consulta = consulta.where(Acta.vehiculo_id == vehiculo_id)
    if desde is not None:
        consulta = consulta.where(Acta.creado_en >= _inicio_del_dia(desde))
    if hasta is not None:
        consulta = consulta.where(Acta.creado_en < _inicio_del_dia(hasta + timedelta(days=1)))
    return paginar(sesion, consulta, parametros)


def _inicio_del_dia(dia: date) -> datetime:
    """Medianoche en Colombia: los rangos de fechas son de días de Colombia."""
    return datetime(dia.year, dia.month, dia.day, tzinfo=fechas.ZONA_COLOMBIA)


def obtener_acta(sesion: Session, acta_id: int, usuario: Usuario) -> Acta:
    acta = sesion.scalars(_consulta().where(Acta.id == acta_id)).unique().one_or_none()
    if acta is None or not _visible(acta, usuario):
        raise ActaNoEncontrada()
    return acta


def pdf(sesion: Session, acta_id: int, usuario: Usuario) -> bytes:
    """El PDF del acta: siempre el mismo para la misma acta (ver ``documentos``)."""
    return pdf_acta(obtener_acta(sesion, acta_id, usuario))


def dar_conformidad(
    sesion: Session, acta_id: int, usuario: Usuario, *, momento: datetime | None = None
) -> Acta:
    """El cliente de la operación acepta el acta: queda su usuario, la fecha y el SHA-256 del PDF.

    Solo una vez. La huella permite verificar después que el documento no cambió: quien
    tenga el PDF calcula su SHA-256 y lo compara con ``hash_pdf``.
    """
    acta = obtener_acta(sesion, acta_id, usuario)
    if usuario.rol != Rol.CLIENTE:
        raise PermisoDenegado("La conformidad la da el cliente de la operación.")
    bloqueada = sesion.scalars(
        select(Acta)
        .where(Acta.id == acta.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one()
    if bloqueada.conforme_en is not None:
        raise ConformidadYaRegistrada()
    hash_pdf = huella(pdf_acta(bloqueada))
    bloqueada.conforme_por_id = usuario.id
    bloqueada.conforme_en = momento or fechas.ahora()
    bloqueada.hash_pdf = hash_pdf
    registrar_auditoria(
        sesion,
        usuario_id=usuario.id,
        accion="conformidad",
        entidad="actas",
        entidad_id=acta.id,
        despues={"hash_pdf": hash_pdf},
    )
    sesion.commit()
    return obtener_acta(sesion, acta.id, usuario)


def verificar(sesion: Session, acta_id: int, usuario: Usuario) -> bool | None:
    """¿El PDF de hoy es el mismo que se aceptó? ``None`` si aún no hay conformidad."""
    acta = obtener_acta(sesion, acta_id, usuario)
    if acta.hash_pdf is None:
        return None
    return huella(pdf_acta(acta)) == acta.hash_pdf


def reporte(
    sesion: Session,
    usuario: Usuario,
    *,
    desde: date | None = None,
    hasta: date | None = None,
    tipo: TipoActa | None = None,
) -> Reporte:
    """Las actas de un rango (por defecto, los últimos 30 días), para exportar."""
    if usuario.rol not in ROLES_DE_MOSTRADOR:
        raise PermisoDenegado()
    hasta = hasta or fechas.hoy()
    desde = desde or hasta - timedelta(days=29)
    if desde > hasta:
        raise RangoDeReporteInvalido("`desde` es posterior a `hasta`.")
    if (hasta - desde).days + 1 > MAX_DIAS_REPORTE:
        raise RangoDeReporteInvalido(f"El rango supera los {MAX_DIAS_REPORTE} días.")
    consulta = (
        _consulta()
        .where(
            Acta.creado_en >= _inicio_del_dia(desde),
            Acta.creado_en < _inicio_del_dia(hasta + timedelta(days=1)),
        )
        .order_by(Acta.creado_en, Acta.id)
    )
    if tipo is not None:
        consulta = consulta.where(Acta.tipo == tipo)
    actas = list(sesion.scalars(consulta).unique())
    nombre = {TipoActa.ENTREGA: "de entrega", TipoActa.RECEPCION: "de recepción"}.get(tipo, "")
    titulo = f"Actas {nombre} del {desde:%d/%m/%Y} al {hasta:%d/%m/%Y}".replace("  ", " ")
    return Reporte(actas, titulo)
