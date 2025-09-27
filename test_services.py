#!/usr/bin/env python3
"""
Quick Service Test Script
Tests the basic functionality of UK Management Bot microservices
"""

import asyncio
import httpx
import json
import sys
from typing import Dict, Any

class ServiceTester:
    def __init__(self):
        self.base_urls = {
            "auth": "http://localhost:8000",
            "user": "http://localhost:8001",
            "notification": "http://localhost:8003"
        }
        self.test_results = {}

    async def test_service_health(self, service_name: str, url: str) -> Dict[str, Any]:
        """Test service health endpoint"""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{url}/health")

                if response.status_code == 200:
                    data = response.json()
                    return {
                        "status": "✅ HEALTHY",
                        "response_time": response.elapsed.total_seconds(),
                        "data": data
                    }
                else:
                    return {
                        "status": "❌ UNHEALTHY",
                        "status_code": response.status_code,
                        "response": response.text
                    }

        except httpx.ConnectError:
            return {
                "status": "❌ NOT_RUNNING",
                "error": "Connection refused - service not running"
            }
        except httpx.TimeoutException:
            return {
                "status": "❌ TIMEOUT",
                "error": "Service did not respond within 5 seconds"
            }
        except Exception as e:
            return {
                "status": "❌ ERROR",
                "error": str(e)
            }

    async def test_service_info(self, service_name: str, url: str) -> Dict[str, Any]:
        """Test service info endpoint"""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{url}/info")

                if response.status_code == 200:
                    return {
                        "status": "✅ AVAILABLE",
                        "data": response.json()
                    }
                else:
                    return {
                        "status": "❌ UNAVAILABLE",
                        "status_code": response.status_code
                    }

        except Exception as e:
            return {
                "status": "❌ ERROR",
                "error": str(e)
            }

    async def test_auth_service_specific(self, url: str) -> Dict[str, Any]:
        """Test Auth Service specific endpoints"""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                # Test permissions endpoint
                response = await client.get(f"{url}/api/v1/permissions/roles")

                if response.status_code == 200:
                    return {
                        "status": "✅ API_WORKING",
                        "endpoints_tested": ["GET /api/v1/permissions/roles"],
                        "roles_count": len(response.json())
                    }
                else:
                    return {
                        "status": "❌ API_ERROR",
                        "status_code": response.status_code
                    }

        except Exception as e:
            return {
                "status": "❌ ERROR",
                "error": str(e)
            }

    async def test_user_service_specific(self, url: str) -> Dict[str, Any]:
        """Test User Service specific endpoints"""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                # Test users stats endpoint
                response = await client.get(f"{url}/api/v1/users/stats/overview")

                if response.status_code == 200:
                    return {
                        "status": "✅ API_WORKING",
                        "endpoints_tested": ["GET /api/v1/users/stats/overview"],
                        "stats": response.json()
                    }
                else:
                    return {
                        "status": "❌ API_ERROR",
                        "status_code": response.status_code
                    }

        except Exception as e:
            return {
                "status": "❌ ERROR",
                "error": str(e)
            }

    async def run_tests(self):
        """Run all service tests"""
        print("🚀 UK Management Bot - Service Health Check")
        print("=" * 50)

        for service_name, url in self.base_urls.items():
            print(f"\n📋 Testing {service_name.upper()} Service ({url})")
            print("-" * 30)

            # Test health endpoint
            health_result = await self.test_service_health(service_name, url)
            print(f"Health Check: {health_result['status']}")

            if health_result['status'] == "✅ HEALTHY":
                print(f"Response Time: {health_result['response_time']:.3f}s")

                # Test info endpoint
                info_result = await self.test_service_info(service_name, url)
                print(f"Info Endpoint: {info_result['status']}")

                # Test service-specific endpoints
                if service_name == "auth":
                    api_result = await self.test_auth_service_specific(url)
                    print(f"API Endpoints: {api_result['status']}")
                    if api_result['status'] == "✅ API_WORKING":
                        print(f"Roles Available: {api_result.get('roles_count', 0)}")

                elif service_name == "user":
                    api_result = await self.test_user_service_specific(url)
                    print(f"API Endpoints: {api_result['status']}")
                    if api_result['status'] == "✅ API_WORKING":
                        stats = api_result.get('stats', {})
                        print(f"Total Users: {stats.get('total_users', 0)}")

            else:
                print(f"Error: {health_result.get('error', 'Unknown error')}")

            self.test_results[service_name] = health_result

    def print_summary(self):
        """Print test summary"""
        print("\n" + "=" * 50)
        print("📊 TEST SUMMARY")
        print("=" * 50)

        healthy_count = 0
        total_count = len(self.test_results)

        for service_name, result in self.test_results.items():
            status_icon = "✅" if result['status'] == "✅ HEALTHY" else "❌"
            print(f"{status_icon} {service_name.upper()} Service: {result['status']}")

            if result['status'] == "✅ HEALTHY":
                healthy_count += 1

        print(f"\n🎯 Overall Status: {healthy_count}/{total_count} services healthy")

        if healthy_count == total_count:
            print("🎉 All services are running correctly!")
            return True
        else:
            print("⚠️  Some services need attention.")
            return False

async def main():
    """Main test function"""
    tester = ServiceTester()

    try:
        await tester.run_tests()
        success = tester.print_summary()

        if success:
            sys.exit(0)
        else:
            sys.exit(1)

    except KeyboardInterrupt:
        print("\n❌ Tests interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Test runner error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())