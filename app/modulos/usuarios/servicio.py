"""Reglas de negocio de usuarios, autenticación y roles (HU-12).

Cada función de escritura confirma su propia transacción. Las rutas solo llaman aquí.
"""

from dataclasses import dataclass
from functools import cache

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auditoria import registrar_auditoria
from app.comun.paginacion import ParametrosPagina, ResultadoPagina, paginar
from app.modulos.usuarios.esquemas import RegistroCliente, UsuarioActualizar, UsuarioCrear
from app.modulos.usuarios.excepciones import (
    CambioSobreSiMismo,
    CorreoYaRegistrado,
    CredencialesInvalidas,
    CuentaInactiva,
    UsuarioNoEncontrado,
)
from app.modulos.usuarios.modelos import Rol, Usuario
from app.seguridad import crear_token_acceso, hashear_contrasena, verificar_contrasena


@dataclass(frozen=True)
class SesionIniciada:
    token: str
    expira_en_segundos: int
    usuario: Usuario


def _normalizar_correo(correo: str) -> str:
    return correo.strip().lower()


@cache
def _hash_ficticio() -> str:
    """Hash de relleno para que un correo inexistente tarde lo mismo que uno real."""
    return hashear_contrasena("contrasena-ficticia-para-igualar-tiempos")


def _crear(sesion: Session, datos: RegistroCliente, rol: Rol) -> Usuario:
    correo = _normalizar_correo(datos.correo)
    if sesion.scalars(select(Usuario.id).filter_by(correo=correo)).first() is not None:
        raise CorreoYaRegistrado()
    usuario = Usuario(
        nombre_completo=datos.nombre_completo,
        correo=correo,
        telefono=datos.telefono,
        rol=rol,
        hash_contrasena=hashear_contrasena(datos.contrasena),
    )
    sesion.add(usuario)
    try:
        sesion.flush()
    except IntegrityError as error:
        # Dos registros simultáneos con el mismo correo: la restricción única decide.
        sesion.rollback()
        raise CorreoYaRegistrado() from error
    return usuario


def registrar_cliente(sesion: Session, datos: RegistroCliente) -> Usuario:
    """Registro público. Siempre crea una cuenta de cliente, sin importar lo que se envíe."""
    usuario = _crear(sesion, datos, Rol.CLIENTE)
    sesion.commit()
    return usuario


def crear_usuario(sesion: Session, datos: UsuarioCrear, administrador: Usuario) -> Usuario:
    """Un administrador crea una cuenta con cualquier rol. Queda en auditoría."""
    usuario = _crear(sesion, datos, datos.rol)
    registrar_auditoria(
        sesion,
        usuario_id=administrador.id,
        accion="crear",
        entidad="usuarios",
        entidad_id=usuario.id,
        despues={"correo": usuario.correo, "rol": usuario.rol.value},
    )
    sesion.commit()
    return usuario


def autenticar(sesion: Session, correo: str, contrasena: str) -> Usuario:
    """Devuelve el usuario si correo y contraseña coinciden y la cuenta está activa."""
    usuario = sesion.scalars(
        select(Usuario).filter_by(correo=_normalizar_correo(correo))
    ).one_or_none()
    if usuario is None:
        verificar_contrasena(contrasena, _hash_ficticio())
        raise CredencialesInvalidas()
    if not verificar_contrasena(contrasena, usuario.hash_contrasena):
        raise CredencialesInvalidas()
    # Solo se revela que la cuenta está inactiva a quien demostró conocer la contraseña.
    if not usuario.activo:
        raise CuentaInactiva()
    return usuario


def iniciar_sesion(sesion: Session, correo: str, contrasena: str) -> SesionIniciada:
    """Autentica y emite el token de acceso."""
    usuario = autenticar(sesion, correo, contrasena)
    token, expira_en = crear_token_acceso(usuario)
    return SesionIniciada(token=token, expira_en_segundos=expira_en, usuario=usuario)


def obtener_usuario(sesion: Session, usuario_id: int) -> Usuario:
    usuario = sesion.get(Usuario, usuario_id)
    if usuario is None:
        raise UsuarioNoEncontrado()
    return usuario


def listar_usuarios(
    sesion: Session,
    parametros: ParametrosPagina,
    rol: Rol | None = None,
    activo: bool | None = None,
    busqueda: str | None = None,
) -> ResultadoPagina:
    """Lista paginada, filtrable por rol, estado y texto (nombre o correo)."""
    consulta = select(Usuario).order_by(Usuario.id)
    if rol is not None:
        consulta = consulta.where(Usuario.rol == rol)
    if activo is not None:
        consulta = consulta.where(Usuario.activo == activo)
    if busqueda:
        patron = f"%{busqueda.strip()}%"
        consulta = consulta.where(
            or_(Usuario.nombre_completo.ilike(patron), Usuario.correo.ilike(patron))
        )
    return paginar(sesion, consulta, parametros)


def actualizar_usuario(
    sesion: Session, usuario_id: int, cambios: UsuarioActualizar, administrador: Usuario
) -> Usuario:
    """Aplica los campos enviados. Los cambios de rol y de estado quedan en auditoría.

    Un administrador no puede desactivarse ni quitarse el rol a sí mismo, para que el
    sistema nunca se quede sin quien lo administre por un error.
    """
    usuario = obtener_usuario(sesion, usuario_id)
    campos = cambios.model_dump(exclude_unset=True)

    if usuario.id == administrador.id and (
        campos.get("activo") is False or campos.get("rol", Rol.ADMINISTRADOR) != Rol.ADMINISTRADOR
    ):
        raise CambioSobreSiMismo()

    antes = {campo: getattr(usuario, campo) for campo in campos}
    for campo, valor in campos.items():
        setattr(usuario, campo, valor)

    sensibles = {"rol", "activo"} & {c for c in campos if antes[c] != campos[c]}
    if sensibles:
        registrar_auditoria(
            sesion,
            usuario_id=administrador.id,
            accion="actualizar",
            entidad="usuarios",
            entidad_id=usuario.id,
            antes={c: _valor_json(antes[c]) for c in sensibles},
            despues={c: _valor_json(campos[c]) for c in sensibles},
        )
    sesion.commit()
    return usuario


def _valor_json(valor: object) -> object:
    return valor.value if isinstance(valor, Rol) else valor
