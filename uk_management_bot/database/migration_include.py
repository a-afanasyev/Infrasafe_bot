"""Alembic autogenerate object filter (PRC-05).

Извлечено из ``alembic/env.py`` в отдельный importable-модуль, чтобы
allowlist можно было юнит-тестировать без исполнения env.py (который в конце
запускает миграции). env.py и тест импортируют ОДНУ И ТУ ЖЕ функцию — SSOT.
"""

# media_* — чужой сервис (собственная Base) живёт в общей dev-БД. В UK-контракт
# (squashed baseline + drift-гейт ``alembic check``, PRC-05) НЕ входит. Исключаем
# ТОЧНЫМ allowlist из ровно 4 подтверждённых таблиц — НЕ по namespace-паттерну:
# иначе новая UK-таблица со схожим префиксом молча выпала бы из drift-гейта.
MEDIA_TABLES_EXCLUDED = frozenset({
    "media_files",
    "media_tags",
    "media_channels",
    "media_upload_sessions",
})

# Функциональные (expression) индексы, которые autogenerate НЕ воспроизводит
# надёжно и которые нельзя объявить в модели без поломки sqlite-create_all
# (postgres-only выражение). Создаются миграцией/baseline вручную (как триггеры)
# и НЕ полицуются drift-гейтом — осознанно, по аналогии с триггерами/GRANT'ами.
# idx_requests_date_prefix = substring((request_number)::text, 1, 6) (PRC-05).
FUNCTIONAL_INDEXES_EXCLUDED = frozenset({
    "idx_requests_date_prefix",
})


def include_object(obj, name, type_, reflected, compare_to):  # noqa: ANN001
    """Return False → объект исключается из autogenerate/`alembic check`."""
    if type_ == "table" and name in MEDIA_TABLES_EXCLUDED:
        return False
    if type_ == "index" and name in FUNCTIONAL_INDEXES_EXCLUDED:
        return False
    return True
