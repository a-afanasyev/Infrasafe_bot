"""A11-CODE-11: в репозитории нет дампов с персональными данными.

Проверка — CI-инструмент (``ci/``), а не тест приложения: обход ``git ls-files``
нужен checkout, а в образе нет ``.git``, ``docs/`` и ``scripts/``. Тесты чистой
функции на синтетике гоняет CI-job ``lint`` (без conftest приложения):
``python -m pytest -p no:cacheprovider ci/test_check_no_data_dumps.py``.
"""
from __future__ import annotations

import gzip
import importlib.util
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parent / "check_no_data_dumps.py"
_spec = importlib.util.spec_from_file_location("check_no_data_dumps", _SCRIPT)
dumps = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dumps)


@pytest.mark.parametrize("sql", [
    "COPY public.users (id, telegram_id, first_name) FROM stdin;",
    'copy "public"."users"(id) from stdin;',
    "INSERT  INTO\n   users VALUES (1, 'Иван');",
    'insert into "USERS" (id) values (1);',
    "INSERT INTO public . user_documents (id) VALUES (1);",
    "COPY account_owners FROM stdin;",
    "\tInsert Into user_verifications\n(id) values (2);",
])
def test_pii_data_statements_are_violations(sql):
    assert dumps.check_file("docs/x.sql", sql.encode()), sql


@pytest.mark.parametrize("sql", [
    "CREATE TABLE users (id int);",
    "DELETE FROM users WHERE id = 1;",
    "INSERT INTO users_backup VALUES (1);",
    "COPY public.user_roles (id) FROM stdin;",
    "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO uk_app_rw;",
    "INSERT INTO media_files (id) VALUES (1);",
    "-- комментарий без данных: users",
])
def test_schema_and_other_tables_pass(sql):
    assert dumps.check_file("scripts/x.sql", sql.encode()) == [], sql


def test_gzip_sql_is_unpacked_and_checked():
    payload = gzip.compress(b"SET x;\nCOPY public.users (id) FROM stdin;\n1\n\\.\n")
    assert dumps.check_file("backups/db.sql.gz", payload)
    assert dumps.check_file("backups/schema.sql.gz", gzip.compress(b"CREATE TABLE users (id int);")) == []


def test_broken_gzip_is_violation():
    assert dumps.check_file("backups/db.sql.gz", b"not gzip at all")


@pytest.mark.parametrize("path, content", [
    ("backups/db.dump", b"anything"),
    ("x/db.backup", b"anything"),
    ("x/db.pgdump", b"anything"),
    ("docs/innocent.bin", b"PGDMP\x01\x0e\x00binary"),  # сигнатура pg_dump -Fc под чужим расширением
])
def test_binary_dumps_are_forbidden_without_parsing(path, content):
    assert dumps.check_file(path, content)


def test_unrelated_files_ignored():
    assert dumps.check_file("README.md", b"COPY public.users FROM stdin;") == []


# ───────────── ревью A11: обходы и ресурсы ─────────────


@pytest.mark.parametrize("sql", [
    "INSERT INTO uk.users (id) VALUES (1);",                  # не public
    'COPY "app"."users" (id) FROM stdin;',
    "COPY /* выгрузка */ users (id) FROM stdin;",               # комментарий между токенами
    "INSERT INTO -- c\n users VALUES (1);",
    "\\copy users to 'u.csv'",                                  # psql meta-команда
    "COPY public.requests (request_number, description) FROM stdin;",
    "INSERT INTO user_apartments VALUES (1, 2);",
    "COPY public.audit_logs FROM stdin;",
])
def test_bypass_variants_are_violations(sql):
    assert dumps.check_file("docs/x.sql", sql.encode()), sql


def test_commented_out_statement_is_not_a_violation():
    assert dumps.check_file("docs/x.sql", b"-- INSERT INTO requests (id) VALUES (1);\nSELECT 1;") == []
    assert dumps.check_file("docs/x.sql", b"/* COPY users FROM stdin; */ SELECT 1;") == []


@pytest.mark.parametrize("encoded", [
    "﻿COPY public.users (id) FROM stdin;".encode("utf-16"),       # UTF-16 с BOM
    "COPY public.users (id) FROM stdin;".encode("utf-16-le"),          # UTF-16 без BOM
    "﻿COPY public.users (id) FROM stdin;".encode("utf-8"),        # UTF-8 с BOM
])
def test_other_encodings_are_checked(encoded):
    assert dumps.check_file("docs/x.sql", encoded)


def test_gzip_bomb_is_violation_not_oom(monkeypatch):
    monkeypatch.setattr(dumps, "MAX_BYTES", 1024)
    bomb = gzip.compress(b"0" * 100_000)
    assert len(bomb) < 1024
    problems = dumps.check_file("backups/x.sql.gz", bomb)
    assert problems and "распаковки" in problems[0]


def test_plain_sql_over_limit_is_violation(monkeypatch):
    monkeypatch.setattr(dumps, "MAX_BYTES", 10)
    assert dumps.check_file("docs/x.sql", b"SELECT 1; SELECT 2; SELECT 3;")


def test_pg_custom_dump_inside_gzip_is_violation():
    assert dumps.check_file("docs/x.sql.gz", gzip.compress(b"PGDMP\x01\x0e\x00rest"))


@pytest.mark.parametrize("path", ["db.sql.bz2", "db.sql.xz", "db.sql.zst", "db.sql.zip", "db.dump.gz", "x.backup.tar"])
def test_opaque_compressed_dumps_are_forbidden(path):
    assert dumps.check_file(path, b"\x00\x01\x02\x03\x04")


def test_multi_member_gzip_is_violation():
    """`cat clean.gz dump.gz` — второй член не проверить → не принимаем."""
    payload = gzip.compress(b"SELECT 1;") + gzip.compress(b"COPY public.users (id) FROM stdin;")
    assert dumps.check_file("docs/x.sql.gz", payload)


@pytest.mark.parametrize("sql, bad", [
    ("COPY (SELECT id, phone FROM public.users WHERE id > 1) TO STDOUT;", True),
    ("\\copy (select * from \"users\") to 'u.csv' csv", True),
    ("COPY (SELECT 1 FROM media_files) TO STDOUT;", False),
])
def test_copy_query_export(sql, bad):
    assert bool(dumps.check_file("scripts/x.sql", sql.encode())) is bad
