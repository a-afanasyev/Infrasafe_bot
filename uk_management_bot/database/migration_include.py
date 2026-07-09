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


def include_object(obj, name, type_, reflected, compare_to):  # noqa: ANN001
    """Return False → таблица исключается из autogenerate/`alembic check`."""
    if type_ == "table" and name in MEDIA_TABLES_EXCLUDED:
        return False
    return True
