"""
Request Service - API Module
UK Management Bot - Request Management System

API router configuration and versioning.
"""

from .v1 import api_router

__all__ = ["api_router"]