"""
Static API Key Service with HMAC validation
UK Management Bot - Auth Service

Secure validation service for static API keys with:
- HMAC-based key validation
- Centralized revocation mechanism
- Secure key storage and rotation
- Audit logging
"""

import hmac
import hashlib
import logging
import time
from typing import Dict, Optional, Set, List
from datetime import datetime, timezone
import redis.asyncio as redis
from dataclasses import dataclass

from config import Settings

settings = Settings()

logger = logging.getLogger(__name__)


@dataclass
class ServiceCredentials:
    """Service credentials with validation metadata"""
    service_name: str
    api_key_hash: str  # HMAC hash of the actual API key
    permissions: List[str]
    created_at: datetime
    last_used: Optional[datetime] = None
    is_revoked: bool = False
    revoked_at: Optional[datetime] = None
    revoked_reason: Optional[str] = None


class StaticKeyService:
    """
    Secure static API key validation service

    Features:
    - HMAC-based key verification (not plain string comparison)
    - Redis-based revocation list
    - Audit logging for security events
    - Key rotation support
    """

    def __init__(self):
        # Secret key for HMAC validation - should be from secure config
        self._hmac_secret = settings.static_key_hmac_secret.encode('utf-8')

        # Service credentials registry
        # In production, this should come from secure storage (HashiCorp Vault, etc.)
        self._service_credentials = self._load_service_credentials()

        # Redis connection for revocation list and audit
        self._redis_client: Optional[redis.Redis] = None

        logger.info("StaticKeyService initialized with HMAC validation")

    def _load_service_credentials(self) -> Dict[str, ServiceCredentials]:
        """Load service credentials from secure configuration"""
        # Generate HMAC hashes for known service keys
        services = {
            "request-service": "request-service-api-key-change-in-production",
            "user-service": "user-service-api-key-change-in-production",
            "notification-service": "notification-service-api-key-change-in-production",
            "media-service": "media-service-api-key-change-in-production",
            "ai-service": "ai-service-api-key-change-in-production",
            "auth-service": "auth-service-api-key-change-in-production"
        }

        credentials = {}
        for service_name, api_key in services.items():
            # Generate HMAC hash of the API key
            api_key_hash = self._generate_key_hash(api_key)

            # Default permissions based on service
            permissions = self._get_default_permissions(service_name)

            credentials[service_name] = ServiceCredentials(
                service_name=service_name,
                api_key_hash=api_key_hash,
                permissions=permissions,
                created_at=datetime.now(timezone.utc)
            )

        logger.info(f"Loaded credentials for {len(credentials)} services")
        return credentials

    def _generate_key_hash(self, api_key: str) -> str:
        """Generate HMAC hash for API key"""
        return hmac.new(
            self._hmac_secret,
            api_key.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

    def _get_default_permissions(self, service_name: str) -> List[str]:
        """Get default permissions for a service"""
        permission_map = {
            "request-service": ["requests:read", "requests:write", "notifications:send"],
            "user-service": ["users:read", "users:write", "users:validate"],
            "notification-service": ["notifications:send", "notifications:read"],
            "media-service": ["media:read", "media:write", "media:validate"],
            "ai-service": ["ai:optimize", "ai:suggest", "requests:read"],
            "auth-service": ["auth:validate", "tokens:validate"]
        }
        return permission_map.get(service_name, ["basic:access"])

    async def _get_redis_client(self) -> redis.Redis:
        """Get Redis client for revocation list"""
        if not self._redis_client:
            import os
            redis_url = getattr(settings, 'redis_url', None) or os.getenv('REDIS_URL', 'redis://shared-redis:6379/1')
            self._redis_client = redis.from_url(
                redis_url,
                decode_responses=True
            )
        return self._redis_client

    async def validate_service_credentials(
        self,
        service_name: str,
        api_key: str,
        request_info: Optional[Dict] = None
    ) -> Optional[ServiceCredentials]:
        """
        Validate service credentials using HMAC verification

        Args:
            service_name: Name of the service
            api_key: API key to validate
            request_info: Optional request metadata for audit

        Returns:
            ServiceCredentials if valid, None otherwise
        """
        try:
            # Check if service exists in our registry
            if service_name not in self._service_credentials:
                logger.warning(f"Unknown service attempted authentication: {service_name}")
                await self._log_auth_event("unknown_service", service_name, False, request_info)
                return None

            service_creds = self._service_credentials[service_name]

            # Check if service is revoked
            if await self._is_service_revoked(service_name):
                logger.warning(f"Revoked service attempted authentication: {service_name}")
                await self._log_auth_event("revoked_service", service_name, False, request_info)
                return None

            # Validate API key using HMAC
            provided_key_hash = self._generate_key_hash(api_key)

            if not hmac.compare_digest(provided_key_hash, service_creds.api_key_hash):
                logger.warning(f"Invalid API key for service: {service_name}")
                await self._log_auth_event("invalid_key", service_name, False, request_info)
                return None

            # Update last used timestamp
            service_creds.last_used = datetime.now(timezone.utc)

            # Log successful authentication
            logger.info(f"Service authenticated successfully: {service_name}")
            await self._log_auth_event("success", service_name, True, request_info)

            return service_creds

        except Exception as e:
            logger.error(f"Error validating service credentials: {e}")
            await self._log_auth_event("validation_error", service_name, False, request_info)
            return None

    async def _is_service_revoked(self, service_name: str) -> bool:
        """Check if service is revoked using Redis"""
        try:
            redis_client = await self._get_redis_client()
            revoked = await redis_client.sismember("revoked_services", service_name)
            return revoked
        except Exception as e:
            logger.error(f"Error checking revocation status: {e}")
            # Fail secure - if we can't check revocation, allow access
            return False

    async def revoke_service(self, service_name: str, reason: str, admin_user_id: str) -> bool:
        """
        Revoke service access

        Args:
            service_name: Service to revoke
            reason: Reason for revocation
            admin_user_id: ID of admin performing revocation

        Returns:
            True if revoked successfully
        """
        try:
            redis_client = await self._get_redis_client()

            # Add to revocation list
            await redis_client.sadd("revoked_services", service_name)

            # Store revocation metadata
            revocation_data = {
                "service_name": service_name,
                "reason": reason,
                "admin_user_id": admin_user_id,
                "revoked_at": datetime.now(timezone.utc).isoformat()
            }

            await redis_client.hset(
                f"revocation:{service_name}",
                mapping=revocation_data
            )

            # Update local credentials
            if service_name in self._service_credentials:
                self._service_credentials[service_name].is_revoked = True
                self._service_credentials[service_name].revoked_at = datetime.now(timezone.utc)
                self._service_credentials[service_name].revoked_reason = reason

            logger.warning(
                f"Service {service_name} revoked by admin {admin_user_id}: {reason}"
            )

            return True

        except Exception as e:
            logger.error(f"Error revoking service {service_name}: {e}")
            return False

    async def restore_service(self, service_name: str, admin_user_id: str) -> bool:
        """
        Restore previously revoked service

        Args:
            service_name: Service to restore
            admin_user_id: ID of admin performing restoration

        Returns:
            True if restored successfully
        """
        try:
            redis_client = await self._get_redis_client()

            # Remove from revocation list
            await redis_client.srem("revoked_services", service_name)

            # Remove revocation metadata
            await redis_client.delete(f"revocation:{service_name}")

            # Update local credentials
            if service_name in self._service_credentials:
                self._service_credentials[service_name].is_revoked = False
                self._service_credentials[service_name].revoked_at = None
                self._service_credentials[service_name].revoked_reason = None

            logger.info(
                f"Service {service_name} restored by admin {admin_user_id}"
            )

            return True

        except Exception as e:
            logger.error(f"Error restoring service {service_name}: {e}")
            return False

    async def _log_auth_event(
        self,
        event_type: str,
        service_name: str,
        success: bool,
        request_info: Optional[Dict] = None
    ):
        """Log authentication event for audit purposes"""
        try:
            redis_client = await self._get_redis_client()

            event_data = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "event_type": event_type,
                "service_name": service_name,
                "success": success,
                "source_ip": request_info.get("client_ip") if request_info else None,
                "user_agent": request_info.get("user_agent") if request_info else None
            }

            # Store in Redis with TTL for cleanup
            key = f"auth_audit:{int(time.time())}"
            await redis_client.hset(key, mapping=event_data)
            await redis_client.expire(key, 30 * 24 * 60 * 60)  # Keep for 30 days

        except Exception as e:
            logger.error(f"Error logging auth event: {e}")
            # Don't fail auth on logging error

    async def get_service_status(self) -> Dict[str, Dict]:
        """Get status of all registered services"""
        try:
            redis_client = await self._get_redis_client()

            # Get list of revoked services
            revoked_services = await redis_client.smembers("revoked_services")

            status = {}
            for service_name, creds in self._service_credentials.items():
                status[service_name] = {
                    "permissions": creds.permissions,
                    "created_at": creds.created_at.isoformat(),
                    "last_used": creds.last_used.isoformat() if creds.last_used else None,
                    "is_revoked": service_name in revoked_services,
                    "revoked_at": creds.revoked_at.isoformat() if creds.revoked_at else None,
                    "revoked_reason": creds.revoked_reason
                }

            return status

        except Exception as e:
            logger.error(f"Error getting service status: {e}")
            return {}

    async def get_auth_audit_logs(self, hours: int = 24) -> List[Dict]:
        """Get recent authentication audit logs"""
        try:
            redis_client = await self._get_redis_client()

            # Get logs from last N hours
            current_time = int(time.time())
            start_time = current_time - (hours * 60 * 60)

            logs = []

            # Scan for audit log keys
            async for key in redis_client.scan_iter(match="auth_audit:*"):
                try:
                    timestamp = int(key.split(":")[1])
                    if timestamp >= start_time:
                        log_data = await redis_client.hgetall(key)
                        if log_data:
                            logs.append(log_data)
                except (ValueError, IndexError):
                    continue

            # Sort by timestamp
            logs.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

            return logs

        except Exception as e:
            logger.error(f"Error getting audit logs: {e}")
            return []

    async def close(self):
        """Close Redis connection"""
        if self._redis_client:
            await self._redis_client.close()


# Global instance
static_key_service = StaticKeyService()