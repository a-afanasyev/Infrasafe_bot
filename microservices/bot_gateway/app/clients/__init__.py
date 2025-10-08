"""
Service clients for external microservice communication.

This module provides HTTP clients for Bot Gateway to communicate with:
- Integration Service (geocoding, building directory, webhooks)
- Auth Service (authentication, permissions)
- User Service (profiles, roles)
- Request Service (requests, assignments)
"""

from .integration_service_client import IntegrationServiceClient

__all__ = ["IntegrationServiceClient"]
