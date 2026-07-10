"""PRC-05 — SSOT-гейты полноты Base.metadata и media-allowlist.

Зачем subprocess: env.py собирает target_metadata РОВНО двумя импортами
(``from ...models import *`` + ``import access_control.domain``). Если прогонять
проверку в общем pytest-процессе, любой ДРУГОЙ тест мог уже импортировать модель
напрямую и зарегистрировать её таблицу в глобальном Base.metadata — регрессия в
models/__init__.py (забыли добавить модель в __all__/импорт) была бы скрыта.
Поэтому импортируем в чистом интерпретаторе через subprocess.

Числа/имена — ЖЁСТКИЕ (снимок фактического Base.metadata). Тест ПО ДИЗАЙНУ
требует правки в каждом schema-PR, добавляющем/удаляющем таблицу — это осознанный
выбор владельца: baseline == прод точно, drift не проходит молча.
"""
import json
import os
import subprocess
import sys

from uk_management_bot.database.migration_include import (
    FUNCTIONAL_INDEXES_EXCLUDED,
    MEDIA_TABLES_EXCLUDED,
    include_object,
)

# Ровно то, что импортирует alembic/env.py (строки 10 и 13). НЕ менять на прямые
# импорты моделей — иначе теряется смысл subprocess-изоляции.
_ENV_IMPORTS_SNIPPET = (
    "from uk_management_bot.database.models import *\n"
    "import access_control.domain\n"
    "from uk_management_bot.database.session import Base\n"
    "import json\n"
    "print(json.dumps(sorted(Base.metadata.tables.keys())))\n"
)

# Снимок фактического Base.metadata (56 таблиц UK + access_control домен).
# media_* здесь НЕТ — они на чужой Base (SDK), в UK-контракт не входят.
_EXPECTED_TABLES = frozenset({
    "access_audit_logs",
    "access_barriers",
    "access_cameras",
    "access_decisions",
    "access_entry_confirmations",
    "access_events",
    "access_gates",
    "access_passes",
    "access_rights",
    "access_rules",
    "apartments",
    "audit_logs",
    "barrier_commands",
    "board_config",
    "buildings",
    "camera_events",
    "controller_sync_events",
    "edge_controllers",
    "feedback",
    "invite_nonces",
    "manual_openings",
    "material_issue_allocations",
    "material_issues",
    "material_receipts",
    "materials",
    "notifications",
    "parking_spot_assignments",
    "parking_spots",
    "parking_zone_yards",
    "parking_zones",
    "planning_conflicts",
    "quarterly_plans",
    "quarterly_shift_schedules",
    "ratings",
    "refresh_tokens",
    "request_assignments",
    "request_comments",
    "request_number_counters",
    "requests",
    "resident_access_requests",
    "shift_assignments",
    "shift_schedules",
    "shift_templates",
    "shift_transfers",
    "shifts",
    "user_apartments",
    "user_documents",
    "user_verifications",
    "user_yards",
    "users",
    "vehicle_apartments",
    "vehicle_presence_sessions",
    "vehicles",
    "webhook_inbox",
    "webhook_outbox",
    "yards",
})


def _tables_from_isolated_interpreter() -> frozenset:
    env = dict(os.environ)
    # Чистый интерпретатор без postgres: sqlite достаточно (метадата строится на
    # import, БД не трогается). Обязательные для settings переменные — на случай
    # запуска теста в изоляции (без conftest родителя).
    env.setdefault("DATABASE_URL", "sqlite:///:memory:")
    env.setdefault("DEBUG", "true")
    env.setdefault("INVITE_SECRET", "test_secret_for_unit_tests")
    env.setdefault("ADMIN_PASSWORD", "test_admin_password")
    proc = subprocess.run(
        [sys.executable, "-c", _ENV_IMPORTS_SNIPPET],
        capture_output=True,
        text=True,
        env=env,
        cwd=os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    )
    assert proc.returncode == 0, (
        f"isolated import failed:\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    )
    return frozenset(json.loads(proc.stdout.strip().splitlines()[-1]))


def test_base_metadata_exact_table_set():
    """models/__init__.py + access_control.domain дают РОВНО ожидаемый набор.

    Ловит забытый импорт модели (напр. WebhookInbox не в __all__) в чистом
    интерпретаторе, где никакой другой тест не «подрегистрировал» таблицу.
    """
    actual = _tables_from_isolated_interpreter()
    missing = _EXPECTED_TABLES - actual
    extra = actual - _EXPECTED_TABLES
    assert not missing, f"таблицы пропали из Base.metadata (забыт импорт?): {sorted(missing)}"
    assert not extra, (
        "в Base.metadata появились новые таблицы — обнови _EXPECTED_TABLES "
        f"в этом тесте (schema-PR требует правки по дизайну): {sorted(extra)}"
    )


def test_media_allowlist_excludes_exactly_four():
    """include_object исключает РОВНО 4 media-таблицы и ничего больше."""
    assert MEDIA_TABLES_EXCLUDED == frozenset({
        "media_files",
        "media_tags",
        "media_channels",
        "media_upload_sessions",
    })
    for name in MEDIA_TABLES_EXCLUDED:
        assert include_object(None, name, "table", True, None) is False


def test_media_allowlist_does_not_hide_new_uk_table():
    """Новая UK-таблица НЕ исключается молча (allowlist не расширяется паттерном)."""
    assert include_object(None, "some_new_uk_table", "table", True, None) is True
    # Не-таблица (индекс/констрейнт) с media-подобным именем тоже не трогается.
    assert include_object(None, "media_files", "index", True, None) is True


def test_seed_system_user_constant_matches_settings():
    """PRC-05: константа system-user в seed-миграции 002 == settings-дефолту.

    Ловит расхождение fresh-install (сид пишет telegram_id=0) vs рантайм-резолвер
    (settings.INFRASAFE_SYSTEM_USER_TELEGRAM_ID). На обоих продах = 0 (env unset)."""
    from uk_management_bot.config.settings import settings
    assert settings.INFRASAFE_SYSTEM_USER_TELEGRAM_ID == 0  # см. 0002_seed_system_user.SYSTEM_TELEGRAM_ID


def test_functional_index_allowlist_excludes_exactly_date_prefix():
    """include_object исключает РОВНО функциональный idx_requests_date_prefix
    (expr-индекс, postgres-only, не полицуется drift-гейтом; PRC-05 037)."""
    assert FUNCTIONAL_INDEXES_EXCLUDED == frozenset({"idx_requests_date_prefix"})
    assert include_object(None, "idx_requests_date_prefix", "index", True, None) is False
    # Обычный индекс НЕ исключается (allowlist не расширяется молча).
    assert include_object(None, "ix_requests_status", "index", True, None) is True
    # Таблица с таким именем (гипотетически) не трогается фильтром индексов.
    assert include_object(None, "idx_requests_date_prefix", "table", True, None) is True
