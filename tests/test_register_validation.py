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


if __name__ == "__main__":
    unittest.main()
