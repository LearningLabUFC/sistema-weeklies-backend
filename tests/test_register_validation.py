"""
Testes unitários para validações do schema de cadastro (RegisterRequest).
Compatível com unittest (stdlib) e pytest.
"""
import unittest
from datetime import date
from uuid import uuid4

from pydantic import ValidationError
from app.schemas import RegisterRequest


class TestRegisterValidation(unittest.TestCase):
    def test_matricula_valida(self):
        """Matrícula com 6 dígitos numéricos deve ser aceita."""
        req = RegisterRequest(
            nome_completo="João Silva",
            email="joao@exemplo.com",
            senha="SenhaForte123!",
            data_nascimento=date(2000, 1, 1),
            matricula="512345",
            curso_id=uuid4(),
            metas_horas_semanais=12,
        )
        self.assertEqual(req.matricula, "512345")

    def test_matricula_invalida_7_digitos(self):
        """BUG-001: Matrícula com 7 dígitos deve ser rejeitada."""
        with self.assertRaises(ValidationError) as ctx:
            RegisterRequest(
                nome_completo="João Silva",
                email="joao@exemplo.com",
                senha="SenhaForte123!",
                data_nascimento=date(2000, 1, 1),
                matricula="5123456",  # 7 dígitos
                curso_id=uuid4(),
                metas_horas_semanais=12,
            )
        self.assertIn("A matrícula deve conter exatamente 6 dígitos numéricos.", str(ctx.exception))

    def test_matricula_invalida_outros_formatos(self):
        """Matrículas com formatos inválidos (curto, letras, símbolos) devem ser rejeitadas."""
        formatos_invalidos = ["51234", "51234a", "abcdef", "51 234", "123-45", ""]
        for mat in formatos_invalidos:
            with self.subTest(matricula=mat):
                with self.assertRaises(ValidationError) as ctx:
                    RegisterRequest(
                        nome_completo="João Silva",
                        email="joao@exemplo.com",
                        senha="SenhaForte123!",
                        data_nascimento=date(2000, 1, 1),
                        matricula=mat,
                        curso_id=uuid4(),
                        metas_horas_semanais=12,
                    )
                self.assertIn("A matrícula deve conter exatamente 6 dígitos numéricos.", str(ctx.exception))

    def test_nome_completo_valido(self):
        """Nomes compostos com acentos, apóstrofos e hífens devem ser aceitos."""
        nomes_validos = [
            "João Silva",
            "Maria de Fátima",
            "Jean-Paul Sartre",
            "Luís d'Ávila",
            "Ana Cláudia Gonçalves da Costa",
        ]
        for nome in nomes_validos:
            with self.subTest(nome=nome):
                req = RegisterRequest(
                    nome_completo=nome,
                    email="joao@exemplo.com",
                    senha="SenhaForte123!",
                    data_nascimento=date(2000, 1, 1),
                    matricula="512345",
                    curso_id=uuid4(),
                    metas_horas_semanais=12,
                )
                self.assertEqual(req.nome_completo, nome.strip())

    def test_nome_completo_invalido_numeros_e_simbolos(self):
        """BUG-002: Nomes contendo números e caracteres especiais devem ser rejeitados."""
        nomes_invalidos = [
            "João123!@#",
            "Carlos Eduardo 2",
            "Ana_Paula",
            "Lucas # Santos",
            "Pedro $ Silva",
        ]
        for nome in nomes_invalidos:
            with self.subTest(nome=nome):
                with self.assertRaises(ValidationError) as ctx:
                    RegisterRequest(
                        nome_completo=nome,
                        email="joao@exemplo.com",
                        senha="SenhaForte123!",
                        data_nascimento=date(2000, 1, 1),
                        matricula="512345",
                        curso_id=uuid4(),
                        metas_horas_semanais=12,
                    )
                self.assertIn("O nome completo deve conter apenas letras", str(ctx.exception))

    def test_nome_completo_invalido_apenas_um_nome_ou_vazio(self):
        """Nomes com apenas uma palavra ou vazios devem ser rejeitados."""
        nomes_invalidos = ["João", "Maria", "", "   "]
        for nome in nomes_invalidos:
            with self.subTest(nome=nome):
                with self.assertRaises(ValidationError) as ctx:
                    RegisterRequest(
                        nome_completo=nome,
                        email="joao@exemplo.com",
                        senha="SenhaForte123!",
                        data_nascimento=date(2000, 1, 1),
                        matricula="512345",
                        curso_id=uuid4(),
                        metas_horas_semanais=12,
                    )
                self.assertIn("O nome completo deve conter apenas letras", str(ctx.exception))

    def test_data_nascimento_valida(self):
        """Idades válidas (ex: 20 anos, 35 anos, 15 anos) devem ser aceitas."""
        hoje = date.today()
        datas_validas = [
            hoje.replace(year=hoje.year - 20),   # 20 anos
            hoje.replace(year=hoje.year - 35),   # 35 anos
            hoje.replace(year=hoje.year - 15),   # 15 anos (acima do mínimo de 14)
        ]
        for d in datas_validas:
            with self.subTest(data=d):
                req = RegisterRequest(
                    nome_completo="João Silva",
                    email="joao@exemplo.com",
                    senha="SenhaForte123!",
                    data_nascimento=d,
                    matricula="512345",
                    curso_id=uuid4(),
                    metas_horas_semanais=12,
                )
                self.assertEqual(req.data_nascimento, d)

    def test_data_nascimento_invalida_futura(self):
        """BUG-003 (b): Data no futuro deve ser rejeitada."""
        amanha = date.today().replace(year=date.today().year + 1)
        with self.assertRaises(ValidationError) as ctx:
            RegisterRequest(
                nome_completo="João Silva",
                email="joao@exemplo.com",
                senha="SenhaForte123!",
                data_nascimento=amanha,
                matricula="512345",
                curso_id=uuid4(),
                metas_horas_semanais=12,
            )
        self.assertIn("A data de nascimento não pode ser uma data futura.", str(ctx.exception))

    def test_data_nascimento_invalida_menor_de_14_anos(self):
        """BUG-003 (a): Idade menor que 14 anos (~10 anos) deve ser rejeitada."""
        dez_anos_atras = date.today().replace(year=date.today().year - 10)
        with self.assertRaises(ValidationError) as ctx:
            RegisterRequest(
                nome_completo="João Silva",
                email="joao@exemplo.com",
                senha="SenhaForte123!",
                data_nascimento=dez_anos_atras,
                matricula="512345",
                curso_id=uuid4(),
                metas_horas_semanais=12,
            )
        self.assertIn("mínimo 14 anos de idade", str(ctx.exception))

    def test_data_nascimento_invalida_ano_anterior_a_1900(self):
        """BUG-003 (c): Data muito antiga (ex: ano 1826 / ~200 anos) deve ser rejeitada."""
        with self.assertRaises(ValidationError) as ctx:
            RegisterRequest(
                nome_completo="João Silva",
                email="joao@exemplo.com",
                senha="SenhaForte123!",
                data_nascimento=date(1826, 1, 1),
                matricula="512345",
                curso_id=uuid4(),
                metas_horas_semanais=12,
            )
        self.assertIn("ano de nascimento deve ser a partir de 1900", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
