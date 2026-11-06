"""A11-CODE-05: атомарное изменение singleton-конфига с записью в ``audit_logs``.

Конфиги ИИ (news-watch: источники/автопубликация/описание комплекса;
автоменеджер: режим, системные промпты ``ai.*_instructions``, шаблоны пингов)
меняли поведение модели и тексты жителям без следа. Здесь строка конфига и
запись аудита уходят ОДНИМ ``commit``; ``before`` читается под ``FOR UPDATE``,
поэтому параллельные правки дают последовательную историю, а сбой записи
аудита откатывает и сам конфиг. На sqlite (тесты) ``FOR UPDATE`` игнорируется —
гарантия блокировки только на PostgreSQL.
"""
from __future__ import annotations

import copy
import logging
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.database.models.audit import AuditLog

logger = logging.getLogger(__name__)

CONFIG_ROW_ID = 1


def config_diff(before: dict, after: dict) -> dict[str, dict[str, Any]]:
    """Изменившиеся ключи: верхний уровень, вложенные dict — по ключам (``ai.x``)."""
    out: dict[str, dict[str, Any]] = {}
    for key in sorted(set(before) | set(after)):
        old, new = before.get(key), after.get(key)
        if old == new:
            continue
        if isinstance(old, dict) and isinstance(new, dict):
            for sub in sorted(set(old) | set(new)):
                if old.get(sub) != new.get(sub):
                    out[f"{key}.{sub}"] = {"before": old.get(sub), "after": new.get(sub)}
        else:
            out[key] = {"before": old, "after": new}
    return out


class FirstInsertRace(Exception):
    """Две первые записи конфига разошлись на PK — повторить под блокировкой."""


async def _apply(db: AsyncSession, model: type[Any], data: dict, validate: Callable[[dict], dict],
                 defaults: dict, actor_id: int, action: str) -> tuple[dict, dict]:
    row = (await db.execute(
        select(model).where(model.id == CONFIG_ROW_ID).with_for_update()
    )).scalar_one_or_none()
    if row is not None and row.data:
        try:
            before = validate(row.data)
        except (ValueError, TypeError, KeyError, AttributeError):
            # Битые сохранённые данные не должны мешать сохранить исправление:
            # в аудит — как есть (если это вообще объект), иначе пустой before.
            before = copy.deepcopy(row.data) if isinstance(row.data, dict) else {}
    else:
        before = validate(defaults)
    after = validate(data)
    inserted = row is None
    if inserted:
        db.add(model(id=CONFIG_ROW_ID, data=after, updated_by=actor_id))
    else:
        row.data = after
        row.updated_by = actor_id
    changed = config_diff(before, after)
    if changed:
        db.add(AuditLog(user_id=actor_id, action=action, details={"changed": changed}))
    try:
        await db.commit()
    except IntegrityError:
        if inserted:
            raise FirstInsertRace() from None
        raise
    return before, after


async def update_singleton_audited(
    db: AsyncSession, model: type[Any], data: dict, *, validate: Callable[[dict], dict], defaults: dict,
    actor_id: int, action: str,
) -> tuple[dict, dict]:
    """Валидировать, сохранить и записать аудит одной транзакцией → (before, after).

    ``ValueError`` валидации и любой сбой — ``rollback``, ничего не сохранено.
    Гонка двух ПЕРВЫХ записей (строки ещё не было, конфликт PK при commit) —
    откат и один повтор: теперь строка есть и берётся под блокировкой. Прочие
    нарушения целостности (например, FK ``audit_logs.user_id``) не повторяются.
    """
    try:
        return await _apply(db, model, data, validate, defaults, actor_id, action)
    except FirstInsertRace:
        await db.rollback()
        logger.info("%s: concurrent first insert, retrying under row lock", action)
    except Exception:
        await db.rollback()
        raise
    try:
        return await _apply(db, model, data, validate, defaults, actor_id, action)
    except Exception:
        await db.rollback()
        raise
