"""
Script utilitário de desenvolvimento — Seed de Personas e Setores.

Popula o banco local com um conjunto enxuto e estratégico de usuários,
setores e vínculos cobrindo a matriz de permissões do sistema
(cargo global × vínculo no setor × status da conta).

Segurança e garantias:
- Isolado em scripts/ (nunca executado automaticamente no startup).
- Trava dupla de ambiente: bloqueia execução se ENVIRONMENT/APP_ENV não for
  de desenvolvimento ou se o host do banco não for local.
- 100% idempotente: pode ser executado múltiplas vezes sem duplicar registros.
- Domínio dedicado (@dev.learninglab.com.br): compatível com EmailStr do
  Pydantic e isolado para remoção segura via --clean / --reset.

Uso:
    python scripts/seed_dev.py           # Cria personas e vínculos faltantes
    python scripts/seed_dev.py --reset   # Remove mocks existentes e recria do zero
    python scripts/seed_dev.py --clean   # Remove apenas os dados de mock
"""

from __future__ import annotations

import argparse
import os
import sys
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone

from sqlalchemy import or_
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

# Adiciona o diretório raiz ao path para permitir importar o pacote app
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings
from app.core.constants import RoleID, RoleName, StatusID, StatusName
from app.core.security import hash_senha
from app.database import SessionLocal
from app.models.course import Course
from app.models.pause import Pause
from app.models.role import Role
from app.models.sector import Sector
from app.models.sector_user import SectorUser
from app.models.status import Status
from app.models.task import Task
from app.models.task_assignment import TaskAssignment
from app.models.user import User
from app.models.weekly import Weekly
from app.models.weekly_task import WeeklyTask
from app.models.weekly_warning import WeeklyWarning
from app.models.work_session import WorkSession

DEV_EMAIL_DOMAIN = "@dev.learninglab.com.br"
DEV_DEFAULT_PASSWORD = os.getenv("DEV_SEED_PASSWORD", "Dev@1234")
DEV_DEFAULT_COURSE_NAME = "Engenharia de Software"

ALLOWED_ENVS = {"development", "dev", "local", "test"}
ALLOWED_DB_HOSTS = {"localhost", "127.0.0.1", "::1", "db", "weeklies_db"}

BASE_ROLES = [
    (RoleID.SUPER_ADMIN, RoleName.SUPER_ADMIN),
    (RoleID.ADMIN, RoleName.ADMIN),
    (RoleID.USUARIO, RoleName.USUARIO),
]

BASE_STATUSES = [
    (StatusID.PENDENTE, StatusName.PENDENTE),
    (StatusID.ATIVO, StatusName.ATIVO),
    (StatusID.INATIVO, StatusName.INATIVO),
]

DEV_SECTORS = [
    {
        "id": uuid.UUID("4fa85f64-5717-4562-b3fc-2c963f66afa1"),
        "nome": "Desenvolvimento",
        "descricao": "Setor responsável pelo desenvolvimento de software.",
    },
    {
        "id": uuid.UUID("4fa85f64-5717-4562-b3fc-2c963f66afa2"),
        "nome": "Design",
        "descricao": "Setor responsável pelo design de interfaces e experiência do usuário.",
    },
]


@dataclass(frozen=True)
class PersonaSpec:
    """Especificação de uma persona de desenvolvimento."""

    nome_completo: str
    email_prefix: str
    matricula: str
    role_nome: str
    status_nome: str
    meta_horas_semanais: int
    vinculos: list[tuple[str, str]] = field(default_factory=list)  # (setor_nome, papel)
    descricao_cenario: str = ""

    @property
    def email(self) -> str:
        return f"{self.email_prefix}{DEV_EMAIL_DOMAIN}"


