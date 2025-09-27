"""
Request Service - Services Module
UK Management Bot - Request Management System

Business logic services for the Request Service microservice.
"""

from .request_number_service import RequestNumberService, request_number_service, NumberGenerationResult
from .assignment_service import AssignmentService, assignment_service
from .material_service import MaterialService, material_service

__all__ = [
    "RequestNumberService",
    "request_number_service",
    "NumberGenerationResult",
    "AssignmentService",
    "assignment_service",
    "MaterialService",
    "material_service",
]