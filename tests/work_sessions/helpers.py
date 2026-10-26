"""Helpers compartilhados pelos testes de work sessions."""

from uuid import UUID

from app.core.constants import StatusID, TestID
from app.models.sector_user import SectorUser
from app.models.user import User
from app.models.work_session import WorkSession


def _registrar_e_logar(
    client,
    db_session,
    email: str,
    matricula: str,
    role_id,
):
    """Registra, ativa, define o papel global e autentica um usuário."""
    payload = {
        "nome_completo": f"Teste {email.split('@')[0].title()}",
        "email": email,
        "senha": "SenhaForte123!",
        "matricula": matricula,
        "data_nascimento": "2000-01-01",
        "meta_horas_semanais": 12,
        "curso_id": str(TestID.CURSO_TESTE),
    }

    client.post("/auth/register", json=payload)

    user = (
        db_session.query(User)
        .filter(User.email == email)
        .first()
    )
    user.status_id = StatusID.ATIVO
    user.global_role = role_id
    db_session.commit()

    response = client.post(
        "/auth/login",
        json={
            "email": email,
            "senha": "SenhaForte123!",
        },
    )

    return user, response.json()["token_acesso"]

def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
    }

def _adicionar_ao_setor(
    db_session,
    usuario: User,
    papel: str = "membro",
) -> SectorUser:
    vinculo = SectorUser(
        setor_id=TestID.SETOR_TESTE,
        usuario_id=usuario.id,
        papel=papel,
    )
    db_session.add(vinculo)
    db_session.commit()
    db_session.refresh(vinculo)
    return vinculo

def _buscar_sessao(
    db_session,
    session_id: str,
) -> WorkSession:
    return (
        db_session.query(WorkSession)
        .filter(
            WorkSession.id == UUID(session_id),
        )
        .first()
    )

