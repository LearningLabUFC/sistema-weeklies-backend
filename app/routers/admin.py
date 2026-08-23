"""
Router — Administração do Sistema

Endpoints protegidos para gerenciamento de usuários.
Exigem cargo (role) de 'admin' ou 'super_admin'.
"""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_role
from app.models.role import Role
from app.models.status import Status
from app.models.user import User
from app.schemas import (
    ChangeRoleRequest,
    ChangeStatusRequest,
    MensagemResponse,
    UsuarioCompleto,
    UsuarioListItem,
    UsuarioListResponse,
)

router = APIRouter(
    prefix="/admin",
    tags=["Administração"],
)

def _build_usuario_completo(usuario: User) -> UsuarioCompleto:
    """Helper para serialização."""
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


# ── GET /admin/users ────────────────────────────────────────
@router.get(
    "/users",
    response_model=UsuarioListResponse,
    status_code=200,
    summary="Listar todos os usuários (paginado e filtrável)",
    description=(
        "Retorna a lista completa de usuários cadastrados com paginação, "
        "filtros por status e cargo, e busca por nome ou e-mail. "
        "Acessível para admins e super_admins."
    ),
)
async def list_all_users(
    pagina: int = Query(1, ge=1, description="Número da página (1-indexed)."),
    limite: int = Query(20, ge=1, le=100, description="Itens por página (máx. 100)."),
    status_filtro: str | None = Query(None, alias="status", description="Filtrar por status: 'ativo', 'pendente', 'inativo'."),
    role_filtro: str | None = Query(None, alias="role", description="Filtrar por cargo: 'super_admin', 'admin', 'aluno'."),
    busca: str | None = Query(None, description="Busca por nome ou e-mail (case-insensitive)."),
    admin_user: User = Depends(require_role(["super_admin", "admin"])),
    db: Session = Depends(get_db),
) -> Any:
    query = db.query(User)

    # Filtro por status
    if status_filtro:
        query = query.join(Status, User.status_id == Status.id).filter(
            Status.nome == status_filtro
        )

    # Filtro por cargo
    if role_filtro:
        query = query.join(Role, User.global_role == Role.id).filter(
            Role.nome == role_filtro
        )

    # Busca por nome ou e-mail (case-insensitive)
    if busca:
        termo = f"%{busca}%"
        query = query.filter(
            (func.lower(User.nome_completo).like(func.lower(termo)))
            | (func.lower(User.email).like(func.lower(termo)))
        )

    total = query.count()
    offset = (pagina - 1) * limite
    usuarios = query.order_by(User.nome_completo.asc()).offset(offset).limit(limite).all()

    return UsuarioListResponse(
        usuarios=[_build_usuario_list_item(u) for u in usuarios],
        total=total,
        pagina=pagina,
        limite=limite,
    )


# ── GET /admin/users/pending ────────────────────────────────
@router.get(
    "/users/pending",
    response_model=list[UsuarioCompleto],
    status_code=200,
    summary="Listar usuários pendentes",
    description="Lista todos os usuários que estão aguardando aprovação (status = pendente). Acessível para admins e super_admins.",
)
async def list_pending_users(
    admin_user: User = Depends(require_role(["super_admin", "admin"])),
    db: Session = Depends(get_db),
) -> Any:
    pendentes = db.query(User).join(Status).filter(Status.nome == "pendente").all()
    return [_build_usuario_completo(u) for u in pendentes]


