"""
Testes unitários para validações do schema de cadastro (RegisterRequest).

Cobre as validações de:
- Matrícula (exatamente 6 dígitos numéricos)
- Nome completo (apenas letras, acentos, no mínimo nome e sobrenome)
- Data de nascimento (não futura, >= 1900, idade mínima 14 anos)
"""

from datetime import date, datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas import _MATRICULA_MSG, _NOME_MSG, RegisterRequest

# Campos válidos base para o RegisterRequest (evita repetição).
# Para sobrescrever um campo específico, use:
#   RegisterRequest(**{**_REGISTER_BASE, "campo": novo_valor})

_REGISTER_BASE = {
    "nome_completo": "João Silva",
    "email": "joao@exemplo.com",
    "senha": "SenhaForte123!",
    "data_nascimento": date(2000, 1, 1),
    "matricula": "512345",
    "curso_id": uuid4(),
    "meta_horas_semanais": 12,
}


# ── Matrícula ────────────────────────────────────────────────

def test_matricula_valida():
    """Matrícula com 6 dígitos numéricos deve ser aceita."""
    req = RegisterRequest(**_REGISTER_BASE)
    assert req.matricula == "512345"


def test_matricula_invalida_7_digitos():
    """BUG-001: Matrícula com 7 dígitos deve ser rejeitada."""
    with pytest.raises(ValidationError) as exc_info:
        RegisterRequest(**{**_REGISTER_BASE, "matricula": "5123456"})
    assert _MATRICULA_MSG in str(exc_info.value)


@pytest.mark.parametrize("matricula", [
    "51234",    # 5 dígitos (curto)
    "51234a",   # contém letra
    "abcdef",   # só letras
    "51 234",   # contém espaço
    "123-45",   # contém hífen
    "",         # vazia
])
def test_matricula_invalida_outros_formatos(matricula):
    """Matrículas com formatos inválidos devem ser rejeitadas."""
    with pytest.raises(ValidationError) as exc_info:
        RegisterRequest(**{**_REGISTER_BASE, "matricula": matricula})
    assert _MATRICULA_MSG in str(exc_info.value)


# ── Nome completo ───────────────────────────────────────────

@pytest.mark.parametrize("nome", [
    "João Silva",
    "Maria de Fátima",
    "Jean-Paul Sartre",
    "Luís d'Ávila",
    "Ana Cláudia Gonçalves da Costa",
])
def test_nome_completo_valido(nome):
    """Nomes compostos com acentos, apóstrofos e hífens devem ser aceitos."""
    req = RegisterRequest(**{**_REGISTER_BASE, "nome_completo": nome})
    assert req.nome_completo == nome.strip()


@pytest.mark.parametrize("nome", [
    "João123!@#",
    "Carlos Eduardo 2",
    "Ana_Paula",
    "Lucas # Santos",
    "Pedro $ Silva",
])
def test_nome_completo_invalido_numeros_e_simbolos(nome):
    """BUG-002: Nomes contendo números e caracteres especiais devem ser rejeitados."""
    with pytest.raises(ValidationError) as exc_info:
        RegisterRequest(**{**_REGISTER_BASE, "nome_completo": nome})
    assert _NOME_MSG in str(exc_info.value)


@pytest.mark.parametrize("nome", [
    "João",     # apenas um nome
    "Maria",    # apenas um nome
    "",         # vazio
    "   ",      # só espaços
])
def test_nome_completo_invalido_apenas_um_nome_ou_vazio(nome):
    """Nomes com apenas uma palavra ou vazios devem ser rejeitados."""
    with pytest.raises(ValidationError) as exc_info:
        RegisterRequest(**{**_REGISTER_BASE, "nome_completo": nome})
    assert _NOME_MSG in str(exc_info.value)


# ── Data de nascimento ───────────────────────────────────────

_HOJE = datetime.now(tz=timezone.utc).date()


@pytest.mark.parametrize("data", [
    _HOJE.replace(year=_HOJE.year - 20),   # 20 anos
    _HOJE.replace(year=_HOJE.year - 35),   # 35 anos
    _HOJE.replace(year=_HOJE.year - 15),   # 15 anos (acima do mínimo de 14)
])
def test_data_nascimento_valida(data):
    """Idades válidas (ex: 20, 35, 15 anos) devem ser aceitas."""
    req = RegisterRequest(**{**_REGISTER_BASE, "data_nascimento": data})
    assert req.data_nascimento == data


def test_data_nascimento_invalida_futura():
    """BUG-003 (b): Data no futuro deve ser rejeitada."""
    ano_que_vem = _HOJE.replace(year=_HOJE.year + 1)
    with pytest.raises(ValidationError) as exc_info:
        RegisterRequest(**{**_REGISTER_BASE, "data_nascimento": ano_que_vem})
    assert "A data de nascimento não pode ser uma data futura" in str(exc_info.value)


def test_data_nascimento_invalida_menor_de_14_anos():
    """BUG-003 (a): Idade menor que 14 anos (~10 anos) deve ser rejeitada."""
    dez_anos_atras = _HOJE.replace(year=_HOJE.year - 10)
    with pytest.raises(ValidationError) as exc_info:
        RegisterRequest(**{**_REGISTER_BASE, "data_nascimento": dez_anos_atras})
    assert "mínimo 14 anos de idade" in str(exc_info.value)


def test_data_nascimento_invalida_ano_anterior_a_1900():
    """BUG-003 (c): Data muito antiga (ex: ano 1826 / ~200 anos) deve ser rejeitada."""
    with pytest.raises(ValidationError) as exc_info:
        RegisterRequest(**{**_REGISTER_BASE, "data_nascimento": date(1826, 1, 1)})
    assert "ano de nascimento deve ser a partir de 1900" in str(exc_info.value)
