"""
Router central da aplicação.
Agrupa todas as rotas dos submódulos sob um único APIRouter.
"""

from fastapi import APIRouter

from app.admin.router import router as admin_router
from app.auth.router import router as auth_router
from app.courses.router import router as courses_router
from app.users.router import router as users_router

api_router = APIRouter()

api_router.include_router(admin_router)
api_router.include_router(auth_router)
api_router.include_router(users_router)
api_router.include_router(courses_router)
