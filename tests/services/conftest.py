"""
conftest.py for tests/services/ — patches DATABASE_URL to SQLite
before any uk_management_bot modules are imported, avoiding
the need for psycopg2 or a running PostgreSQL instance.
"""
import os
import sys

# Force SQLite and DEBUG mode for tests that run outside Docker.
# This MUST happen before any uk_management_bot import triggers
# database/session.py which calls create_engine at import time.
os.environ["DATABASE_URL"] = "sqlite:///test_services.db"
os.environ["DEBUG"] = "true"
os.environ["INVITE_SECRET"] = "test_secret_for_unit_tests"
os.environ["ADMIN_PASSWORD"] = "test_admin_password"
