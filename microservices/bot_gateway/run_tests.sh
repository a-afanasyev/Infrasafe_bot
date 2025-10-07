#!/bin/bash

# Bot Gateway Service - Test Runner Script
# UK Management Bot
#
# Usage:
#   ./run_tests.sh              # Run all tests
#   ./run_tests.sh unit         # Run only unit tests
#   ./run_tests.sh integration  # Run only integration tests
#   ./run_tests.sh coverage     # Run tests with detailed coverage report

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Functions
print_header() {
    echo -e "${BLUE}=====================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}=====================================${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_info() {
    echo -e "${YELLOW}ℹ️  $1${NC}"
}

# Check if we're running in Docker
if [ -f /.dockerenv ]; then
    IN_DOCKER=true
else
    IN_DOCKER=false
fi

# Determine test type
TEST_TYPE=${1:-all}

print_header "Bot Gateway Service - Test Suite"

# Check dependencies
print_info "Checking dependencies..."
if ! python -m pytest --version &> /dev/null; then
    print_error "pytest not found. Please install test dependencies:"
    echo "pip install -r requirements.txt"
    exit 1
fi

print_success "Dependencies OK"

# Run tests based on type
case $TEST_TYPE in
    unit)
        print_header "Running Unit Tests"
        pytest tests/ -m "unit" -v
        ;;

    integration)
        print_header "Running Integration Tests"
        pytest tests/ -m "integration" -v
        ;;

    middleware)
        print_header "Running Middleware Tests"
        pytest tests/test_middleware_*.py -v
        ;;

    clients)
        print_header "Running Service Client Tests"
        pytest tests/test_service_clients.py -v
        ;;

    handlers)
        print_header "Running Handler Tests"
        pytest tests/test_handlers.py -v
        ;;

    coverage)
        print_header "Running Tests with Coverage Report"
        pytest tests/ -v \
            --cov=app \
            --cov-report=term-missing \
            --cov-report=html \
            --cov-report=xml

        print_success "Coverage report generated:"
        print_info "  HTML: htmlcov/index.html"
        print_info "  XML: coverage.xml"
        ;;

    fast)
        print_header "Running Fast Tests (Unit Only)"
        pytest tests/ -m "not slow" -v
        ;;

    slow)
        print_header "Running Slow Tests"
        pytest tests/ -m "slow" -v
        ;;

    all|*)
        print_header "Running All Tests"
        pytest tests/ -v
        ;;
esac

# Check test result
TEST_EXIT_CODE=$?

if [ $TEST_EXIT_CODE -eq 0 ]; then
    print_success "All tests passed!"

    # Show coverage summary if available
    if [ -f .coverage ]; then
        print_info "Coverage Summary:"
        coverage report --skip-empty
    fi

    exit 0
else
    print_error "Some tests failed. Exit code: $TEST_EXIT_CODE"
    exit $TEST_EXIT_CODE
fi
