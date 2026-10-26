from sqlalchemy.orm import Session

from app.core.constants import RoleID, RoleName
from app.database import SessionLocal
from app.models.role import Role

ROLES = [
    {"id": RoleID.SUPER_ADMIN, "nome": RoleName.SUPER_ADMIN},
    {"id": RoleID.ADMIN, "nome": RoleName.ADMIN},
    {"id": RoleID.USUARIO, "nome": RoleName.USUARIO},
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
