#!/usr/bin/env python3
"""
Comprehensive Test Runner
UK Management Bot - Microservices Testing Suite

Runs all smoke tests and integration tests for the microservices
"""

import asyncio
import subprocess
import sys
import logging
import time
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TestRunner:
    """Comprehensive test runner for all services"""

    def __init__(self):
        self.base_dir = Path(__file__).parent
        self.results = {}

    async def run_all_tests(self):
        """Run comprehensive test suite"""
        logger.info("🚀 Starting comprehensive microservices test suite")
        logger.info("=" * 60)

        # Run individual service smoke tests
        await self.run_smoke_tests()

        # Run cross-service integration tests
        await self.run_integration_tests()

        # Print final summary
        self.print_final_summary()

        return self.all_tests_successful()

    async def run_smoke_tests(self):
        """Run smoke tests for each service"""
        logger.info("\n🔥 RUNNING SERVICE SMOKE TESTS")
        logger.info("-" * 40)

        smoke_tests = [
            ("Auth Service", "test_smoke_auth_service.py"),
            ("User Service", "test_smoke_user_service.py"),
            ("Media Service", "test_smoke_media_service.py"),
        ]

        for service_name, test_file in smoke_tests:
            logger.info(f"\n🧪 Testing {service_name}...")

            try:
                result = subprocess.run(
                    [sys.executable, str(self.base_dir / test_file)],
                    capture_output=True,
                    text=True,
                    timeout=60
                )

                if result.returncode == 0:
                    self.results[f"{service_name}_smoke"] = "✅ PASS"
                    logger.info(f"✅ {service_name} smoke tests: PASSED")
                else:
                    self.results[f"{service_name}_smoke"] = "❌ FAIL"
                    logger.error(f"❌ {service_name} smoke tests: FAILED")
                    if result.stderr:
                        logger.error(f"   Error: {result.stderr}")

            except subprocess.TimeoutExpired:
                self.results[f"{service_name}_smoke"] = "❌ TIMEOUT"
                logger.error(f"❌ {service_name} smoke tests: TIMEOUT")
            except Exception as e:
                self.results[f"{service_name}_smoke"] = f"❌ ERROR: {str(e)}"
                logger.error(f"❌ {service_name} smoke tests: ERROR - {e}")

    async def run_integration_tests(self):
        """Run cross-service integration tests"""
        logger.info("\n🔗 RUNNING INTEGRATION TESTS")
        logger.info("-" * 40)

        try:
            logger.info("🧪 Testing cross-service integration...")

            result = subprocess.run(
                [sys.executable, str(self.base_dir / "test_integration_services.py")],
                capture_output=True,
                text=True,
                timeout=120
            )

            if result.returncode == 0:
                self.results["integration_tests"] = "✅ PASS"
                logger.info("✅ Integration tests: PASSED")
            else:
                self.results["integration_tests"] = "❌ FAIL"
                logger.error("❌ Integration tests: FAILED")
                if result.stderr:
                    logger.error(f"   Error: {result.stderr}")

        except subprocess.TimeoutExpired:
            self.results["integration_tests"] = "❌ TIMEOUT"
            logger.error("❌ Integration tests: TIMEOUT")
        except Exception as e:
            self.results["integration_tests"] = f"❌ ERROR: {str(e)}"
            logger.error(f"❌ Integration tests: ERROR - {e}")

    def print_final_summary(self):
        """Print comprehensive test summary"""
        logger.info("\n" + "=" * 60)
        logger.info("📊 COMPREHENSIVE TEST RESULTS SUMMARY")
        logger.info("=" * 60)

        # Group results by category
        smoke_results = {k: v for k, v in self.results.items() if "_smoke" in k}
        integration_results = {k: v for k, v in self.results.items() if "integration" in k}

        if smoke_results:
            logger.info("\n🔥 Smoke Test Results:")
            for test_name, result in smoke_results.items():
                service_name = test_name.replace("_smoke", "")
                logger.info(f"  {service_name}: {result}")

        if integration_results:
            logger.info("\n🔗 Integration Test Results:")
            for test_name, result in integration_results.items():
                logger.info(f"  {test_name.replace('_', ' ').title()}: {result}")

        # Calculate statistics
        total_tests = len(self.results)
        passed_tests = len([r for r in self.results.values() if r.startswith("✅")])
        failed_tests = len([r for r in self.results.values() if r.startswith("❌")])

        logger.info("\n" + "=" * 60)
        logger.info(f"📈 OVERALL STATISTICS:")
        logger.info(f"   Total Test Suites: {total_tests}")
        logger.info(f"   Passed: {passed_tests}")
        logger.info(f"   Failed: {failed_tests}")
        logger.info(f"   Success Rate: {(passed_tests/total_tests)*100:.1f}%")

        if failed_tests == 0:
            logger.info("\n🎉 ALL TESTS PASSED! Microservices are ready for deployment.")
        else:
            logger.error(f"\n💥 {failed_tests} TEST SUITE(S) FAILED! Review issues before deployment.")

        logger.info("=" * 60)

    def all_tests_successful(self):
        """Check if all tests passed"""
        return all(result.startswith("✅") for result in self.results.values())

    async def generate_test_report(self):
        """Generate detailed test report"""
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        report_file = self.base_dir / f"test_report_{timestamp}.md"

        report_content = f"""# Microservices Test Report

**Generated:** {time.strftime("%Y-%m-%d %H:%M:%S")}

## Summary

- **Total Test Suites:** {len(self.results)}
- **Passed:** {len([r for r in self.results.values() if r.startswith("✅")])}
- **Failed:** {len([r for r in self.results.values() if r.startswith("❌")])}

## Detailed Results

### Smoke Tests
"""

        smoke_results = {k: v for k, v in self.results.items() if "_smoke" in k}
        for test_name, result in smoke_results.items():
            service_name = test_name.replace("_smoke", "")
            status = "✅ PASS" if result.startswith("✅") else "❌ FAIL"
            report_content += f"- **{service_name}:** {status}\n"

        report_content += "\n### Integration Tests\n"
        integration_results = {k: v for k, v in self.results.items() if "integration" in k}
        for test_name, result in integration_results.items():
            status = "✅ PASS" if result.startswith("✅") else "❌ FAIL"
            report_content += f"- **{test_name.replace('_', ' ').title()}:** {status}\n"

        report_content += f"""
## Recommendations

"""
        if self.all_tests_successful():
            report_content += "🎉 All tests passed! The microservices are ready for production deployment.\n"
        else:
            report_content += "⚠️ Some tests failed. Review the failed components before deployment:\n\n"
            failed_tests = [k for k, v in self.results.items() if v.startswith("❌")]
            for failed_test in failed_tests:
                report_content += f"- Fix issues in: **{failed_test.replace('_', ' ').title()}**\n"

        # Write report
        with open(report_file, 'w') as f:
            f.write(report_content)

        logger.info(f"📄 Test report generated: {report_file}")

async def main():
    """Main test runner"""
    runner = TestRunner()

    try:
        success = await runner.run_all_tests()
        await runner.generate_test_report()

        if not success:
            sys.exit(1)

    except KeyboardInterrupt:
        logger.warning("\n⚠️ Tests interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"💥 Test runner failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())