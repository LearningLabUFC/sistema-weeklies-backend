from uuid import UUID

from sqlalchemy.orm import Session

from app.admin.repository import (
    count_active_admins,
    find_role_by_name,
    find_status_by_name,
    find_user_by_id,
    list_pending_users,
    list_users_paginated,
    update_user,
)
from app.admin.schemas import (
    ChangeRoleRequest,
    ChangeStatusRequest,
    UsuarioListItem,
    UsuarioListResponse,
)
from app.core.exceptions import (
    BadRequestError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
)
from app.core.schemas import MensagemResponse
from app.models.user import User
from app.users.schemas import UsuarioCompleto, build_usuario_completo


def _build_usuario_list_item(usuario: User) -> UsuarioListItem:
    """Helper para serialização com nomes resolvidos das relações."""
    return UsuarioListItem(
        id=usuario.id,
        nome_completo=usuario.nome_completo,
        email=usuario.email,
        matricula=usuario.matricula,
        data_ingresso=usuario.data_ingresso,
        foto_perfil=usuario.foto_perfil,
        curso_nome=usuario.curso.nome if usuario.curso else "—",
        status_nome=usuario.status.nome if usuario.status else "—",
        role_nome=usuario.role.nome if usuario.role else "—",
    )


def svc_list_all_users(
    pagina: int,
    limite: int,
    status_filtro: str | None,
    role_filtro: str | None,
    busca: str | None,
    db: Session,
) -> UsuarioListResponse:
    usuarios, total = list_users_paginated(
        db, pagina, limite, status_filtro, role_filtro, busca
    )

    return UsuarioListResponse(
        usuarios=[_build_usuario_list_item(u) for u in usuarios],
        total=total,
        pagina=pagina,
        limite=limite,
    )


def svc_list_pending_users(db: Session) -> list[UsuarioCompleto]:
    pendentes = list_pending_users(db)
    return [build_usuario_completo(u) for u in pendentes]


def svc_change_user_status(
    user_id: UUID, body: ChangeStatusRequest, admin_user: User, db: Session
) -> MensagemResponse:
    if body.novo_status not in ["ativo", "inativo"]:
        raise BadRequestError("Status inválido. Escolha 'ativo' ou 'inativo'.")

    usuario = find_user_by_id(db, user_id)
    if not usuario:
        raise NotFoundError("Usuário não encontrado.")

    if usuario.role.nome == "super_admin" and admin_user.role.nome != "super_admin":
        raise ForbiddenError(
            "Apenas outro super_admin pode alterar um super_admin.",
        )

    status_obj = find_status_by_name(db, body.novo_status)
    if not status_obj:
        raise NotFoundError("Status não encontrado no banco.")

    usuario.status_id = status_obj.id
    update_user(db)

    return MensagemResponse(
        mensagem=f"Status do usuário alterado para {body.novo_status} com sucesso."
    )


def svc_change_user_role(
    user_id: UUID, body: ChangeRoleRequest, admin_user: User, db: Session
) -> MensagemResponse:
    novo_role = find_role_by_name(db, body.role_nome)
    if not novo_role:
        raise BadRequestError(
            f"Cargo '{body.role_nome}' inválido. Valores aceitos: 'super_admin', 'admin', 'aluno'.",
        )

    usuario = find_user_by_id(db, user_id)
    if not usuario:
        raise NotFoundError("Usuário não encontrado.")

    if usuario.status.nome != "ativo":
        raise BadRequestError(
            "Só é possível alterar o cargo de usuários com status ativo.",
        )

    if usuario.id == admin_user.id:
        raise ForbiddenError(
            "Você não pode alterar o seu próprio cargo. Peça a outro administrador.",
        )

    if usuario.role.nome == "super_admin" and admin_user.role.nome != "super_admin":
        raise ForbiddenError(
            "Apenas um super_admin pode alterar o cargo de outro super_admin.",
        )

    if usuario.role.nome in ["admin", "super_admin"] and body.role_nome not in [
        "admin",
        "super_admin",
    ]:
        total_admins_ativos = count_active_admins(db)
        if total_admins_ativos <= 1:
            raise ConflictError(
                "Operação negada. O sistema deve ter pelo menos um administrador ativo.",
            )

    usuario.global_role = novo_role.id
    update_user(db)

    return MensagemResponse(
        mensagem=f"Cargo do usuário alterado para '{body.role_nome}' com sucesso.",
    )


def svc_delete_user_by_admin(user_id: UUID, db: Session) -> MensagemResponse:
    usuario = find_user_by_id(db, user_id)
    if not usuario:
        raise NotFoundError("Usuário não encontrado.")

    inativo_status = find_status_by_name(db, "inativo")
    usuario.status_id = inativo_status.id
    update_user(db)

    return MensagemResponse(mensagem="Usuário excluído (inativado) com sucesso.")
