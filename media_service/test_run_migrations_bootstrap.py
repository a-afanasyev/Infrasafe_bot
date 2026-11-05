"""A9-P3-33: media-migrate на пустой БД (новая площадка) не падает на 0001.

0001 начинается с ALTER TABLE media_files — до create_all таблиц нет. main()
обязан создать таблицы ДО SQL-файлов. Сами .sql — postgres-диалект и
проверяются дрейф-гейтом test_schema_drift_pg.py; здесь — только порядок.
"""
from sqlalchemy import create_engine, inspect

import run_migrations


def test_main_creates_tables_before_sql_files(monkeypatch):
    engine = create_engine("sqlite://")
    seen = {}

    def fake_apply(conn):
        seen["tables"] = set(inspect(conn).get_table_names())
        return 2

    monkeypatch.setattr(run_migrations, "engine", engine)
    monkeypatch.setattr(run_migrations, "apply_migrations", fake_apply)
    run_migrations.main()

    assert "media_files" in seen["tables"]
