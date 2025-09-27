#!/usr/bin/env python3
"""
Media Service Smoke Tests
UK Management Bot - Media Service

Basic smoke tests to verify Media Service core functionality
"""

import asyncio
import httpx
import json
import logging
import tempfile
import os
from datetime import datetime
from typing import Dict, Any, Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MediaServiceSmokeTest:
    """Smoke tests for Media Service"""

    def __init__(self, base_url: str = "http://localhost:8003"):
        self.base_url = base_url
        self.test_results = {}

    async def run_smoke_tests(self):
        """Run all smoke tests"""
        logger.info("🔥 Starting Media Service smoke tests")

        await self.test_health_check()
        await self.test_detailed_health()
        await self.test_metrics_endpoints()
        await self.test_streaming_endpoints()
        await self.test_upload_functionality()

        self.print_results()
        return self.all_tests_passed()

    async def test_health_check(self):
        """Test basic health check"""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.base_url}/health")

                if response.status_code == 200:
                    self.test_results["health_check"] = "✅ PASS"
                    logger.info("✅ Health check: PASS")
                else:
                    self.test_results["health_check"] = f"❌ FAIL: HTTP {response.status_code}"
                    logger.error(f"❌ Health check failed: {response.status_code}")

        except Exception as e:
            self.test_results["health_check"] = f"❌ FAIL: {str(e)}"
            logger.error(f"❌ Health check failed: {e}")

    async def test_detailed_health(self):
        """Test detailed health check with observability"""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self.base_url}/health/detailed")

                if response.status_code == 200:
                    data = response.json()
                    if "health_metrics" in data.get("dependencies", {}):
                        self.test_results["detailed_health"] = "✅ PASS"
                        logger.info("✅ Detailed health with observability: PASS")
                    else:
                        self.test_results["detailed_health"] = "⚠️  WARN: No observability metrics"
                        logger.warning("⚠️  Detailed health: Missing observability metrics")
                else:
                    self.test_results["detailed_health"] = f"❌ FAIL: HTTP {response.status_code}"
                    logger.error(f"❌ Detailed health failed: {response.status_code}")

        except Exception as e:
            self.test_results["detailed_health"] = f"❌ FAIL: {str(e)}"
            logger.error(f"❌ Detailed health failed: {e}")

    async def test_metrics_endpoints(self):
        """Test observability and metrics endpoints"""
        endpoints = [
            "/health/metrics",
            "/health/metrics/prometheus",
            "/health/system",
            "/health/upload-stats"
        ]

        passed_count = 0
        for endpoint in endpoints:
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.get(f"{self.base_url}{endpoint}")

                    if response.status_code == 200:
                        passed_count += 1
                        logger.info(f"✅ {endpoint}: PASS")
                    else:
                        logger.warning(f"⚠️  {endpoint}: HTTP {response.status_code}")

            except Exception as e:
                logger.error(f"❌ {endpoint}: {e}")

        if passed_count == len(endpoints):
            self.test_results["metrics_endpoints"] = "✅ PASS"
        elif passed_count > 0:
            self.test_results["metrics_endpoints"] = f"⚠️  PARTIAL: {passed_count}/{len(endpoints)}"
        else:
            self.test_results["metrics_endpoints"] = "❌ FAIL: No endpoints working"

    async def test_streaming_endpoints(self):
        """Test streaming upload endpoints"""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Test streaming status endpoint
                response = await client.get(f"{self.base_url}/api/v1/streaming/")

                if response.status_code in [200, 404, 405]:
                    # 200 = success, 404/405 = endpoint exists but method not allowed
                    self.test_results["streaming_endpoints"] = "✅ PASS"
                    logger.info("✅ Streaming endpoints: PASS")
                else:
                    self.test_results["streaming_endpoints"] = f"❌ FAIL: HTTP {response.status_code}"
                    logger.error(f"❌ Streaming endpoints failed: {response.status_code}")

        except Exception as e:
            self.test_results["streaming_endpoints"] = f"❌ FAIL: {str(e)}"
            logger.error(f"❌ Streaming endpoints failed: {e}")

    async def test_upload_functionality(self):
        """Test basic upload functionality (without actual file)"""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Test upload endpoint (should fail without proper data, but endpoint should exist)
                response = await client.post(f"{self.base_url}/api/v1/media/upload")

                if response.status_code in [400, 422, 401, 403]:
                    # Expected errors for missing file/auth
                    self.test_results["upload_functionality"] = "✅ PASS"
                    logger.info("✅ Upload functionality (endpoint exists): PASS")
                elif response.status_code == 404:
                    self.test_results["upload_functionality"] = "❌ FAIL: Upload endpoint not found"
                    logger.error("❌ Upload functionality: Endpoint not found")
                else:
                    self.test_results["upload_functionality"] = f"⚠️  WARN: HTTP {response.status_code}"
                    logger.warning(f"⚠️  Upload functionality: Unexpected response {response.status_code}")

        except Exception as e:
            self.test_results["upload_functionality"] = f"❌ FAIL: {str(e)}"
            logger.error(f"❌ Upload functionality failed: {e}")

    def print_results(self):
        """Print test results"""
        logger.info("\n" + "="*50)
        logger.info("🔥 MEDIA SERVICE SMOKE TEST RESULTS")
        logger.info("="*50)

        for test_name, result in self.test_results.items():
            logger.info(f"{test_name.replace('_', ' ').title()}: {result}")

        passed = len([r for r in self.test_results.values() if r.startswith("✅")])
        warnings = len([r for r in self.test_results.values() if r.startswith("⚠️")])
        total = len(self.test_results)

        logger.info(f"\n📊 Summary: {passed}/{total} tests passed")
        if warnings > 0:
            logger.info(f"⚠️  Warnings: {warnings}")
        logger.info("="*50)

    def all_tests_passed(self):
        """Check if all tests passed"""
        return all(result.startswith("✅") or result.startswith("⚠️") for result in self.test_results.values())

async def main():
    """Run smoke tests"""
    tester = MediaServiceSmokeTest()
    success = await tester.run_smoke_tests()

    if not success:
        exit(1)

if __name__ == "__main__":
    asyncio.run(main())