"""Регистронезависимый поиск по тексту, честный для кириллицы.

⚠ Прод-кластер создан в локали `C` (`lc_ctype=C`), а в ней `lower()` и `ILIKE`
сворачивают регистр **только для ASCII**:

    profk_management=# SELECT lower('АДМИН');                   -- → 'АДМИН'
    profk_management=# SELECT 'Администратор' ILIKE '%админ%';  -- → false

Система русскоязычная, поэтому любой `ILIKE`-поиск по ФИО, адресу или названию
материала в такой локали — нерабочая функция: латиница ищется, русские имена
нет. Найдено прод-проверкой раздела «Жители» 2026-07-28
(`docs/bugs-2026-07-28.md`, BUG-1).

Чинится без миграции и без расширений: ICU-коллация (`und-x-icu` есть в
`postgres:15` из коробки) заставляет `lower()` использовать юникодный
case-mapping. Системно правильнее пересоздать кластер в UTF-8-локали
(`initdb --locale`), но это dump/restore с даунтаймом — отдельная операция;
до неё каждый поиск обязан идти через этот модуль.

Гейт `tests/api/test_search_no_raw_ilike.py` запрещает голый `.ilike(` в коде:
дефект невидим для сьюта (он на sqlite, где `ILIKE` эмулируется питоновским
слоем SQLAlchemy и кириллицу сворачивает), поэтому его ловит не тест
поведения, а запрет конструкции.
"""

from __future__ import annotations

import re

from sqlalchemy import collate, func

# `und` — language-agnostic корень CLDR: нам нужно юникодное сворачивание
# регистра, а не порядок сортировки конкретной локали.
ICU_COLLATION = "und-x-icu"


def escape_like(value: str) -> str:
    """Экранирует LIKE-мета-символы `% _ \\`.

    Без этого `q=%` матчит вообще всё, а одиночный `\\` в конце шаблона —
    синтаксическая ошибка в PostgreSQL.
    """
    return re.sub(r'([%_\\])', r'\\\1', value)


def is_postgres(db) -> bool:
    """True, если сессия привязана к PostgreSQL.

    Работает и с `AsyncSession` (API), и с sync `Session` (бот) — хелпер
    применяется в обоих слоях. Неизвестная форма сессии трактуется как
    «не postgres»: это прежнее поведение (`ILIKE`), а не падение запроса.
    """
    bind = getattr(db, "bind", None)
    if bind is None:
        get_bind = getattr(db, "get_bind", None)
        if callable(get_bind):
            try:
                bind = get_bind()
            except Exception:
                return False
    return getattr(getattr(bind, "dialect", None), "name", "") == "postgresql"


def ci_contains(column, pattern: str, *, is_postgres: bool):
    """Регистронезависимое сравнение с LIKE-шаблоном.

    `pattern` — уже готовый шаблон с обрамляющими `%` и **уже экранированным**
    пользовательским текстом (`escape_like`).

    Нижний регистр наводится ТОЛЬКО на PG-ветке: на sqlite `lower()` тоже
    ASCII-only, и опущенный заранее шаблон перестал бы находить кириллицу
    вообще — там регистр сворачивает сам `ILIKE` силами SQLAlchemy.
    """
    if is_postgres:
        return func.lower(collate(column, ICU_COLLATION)).like(
            pattern.lower(), escape="\\",
        )
    return column.ilike(pattern, escape="\\")


def ci_contains_any(columns, pattern: str, *, is_postgres: bool):
    """`ci_contains` по нескольким колонкам через OR — частый случай (ФИО+телефон)."""
    from sqlalchemy import or_

    return or_(*(ci_contains(c, pattern, is_postgres=is_postgres) for c in columns))