PERSONAS: list[PersonaSpec] = [
    PersonaSpec(
        nome_completo="Super Admin Dev",
        email_prefix="superadmin",
        matricula="990001",
        role_nome=RoleName.SUPER_ADMIN,
        status_nome=StatusName.ATIVO,
        meta_horas_semanais=0,
        vinculos=[],
        descricao_cenario="Gestão total; bloqueado para ponto e isento de weeklies",
    ),
    PersonaSpec(
        nome_completo="Admin Sem Setor",
        email_prefix="admin.semsetor",
        matricula="990002",
        role_nome=RoleName.ADMIN,
        status_nome=StatusName.ATIVO,
        meta_horas_semanais=0,
        vinculos=[],
        descricao_cenario="Admin global sem setor; acessa métricas, não bate ponto",
    ),
    PersonaSpec(
        nome_completo="Admin Lider Dev",
        email_prefix="admin.lider",
        matricula="990003",
        role_nome=RoleName.ADMIN,
        status_nome=StatusName.ATIVO,
        meta_horas_semanais=12,
        vinculos=[("Desenvolvimento", "lider")],
        descricao_cenario="Admin vinculado como líder; bate ponto e avalia weeklies",
    ),
    PersonaSpec(
        nome_completo="Admin Membro Dev",
        email_prefix="admin.membro",
        matricula="990004",
        role_nome=RoleName.ADMIN,
        status_nome=StatusName.ATIVO,
        meta_horas_semanais=12,
        vinculos=[("Desenvolvimento", "membro")],
        descricao_cenario="Admin vinculado como membro; bate ponto e envia weeklies",
    ),
    PersonaSpec(
        nome_completo="Lider Design Dev",
        email_prefix="lider",
        matricula="990005",
        role_nome=RoleName.USUARIO,
        status_nome=StatusName.ATIVO,
        meta_horas_semanais=12,
        vinculos=[("Design", "lider")],
        descricao_cenario="Usuário comum com papel de líder no setor Design",
    ),
    PersonaSpec(
        nome_completo="Membro Desenvolvimento Dev",
        email_prefix="membro",
        matricula="990006",
        role_nome=RoleName.USUARIO,
        status_nome=StatusName.ATIVO,
        meta_horas_semanais=12,
        vinculos=[("Desenvolvimento", "membro")],
        descricao_cenario="Membro padrão vinculado a um único setor",
    ),
    PersonaSpec(
        nome_completo="Usuario Multi Setores",
        email_prefix="multi",
        matricula="990007",
        role_nome=RoleName.USUARIO,
        status_nome=StatusName.ATIVO,
        meta_horas_semanais=16,
        vinculos=[("Desenvolvimento", "membro"), ("Design", "lider")],
        descricao_cenario="Membro em Desenvolvimento e líder em Design",
    ),
    PersonaSpec(
        nome_completo="Usuario Pendente Dev",
        email_prefix="pendente",
        matricula="990008",
        role_nome=RoleName.USUARIO,
        status_nome=StatusName.PENDENTE,
        meta_horas_semanais=12,
        vinculos=[],
        descricao_cenario="Conta aguardando aprovação de administrador",
    ),
    PersonaSpec(
        nome_completo="Usuario Inativo Dev",
        email_prefix="inativo",
        matricula="990009",
        role_nome=RoleName.USUARIO,
        status_nome=StatusName.INATIVO,
        meta_horas_semanais=12,
        vinculos=[("Design", "membro")],
        descricao_cenario="Conta inativada (login bloqueado e fora das obrigações)",
    ),
]


def validar_ambiente_seguro(
    database_url: str | None = None,
    environment: str | None = None,
) -> None:
    """
    Garante que o script nunca seja executado contra ambientes de produção/remotos.

    Levanta RuntimeError caso ENVIRONMENT/APP_ENV indique ambiente não-local
    ou o host da URL de conexão não pertença à lista de hosts locais permitidos.
    """
    env_atual = (
        environment
        if environment is not None
        else os.getenv("ENVIRONMENT") or os.getenv("APP_ENV") or "development"
    )
    env_normalizado = env_atual.strip().lower()

    if env_normalizado not in ALLOWED_ENVS:
        raise RuntimeError(
            f"Execução bloqueada: ambiente '{env_atual}' não é permitido para seed de mock. "
            f"Ambientes aceitos: {', '.join(sorted(ALLOWED_ENVS))}."
        )

    url_str = database_url or settings.DATABASE_URL
    parsed_url = make_url(url_str)

    # Bancos em arquivo/memória (ex: sqlite nos testes automatizados) não têm host remoto
    if parsed_url.get_backend_name() == "sqlite":
        return

    db_host = (parsed_url.host or "").strip().lower()
    if db_host not in ALLOWED_DB_HOSTS:
        raise RuntimeError(
            f"Execução bloqueada: host do banco '{db_host or '<vazio>'}' não é local. "
            f"Hosts permitidos: {', '.join(sorted(ALLOWED_DB_HOSTS))}."
        )


