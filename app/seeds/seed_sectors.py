import uuid

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.sector import Sector

SECTORS = [
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


def seed_sectors():
    """Insere os setores padrão se eles não existirem."""
    db: Session = SessionLocal()
    try:
        for s_data in SECTORS:
            setor = db.query(Sector).filter(Sector.nome == s_data["nome"]).first()
            if not setor:
                novo_setor = Sector(
                    id=s_data["id"],
                    nome=s_data["nome"],
                    descricao=s_data["descricao"],
                )
                db.add(novo_setor)
                print(f"Setor '{s_data['nome']}' inserido.")
            else:
                print(f"Setor '{s_data['nome']}' já existe.")
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    print("Executando seed de setores...")
    seed_sectors()
    print("Seed finalizado.")
