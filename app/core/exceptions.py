"""
Exceções de domínio da aplicação.

Cada exceção mapeia para um código HTTP específico, mas os services
não precisam conhecer HTTP — apenas lançam a exceção semântica correta.
O mapeamento HTTP é feito pelo exception handler em exception_handlers.py.
"""


class AppException(Exception):
    """Exceção base da aplicação. Todas as demais herdam desta."""

    def __init__(self, message: str, status_code: int = 500) -> None:
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class BadRequestError(AppException):
    """Dados inválidos ou violação de regra de negócio (HTTP 400)."""

    def __init__(self, message: str = "Requisição inválida.") -> None:
        super().__init__(message, status_code=400)


class UnauthorizedError(AppException):
    """Falha de autenticação — credenciais ausentes ou inválidas (HTTP 401)."""

    def __init__(self, message: str = "Não autenticado.") -> None:
        super().__init__(message, status_code=401)


class ForbiddenError(AppException):
    """Ação não permitida para o papel/permissão atual (HTTP 403)."""

    def __init__(self, message: str = "Ação não permitida.") -> None:
        super().__init__(message, status_code=403)


class NotFoundError(AppException):
    """Recurso não encontrado (HTTP 404)."""

    def __init__(self, message: str = "Recurso não encontrado.") -> None:
        super().__init__(message, status_code=404)


class ConflictError(AppException):
    """Conflito de dados — recurso duplicado (HTTP 409)."""

    def __init__(self, message: str = "Conflito de dados.") -> None:
        super().__init__(message, status_code=409)


class RateLimitError(AppException):
    """Limite de requisições excedido (HTTP 429)."""

    def __init__(
        self, message: str = "Muitas requisições. Tente novamente mais tarde."
    ) -> None:
        super().__init__(message, status_code=429)
