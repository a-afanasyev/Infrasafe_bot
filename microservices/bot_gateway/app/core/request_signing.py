"""
Request Signing for Service-to-Service Authentication
UK Management Bot - Bot Gateway Service

HMAC-based request signing to prevent tampering and replay attacks.
"""

import hmac
import hashlib
import time
import logging
from typing import Optional, Dict
from dataclasses import dataclass

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class SignatureResult:
    """Result of signature verification"""
    valid: bool
    error: Optional[str] = None
    timestamp: Optional[int] = None


class RequestSigner:
    """
    HMAC-SHA256 request signing for service-to-service communication.

    Features:
    - HMAC-SHA256 signatures
    - Timestamp validation (prevents replay attacks)
    - Per-service secret keys
    - Signature verification
    """

    # Signature valid for 5 minutes
    MAX_TIMESTAMP_DELTA = 300

    def __init__(self, secret_key: Optional[str] = None):
        """
        Initialize request signer.

        Args:
            secret_key: Secret key for HMAC (uses JWT secret if not provided)
        """
        self.secret_key = secret_key or settings.JWT_SECRET_KEY

    def sign_request(
        self,
        method: str,
        path: str,
        body: Optional[str] = None,
        timestamp: Optional[int] = None
    ) -> tuple[str, int]:
        """
        Sign HTTP request.

        Args:
            method: HTTP method (GET, POST, etc.)
            path: Request path
            body: Request body (if any)
            timestamp: Unix timestamp (generated if not provided)

        Returns:
            (signature, timestamp) tuple
        """
        # Get current timestamp if not provided
        if timestamp is None:
            timestamp = int(time.time())

        # Build signature string
        signature_string = self._build_signature_string(
            method=method,
            path=path,
            body=body,
            timestamp=timestamp
        )

        # Generate HMAC signature
        signature = self._generate_hmac(signature_string)

        return signature, timestamp

    def verify_request(
        self,
        method: str,
        path: str,
        signature: str,
        timestamp: int,
        body: Optional[str] = None
    ) -> SignatureResult:
        """
        Verify request signature.

        Args:
            method: HTTP method
            path: Request path
            signature: Signature to verify
            timestamp: Request timestamp
            body: Request body (if any)

        Returns:
            SignatureResult with validation result
        """
        # Check timestamp is not too old (prevent replay attacks)
        current_time = int(time.time())
        time_delta = abs(current_time - timestamp)

        if time_delta > self.MAX_TIMESTAMP_DELTA:
            return SignatureResult(
                valid=False,
                error=f"Timestamp too old (delta: {time_delta}s, max: {self.MAX_TIMESTAMP_DELTA}s)",
                timestamp=timestamp
            )

        # Rebuild signature string
        signature_string = self._build_signature_string(
            method=method,
            path=path,
            body=body,
            timestamp=timestamp
        )

        # Generate expected signature
        expected_signature = self._generate_hmac(signature_string)

        # Compare signatures (constant time comparison)
        if not hmac.compare_digest(signature, expected_signature):
            return SignatureResult(
                valid=False,
                error="Invalid signature",
                timestamp=timestamp
            )

        return SignatureResult(
            valid=True,
            timestamp=timestamp
        )

    def _build_signature_string(
        self,
        method: str,
        path: str,
        body: Optional[str],
        timestamp: int
    ) -> str:
        """
        Build canonical string for signing.

        Format: METHOD\nPATH\nTIMESTAMP\nBODY_HASH

        Args:
            method: HTTP method
            path: Request path
            body: Request body
            timestamp: Unix timestamp

        Returns:
            Canonical signature string
        """
        # Normalize method to uppercase
        method = method.upper()

        # Hash body if present
        if body:
            body_hash = hashlib.sha256(body.encode()).hexdigest()
        else:
            body_hash = ""

        # Build canonical string
        parts = [
            method,
            path,
            str(timestamp),
            body_hash
        ]

        return "\n".join(parts)

    def _generate_hmac(self, data: str) -> str:
        """
        Generate HMAC-SHA256 signature.

        Args:
            data: Data to sign

        Returns:
            Hex-encoded HMAC signature
        """
        signature = hmac.new(
            key=self.secret_key.encode(),
            msg=data.encode(),
            digestmod=hashlib.sha256
        ).hexdigest()

        return signature


