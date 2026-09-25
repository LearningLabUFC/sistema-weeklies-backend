"""Router — Rotas de Setores."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.schemas import MensagemResponse
from app.database import get_db
from app.deps import require_role
from app.models.user import User
from app.sectors.schemas import (
    AddMemberRequest,
    ChangeMemberRoleRequest,
    CreateSectorRequest,
    SectorDetail,
    SectorListResponse,
    UpdateSectorRequest,
)
from app.sectors.service import (
    svc_add_member,
    svc_change_member_role,
    svc_create_sector,
    svc_delete_sector,
    svc_get_sector_detail,
    svc_list_sectors,
    svc_remove_member,
    svc_update_sector,
)

router = APIRouter(
    prefix="/sectors",
    tags=["Setores"],
)


# ── CRUD de Setores ──────────────────────────────────────────


@router.post(
    "",
    response_model=MensagemResponse,
    status_code=201,
    summary="Criar um novo setor",
    description="Cria um novo setor no sistema. Acessível para admins e super_admins.",
)
async def create_sector(
    body: CreateSectorRequest,
    admin_user: User = Depends(require_role(["super_admin", "admin"])),
    db: Session = Depends(get_db),
) -> Any:
    return svc_create_sector(body, db)


@router.get(
    "",
    response_model=SectorListResponse,
    status_code=200,
    summary="Listar todos os setores (paginado)",
    description=(
        "Retorna a lista de setores cadastrados com paginação e contagem "
        "de membros e líderes. Acessível para todos os usuários autenticados."
    ),
)
async def list_sectors(
    pagina: int = Query(1, ge=1, description="Número da página (1-indexed)."),
    limite: int = Query(20, ge=1, le=100, description="Itens por página (máx. 100)."),
    user: User = Depends(require_role(["super_admin", "admin", "usuario"])),
    db: Session = Depends(get_db),
) -> Any:
    return svc_list_sectors(pagina, limite, db)


@router.get(
    "/{sector_id}",
    response_model=SectorDetail,
    status_code=200,
    summary="Detalhar um setor",
    description="Retorna os dados do setor com a lista completa de membros e líderes.",
)
async def get_sector_detail(
    sector_id: UUID,
    admin_user: User = Depends(require_role(["super_admin", "admin"])),
    db: Session = Depends(get_db),
) -> Any:
    return svc_get_sector_detail(sector_id, db)


@router.patch(
    "/{sector_id}",
    response_model=MensagemResponse,
    status_code=200,
    summary="Atualizar um setor",
    description="Atualiza nome, descrição ou status de ativação de um setor.",
)
async def update_sector(
    sector_id: UUID,
    body: UpdateSectorRequest,
    admin_user: User = Depends(require_role(["super_admin", "admin"])),
    db: Session = Depends(get_db),
) -> Any:
    return svc_update_sector(sector_id, body, db)


@router.delete(
    "/{sector_id}",
    response_model=MensagemResponse,
    status_code=200,
    summary="Desativar um setor (soft delete)",
    description="Desativa um setor no sistema. Apenas super_admins podem acessar.",
)
async def delete_sector(
    sector_id: UUID,
    super_admin: User = Depends(require_role(["super_admin"])),
    db: Session = Depends(get_db),
) -> Any:
    return svc_delete_sector(sector_id, db)


# ── Gestão de Membros ────────────────────────────────────────


@router.post(
    "/{sector_id}/members",
    response_model=MensagemResponse,
    status_code=201,
    summary="Adicionar um usuário ao setor",
    description="Adiciona um usuário como membro ou líder de um setor.",
)
async def add_member(
    sector_id: UUID,
    body: AddMemberRequest,
    admin_user: User = Depends(require_role(["super_admin", "admin"])),
    db: Session = Depends(get_db),
) -> Any:
    return svc_add_member(sector_id, body, db)


@router.delete(
    "/{sector_id}/members/{user_id}",
    response_model=MensagemResponse,
    status_code=200,
    summary="Remover um usuário do setor",
    description="Remove a associação de um usuário com um setor.",
)
async def remove_member(
    sector_id: UUID,
    user_id: UUID,
    admin_user: User = Depends(require_role(["super_admin", "admin"])),
    db: Session = Depends(get_db),
) -> Any:
    return svc_remove_member(sector_id, user_id, db)


@router.patch(
    "/{sector_id}/members/{user_id}/role",
    response_model=MensagemResponse,
    status_code=200,
    summary="Alterar o papel de um usuário no setor",
    description="Altera o papel de um usuário dentro de um setor (lider ↔ membro).",
)
async def change_member_role(
    sector_id: UUID,
    user_id: UUID,
    body: ChangeMemberRoleRequest,
    admin_user: User = Depends(require_role(["super_admin", "admin"])),
    db: Session = Depends(get_db),
) -> Any:
    return svc_change_member_role(sector_id, user_id, body, db)
