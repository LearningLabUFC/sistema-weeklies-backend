import os
import sys
import uuid
from datetime import date

# Adiciona o diretório raiz ao path para poder importar o app
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models.user import User
from app.models.role import Role
from app.models.status import Status
from app.models.course import Course
from app.utils.security import hash_senha

def create_super_admin():
    db = SessionLocal()
    try:
        # Verificar se já existe algum super_admin
        super_admin_role = db.query(Role).filter(Role.nome == "super_admin").first()
        if not super_admin_role:
            print("❌ Erro: Cargo 'super_admin' não encontrado no banco. Rode o seed de cargos primeiro.")
            return

        admin_existente = db.query(User).filter(User.global_role == super_admin_role.id).first()
        if admin_existente:
            print(f"⚠️ Já existe um super_admin no sistema: {admin_existente.email}")
            return

        # Obter status ativo
        status_ativo = db.query(Status).filter(Status.nome == "ativo").first()
        if not status_ativo:
            print("❌ Erro: Status 'ativo' não encontrado. Rode o seed de status primeiro.")
            return

        # Precisamos de um curso padrão para associar ao usuário
        curso = db.query(Course).first()
        if not curso:
            print("⚠️ Nenhum curso encontrado. Criando um curso padrão...")
            curso = Course(id=uuid.uuid4(), nome="Curso Padrão", ativo=True)
            db.add(curso)
            db.commit()
            db.refresh(curso)

        # Criar o super_admin
        novo_admin = User(
            nome_completo="Super Administrador",
            email="admin@learninglab.com.br",
            senha_hash=hash_senha("Admin@123"),
            matricula="000000",
            data_nascimento=date(1990, 1, 1),
            data_ingresso=date.today(),
            meta_horas_semanais=0,
            foto_perfil="avatar_padrao.png",
            curso_id=curso.id,
            status_id=status_ativo.id,
            global_role=super_admin_role.id
        )

        db.add(novo_admin)
        db.commit()
        print(f"✅ Super_admin criado com sucesso!")
        print(f"📧 E-mail: {novo_admin.email}")
        print(f"🔑 Senha: Admin@123")

    except Exception as e:
        print(f"❌ Erro ao criar super_admin: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    create_super_admin()
