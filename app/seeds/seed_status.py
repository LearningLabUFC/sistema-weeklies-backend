from sqlalchemy.orm import Session

from app.core.constants import StatusID, StatusName
from app.database import SessionLocal
from app.models.status import Status

STATUSES = [
    {"id": StatusID.PENDENTE, "nome": StatusName.PENDENTE},
    {"id": StatusID.ATIVO, "nome": StatusName.ATIVO},
    {"id": StatusID.INATIVO, "nome": StatusName.INATIVO},
]


def seed_statuses():
    """Insere os status padrão se eles não existirem."""
    db: Session = SessionLocal()
    try:
        for s_data in STATUSES:
            status = db.query(Status).filter(Status.nome == s_data["nome"]).first()
            if not status:
                novo_status = Status(id=s_data["id"], nome=s_data["nome"])
                db.add(novo_status)
                print(f"Status '{s_data['nome']}' inserido.")
            else:
                print(f"Status '{s_data['nome']}' já existe.")
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    print("Executando seed de status...")
    seed_statuses()
    print("Seed finalizado.")