def _garantir_base_dominio(
    db: Session,
) -> tuple[dict[str, Role], dict[str, Status], dict[str, Sector], Course]:
    """Garante cargos, status, setores padrão e ao menos um curso ativo (idempotente)."""
    roles_map: dict[str, Role] = {}
    for role_id, role_nome in BASE_ROLES:
        role = db.query(Role).filter(Role.nome == role_nome).first()
        if not role:
            role = Role(id=role_id, nome=role_nome)
            db.add(role)
            db.flush()
        roles_map[role_nome] = role

    status_map: dict[str, Status] = {}
    for status_id, status_nome in BASE_STATUSES:
        status = db.query(Status).filter(Status.nome == status_nome).first()
        if not status:
            status = Status(id=status_id, nome=status_nome)
            db.add(status)
            db.flush()
        status_map[status_nome] = status

    sectors_map: dict[str, Sector] = {}
    for s_data in DEV_SECTORS:
        setor = db.query(Sector).filter(Sector.nome == s_data["nome"]).first()
        if not setor:
            id_em_uso = (
                db.query(Sector.id).filter(Sector.id == s_data["id"]).first()
            )
            setor_id = uuid.uuid4() if id_em_uso else s_data["id"]
            setor = Sector(
                id=setor_id,
                nome=s_data["nome"],
                descricao=s_data["descricao"],
                ativo=True,
            )
            db.add(setor)
            db.flush()
        sectors_map[s_data["nome"]] = setor

    curso = db.query(Course).filter(Course.ativo.is_(True)).first()
    if not curso:
        curso = Course(id=uuid.uuid4(), nome=DEV_DEFAULT_COURSE_NAME, ativo=True)
        db.add(curso)
        db.flush()

    return roles_map, status_map, sectors_map, curso


def clean_dev_data(db: Session) -> int:
    """
    Remove apenas os usuários do domínio de mock (@dev.learninglab.com.br)
    e seus registros dependentes criados durante testes manuais.
    """
    mock_users = (
        db.query(User)
        .filter(User.email.like(f"%{DEV_EMAIL_DOMAIN}"))
        .all()
    )
    if not mock_users:
        return 0

    user_ids = [u.id for u in mock_users]

    # Desvincula referências opcionais em registros de outros usuários
    db.query(Weekly).filter(Weekly.avaliada_por.in_(user_ids)).update(
        {Weekly.avaliada_por: None}, synchronize_session=False
    )
    db.query(Task).filter(Task.removida_por.in_(user_ids)).update(
        {Task.removida_por: None}, synchronize_session=False
    )

    # Pausas e sessões de trabalho dos usuários mock
    session_ids = [
        row[0]
        for row in db.query(WorkSession.id)
        .filter(WorkSession.usuario_id.in_(user_ids))
        .all()
    ]
    if session_ids:
        db.query(Pause).filter(
            Pause.sessao_trabalho_id.in_(session_ids)
        ).delete(synchronize_session=False)
        db.query(WorkSession).filter(
            WorkSession.id.in_(session_ids)
        ).delete(synchronize_session=False)

    # Tasks, atribuições, weeklies e advertências dos usuários mock
    task_ids = [
        row[0]
        for row in db.query(Task.id).filter(Task.usuario_id.in_(user_ids)).all()
    ]
    weekly_ids = [
        row[0]
        for row in db.query(Weekly.id).filter(Weekly.usuario_id.in_(user_ids)).all()
    ]

    if task_ids:
        db.query(Task).filter(Task.origem_task_id.in_(task_ids)).update(
            {Task.origem_task_id: None}, synchronize_session=False
        )
        db.query(TaskAssignment).filter(
            or_(
                TaskAssignment.task_id.in_(task_ids),
                TaskAssignment.solicitante_id.in_(user_ids),
                TaskAssignment.atribuido_id.in_(user_ids),
            )
        ).delete(synchronize_session=False)
        db.query(WeeklyTask).filter(WeeklyTask.task_id.in_(task_ids)).delete(
            synchronize_session=False
        )
    else:
        db.query(TaskAssignment).filter(
            or_(
                TaskAssignment.solicitante_id.in_(user_ids),
                TaskAssignment.atribuido_id.in_(user_ids),
            )
        ).delete(synchronize_session=False)

    if weekly_ids:
        db.query(WeeklyTask).filter(WeeklyTask.weekly_id.in_(weekly_ids)).delete(
            synchronize_session=False
        )
        db.query(Weekly).filter(Weekly.id.in_(weekly_ids)).delete(
            synchronize_session=False
        )

    if task_ids:
        db.query(Task).filter(Task.id.in_(task_ids)).delete(
            synchronize_session=False
        )

    db.query(WeeklyWarning).filter(WeeklyWarning.usuario_id.in_(user_ids)).delete(
        synchronize_session=False
    )
    db.query(SectorUser).filter(SectorUser.usuario_id.in_(user_ids)).delete(
        synchronize_session=False
    )
    db.query(User).filter(User.id.in_(user_ids)).delete(synchronize_session=False)

    db.commit()
    return len(user_ids)


