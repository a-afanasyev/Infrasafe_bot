# Request Service - Test and Development Commands
# UK Management Bot - Request Management System

.PHONY: help test test-unit test-integration test-api test-smoke test-all test-coverage clean install-deps lint format type-check docker-test

# Default target
help:
	@echo "Request Service - Available Commands:"
	@echo ""
	@echo "Testing:"
	@echo "  test              Run all tests"
	@echo "  test-unit         Run unit tests only"
	@echo "  test-integration  Run integration tests only"
	@echo "  test-api          Run API tests only"
	@echo "  test-smoke        Run smoke tests only"
	@echo "  test-coverage     Run tests with coverage report"
	@echo "  test-fast         Run tests without slow tests"
	@echo ""
	@echo "Development:"
	@echo "  install-deps      Install development dependencies"
	@echo "  lint              Run code linting"
	@echo "  format            Format code"
	@echo "  type-check        Run type checking"
	@echo "  clean             Clean temporary files"
	@echo ""
	@echo "Docker:"
	@echo "  docker-test       Run tests in Docker container"
	@echo "  docker-smoke      Run smoke tests in Docker"

# Install development dependencies
install-deps:
	pip install -r requirements.txt
	pip install -r requirements-test.txt

# Run all tests
test:
	pytest tests/ -v

# Run unit tests only
test-unit:
	pytest tests/unit/ -m unit -v

# Run integration tests only
test-integration:
	pytest tests/integration/ -m integration -v

# Run API tests only
test-api:
	pytest tests/api/ -m api -v

# Run smoke tests only
test-smoke:
	pytest tests/smoke_tests.py -m smoke -v

# Run all tests
test-all:
	pytest tests/ -v --cov=app --cov-report=term-missing --cov-report=html

# Run tests with coverage
test-coverage:
	pytest tests/ --cov=app --cov-report=term-missing --cov-report=html --cov-fail-under=85

# Run fast tests (exclude slow tests)
test-fast:
	pytest tests/ -m "not slow" -v

# Run tests in parallel
test-parallel:
	pytest tests/ -n auto -v

# Run linting
lint:
	ruff check app/ tests/
	black --check app/ tests/
	isort --check-only app/ tests/

# Format code
format:
	black app/ tests/
	isort app/ tests/
	ruff check --fix app/ tests/

# Type checking
type-check:
	mypy app/

# Clean temporary files
clean:
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type f -name ".coverage" -delete
	rm -rf htmlcov/
	rm -rf .testmon/
	rm -rf test_request_service.db*

# Docker test commands (assuming Docker Compose setup)
docker-test:
	docker-compose -f ../../../docker-compose.dev.yml exec request_service pytest tests/ -v

docker-smoke:
	docker-compose -f ../../../docker-compose.dev.yml exec request_service pytest tests/smoke_tests.py -m smoke -v

# Database operations for testing
test-db-setup:
	@echo "Setting up test database..."
	# This would be expanded based on specific database setup needs

test-db-teardown:
	@echo "Tearing down test database..."
	rm -f test_request_service.db*

# Performance testing
test-performance:
	pytest tests/ -m slow --benchmark-only -v

# Generate test report
test-report:
	pytest tests/ --html=reports/test_report.html --json-report --json-report-file=reports/test_report.json

# Continuous Integration helpers
ci-test:
	pytest tests/ --cov=app --cov-report=xml --cov-report=term --junitxml=reports/junit.xml

# Development workflow
dev-test: clean install-deps lint type-check test-fast

# Pre-commit checks
pre-commit: format lint type-check test-unit

# Full validation (for CI/CD)
validate: clean install-deps lint type-check test-all

# Watch tests (requires pytest-watch)
watch:
	ptw tests/ app/ --runner="pytest -v"

# Debug test failures
test-debug:
	pytest tests/ -v -s --tb=long --pdb

# Test specific file or function
# Usage: make test-file FILE=tests/unit/test_models.py
test-file:
ifdef FILE
	pytest $(FILE) -v
else
	@echo "Usage: make test-file FILE=path/to/test_file.py"
endif

# Test with specific marker
# Usage: make test-marker MARKER=unit
test-marker:
ifdef MARKER
	pytest tests/ -m $(MARKER) -v
else
	@echo "Usage: make test-marker MARKER=marker_name"
endif

# Install pre-commit hooks
install-hooks:
	pre-commit install

# Update dependencies
update-deps:
	pip-compile requirements.in
	pip-compile requirements-test.in

# Security scanning
security-scan:
	bandit -r app/
	safety check