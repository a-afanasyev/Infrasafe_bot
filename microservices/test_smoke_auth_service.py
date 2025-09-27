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
        await self.test_service_token_generation()
        await self.test_service_token_validation()
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

    async def test_service_token_generation(self):
        """Test service token generation"""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{self.base_url}/api/v1/internal/generate-service-token",
                    json={
                        "service_name": "test-service",
                        "permissions": ["users:read", "requests:read"]
                    }
                )

                if response.status_code == 200:
                    data = response.json()
                    if "token" in data and "service_name" in data:
                        self.test_results["token_generation"] = "✅ PASS"
                        logger.info("✅ Service token generation: PASS")
                        # Store token for validation test
                        self.test_token = data["token"]
                    else:
                        self.test_results["token_generation"] = "❌ FAIL: Invalid response format"
                        logger.error("❌ Token generation: Invalid response format")
                else:
                    self.test_results["token_generation"] = f"❌ FAIL: HTTP {response.status_code}"
                    logger.error(f"❌ Token generation failed: {response.status_code}")

        except Exception as e:
            self.test_results["token_generation"] = f"❌ FAIL: {str(e)}"
            logger.error(f"❌ Token generation failed: {e}")

    async def test_service_token_validation(self):
        """Test service token validation"""
        if not hasattr(self, 'test_token'):
            self.test_results["token_validation"] = "❌ FAIL: No token to validate"
            return

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{self.base_url}/api/v1/internal/validate-service-token",
                    json={
                        "token": self.test_token,
                        "service_name": "test-service"
                    }
                )

                if response.status_code == 200:
                    data = response.json()
                    if data.get("valid") and data.get("service_name") == "test-service":
                        self.test_results["token_validation"] = "✅ PASS"
                        logger.info("✅ Service token validation: PASS")
                    else:
                        self.test_results["token_validation"] = "❌ FAIL: Token not valid"
                        logger.error("❌ Token validation: Token marked as invalid")
                else:
                    self.test_results["token_validation"] = f"❌ FAIL: HTTP {response.status_code}"
                    logger.error(f"❌ Token validation failed: {response.status_code}")

        except Exception as e:
            self.test_results["token_validation"] = f"❌ FAIL: {str(e)}"
            logger.error(f"❌ Token validation failed: {e}")

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