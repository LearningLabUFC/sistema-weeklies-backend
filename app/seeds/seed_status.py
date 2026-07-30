import uuid

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.status import Status

STATUSES = [
    {"id": uuid.UUID("1fa85f64-5717-4562-b3fc-2c963f66afa1"), "nome": "pendente"},
    {"id": uuid.UUID("1fa85f64-5717-4562-b3fc-2c963f66afa2"), "nome": "ativo"},
    {"id": uuid.UUID("1fa85f64-5717-4562-b3fc-2c963f66afa3"), "nome": "inativo"},
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
