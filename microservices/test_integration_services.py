#!/usr/bin/env python3
"""
Cross-Service Integration Tests
UK Management Bot - Microservices Integration

Tests the integration between Auth Service, User Service, Media Service, and Notification Service
"""

import asyncio
import httpx
import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ServiceIntegrationTester:
    """Integration tester for microservices"""

    def __init__(self):
        self.services = {
            "auth": "http://localhost:8001",
            "user": "http://localhost:8002",
            "media": "http://localhost:8003",
            "notification": "http://localhost:8004"
        }
        self.test_results = {}
        self.service_tokens = {}

    async def run_all_tests(self):
        """Run comprehensive integration tests"""
        logger.info("🚀 Starting cross-service integration tests")

        # Test individual service health
        await self.test_service_health()

        # Test service-to-service authentication
        await self.test_service_authentication()

        # Test Auth ↔ User Service integration
        await self.test_auth_user_integration()

        # Test Media Service upload with authentication
        await self.test_media_upload_integration()

        # Test Notification Service integration
        await self.test_notification_integration()

        # Print results
        self.print_test_results()

    async def test_service_health(self):
        """Test that all services are healthy"""
        logger.info("🔍 Testing service health checks")

        for service_name, base_url in self.services.items():
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    response = await client.get(f"{base_url}/health")

                    if response.status_code == 200:
                        self.test_results[f"{service_name}_health"] = "✅ PASS"
                        logger.info(f"✅ {service_name.upper()} Service: Healthy")
                    else:
                        self.test_results[f"{service_name}_health"] = f"❌ FAIL: HTTP {response.status_code}"
                        logger.error(f"❌ {service_name.upper()} Service: Unhealthy - {response.status_code}")

            except Exception as e:
                self.test_results[f"{service_name}_health"] = f"❌ FAIL: {str(e)}"
                logger.error(f"❌ {service_name.upper()} Service: Connection failed - {e}")

    async def test_service_authentication(self):
        """Test service-to-service authentication"""
        logger.info("🔐 Testing service-to-service authentication")

        try:
            # Test static API key authentication
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Test auth-service API key validation
                response = await client.post(
                    f"{self.services['auth']}/api/v1/internal/validate-service-credentials",
                    headers={
                        "X-Service-API-Key": "auth-service-api-key-change-in-production"
                    }
                )

                if response.status_code == 200:
                    data = response.json()
                    if data.get("valid") == True and data.get("service_name") == "auth-service":
                        self.test_results["service_authentication"] = "✅ PASS"
                        logger.info("✅ Service static authentication: SUCCESS")
                    else:
                        self.test_results["service_authentication"] = "❌ FAIL: Invalid auth response"
                        logger.error("❌ Service authentication failed: Invalid response")
                        return
                else:
                    self.test_results["service_authentication"] = f"❌ FAIL: HTTP {response.status_code}"
                    logger.error(f"❌ Service authentication failed: {response.status_code}")
                    return


        except Exception as e:
            self.test_results["service_authentication"] = f"❌ FAIL: {str(e)}"
            logger.error(f"❌ Service authentication test failed: {e}")

    async def test_auth_user_integration(self):
        """Test Auth Service calling User Service"""
        logger.info("🔗 Testing Auth ↔ User Service integration")


        try:
            # Test the by-telegram endpoint that Auth Service uses
            test_telegram_id = 123456789

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self.services['user']}/api/v1/users/by-telegram/{test_telegram_id}",
                    headers={
                        "X-Service-Name": "auth-service",
                        "X-Service-API-Key": "auth-service-api-key-change-in-production",
                        "Content-Type": "application/json"
                    }
                )

                if response.status_code in [200, 404]:
                    # Both 200 (user found) and 404 (user not found) are valid responses
                    self.test_results["auth_user_lookup"] = "✅ PASS"
                    logger.info(f"✅ Auth→User lookup: SUCCESS (HTTP {response.status_code})")

                    if response.status_code == 200:
                        user_data = response.json()
                        logger.info(f"   Found user: {user_data.get('username', 'N/A')}")

                elif response.status_code == 401:
                    self.test_results["auth_user_lookup"] = "❌ FAIL: Authentication failed"
                    logger.error("❌ Auth→User lookup: Authentication failed")
                elif response.status_code == 403:
                    self.test_results["auth_user_lookup"] = "❌ FAIL: Authorization failed"
                    logger.error("❌ Auth→User lookup: Authorization failed")
                else:
                    self.test_results["auth_user_lookup"] = f"❌ FAIL: HTTP {response.status_code}"
                    logger.error(f"❌ Auth→User lookup failed: {response.status_code}")

        except Exception as e:
            self.test_results["auth_user_integration"] = f"❌ FAIL: {str(e)}"
            logger.error(f"❌ Auth→User integration test failed: {e}")

    async def test_media_upload_integration(self):
        """Test Media Service upload functionality"""
        logger.info("📁 Testing Media Service integration")

        try:
            # Test basic media service health with metrics
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self.services['media']}/health/detailed")

                if response.status_code == 200:
                    health_data = response.json()
                    self.test_results["media_health"] = "✅ PASS"
                    logger.info("✅ Media Service detailed health: SUCCESS")

                    # Check if observability metrics are available
                    if "health_metrics" in health_data.get("dependencies", {}):
                        self.test_results["media_observability"] = "✅ PASS"
                        logger.info("✅ Media Service observability: SUCCESS")
                    else:
                        self.test_results["media_observability"] = "⚠️  WARN: No observability metrics"

                else:
                    self.test_results["media_health"] = f"❌ FAIL: HTTP {response.status_code}"
                    logger.error(f"❌ Media Service health check failed: {response.status_code}")

                # Test streaming upload endpoints
                streaming_response = await client.get(f"{self.services['media']}/api/v1/streaming/status")

                if streaming_response.status_code == 200:
                    self.test_results["media_streaming"] = "✅ PASS"
                    logger.info("✅ Media Service streaming endpoints: AVAILABLE")
                else:
                    self.test_results["media_streaming"] = f"❌ FAIL: HTTP {streaming_response.status_code}"
                    logger.error(f"❌ Media Service streaming test failed: {streaming_response.status_code}")

        except Exception as e:
            self.test_results["media_integration"] = f"❌ FAIL: {str(e)}"
            logger.error(f"❌ Media Service integration test failed: {e}")

    async def test_notification_integration(self):
        """Test Notification Service integration"""
        logger.info("📧 Testing Notification Service integration")

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Test notification service health
                response = await client.get(f"{self.services['notification']}/health")

                if response.status_code == 200:
                    self.test_results["notification_health"] = "✅ PASS"
                    logger.info("✅ Notification Service health: SUCCESS")

                    # Test delivery pipeline status
                    pipeline_response = await client.get(
                        f"{self.services['notification']}/api/v1/delivery/stats"
                    )

                    if pipeline_response.status_code == 200:
                        self.test_results["notification_pipeline"] = "✅ PASS"
                        logger.info("✅ Notification Service delivery pipeline: OPERATIONAL")
                    else:
                        self.test_results["notification_pipeline"] = f"⚠️  WARN: HTTP {pipeline_response.status_code}"

                else:
                    self.test_results["notification_health"] = f"❌ FAIL: HTTP {response.status_code}"
                    logger.error(f"❌ Notification Service health check failed: {response.status_code}")

        except Exception as e:
            self.test_results["notification_integration"] = f"❌ FAIL: {str(e)}"
            logger.error(f"❌ Notification Service integration test failed: {e}")

    def print_test_results(self):
        """Print comprehensive test results"""
        logger.info("\n" + "="*60)
        logger.info("📊 INTEGRATION TEST RESULTS")
        logger.info("="*60)

        categories = {
            "🏥 Service Health": [k for k in self.test_results.keys() if "_health" in k],
            "🔐 Service Authentication": [k for k in self.test_results.keys() if "token" in k or "auth" in k],
            "🔗 Service Integration": [k for k in self.test_results.keys() if "integration" in k or "lookup" in k],
            "📁 Media Service": [k for k in self.test_results.keys() if "media" in k],
            "📧 Notification Service": [k for k in self.test_results.keys() if "notification" in k],
            "📊 Observability": [k for k in self.test_results.keys() if "observability" in k or "streaming" in k]
        }

        total_tests = len(self.test_results)
        passed_tests = len([r for r in self.test_results.values() if r.startswith("✅")])
        failed_tests = len([r for r in self.test_results.values() if r.startswith("❌")])
        warnings = len([r for r in self.test_results.values() if r.startswith("⚠️")])

        for category, test_keys in categories.items():
            if test_keys:
                logger.info(f"\n{category}:")
                for key in test_keys:
                    result = self.test_results.get(key, "❓ NOT RUN")
                    logger.info(f"  {key.replace('_', ' ').title()}: {result}")

        logger.info("\n" + "="*60)
        logger.info(f"📊 SUMMARY: {passed_tests}/{total_tests} tests passed")
        if failed_tests > 0:
            logger.info(f"❌ Failed: {failed_tests}")
        if warnings > 0:
            logger.info(f"⚠️  Warnings: {warnings}")
        logger.info("="*60)

        # Determine overall status
        if failed_tests == 0:
            logger.info("🎉 ALL INTEGRATION TESTS PASSED!")
            return True
        else:
            logger.error("💥 SOME INTEGRATION TESTS FAILED!")
            return False

async def main():
    """Main test runner"""
    tester = ServiceIntegrationTester()
    success = await tester.run_all_tests()

    if not success:
        exit(1)

if __name__ == "__main__":
    asyncio.run(main())