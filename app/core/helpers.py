"""Helpers de serialização compartilhados."""

from app.core.schemas import UsuarioCompleto
from app.models.user import User


def build_usuario_completo(usuario: User) -> UsuarioCompleto:
    """Constrói o schema UsuarioCompleto a partir do model User."""
    return UsuarioCompleto(
        id=usuario.id,
        nome_completo=usuario.nome_completo,
        email=usuario.email,
        matricula=usuario.matricula,
        data_nascimento=usuario.data_nascimento,
        data_ingresso=usuario.data_ingresso,
        meta_horas_semanais=usuario.meta_horas_semanais,
        foto_perfil=usuario.foto_perfil,
        curso_id=usuario.curso_id,
        status_id=usuario.status_id,
        global_role=usuario.global_role,
    )
