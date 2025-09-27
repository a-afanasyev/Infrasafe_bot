#!/usr/bin/env python3
"""
Auth Service Test Runner
Run this script to execute all tests for the Auth Service
"""

import subprocess
import sys
import os

def run_tests():
    """Run all tests for Auth Service"""
    print("🧪 Running Auth Service Tests")
    print("=" * 50)

    # Change to auth_service directory
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    try:
        # Run pytest with coverage
        result = subprocess.run([
            "python", "-m", "pytest",
            "-v",
            "--tb=short",
            "--cov=.",
            "--cov-report=term-missing",
            "--cov-report=html:htmlcov",
            "tests/"
        ], check=False)

        if result.returncode == 0:
            print("\n✅ All tests passed!")
            print("\n📊 Coverage report generated in htmlcov/")
            return True
        else:
            print("\n❌ Some tests failed!")
            return False

    except FileNotFoundError:
        print("❌ pytest not found. Please install test dependencies:")
        print("pip install -r requirements.txt")
        return False

    except Exception as e:
        print(f"❌ Error running tests: {e}")
        return False

if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)