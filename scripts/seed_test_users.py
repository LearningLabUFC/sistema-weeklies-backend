"""Script para criar automaticamente usuários de teste com papéis e setores configurados.

Cria:
1. Líder do Setor: lider@learninglab.com.br (papel='lider' no setor Desenvolvimento)
2. Membro 1: membro1@learninglab.com.br (papel='membro' no setor Desenvolvimento)
3. Membro 2: membro2@learninglab.com.br (papel='membro' no setor Desenvolvimento)

Todos com status 'ativo' (login imediato sem precisar de aprovação manual)
e senha padrão: Teste@123

Uso:
    python scripts/seed_test_users.py
"""

import os
import sys
import uuid
from datetime import date, timedelta

# Adiciona o diretório raiz ao path para poder importar o app
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.constants import RoleID, StatusID
from app.core.security import hash_senha
from app.database import SessionLocal
from app.models.course import Course
from app.models.role import Role
from app.models.sector import Sector
from app.models.sector_user import SectorUser
from app.models.status import Status
from app.models.user import User
from app.seeds.seed_roles import seed_roles
from app.seeds.seed_sectors import seed_sectors
from app.seeds.seed_status import seed_statuses


def get_or_create_course(db):
    curso = db.query(Course).first()
    if not curso:
        curso = Course(id=uuid.uuid4(), nome="Engenharia de Software", ativo=True)
        db.add(curso)
        db.commit()
        db.refresh(curso)
    return curso


def get_or_create_sector(db):
    setor = db.query(Sector).filter(Sector.nome == "Desenvolvimento").first()
    if not setor:
        setor = Sector(
            id=uuid.UUID("4fa85f64-5717-4562-b3fc-2c963f66afa1"),
            nome="Desenvolvimento",
            descricao="Setor de Desenvolvimento de Software",
            ativo=True,
        )
        db.add(setor)
        db.commit()
        db.refresh(setor)
    return setor


def seed_test_users():
    db = SessionLocal()
    try:
        # Garante as tabelas auxiliares preenchidas
        seed_roles()
        seed_statuses()
        seed_sectors()

        curso = get_or_create_course(db)
        setor = get_or_create_sector(db)

        usuarios_config = [
            {
                "nome": "Líder Desenvolvimento",
                "email": "lider@learninglab.com.br",
                "matricula": "100001",
                "papel_setor": "lider",
                "global_role": RoleID.USUARIO,
            },
            {
                "nome": "Membro Exemplar",
                "email": "membro1@learninglab.com.br",
                "matricula": "100002",
                "papel_setor": "membro",
                "global_role": RoleID.USUARIO,
            },
            {
                "nome": "Membro Faltoso",
                "email": "membro2@learninglab.com.br",
                "matricula": "100003",
                "papel_setor": "membro",
                "global_role": RoleID.USUARIO,
            },
        ]

        print("\n" + "=" * 65)
        print("👥 CRIANDO USUÁRIOS DE TESTE PARA O MÓDULO DE WEEKLIES")
        print("=" * 65)

        # Data de ingresso retroativa de 30 dias para evitar isenção de novatos
        data_ingresso_retroativa = date.today() - timedelta(days=30)
        senha_padrao = "Teste@123"
        senha_hash = hash_senha(senha_padrao)

        criados = []

        for item in usuarios_config:
            user = db.query(User).filter(User.email == item["email"]).first()
            if not user:
                user = User(
                    id=uuid.uuid4(),
                    nome_completo=item["nome"],
                    email=item["email"],
                    senha_hash=senha_hash,
                    matricula=item["matricula"],
                    data_nascimento=date(2000, 1, 1),
                    data_ingresso=data_ingresso_retroativa,
                    meta_horas_semanais=12,
                    foto_perfil="avatar_padrao.png",
                    curso_id=curso.id,
                    status_id=StatusID.ATIVO,
                    global_role=item["global_role"],
                )
                db.add(user)
                db.flush()
                print(f"✨ Usuário criado: {item['nome']} ({item['email']})")
            else:
                # Garante que está ativo
                user.status_id = StatusID.ATIVO
                print(f"ℹ️ Usuário já existia: {item['email']} (status mantido como ATIVO)")

            # Vincula ao setor com o papel especificado (lider ou membro)
            assoc = (
                db.query(SectorUser)
                .filter(
                    SectorUser.usuario_id == user.id,
                    SectorUser.setor_id == setor.id,
                )
                .first()
            )
            if not assoc:
                assoc = SectorUser(
                    id=uuid.uuid4(),
                    usuario_id=user.id,
                    setor_id=setor.id,
                    papel=item["papel_setor"],
                    data_ingresso=data_ingresso_retroativa,
                )
                db.add(assoc)
                print(f"   ↳ Vinculado ao setor '{setor.nome}' como [{item['papel_setor'].upper()}]")
            else:
                assoc.papel = item["papel_setor"]
                assoc.data_ingresso = data_ingresso_retroativa
                print(f"   ↳ Associação atualizada: papel [{item['papel_setor'].upper()}] no setor '{setor.nome}'")

            criados.append({
                "nome": item["nome"],
                "email": item["email"],
                "senha": senha_padrao,
                "papel": item["papel_setor"],
                "setor": setor.nome,
            })

        db.commit()

        print("\n" + "-" * 65)
        print("🎉 USUÁRIOS PRONTOS PARA TESTE:")
        print("-" * 65)
        for u in criados:
            print(f"• {u['nome']}")
            print(f"  📧 E-mail : {u['email']}")
            print(f"  🔑 Senha  : {u['senha']}")
            print(f"  🏢 Setor  : {u['setor']} (Papel: {u['papel'].upper()})")
            print()
        print("💡 Todos já estão com status ATIVO e podem logar direto na interface!")
        print("=" * 65 + "\n")

    except Exception as e:
        db.rollback()
        print(f"❌ Erro ao criar usuários de teste: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    seed_test_users()
