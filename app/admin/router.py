from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.admin.schemas import (
    ChangeRoleRequest,
    ChangeStatusRequest,
    UsuarioListResponse,
)
from app.admin.service import (
    svc_change_user_role,
    svc_change_user_status,
    svc_delete_user_by_admin,
    svc_list_all_users,
    svc_list_pending_users,
)
from app.core.schemas import MensagemResponse
from app.database import get_db
from app.deps import require_role
from app.models.user import User
from app.users.schemas import UsuarioCompleto

router = APIRouter(
    prefix="/admin",
    tags=["Administração"],
)


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
    status_filtro: str | None = Query(
        None,
        alias="status",
        description="Filtrar por status: 'ativo', 'pendente', 'inativo'.",
    ),
    role_filtro: str | None = Query(
        None,
        alias="role",
        description="Filtrar por cargo: 'super_admin', 'admin', 'usuario'.",
    ),
    busca: str | None = Query(
        None, description="Busca por nome ou e-mail (case-insensitive)."
    ),
    admin_user: User = Depends(require_role(["super_admin", "admin"])),
    db: Session = Depends(get_db),
) -> Any:
    return svc_list_all_users(pagina, limite, status_filtro, role_filtro, busca, db)


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
    return svc_list_pending_users(db)


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
    return svc_change_user_status(user_id, body, admin_user, db)


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
    return svc_change_user_role(user_id, body, admin_user, db)


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
    return svc_delete_user_by_admin(user_id, db)