def seed_dev_data(db: Session, *, reset: bool = False) -> dict[str, int]:
    """
    Popula as personas e vínculos de desenvolvimento de forma idempotente.

    Se `reset=True`, limpa antes todos os mocks existentes para restaurar
    senhas, status, cargos e vínculos ao estado original.
    """
    removidos = clean_dev_data(db) if reset else 0

    roles_map, status_map, sectors_map, curso = _garantir_base_dominio(db)
    senha_hash_padrao = hash_senha(DEV_DEFAULT_PASSWORD)
    hoje = datetime.now(tz=timezone.utc).date()

    criados = 0
    existentes = 0
    vinculos_criados = 0

    for spec in PERSONAS:
        usuario = db.query(User).filter(User.email == spec.email).first()

        if usuario is None:
            # Evita colisão caso a matrícula de mock já tenha sido usada manualmente
            conflito_matricula = (
                db.query(User).filter(User.matricula == spec.matricula).first()
            )
            if conflito_matricula is not None:
                raise RuntimeError(
                    f"Matrícula {spec.matricula} já está em uso por '{conflito_matricula.email}'."
                )

            usuario = User(
                nome_completo=spec.nome_completo,
                email=spec.email,
                senha_hash=senha_hash_padrao,
                matricula=spec.matricula,
                data_nascimento=date(2000, 1, 15),
                data_ingresso=hoje,
                meta_horas_semanais=spec.meta_horas_semanais,
                foto_perfil="avatar_padrao.png",
                curso_id=curso.id,
                status_id=status_map[spec.status_nome].id,
                global_role=roles_map[spec.role_nome].id,
            )
            db.add(usuario)
            db.flush()
            criados += 1
        else:
            existentes += 1

        for setor_nome, papel in spec.vinculos:
            setor = sectors_map[setor_nome]
            vinculo = (
                db.query(SectorUser)
                .filter(
                    SectorUser.setor_id == setor.id,
                    SectorUser.usuario_id == usuario.id,
                )
                .first()
            )
            if vinculo is None:
                db.add(
                    SectorUser(
                        setor_id=setor.id,
                        usuario_id=usuario.id,
                        papel=papel,
                        data_ingresso=hoje,
                    )
                )
                vinculos_criados += 1

    db.commit()
    return {
        "removidos": removidos,
        "criados": criados,
        "existentes": existentes,
        "vinculos_criados": vinculos_criados,
    }


def _imprimir_resumo(stats: dict[str, int]) -> None:
    """Exibe no terminal o resumo da operação e a tabela de credenciais."""
    print("\n✅ Seed de desenvolvimento concluído!")
    if stats["removidos"]:
        print(f"   • Mocks antigos removidos (--reset): {stats['removidos']}")
    print(
        f"   • Usuários criados: {stats['criados']} | "
        f"Já existentes: {stats['existentes']} | "
        f"Novos vínculos: {stats['vinculos_criados']}"
    )
    print(f"\n🔑 Senha padrão de todas as personas: {DEV_DEFAULT_PASSWORD}\n")

    cabecalho = (
        f"{'E-MAIL':<38} {'CARGO':<13} {'STATUS':<10} {'SETORES (PAPEL)':<34}"
    )
    print(cabecalho)
    print("─" * len(cabecalho))
    for spec in PERSONAS:
        vinculos_fmt = (
            ", ".join(f"{s} ({p})" for s, p in spec.vinculos)
            if spec.vinculos
            else "—"
        )
        print(
            f"{spec.email:<38} {spec.role_nome:<13} "
            f"{spec.status_nome:<10} {vinculos_fmt:<34}"
        )
    print()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Gerencia personas de mock para desenvolvimento local."
    )
    grupo = parser.add_mutually_exclusive_group()
    grupo.add_argument(
        "--clean",
        action="store_true",
        help=f"Remove todos os usuários *{DEV_EMAIL_DOMAIN} e registros vinculados.",
    )
    grupo.add_argument(
        "--reset",
        action="store_true",
        help="Remove os mocks atuais e recria todas as personas do zero.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    try:
        validar_ambiente_seguro()
    except RuntimeError as exc:
        print(f"❌ {exc}")
        sys.exit(1)

    db = SessionLocal()
    try:
        if args.clean:
            removidos = clean_dev_data(db)
            print(
                f"🧹 Limpeza concluída: {removidos} usuário(s) *{DEV_EMAIL_DOMAIN} removido(s)."
            )
            return

        stats = seed_dev_data(db, reset=args.reset)
        _imprimir_resumo(stats)
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        print(f"❌ Erro ao executar seed de desenvolvimento: {exc}")
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
