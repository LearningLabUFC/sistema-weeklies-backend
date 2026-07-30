"""
Router — Administração do Sistema

Endpoints protegidos para gerenciamento de usuários.
Exigem cargo (role) de 'admin' ou 'super_admin'.
"""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_role
from app.models.user import User
from app.models.status import Status
from app.models.role import Role
from app.schemas import MensagemResponse, UsuarioCompleto

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
    novo_status: str, # "ativo", "inativo" etc. passado via query param, ou deveria ser body? Vou usar query por simplicidade.
    admin_user: User = Depends(require_role(["super_admin", "admin"])),
    db: Session = Depends(get_db),
) -> Any:
    if novo_status not in ["ativo", "inativo"]:
        raise HTTPException(status_code=400, detail="Status inválido. Escolha 'ativo' ou 'inativo'.")
    
    usuario = db.query(User).filter(User.id == user_id).first()
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
    
    # Impedir que um admin altere um super_admin
    if usuario.role.nome == "super_admin" and admin_user.role.nome != "super_admin":
        raise HTTPException(status_code=403, detail="Apenas outro super_admin pode alterar um super_admin.")

    status_obj = db.query(Status).filter(Status.nome == novo_status).first()
    if not status_obj:
        raise HTTPException(status_code=404, detail="Status não encontrado no banco.")

    usuario.status_id = status_obj.id
    db.commit()

    return MensagemResponse(mensagem=f"Status do usuário alterado para {novo_status} com sucesso.")


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
