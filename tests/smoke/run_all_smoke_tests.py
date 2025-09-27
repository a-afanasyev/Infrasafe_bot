#!/usr/bin/env python3
# Master Smoke Test Runner
# UK Management Bot - Comprehensive Integration Testing

import asyncio
import sys
import time
from pathlib import Path

# Import all smoke test modules
sys.path.append(str(Path(__file__).parent))

from test_auth_user_integration import run_smoke_tests as run_auth_user_tests
from test_user_crud import run_user_crud_tests
from test_media_upload import run_media_upload_tests
from test_auth_service_complete import run_auth_service_tests
from test_microservices_integration import run_microservices_integration_tests

async def check_service_availability():
    """Check if all services are available before running tests"""
    import httpx

    services = [
        ("Auth Service", "http://localhost:8000/health"),
        ("User Service", "http://localhost:8001/health"),
        ("Media Service", "http://localhost:8080/health")
    ]

    available_services = []
    unavailable_services = []

    print("🔍 Checking service availability...")

    async with httpx.AsyncClient(timeout=5.0) as client:
        for service_name, health_url in services:
            try:
                response = await client.get(health_url)
                if response.status_code == 200:
                    health_data = response.json()
                    if health_data.get("status") == "healthy":
                        available_services.append(service_name)
                        print(f"✅ {service_name} is available and healthy")
                    else:
                        unavailable_services.append(service_name)
                        print(f"⚠️  {service_name} is available but reports unhealthy")
                else:
                    unavailable_services.append(service_name)
                    print(f"❌ {service_name} returned {response.status_code}")
            except httpx.RequestError as e:
                unavailable_services.append(service_name)
                print(f"❌ {service_name} is not available: {e}")

    return available_services, unavailable_services

