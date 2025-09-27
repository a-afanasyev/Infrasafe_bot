"""
Request Service - Core Module
UK Management Bot - Request Management System

Core application components and configuration.
"""

from .config import settings, get_settings
from .database import (
    get_async_session,
    init_database,
    close_database,
    check_database_health,
    db_manager
)

__all__ = [
    "settings",
    "get_settings",
    "get_async_session",
    "init_database",
    "close_database",
    "check_database_health",
    "db_manager",
]