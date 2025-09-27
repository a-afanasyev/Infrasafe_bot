"""
JWT Test Helper for Request Service
UK Management Bot - Request Management System

Utilities for generating real JWT tokens for testing purposes.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from jose import jwt

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class JWTTestHelper:
    """Helper class for generating real JWT tokens for testing"""

    def __init__(self):
        self.secret_key = settings.JWT_SECRET_KEY
        self.algorithm = settings.JWT_ALGORITHM
        self.default_expire_minutes = settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES

    def generate_service_token(
        self,
        service_name: str = "request-service",
        permissions: Optional[List[str]] = None,
        expire_minutes: Optional[int] = None
    ) -> str:
        """
        Generate a real service JWT token for testing

        Args:
            service_name: Name of the service
            permissions: List of permissions
            expire_minutes: Token expiration time in minutes

        Returns:
            JWT token string
        """
        if permissions is None:
            permissions = [
                "users:read",
                "notifications:send",
                "media:read"
            ]

        if expire_minutes is None:
            expire_minutes = self.default_expire_minutes

        # Create token payload
        now = datetime.utcnow()
        expire = now + timedelta(minutes=expire_minutes)

        payload = {
            "type": "service",
            "service_name": service_name,
            "permissions": permissions,
            "iat": now.timestamp(),
            "exp": expire.timestamp(),
            "iss": "auth-service",
            "aud": "microservices"
        }

        # Generate JWT token
        token = jwt.encode(
            payload,
            self.secret_key,
            algorithm=self.algorithm
        )

        logger.info(f"Generated service token for {service_name} with permissions: {permissions}")
        return token

    def generate_user_token(
        self,
        user_id: int,
        username: str = "test_user",
        roles: Optional[List[str]] = None,
        expire_minutes: Optional[int] = None
    ) -> str:
        """
        Generate a real user JWT token for testing

        Args:
            user_id: User ID
            username: Username
            roles: List of user roles
            expire_minutes: Token expiration time in minutes

        Returns:
            JWT token string
        """
        if roles is None:
            roles = ["executor"]

        if expire_minutes is None:
            expire_minutes = self.default_expire_minutes

        # Create token payload
        now = datetime.utcnow()
        expire = now + timedelta(minutes=expire_minutes)

        payload = {
            "type": "user",
            "user_id": user_id,
            "username": username,
            "roles": roles,
            "iat": now.timestamp(),
            "exp": expire.timestamp(),
            "iss": "auth-service",
            "aud": "microservices"
        }

        # Generate JWT token
        token = jwt.encode(
            payload,
            self.secret_key,
            algorithm=self.algorithm
        )

        logger.info(f"Generated user token for {username} (ID: {user_id}) with roles: {roles}")
        return token

    def decode_token(self, token: str) -> Dict[str, Any]:
        """
        Decode and validate a JWT token

        Args:
            token: JWT token to decode

        Returns:
            Token payload

        Raises:
            jwt.JWTError: If token is invalid
        """
        payload = jwt.decode(
            token,
            self.secret_key,
            algorithms=[self.algorithm]
        )

        return payload

    def is_token_expired(self, token: str) -> bool:
        """
        Check if a token is expired

        Args:
            token: JWT token to check

        Returns:
            True if token is expired
        """
        try:
            payload = self.decode_token(token)
            exp_timestamp = payload.get("exp", 0)
            current_timestamp = datetime.utcnow().timestamp()
            return current_timestamp > exp_timestamp
        except Exception:
            return True

    def get_token_info(self, token: str) -> Dict[str, Any]:
        """
        Get detailed information about a token

        Args:
            token: JWT token to analyze

        Returns:
            Token information
        """
        try:
            payload = self.decode_token(token)

            exp_timestamp = payload.get("exp", 0)
            iat_timestamp = payload.get("iat", 0)

            exp_datetime = datetime.fromtimestamp(exp_timestamp)
            iat_datetime = datetime.fromtimestamp(iat_timestamp)

            return {
                "valid": True,
                "type": payload.get("type"),
                "service_name": payload.get("service_name"),
                "user_id": payload.get("user_id"),
                "username": payload.get("username"),
                "permissions": payload.get("permissions", []),
                "roles": payload.get("roles", []),
                "issued_at": iat_datetime.isoformat(),
                "expires_at": exp_datetime.isoformat(),
                "expired": self.is_token_expired(token),
                "issuer": payload.get("iss"),
                "audience": payload.get("aud")
            }
        except Exception as e:
            return {
                "valid": False,
                "error": str(e)
            }


# Global instance for easy testing
jwt_test_helper = JWTTestHelper()


def generate_test_service_token(service_name: str = "request-service") -> str:
    """
    Convenience function to generate a service token for testing

    Args:
        service_name: Name of the service

    Returns:
        JWT service token
    """
    return jwt_test_helper.generate_service_token(service_name)


def generate_test_user_token(user_id: int, roles: Optional[List[str]] = None) -> str:
    """
    Convenience function to generate a user token for testing

    Args:
        user_id: User ID
        roles: List of user roles

    Returns:
        JWT user token
    """
    return jwt_test_helper.generate_user_token(user_id, roles=roles)