async def run_all_smoke_tests():
    """Run all smoke tests in sequence"""
    print("=" * 70)
    print("🧪 UK MANAGEMENT BOT - COMPREHENSIVE SMOKE TESTS")
    print("=" * 70)

    start_time = time.time()

    # Check service availability
    available_services, unavailable_services = await check_service_availability()

    if unavailable_services:
        print(f"\n⚠️  Some services are unavailable: {', '.join(unavailable_services)}")
        print("Tests will run for available services only.\n")

    if not available_services:
        print("❌ No services are available. Cannot run smoke tests.")
        return False

    print(f"\n🚀 Starting smoke tests for: {', '.join(available_services)}")
    print("=" * 70)

    # Test suite configuration
    test_suites = []

    # Run Auth Service complete tests if available
    if "Auth Service" in available_services:
        test_suites.append({
            "name": "Auth Service Complete",
            "runner": run_auth_service_tests,
            "description": "Authentication, passwords, MFA, service tokens, and rate limiting"
        })

    # Always run auth-user integration if both are available
    if "Auth Service" in available_services and "User Service" in available_services:
        test_suites.append({
            "name": "Auth-User Service Integration",
            "runner": run_auth_user_tests,
            "description": "Service-to-service authentication and communication"
        })

    # Run user CRUD tests if User Service is available
    if "User Service" in available_services:
        test_suites.append({
            "name": "User CRUD Operations",
            "runner": run_user_crud_tests,
            "description": "User creation, retrieval, update, and deletion"
        })

    # Run media upload tests if Media Service is available
    if "Media Service" in available_services:
        test_suites.append({
            "name": "Media Upload Operations",
            "runner": run_media_upload_tests,
            "description": "File upload, streaming, and retrieval"
        })

    # Run comprehensive integration tests if multiple services are available
    if len(available_services) >= 2:
        test_suites.append({
            "name": "Microservices Integration",
            "runner": run_microservices_integration_tests,
            "description": "End-to-end integration testing across all services"
        })

    if not test_suites:
        print("❌ No test suites can be run with available services.")
        return False

    # Run all test suites
    overall_results = {
        "total_suites": len(test_suites),
        "passed_suites": 0,
        "failed_suites": 0,
        "suite_results": []
    }

    for i, suite in enumerate(test_suites, 1):
        print(f"\n📋 TEST SUITE {i}/{len(test_suites)}: {suite['name']}")
        print(f"📄 {suite['description']}")
        print("-" * 70)

        suite_start_time = time.time()

        try:
            success = await suite["runner"]()
            suite_duration = time.time() - suite_start_time

            if success:
                overall_results["passed_suites"] += 1
                result_status = "✅ PASSED"
            else:
                overall_results["failed_suites"] += 1
                result_status = "❌ FAILED"

            overall_results["suite_results"].append({
                "name": suite["name"],
                "success": success,
                "duration": suite_duration
            })

            print(f"\n{result_status} - {suite['name']} ({suite_duration:.1f}s)")

        except Exception as e:
            suite_duration = time.time() - suite_start_time
            overall_results["failed_suites"] += 1
            overall_results["suite_results"].append({
                "name": suite["name"],
                "success": False,
                "duration": suite_duration,
                "error": str(e)
            })

            print(f"\n❌ FAILED - {suite['name']} ({suite_duration:.1f}s)")
            print(f"Error: {e}")

        # Add delay between test suites
        if i < len(test_suites):
            print(f"\n⏳ Waiting 2 seconds before next test suite...")
            await asyncio.sleep(2)

    # Overall results
    total_duration = time.time() - start_time

    print("\n" + "=" * 70)
    print("📊 OVERALL SMOKE TEST RESULTS")
    print("=" * 70)

    print(f"🔧 Services tested: {', '.join(available_services)}")
    if unavailable_services:
        print(f"⚠️  Services skipped: {', '.join(unavailable_services)}")

    print(f"\n📈 Summary:")
    print(f"  Total test suites: {overall_results['total_suites']}")
    print(f"  ✅ Passed: {overall_results['passed_suites']}")
    print(f"  ❌ Failed: {overall_results['failed_suites']}")
    print(f"  ⏱️  Total duration: {total_duration:.1f}s")

    print(f"\n📋 Detailed Results:")
    for result in overall_results["suite_results"]:
        status = "✅" if result["success"] else "❌"
        duration = result["duration"]
        print(f"  {status} {result['name']} ({duration:.1f}s)")

        if not result["success"] and "error" in result:
            print(f"      Error: {result['error']}")

    # Return overall success
    success_rate = overall_results['passed_suites'] / overall_results['total_suites']
    overall_success = success_rate >= 0.8  # 80% success rate threshold

    if overall_success:
        print(f"\n🎉 SMOKE TESTS PASSED ({success_rate:.0%} success rate)")
    else:
        print(f"\n💥 SMOKE TESTS FAILED ({success_rate:.0%} success rate)")

    # Recommendations
    print(f"\n💡 Recommendations:")
    if overall_results['failed_suites'] == 0:
        print("  - All tests passed! Services are ready for integration.")
        print("  - Consider running full integration tests next.")
    elif overall_results['failed_suites'] < overall_results['passed_suites']:
        print("  - Most tests passed. Review failed tests for minor issues.")
        print("  - Check service logs for specific error details.")
    else:
        print("  - Multiple test failures detected. Review service configurations.")
        print("  - Ensure all services are properly deployed and configured.")
        print("  - Check database connections and service dependencies.")

    if unavailable_services:
        print(f"  - Deploy missing services: {', '.join(unavailable_services)}")

    print("=" * 70)

    return overall_success

def main():
    """Main entry point"""
    try:
        success = asyncio.run(run_all_smoke_tests())
        exit_code = 0 if success else 1

    except KeyboardInterrupt:
        print("\n\n⚠️  Smoke tests interrupted by user")
        exit_code = 130

    except Exception as e:
        print(f"\n\n💥 Smoke test runner failed: {e}")
        exit_code = 1

    sys.exit(exit_code)

if __name__ == "__main__":
    main()