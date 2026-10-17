"""
Pacote de modelos ORM.

Importa todos os modelos aqui para que o Alembic consiga
detectar as tabelas via Base.metadata ao gerar migrations.
"""

from app.models.course import Course  # noqa: F401
from app.models.role import Role  # noqa: F401
from app.models.sector import Sector  # noqa: F401
from app.models.sector_user import SectorUser  # noqa: F401
from app.models.status import Status  # noqa: F401
from app.models.task import Task  # noqa: F401
from app.models.task_assignment import TaskAssignment  # noqa: F401
from app.models.user import User  # noqa: F401
from app.models.weekly import Weekly  # noqa: F401
from app.models.weekly_scheduler_execution import WeeklySchedulerExecution  # noqa: F401
from app.models.weekly_task import WeeklyTask  # noqa: F401
from app.models.weekly_warning import WeeklyWarning  # noqa: F401
