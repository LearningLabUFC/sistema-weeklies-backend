from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.admin.schemas import (
    ChangeRoleRequest,
    ChangeStatusRequest,
    UsuarioListItem,
    UsuarioListResponse,
)
from app.core.helpers import build_usuario_completo
from app.core.schemas import MensagemResponse, UsuarioCompleto
from app.models.role import Role
from app.models.status import Status
from app.models.user import User


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
    query = db.query(User)

    if status_filtro:
        query = query.join(Status, User.status_id == Status.id).filter(
            Status.nome == status_filtro
        )

    if role_filtro:
        query = query.join(Role, User.global_role == Role.id).filter(
            Role.nome == role_filtro
        )

    if busca:
        termo = f"%{busca}%"
        query = query.filter(
            (func.lower(User.nome_completo).like(func.lower(termo)))
            | (func.lower(User.email).like(func.lower(termo)))
        )

    total = query.count()
    offset = (pagina - 1) * limite
    usuarios = (
        query.order_by(User.nome_completo.asc()).offset(offset).limit(limite).all()
    )

    return UsuarioListResponse(
        usuarios=[_build_usuario_list_item(u) for u in usuarios],
        total=total,
        pagina=pagina,
        limite=limite,
    )


def svc_list_pending_users(db: Session) -> list[UsuarioCompleto]:
    pendentes = db.query(User).join(Status).filter(Status.nome == "pendente").all()
    return [build_usuario_completo(u) for u in pendentes]


def svc_change_user_status(
    user_id: UUID, body: ChangeStatusRequest, admin_user: User, db: Session
) -> MensagemResponse:
    if body.novo_status not in ["ativo", "inativo"]:
        raise HTTPException(
            status_code=400, detail="Status inválido. Escolha 'ativo' ou 'inativo'."
        )

    usuario = db.query(User).filter(User.id == user_id).first()
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")

    if usuario.role.nome == "super_admin" and admin_user.role.nome != "super_admin":
        raise HTTPException(
            status_code=403,
            detail="Apenas outro super_admin pode alterar um super_admin.",
        )

    status_obj = db.query(Status).filter(Status.nome == body.novo_status).first()
    if not status_obj:
        raise HTTPException(status_code=404, detail="Status não encontrado no banco.")

    usuario.status_id = status_obj.id
    db.commit()

    return MensagemResponse(
        mensagem=f"Status do usuário alterado para {body.novo_status} com sucesso."
    )


def svc_change_user_role(
    user_id: UUID, body: ChangeRoleRequest, admin_user: User, db: Session
) -> MensagemResponse:
    novo_role = db.query(Role).filter(Role.nome == body.role_nome).first()
    if not novo_role:
        raise HTTPException(
            status_code=400,
            detail=f"Cargo '{body.role_nome}' inválido. Valores aceitos: 'super_admin', 'admin', 'aluno'.",
        )

    usuario = db.query(User).filter(User.id == user_id).first()
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")

    if usuario.status.nome != "ativo":
        raise HTTPException(
            status_code=400,
            detail="Só é possível alterar o cargo de usuários com status ativo.",
        )

    if usuario.id == admin_user.id:
        raise HTTPException(
            status_code=403,
            detail="Você não pode alterar o seu próprio cargo. Peça a outro administrador.",
        )

    if usuario.role.nome == "super_admin" and admin_user.role.nome != "super_admin":
        raise HTTPException(
            status_code=403,
            detail="Apenas um super_admin pode alterar o cargo de outro super_admin.",
        )

    roles_admin = db.query(Role.id).filter(Role.nome.in_(["admin", "super_admin"]))
    status_ativo = db.query(Status.id).filter(Status.nome == "ativo").scalar()

    if usuario.role.nome in ["admin", "super_admin"] and body.role_nome not in [
        "admin",
        "super_admin",
    ]:
        total_admins_ativos = (
            db.query(func.count(User.id))
            .filter(
                User.global_role.in_(roles_admin.subquery().select()),
                User.status_id == status_ativo,
            )
            .scalar()
        )
        if total_admins_ativos <= 1:
            raise HTTPException(
                status_code=409,
                detail="Operação negada. O sistema deve ter pelo menos um administrador ativo.",
            )

    usuario.global_role = novo_role.id
    db.commit()

    return MensagemResponse(
        mensagem=f"Cargo do usuário alterado para '{body.role_nome}' com sucesso.",
    )


def svc_delete_user_by_admin(user_id: UUID, db: Session) -> MensagemResponse:
    usuario = db.query(User).filter(User.id == user_id).first()
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")

    inativo_status = db.query(Status).filter(Status.nome == "inativo").first()
    usuario.status_id = inativo_status.id
    db.commit()

    return MensagemResponse(mensagem="Usuário excluído (inativado) com sucesso.")
