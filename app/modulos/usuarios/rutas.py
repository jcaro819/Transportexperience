"""Rutas de autenticación y usuarios (HU-12). Solo validan, llaman al servicio y responden."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from fastapi.security import OAuth2PasswordRequestForm

from app.comun.errores import respuestas_error
from app.comun.paginacion import Pagina, Paginacion
from app.db import SesionBD
from app.modulos.usuarios import servicio
from app.modulos.usuarios.esquemas import (
    RegistroCliente,
    TokenAcceso,
    UsuarioActualizar,
    UsuarioCrear,
    UsuarioRespuesta,
)
from app.modulos.usuarios.modelos import Rol
from app.seguridad import SoloAdministrador, UsuarioActual

enrutador_autenticacion = APIRouter(prefix="/autenticacion", tags=["autenticación"])
enrutador_usuarios = APIRouter(prefix="/usuarios", tags=["usuarios"])


@enrutador_autenticacion.post(
    "/token",
    response_model=TokenAcceso,
    summary="Iniciar sesión",
    responses=respuestas_error(401, 403, 422),
)
def iniciar_sesion(
    sesion: SesionBD, formulario: Annotated[OAuth2PasswordRequestForm, Depends()]
) -> TokenAcceso:
    """Recibe un formulario (``application/x-www-form-urlencoded``) con ``username`` = el
    correo y ``password``. Devuelve el token para enviar en ``Authorization: Bearer``.
    """
    resultado = servicio.iniciar_sesion(sesion, formulario.username, formulario.password)
    return TokenAcceso(
        access_token=resultado.token,
        expira_en_segundos=resultado.expira_en_segundos,
        usuario=UsuarioRespuesta.model_validate(resultado.usuario),
    )


@enrutador_usuarios.post(
    "/registro",
    response_model=UsuarioRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Registrarse como cliente",
    responses=respuestas_error(409, 422),
)
def registrarse(sesion: SesionBD, datos: RegistroCliente) -> UsuarioRespuesta:
    """Registro público. La cuenta queda con rol ``cliente``."""
    return UsuarioRespuesta.model_validate(servicio.registrar_cliente(sesion, datos))


@enrutador_usuarios.get(
    "/yo",
    response_model=UsuarioRespuesta,
    summary="Mi perfil",
    responses=respuestas_error(401),
)
def mi_perfil(usuario: UsuarioActual) -> UsuarioRespuesta:
    """Datos del usuario dueño del token. Sirve para saber el rol y armar el menú."""
    return UsuarioRespuesta.model_validate(usuario)


@enrutador_usuarios.get(
    "",
    response_model=Pagina[UsuarioRespuesta],
    summary="Listar usuarios (administrador)",
    responses=respuestas_error(401, 403, 422),
)
def listar_usuarios(
    sesion: SesionBD,
    _: SoloAdministrador,
    parametros: Paginacion,
    rol: Rol | None = None,
    activo: bool | None = None,
    busqueda: Annotated[
        str | None, Query(max_length=100, description="Busca en nombre y correo.")
    ] = None,
) -> Pagina[UsuarioRespuesta]:
    resultado = servicio.listar_usuarios(sesion, parametros, rol, activo, busqueda)
    return Pagina[UsuarioRespuesta].model_validate(resultado)


@enrutador_usuarios.post(
    "",
    response_model=UsuarioRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Crear usuario con cualquier rol (administrador)",
    responses=respuestas_error(401, 403, 409, 422),
)
def crear_usuario(
    sesion: SesionBD, administrador: SoloAdministrador, datos: UsuarioCrear
) -> UsuarioRespuesta:
    return UsuarioRespuesta.model_validate(servicio.crear_usuario(sesion, datos, administrador))


@enrutador_usuarios.get(
    "/{usuario_id}",
    response_model=UsuarioRespuesta,
    summary="Ver un usuario (administrador)",
    responses=respuestas_error(401, 403, 404),
)
def ver_usuario(sesion: SesionBD, _: SoloAdministrador, usuario_id: int) -> UsuarioRespuesta:
    return UsuarioRespuesta.model_validate(servicio.obtener_usuario(sesion, usuario_id))


@enrutador_usuarios.patch(
    "/{usuario_id}",
    response_model=UsuarioRespuesta,
    summary="Modificar rol, estado o datos de un usuario (administrador)",
    responses=respuestas_error(401, 403, 404, 409, 422),
)
def actualizar_usuario(
    sesion: SesionBD,
    administrador: SoloAdministrador,
    usuario_id: int,
    cambios: UsuarioActualizar,
) -> UsuarioRespuesta:
    """Solo cambia los campos enviados. Para desactivar una cuenta: ``{"activo": false}``."""
    usuario = servicio.actualizar_usuario(sesion, usuario_id, cambios, administrador)
    return UsuarioRespuesta.model_validate(usuario)
