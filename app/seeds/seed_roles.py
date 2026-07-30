import uuid

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.role import Role

ROLES = [
    {"id": uuid.UUID("2fa85f64-5717-4562-b3fc-2c963f66afa1"), "nome": "super_admin"},
    {"id": uuid.UUID("2fa85f64-5717-4562-b3fc-2c963f66afa2"), "nome": "admin"},
    {"id": uuid.UUID("2fa85f64-5717-4562-b3fc-2c963f66afa3"), "nome": "aluno"},
]

def seed_roles():
    """Insere os cargos (roles) padrão se eles não existirem."""
    db: Session = SessionLocal()
    try:
        for r_data in ROLES:
            role = db.query(Role).filter(Role.nome == r_data["nome"]).first()
            if not role:
                novo_role = Role(id=r_data["id"], nome=r_data["nome"])
                db.add(novo_role)
                print(f"Cargo '{r_data['nome']}' inserido.")
            else:
                print(f"Cargo '{r_data['nome']}' já existe.")
        db.commit()
    finally:
        db.close()

if __name__ == "__main__":
    print("Executando seed de cargos (roles)...")
    seed_roles()
    print("Seed finalizado.")