# ── PATCH /admin/users/{user_id}/status ─────────────────────
@router.patch(
    "/users/{user_id}/status",
    response_model=MensagemResponse,
    status_code=200,
    summary="Aprovar ou rejeitar um usuário",
    description="Altera o status de um usuário. Útil para aprovar (ativo) ou rejeitar (inativo) usuários pendentes.",
)
async def change_user_status(
    user_id: UUID,
    body: ChangeStatusRequest,
    admin_user: User = Depends(require_role(["super_admin", "admin"])),
    db: Session = Depends(get_db),
) -> Any:
    if body.novo_status not in ["ativo", "inativo"]:
        raise HTTPException(status_code=400, detail="Status inválido. Escolha 'ativo' ou 'inativo'.")
    
    usuario = db.query(User).filter(User.id == user_id).first()
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
    
    # Impedir que um admin altere um super_admin
    if usuario.role.nome == "super_admin" and admin_user.role.nome != "super_admin":
        raise HTTPException(status_code=403, detail="Apenas outro super_admin pode alterar um super_admin.")

    status_obj = db.query(Status).filter(Status.nome == body.novo_status).first()
    if not status_obj:
        raise HTTPException(status_code=404, detail="Status não encontrado no banco.")

    usuario.status_id = status_obj.id
    db.commit()

    return MensagemResponse(mensagem=f"Status do usuário alterado para {body.novo_status} com sucesso.")


# ── PATCH /admin/users/{user_id}/role ───────────────────────
@router.patch(
    "/users/{user_id}/role",
    response_model=MensagemResponse,
    status_code=200,
    summary="Alterar o cargo de um usuário",
    description=(
        "Altera o cargo (role) de um usuário. Inclui proteção contra "
        "auto-rebaixamento e impede que o último admin do sistema seja rebaixado."
    ),
)
async def change_user_role(
    user_id: UUID,
    body: ChangeRoleRequest,
    admin_user: User = Depends(require_role(["super_admin", "admin"])),
    db: Session = Depends(get_db),
) -> Any:
    # Validar que o cargo solicitado existe no banco
    novo_role = db.query(Role).filter(Role.nome == body.role_nome).first()
    if not novo_role:
        raise HTTPException(
            status_code=400,
            detail=f"Cargo '{body.role_nome}' inválido. Valores aceitos: 'super_admin', 'admin', 'aluno'.",
        )

    # Buscar o usuário alvo
    usuario = db.query(User).filter(User.id == user_id).first()
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")

    if usuario.status.nome != "ativo":
        raise HTTPException(
            status_code=400,
            detail="Só é possível alterar o cargo de usuários com status ativo.",
        )

    # Impedir que o admin altere o próprio cargo
    if usuario.id == admin_user.id:
        raise HTTPException(
            status_code=403,
            detail="Você não pode alterar o seu próprio cargo. Peça a outro administrador.",
        )

    # Apenas super_admin pode alterar outro super_admin
    if usuario.role.nome == "super_admin" and admin_user.role.nome != "super_admin":
        raise HTTPException(
            status_code=403,
            detail="Apenas um super_admin pode alterar o cargo de outro super_admin.",
        )

    # Proteção do último admin: impedir que fique sem nenhum admin/super_admin ativo
    roles_admin = db.query(Role.id).filter(Role.nome.in_(["admin", "super_admin"]))
    status_ativo = db.query(Status.id).filter(Status.nome == "ativo").scalar()

    if (
        usuario.role.nome in ["admin", "super_admin"]
        and body.role_nome not in ["admin", "super_admin"]
    ):
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

    # Atualizar o cargo
    usuario.global_role = novo_role.id
    db.commit()

    return MensagemResponse(
        mensagem=f"Cargo do usuário alterado para '{body.role_nome}' com sucesso.",
    )


# ── DELETE /admin/users/{user_id} ───────────────────────────
@router.delete(
    "/users/{user_id}",
    response_model=MensagemResponse,
    status_code=200,
    summary="Excluir (soft delete) um admin ou usuário",
    description="Deleta (inativa) qualquer usuário do sistema. Apenas super_admins podem acessar.",
)
async def delete_user_by_admin(
    user_id: UUID,
    super_admin: User = Depends(require_role(["super_admin"])),
    db: Session = Depends(get_db),
) -> Any:
    usuario = db.query(User).filter(User.id == user_id).first()
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
    
    inativo_status = db.query(Status).filter(Status.nome == "inativo").first()
    usuario.status_id = inativo_status.id
    db.commit()

    return MensagemResponse(mensagem="Usuário excluído (inativado) com sucesso.")
