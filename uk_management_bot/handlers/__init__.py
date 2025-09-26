"""
Регистрация всех обработчиков бота
Включает основные обработчики и новые для системы передачи заявок на исполнение
"""

from .auth import router as auth_router
from .admin import router as admin_router
from .employee_management import router as employee_router
from .requests import router as requests_router
from .profile_editing import router as profile_editing_router
from .shifts import router as shift_management_router
 
# Новые обработчики для системы передачи заявок на исполнение
from .request_assignment import router as request_assignment_router
from .request_status_management import router as request_status_management_router
from .request_comments import router as request_comments_router
from .request_reports import router as request_reports_router

# Обработчики системы смен
from .shift_management import router as shift_management_router_new
from .my_shifts import router as my_shifts_router

# Список всех роутеров для регистрации
__all__ = [
    "auth_router",
    "admin_router", 
    "employee_router",
    "requests_router",
    "profile_editing_router",
    "shift_management_router",
    # Новые роутеры
    "request_assignment_router",
    "request_status_management_router", 
    "request_comments_router",
    "request_reports_router",
    # Роутеры системы смен
    "shift_management_router_new",
    "my_shifts_router"
]
