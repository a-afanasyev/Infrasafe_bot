"""
Base HTTP Client for Microservices
UK Management Bot - Bot Gateway Service

Base class for all microservice client implementations.
"""

import logging
from typing import Any, Dict, Optional
from datetime import datetime

import httpx
from app.core.config import settings

logger = logging.getLogger(__name__)


class BaseServiceClient:
    """
    Base HTTP client for microservices communication.

    Provides:
    - HTTP methods (GET, POST, PUT, DELETE, PATCH)
    - Automatic JWT token handling
    - Retry logic with exponential backoff
    - Error handling and logging
    - Request/response tracking
    """

    def __init__(self, base_url: str, service_name: str):
        """
        Initialize service client.

        Args:
            base_url: Base URL of the microservice
            service_name: Service name for logging
        """
        self.base_url = base_url.rstrip("/")
        self.service_name = service_name
        self.timeout = httpx.Timeout(settings.SERVICE_CALL_TIMEOUT_SECONDS)

        # Create persistent HTTP client
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            follow_redirects=True
        )

    async def close(self) -> None:
        """Close HTTP client"""
        await self.client.aclose()

    def _build_headers(
        self,
        token: Optional[str] = None,
        extra_headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, str]:
        """
        Build request headers.

        Args:
            token: JWT access token
            extra_headers: Additional headers

        Returns:
            Complete headers dict
        """
        headers = {
            "Content-Type": "application/json",
            "X-Service-Name": "bot-gateway",
            "X-Request-ID": f"bot-{datetime.utcnow().timestamp()}",
        }

        if token:
            headers["Authorization"] = f"Bearer {token}"

        if extra_headers:
            headers.update(extra_headers)

        return headers

    async def _request(
        self,
        method: str,
        endpoint: str,
        token: Optional[str] = None,
        json_data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        retry_count: int = 0
    ) -> httpx.Response:
        """
        Make HTTP request with retry logic.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE, PATCH)
            endpoint: API endpoint (e.g., "/users/me")
            token: JWT access token
            json_data: JSON request body
            params: Query parameters
            headers: Additional headers
            retry_count: Current retry attempt

        Returns:
            HTTP response

        Raises:
            httpx.HTTPStatusError: On HTTP error
            httpx.TimeoutException: On timeout
        """
        request_headers = self._build_headers(token, headers)
        url = f"{self.base_url}{endpoint}"

        try:
            response = await self.client.request(
                method=method,
                url=url,
                json=json_data,
                params=params,
                headers=request_headers
            )

            # Log request
            logger.debug(
                f"{self.service_name} {method} {endpoint} -> {response.status_code}"
            )

            # Raise for HTTP errors
            response.raise_for_status()

            return response

        except httpx.HTTPStatusError as e:
            logger.error(
                f"{self.service_name} HTTP error: {method} {endpoint} -> "
                f"{e.response.status_code}: {e.response.text}"
            )
            raise

        except httpx.TimeoutException as e:
            logger.error(
                f"{self.service_name} timeout: {method} {endpoint}"
            )

            # Retry logic
            if retry_count < settings.SERVICE_CALL_RETRIES:
                logger.info(
                    f"Retrying {self.service_name} {method} {endpoint} "
                    f"(attempt {retry_count + 1}/{settings.SERVICE_CALL_RETRIES})"
                )
                return await self._request(
                    method=method,
                    endpoint=endpoint,
                    token=token,
                    json_data=json_data,
                    params=params,
                    headers=headers,
                    retry_count=retry_count + 1
                )

            raise

        except Exception as e:
            logger.error(
                f"{self.service_name} request failed: {method} {endpoint} - {e}",
                exc_info=True
            )
            raise

    async def get(
        self,
        endpoint: str,
        token: Optional[str] = None,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None
    ) -> httpx.Response:
        """GET request"""
        return await self._request("GET", endpoint, token, params=params, headers=headers)

    async def post(
        self,
        endpoint: str,
        data: Dict[str, Any],
        token: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None
    ) -> httpx.Response:
        """POST request"""
        return await self._request("POST", endpoint, token, json_data=data, headers=headers)

    async def put(
        self,
        endpoint: str,
        data: Dict[str, Any],
        token: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None
    ) -> httpx.Response:
        """PUT request"""
        return await self._request("PUT", endpoint, token, json_data=data, headers=headers)

    async def patch(
        self,
        endpoint: str,
        data: Dict[str, Any],
        token: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None
    ) -> httpx.Response:
        """PATCH request"""
        return await self._request("PATCH", endpoint, token, json_data=data, headers=headers)

    async def delete(
        self,
        endpoint: str,
        token: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None
    ) -> httpx.Response:
        """DELETE request"""
        return await self._request("DELETE", endpoint, token, headers=headers)

    async def health_check(self) -> bool:
        """
        Check service health.

        Returns:
            True if service is healthy, False otherwise
        """
        try:
            response = await self.get("/health")
            return response.status_code == 200
        except Exception:
            return False
