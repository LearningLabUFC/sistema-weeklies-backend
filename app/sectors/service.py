"""Service — Lógica de negócios de Setores."""

from uuid import UUID

from sqlalchemy.orm import Session

from app.core.exceptions import BadRequestError, ConflictError, NotFoundError
from app.core.schemas import MensagemResponse
from app.models.sector import Sector
from app.models.sector_user import SectorUser
from app.sectors.repository import (
    add_member_to_sector,
    count_leaders_by_sector,
    count_members_by_sector,
    create_sector,
    find_sector_by_id,
    find_sector_by_name,
    find_sector_user,
    find_user_by_id,
    list_sector_members,
    list_sectors_paginated,
    remove_member_from_sector,
    update_sector,
)
from app.sectors.schemas import (
    AddMemberRequest,
    ChangeMemberRoleRequest,
    CreateSectorRequest,
    SectorDetail,
    SectorListItem,
    SectorListResponse,
    SectorMemberItem,
    UpdateSectorRequest,
)

PAPEIS_VALIDOS = ["lider", "membro"]


# ── CRUD de Setores ──────────────────────────────────────────


def svc_create_sector(
    body: CreateSectorRequest, db: Session
) -> MensagemResponse:
    existente = find_sector_by_name(db, body.nome)
    if existente:
        raise ConflictError(f"Já existe um setor com o nome '{body.nome}'.")

    novo_setor = Sector(
        nome=body.nome,
        descricao=body.descricao,
    )
    create_sector(db, novo_setor)

    return MensagemResponse(
        mensagem=f"Setor '{body.nome}' criado com sucesso.",
    )


def svc_list_sectors(
    pagina: int, limite: int, db: Session
) -> SectorListResponse:
    setores, total = list_sectors_paginated(db, pagina, limite)

    items = []
    for setor in setores:
        items.append(
            SectorListItem(
                id=setor.id,
                nome=setor.nome,
                descricao=setor.descricao,
                ativo=setor.ativo,
                criado_em=setor.criado_em,
                qtd_membros=count_members_by_sector(db, setor.id),
                qtd_lideres=count_leaders_by_sector(db, setor.id),
            )
        )

    return SectorListResponse(
        setores=items,
        total=total,
        pagina=pagina,
        limite=limite,
    )


def svc_get_sector_detail(sector_id: UUID, db: Session) -> SectorDetail:
    setor = find_sector_by_id(db, sector_id)
    if not setor:
        raise NotFoundError("Setor não encontrado.")

    associacoes = list_sector_members(db, sector_id)
    membros = []
    for assoc in associacoes:
        usuario = assoc.usuario
        membros.append(
            SectorMemberItem(
                id=usuario.id,
                nome_completo=usuario.nome_completo,
                email=usuario.email,
                papel=assoc.papel,
            )
        )

    return SectorDetail(
        id=setor.id,
        nome=setor.nome,
        descricao=setor.descricao,
        ativo=setor.ativo,
        criado_em=setor.criado_em,
        membros=membros,
    )


def svc_update_sector(
    sector_id: UUID, body: UpdateSectorRequest, db: Session
) -> MensagemResponse:
    setor = find_sector_by_id(db, sector_id)
    if not setor:
        raise NotFoundError("Setor não encontrado.")

    if body.nome is not None and body.nome != setor.nome:
        existente = find_sector_by_name(db, body.nome)
        if existente:
            raise ConflictError(f"Já existe um setor com o nome '{body.nome}'.")
        setor.nome = body.nome

    if body.descricao is not None:
        setor.descricao = body.descricao

    if body.ativo is not None:
        setor.ativo = body.ativo

    update_sector(db)

    return MensagemResponse(mensagem="Setor atualizado com sucesso.")


def svc_delete_sector(sector_id: UUID, db: Session) -> MensagemResponse:
    setor = find_sector_by_id(db, sector_id)
    if not setor:
        raise NotFoundError("Setor não encontrado.")

    setor.ativo = False
    update_sector(db)

    return MensagemResponse(mensagem="Setor desativado com sucesso.")


# ── Gestão de Membros ────────────────────────────────────────


def svc_add_member(
    sector_id: UUID, body: AddMemberRequest, db: Session
) -> MensagemResponse:
    setor = find_sector_by_id(db, sector_id)
    if not setor:
        raise NotFoundError("Setor não encontrado.")

    if body.papel not in PAPEIS_VALIDOS:
        raise BadRequestError(
            f"Papel '{body.papel}' inválido. Valores aceitos: 'lider', 'membro'.",
        )

    usuario = find_user_by_id(db, body.usuario_id)
    if not usuario:
        raise NotFoundError("Usuário não encontrado.")

    existente = find_sector_user(db, sector_id, body.usuario_id)
    if existente:
        raise ConflictError("Este usuário já está associado a este setor.")

    associacao = SectorUser(
        setor_id=sector_id,
        usuario_id=body.usuario_id,
        papel=body.papel,
    )
    add_member_to_sector(db, associacao)

    return MensagemResponse(
        mensagem=f"Usuário adicionado ao setor como '{body.papel}' com sucesso.",
    )


def svc_remove_member(
    sector_id: UUID, user_id: UUID, db: Session
) -> MensagemResponse:
    setor = find_sector_by_id(db, sector_id)
    if not setor:
        raise NotFoundError("Setor não encontrado.")

    associacao = find_sector_user(db, sector_id, user_id)
    if not associacao:
        raise NotFoundError("Usuário não está associado a este setor.")

    remove_member_from_sector(db, associacao)

    return MensagemResponse(mensagem="Usuário removido do setor com sucesso.")


def svc_change_member_role(
    sector_id: UUID,
    user_id: UUID,
    body: ChangeMemberRoleRequest,
    db: Session,
) -> MensagemResponse:
    setor = find_sector_by_id(db, sector_id)
    if not setor:
        raise NotFoundError("Setor não encontrado.")

    if body.papel not in PAPEIS_VALIDOS:
        raise BadRequestError(
            f"Papel '{body.papel}' inválido. Valores aceitos: 'lider', 'membro'.",
        )

    associacao = find_sector_user(db, sector_id, user_id)
    if not associacao:
        raise NotFoundError("Usuário não está associado a este setor.")

    if associacao.papel == body.papel:
        raise BadRequestError(
            f"O usuário já possui o papel '{body.papel}' neste setor.",
        )

    associacao.papel = body.papel
    update_sector(db)

    return MensagemResponse(
        mensagem=f"Papel do usuário alterado para '{body.papel}' com sucesso.",
    )