class ServiceAuthenticator:
    """
    Service-to-service authentication manager.

    Features:
    - Per-service secret keys
    - Automatic signature generation
    - Signature verification
    - Service identity validation
    """

    def __init__(self):
        """Initialize service authenticator"""
        # Service-specific keys (in production, load from secure storage)
        self.service_keys: Dict[str, str] = {
            "auth-service": getattr(settings, "AUTH_SERVICE_KEY", settings.JWT_SECRET_KEY),
            "user-service": getattr(settings, "USER_SERVICE_KEY", settings.JWT_SECRET_KEY),
            "request-service": getattr(settings, "REQUEST_SERVICE_KEY", settings.JWT_SECRET_KEY),
            "shift-service": getattr(settings, "SHIFT_SERVICE_KEY", settings.JWT_SECRET_KEY),
            "notification-service": getattr(settings, "NOTIFICATION_SERVICE_KEY", settings.JWT_SECRET_KEY),
            "analytics-service": getattr(settings, "ANALYTICS_SERVICE_KEY", settings.JWT_SECRET_KEY),
            "ai-service": getattr(settings, "AI_SERVICE_KEY", settings.JWT_SECRET_KEY),
            "media-service": getattr(settings, "MEDIA_SERVICE_KEY", settings.JWT_SECRET_KEY),
            "integration-service": getattr(settings, "INTEGRATION_SERVICE_KEY", settings.JWT_SECRET_KEY),
        }

    def get_signer(self, service_name: str) -> RequestSigner:
        """
        Get request signer for service.

        Args:
            service_name: Name of the service

        Returns:
            RequestSigner instance

        Raises:
            ValueError: If service is unknown
        """
        if service_name not in self.service_keys:
            raise ValueError(f"Unknown service: {service_name}")

        secret_key = self.service_keys[service_name]
        return RequestSigner(secret_key)

    def sign_outgoing_request(
        self,
        service_name: str,
        method: str,
        path: str,
        body: Optional[str] = None
    ) -> Dict[str, str]:
        """
        Sign outgoing request to another service.

        Args:
            service_name: Target service name
            method: HTTP method
            path: Request path
            body: Request body

        Returns:
            Headers dict with signature and timestamp
        """
        signer = self.get_signer(service_name)
        signature, timestamp = signer.sign_request(method, path, body)

        return {
            "X-Service-Signature": signature,
            "X-Service-Timestamp": str(timestamp),
            "X-Service-Name": "bot-gateway"
        }

    def verify_incoming_request(
        self,
        from_service: str,
        method: str,
        path: str,
        signature: str,
        timestamp: str,
        body: Optional[str] = None
    ) -> SignatureResult:
        """
        Verify incoming request from another service.

        Args:
            from_service: Source service name
            method: HTTP method
            path: Request path
            signature: Request signature
            timestamp: Request timestamp
            body: Request body

        Returns:
            SignatureResult with validation result
        """
        try:
            signer = self.get_signer(from_service)
            timestamp_int = int(timestamp)

            return signer.verify_request(
                method=method,
                path=path,
                signature=signature,
                timestamp=timestamp_int,
                body=body
            )

        except ValueError as e:
            return SignatureResult(
                valid=False,
                error=str(e)
            )
        except Exception as e:
            logger.error(f"Error verifying request signature: {e}")
            return SignatureResult(
                valid=False,
                error="Internal error"
            )


# Global service authenticator
service_authenticator = ServiceAuthenticator()
