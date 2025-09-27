# JWT Token Service
# UK Management Bot - Auth Service

import jwt
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Dict, Any

from schemas.auth import TokenResponse
from config import settings

logger = logging.getLogger(__name__)

class JWTService:
    """JWT token creation and validation service"""

    def __init__(self):
        self.secret_key = settings.jwt_secret_key
        self.algorithm = settings.jwt_algorithm
        self.access_token_expire_minutes = settings.jwt_expire_minutes
        self.refresh_token_expire_days = settings.jwt_refresh_expire_days

    def create_tokens(self, payload: Dict[str, Any]) -> TokenResponse:
        """Create access and refresh tokens"""
        try:
            # Generate access token
            access_token_expires = timedelta(minutes=self.access_token_expire_minutes)
            access_token = self._create_token(payload, access_token_expires, token_type="access")

            # Generate refresh token
            refresh_token_expires = timedelta(days=self.refresh_token_expire_days)
            refresh_payload = {
                "user_id": payload["user_id"],
                "telegram_id": payload["telegram_id"],
                "session_id": payload["session_id"],
                "type": "refresh"
            }
            refresh_token = self._create_token(refresh_payload, refresh_token_expires, token_type="refresh")

            return TokenResponse(
                access_token=access_token,
                refresh_token=refresh_token,
                token_type="bearer",
                expires_in=int(access_token_expires.total_seconds()),
                session_id=payload["session_id"]
            )

        except Exception as e:
            logger.error(f"Error creating tokens: {e}")
            raise Exception("Could not create tokens")

    def _create_token(self, data: Dict[str, Any], expires_delta: timedelta, token_type: str) -> str:
        """Create JWT token with expiration"""
        to_encode = data.copy()

        # Use timezone-aware datetime
        expire = datetime.now(timezone.utc) + expires_delta
        to_encode.update({
            "exp": expire,
            "iat": datetime.now(timezone.utc),
            "type": token_type,
            "jti": secrets.token_urlsafe(16)  # JWT ID for token tracking
        })

        try:
            encoded_jwt = jwt.encode(
                to_encode,
                self.secret_key,
                algorithm=self.algorithm
            )
            return encoded_jwt
        except Exception as e:
            logger.error(f"Error encoding JWT token: {e}")
            raise Exception("Could not encode token")

    def validate_access_token(self, token: str) -> Dict[str, Any]:
        """Validate access token and return payload"""
        try:
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm]
            )

            # Verify token type
            if payload.get("type") != "access":
                raise Exception("Invalid token type")

            # Remove token metadata before returning
            payload.pop("exp", None)
            payload.pop("iat", None)
            payload.pop("type", None)
            payload.pop("jti", None)

            return payload

        except jwt.ExpiredSignatureError:
            logger.warning("Access token has expired")
            raise Exception("Token has expired")
        except jwt.JWTError as e:
            logger.warning(f"JWT validation error: {e}")
            raise Exception("Could not validate credentials")
        except Exception as e:
            logger.error(f"Unexpected error validating access token: {e}")
            raise Exception("Authentication error")

    def validate_refresh_token(self, token: str) -> Dict[str, Any]:
        """Validate refresh token and return payload"""
        try:
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm]
            )

            # Verify token type
            if payload.get("type") != "refresh":
                raise Exception("Invalid token type")

            # Remove token metadata before returning
            payload.pop("exp", None)
            payload.pop("iat", None)
            payload.pop("type", None)
            payload.pop("jti", None)

            return payload

        except jwt.ExpiredSignatureError:
            logger.warning("Refresh token has expired")
            raise Exception("Refresh token has expired")
        except jwt.JWTError as e:
            logger.warning(f"JWT validation error: {e}")
            raise Exception("Could not validate refresh token")
        except Exception as e:
            logger.error(f"Unexpected error validating refresh token: {e}")
            raise Exception("Refresh token error")

    def decode_token_without_verification(self, token: str) -> Dict[str, Any]:
        """Decode token without verification (for inspection)"""
        try:
            payload = jwt.decode(
                token,
                options={"verify_signature": False, "verify_exp": False}
            )
            return payload
        except Exception as e:
            logger.error(f"Error decoding token: {e}")
            return {}

    def get_token_expiry(self, token: str) -> datetime:
        """Get token expiration time"""
        try:
            payload = self.decode_token_without_verification(token)
            exp_timestamp = payload.get("exp")
            if exp_timestamp:
                return datetime.fromtimestamp(exp_timestamp, tz=timezone.utc)
            return datetime.now(timezone.utc)
        except Exception:
            return datetime.now(timezone.utc)

    def is_token_expired(self, token: str) -> bool:
        """Check if token is expired"""
        try:
            expiry = self.get_token_expiry(token)
            return datetime.now(timezone.utc) > expiry
        except Exception:
            return True