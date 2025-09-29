# Service Token Management for Inter-Service Authentication
# UK Management Bot - Auth Service

import logging
import jwt
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from config import settings

logger = logging.getLogger(__name__)

class ServiceTokenManager:
    """Manages service-to-service authentication tokens"""

    def __init__(self):
        self.secret_key = settings.jwt_secret_key
        self.algorithm = settings.jwt_algorithm
        self.expire_days = settings.service_tokens_expire_days

    def generate_service_token(self, service_name: str, permissions: list = None) -> str:
        """
        Generate a service-to-service authentication token

        Args:
            service_name: Name of the service requesting the token
            permissions: List of permissions for this service

        Returns:
            JWT token string
        """
        try:
            # Create token payload
            now = datetime.utcnow()
            payload = {
                "iss": "auth-service",  # Issuer
                "sub": service_name,    # Subject (service name)
                "aud": "microservices", # Audience
                "iat": now,             # Issued at
                "exp": now + timedelta(days=self.expire_days),  # Expiration
                "token_type": "service",
                "service_name": service_name,
                "permissions": permissions or self._get_default_permissions(service_name),
                "jti": secrets.token_hex(16)  # Unique token ID
            }

            # Generate JWT token
            token = jwt.encode(payload, self.secret_key, algorithm=self.algorithm)

            logger.info(f"Generated service token for {service_name}")
            return token

        except Exception as e:
            logger.error(f"Error generating service token: {e}")
            raise

    def validate_service_token(self, token: str, expected_service: str = None) -> Optional[Dict[str, Any]]:
        """
        Validate a service-to-service authentication token

        Args:
            token: JWT token to validate
            expected_service: Expected service name (optional)

        Returns:
            Token payload if valid, None if invalid
        """
        try:
            # Decode and validate JWT token
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm],
                audience="microservices"
            )

            # Validate token type
            if payload.get("token_type") != "service":
                logger.warning("Invalid token type for service authentication")
                return None

            # Validate service name if specified
            service_name = payload.get("service_name")
            if expected_service and service_name != expected_service:
                logger.warning(f"Service name mismatch: expected {expected_service}, got {service_name}")
                return None

            # Check if service is allowed
            if service_name not in settings.service_allowlist:
                logger.warning(f"Service not in allowed list: {service_name}")
                return None

            logger.debug(f"Service token validated for {service_name}")
            return payload

        except jwt.ExpiredSignatureError:
            logger.warning("Service token has expired")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid service token: {e}")
            return None
        except Exception as e:
            logger.error(f"Error validating service token: {e}")
            return None

    def _get_default_permissions(self, service_name: str) -> list:
        """
        Get default permissions for a service

        Args:
            service_name: Name of the service

        Returns:
            List of default permissions
        """
        # Define default permissions per service
        service_permissions = {
            "user-service": [
                "users:read",
                "users:write",
                "roles:read",
                "profiles:read",
                "profiles:write"
            ],
            "request-service": [
                "requests:read",
                "requests:write",
                "users:read",
                "notifications:send"
            ],
            "shift-service": [
                "shifts:read",
                "shifts:write",
                "users:read",
                "notifications:send"
            ],
            "notification-service": [
                "notifications:send",
                "notifications:read",
                "users:read"
            ],
            "analytics-service": [
                "analytics:read",
                "analytics:write",
                "requests:read",
                "users:read",
                "shifts:read"
            ],
            "ai-service": [
                "ai:process",
                "requests:read",
                "users:read",
                "shifts:read"
            ]
        }

        return service_permissions.get(service_name, ["basic:read"])

    def generate_api_key(self, service_name: str) -> str:
        """
        Generate a simple API key for development/testing
        Format: service-name.hash
        """
        try:
            # Create deterministic but secure API key
            key_material = f"{service_name}:{settings.jwt_secret_key}:{secrets.token_hex(8)}"
            key_hash = hashlib.sha256(key_material.encode()).hexdigest()[:16]

            api_key = f"{service_name}.{key_hash}"
            logger.info(f"Generated API key for {service_name}")

            return api_key

        except Exception as e:
            logger.error(f"Error generating API key: {e}")
            raise

    async def validate_api_key(self, api_key: str, service_name: str = None) -> Optional[str]:
        """
        Validate service API key using secure HMAC validation
        Returns service name if valid

        SECURITY: This method now uses StaticKeyService with HMAC validation
        instead of plain string comparison for enhanced security.
        """
        try:
            from .static_key_service import static_key_service

            # If service_name is provided, validate specific service
            if service_name:
                service_credentials = await static_key_service.validate_service_credentials(
                    service_name=service_name,
                    api_key=api_key
                )

                if service_credentials and service_name in settings.service_allowlist:
                    logger.info(f"API key validated for service: {service_name}")
                    return service_name
                else:
                    logger.warning(f"Invalid API key for service: {service_name}")
                    return None

            # If no service_name provided, try all known services
            # This maintains backward compatibility for legacy code
            known_services = [
                "request-service", "user-service", "notification-service",
                "media-service", "ai-service", "auth-service"
            ]

            for service in known_services:
                if service in settings.service_allowlist:
                    service_credentials = await static_key_service.validate_service_credentials(
                        service_name=service,
                        api_key=api_key
                    )

                    if service_credentials:
                        logger.info(f"API key validated for service: {service}")
                        return service

            logger.warning(f"Invalid API key attempted: {api_key[:16]}...")
            return None

        except Exception as e:
            logger.error(f"Error validating API key: {e}")
            return None

# Global instance
service_token_manager = ServiceTokenManager()
