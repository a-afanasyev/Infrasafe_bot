#!/usr/bin/env python3
"""
Auth Service Smoke Tests
UK Management Bot - Auth Service

Basic smoke tests to verify Auth Service core functionality
"""

import asyncio
import httpx
import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AuthServiceSmokeTest:
    """Smoke tests for Auth Service"""

    def __init__(self, base_url: str = "http://localhost:8001"):
        self.base_url = base_url
        self.test_results = {}

    async def run_smoke_tests(self):
        """Run all smoke tests"""
        logger.info("🔥 Starting Auth Service smoke tests")

        await self.test_health_check()
        await self.test_service_credentials_validation()
        await self.test_token_generation_security()
        await self.test_permission_validation()
        await self.test_session_lifecycle()

        self.print_results()
        return self.all_tests_passed()

    async def test_health_check(self):
        """Test basic health check"""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.base_url}/health")

                if response.status_code == 200:
                    data = response.json()
                    self.test_results["health_check"] = "✅ PASS"
                    logger.info("✅ Health check: PASS")
                else:
                    self.test_results["health_check"] = f"❌ FAIL: HTTP {response.status_code}"
                    logger.error(f"❌ Health check failed: {response.status_code}")

        except Exception as e:
            self.test_results["health_check"] = f"❌ FAIL: {str(e)}"
            logger.error(f"❌ Health check failed: {e}")

    async def test_service_credentials_validation(self):
        """Test service credentials validation (API key auth)"""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Test the new static API key validation endpoint
                response = await client.post(
                    f"{self.base_url}/api/v1/internal/validate-service-credentials",
                    headers={
                        "X-Service-API-Key": "auth-service-api-key-change-in-production"
                    }
                )

                if response.status_code == 200:
                    data = response.json()
                    if data.get("valid") == True and data.get("service_name") == "auth-service":
                        self.test_results["credentials_validation"] = "✅ PASS"
                        logger.info("✅ Service credentials validation: PASS")
                    else:
                        self.test_results["credentials_validation"] = "❌ FAIL: Invalid validation response"
                        logger.error("❌ Service credentials validation failed: Invalid response")
                else:
                    self.test_results["credentials_validation"] = f"❌ FAIL: HTTP {response.status_code}"
                    logger.error(f"❌ Service credentials validation failed: {response.status_code}")

        except Exception as e:
            self.test_results["credentials_validation"] = f"❌ FAIL: {str(e)}"
            logger.error(f"❌ Service credentials validation failed: {e}")

    async def test_token_generation_security(self):
        """Test that JWT token generation is properly secured (admin-only)"""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Try to call JWT generation without admin auth - should fail
                response = await client.post(
                    f"{self.base_url}/api/v1/internal/generate-service-token",
                    json={
                        "service_name": "test-service",
                        "permissions": ["users:read"]
                    }
                )

                if response.status_code in [401, 403]:
                    self.test_results["token_security"] = "✅ PASS"
                    logger.info("✅ JWT generation security: PASS (properly protected)")
                else:
                    self.test_results["token_security"] = f"❌ FAIL: Should require admin auth but got {response.status_code}"
                    logger.error(f"❌ JWT generation security failed: Expected 401/403, got {response.status_code}")

        except Exception as e:
            self.test_results["token_security"] = f"❌ FAIL: {str(e)}"
            logger.error(f"❌ JWT generation security test failed: {e}")


    async def test_permission_validation(self):
        """Test permission system"""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Try to access permissions endpoint
                response = await client.get(f"{self.base_url}/api/v1/permissions")

                if response.status_code in [200, 401, 403]:
                    # 200 = success, 401/403 = auth required (expected)
                    self.test_results["permission_system"] = "✅ PASS"
                    logger.info("✅ Permission system: PASS")
                else:
                    self.test_results["permission_system"] = f"❌ FAIL: HTTP {response.status_code}"
                    logger.error(f"❌ Permission system failed: {response.status_code}")

        except Exception as e:
            self.test_results["permission_system"] = f"❌ FAIL: {str(e)}"
            logger.error(f"❌ Permission system failed: {e}")

    async def test_session_lifecycle(self):
        """Test session management basics"""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Try to access sessions endpoint
                response = await client.get(f"{self.base_url}/api/v1/sessions")

                if response.status_code in [200, 401, 403]:
                    # 200 = success, 401/403 = auth required (expected)
                    self.test_results["session_lifecycle"] = "✅ PASS"
                    logger.info("✅ Session lifecycle: PASS")
                else:
                    self.test_results["session_lifecycle"] = f"❌ FAIL: HTTP {response.status_code}"
                    logger.error(f"❌ Session lifecycle failed: {response.status_code}")

        except Exception as e:
            self.test_results["session_lifecycle"] = f"❌ FAIL: {str(e)}"
            logger.error(f"❌ Session lifecycle failed: {e}")

    def print_results(self):
        """Print test results"""
        logger.info("\n" + "="*50)
        logger.info("🔥 AUTH SERVICE SMOKE TEST RESULTS")
        logger.info("="*50)

        for test_name, result in self.test_results.items():
            logger.info(f"{test_name.replace('_', ' ').title()}: {result}")

        passed = len([r for r in self.test_results.values() if r.startswith("✅")])
        total = len(self.test_results)

        logger.info(f"\n📊 Summary: {passed}/{total} tests passed")
        logger.info("="*50)

    def all_tests_passed(self):
        """Check if all tests passed"""
        return all(result.startswith("✅") for result in self.test_results.values())

async def main():
    """Run smoke tests"""
    tester = AuthServiceSmokeTest()
    success = await tester.run_smoke_tests()

    if not success:
        exit(1)

if __name__ == "__main__":
    asyncio.run(main())