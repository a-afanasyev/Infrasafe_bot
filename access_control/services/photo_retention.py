"""Retention фото событий (§11): удаление файлов и обнуление ссылок старше срока.

Базовая техническая политика §11: «Фото номера и автомобиля — 30 дней». Кадры
лежат в медиа-сервисе (отдельный Telegram-канал + ``media_files``), в
``camera_events.{plate|overview}_photo_url`` — ссылка ``media://{media_id}``.
Обнуление ссылки само по себе ПДн не удаляет: фото живёт в медиа-сервисе, пока
его не удалили. Поэтому порядок (A9-P2-16) — «сначала файл, потом ссылка»:

1. короткое чтение: до ``PHOTO_RETENTION_BATCH`` просроченных событий с фото
   (``ORDER BY id``) и какие их ``media_id`` ещё нужны событиям ВНЕ пачки;
2. без транзакции: ``DELETE /media/{id}`` по каждому ничьему id
   (``retire_media_file`` различает «удалён», «удерживается», «временный сбой»);
3. короткая транзакция: обнуляются только ссылки, чей файл удалён/удерживается
   медиа-сервисом/нужен другому событию. Временный сбой — ссылка остаётся, и
   событие вернётся на следующем тике (естественный ретрай; media_id не теряется).

Пачка берётся от keyset-курсора по кругу (``advance_photo_retention``), так что
события с постоянным сбоем не занимают её навсегда; «застревание» N тиков
подряд — WARNING и gauge ``access_photo_retention_stuck_ticks``.

``camera_events`` — сырой слой, НЕ append-only (§9.7 hash-chain только на
бизнес-журнале/аудите), поэтому UPDATE разрешён DB grants. Legacy-значения не
вида ``media://`` (сырой URL) удалять негде — они просто обнуляются.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import logging
from dataclasses import dataclass
from typing import Callable

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from access_control.integrations.media import (
    AccessMediaClient,
    MediaRetireOutcome,
    get_access_media_client,
    retire_media_file,
)
from access_control.services.metrics import set_photo_retention_gauges

logger = logging.getLogger(__name__)

# Срок хранения фото по умолчанию (§11), дней.
PHOTO_RETENTION_DAYS = 30

# Событий за один (часовой) тик. Каждое событие — до двух последовательных
# удалений в медиа-сервисе (каждое — вызов Telegram, секунды при rate-limit),
# и тик не должен растягиваться на весь интервал: 200 событий ≈ 400 вызовов.
# При бэклоге (первый запуск, недоступность media) хвост разбирается следующими
# тиками, а не одной пачкой в тысячи запросов.
PHOTO_RETENTION_BATCH = 200

# Сколько тиков подряд с неудалёнными файлами — повод для WARNING (часовой тик:
# 3 часа стабильного сбоя — уже не «моргнул медиа-сервис»).
STUCK_WARN_TICKS = 3

# Верхняя граница курсора для обхода по кругу (BIGINT identity).
_MAX_PK = 2**63 - 1

_MEDIA_PREFIX = "media://"
_COLUMNS = ("plate_photo_url", "overview_photo_url")

# Исходы, при которых ссылку события можно обнулить (файла у media нет либо он
# принадлежит не событию). TRANSIENT — нельзя: media_id хранится только в ссылке.
_CLEARABLE = frozenset({MediaRetireOutcome.GONE, MediaRetireOutcome.RETAINED})


@dataclass(frozen=True)
class ExpiredPhotoRow:
    """Просроченное событие с хотя бы одной ссылкой на фото."""

    event_pk: int
    plate_ref: str | None
    overview_ref: str | None

    @property
    def refs(self) -> tuple[str, ...]:
        return tuple(ref for ref in (self.plate_ref, self.overview_ref) if ref)


def _media_id(ref: str | None) -> int | None:
    """``media://<int>`` → id; иное (NULL, сырой URL, мусор) → None."""
    if not ref or not ref.startswith(_MEDIA_PREFIX):
        return None
    raw = ref[len(_MEDIA_PREFIX):]
    return int(raw) if raw.isdigit() else None


def _cutoff(older_than_days: int, now: dt.datetime | None) -> dt.datetime:
    base = now or dt.datetime.now(dt.timezone.utc)
    return base - dt.timedelta(days=older_than_days)


def select_expired_photos(
    db: Session,
    *,
    older_than_days: int = PHOTO_RETENTION_DAYS,
    now: dt.datetime | None = None,
    limit: int = PHOTO_RETENTION_BATCH,
    after_pk: int = 0,
) -> list[ExpiredPhotoRow]:
    """До ``limit`` событий старше срока с фото (§11): ``id > after_pk``, затем по кругу.

    Keyset-курсор ``after_pk`` + обход по кругу: за ⌈N/limit⌉ тиков пачка
    проходит все N кандидатов, и события с постоянным сбоем удаления не
    занимают пачку навсегда (без курсора первые ``limit`` «застрявших» id
    закрывали бы остальным дорогу). Без новой колонки/миграции.
    """
    query = text(
        "SELECT id, plate_photo_url, overview_photo_url FROM camera_events "
        "WHERE captured_at < :cutoff "
        "  AND (plate_photo_url IS NOT NULL OR overview_photo_url IS NOT NULL) "
        "  AND id > :lo AND id <= :hi "
        "ORDER BY id LIMIT :limit"
    )
    cutoff = _cutoff(older_than_days, now)
    rows = db.execute(
        query, {"cutoff": cutoff, "lo": after_pk, "hi": _MAX_PK, "limit": limit}
    ).all()
    if len(rows) < limit and after_pk > 0:
        rows += db.execute(
            query,
            {"cutoff": cutoff, "lo": 0, "hi": after_pk, "limit": limit - len(rows)},
        ).all()
    return [ExpiredPhotoRow(row[0], row[1], row[2]) for row in rows]


def refs_used_elsewhere(
    db: Session, refs: list[str], exclude_event_pks: list[int]
) -> set[str]:
    """Какие из ``refs`` нужны событиям ВНЕ пачки — их файлы удалять нельзя."""
    if not refs:
        return set()
    rows = db.execute(
        text(
            "SELECT plate_photo_url, overview_photo_url FROM camera_events "
            "WHERE (plate_photo_url IN :refs OR overview_photo_url IN :refs) "
            "  AND id NOT IN :pks"
        ).bindparams(
            bindparam("refs", expanding=True), bindparam("pks", expanding=True)
        ),
        {"refs": refs, "pks": exclude_event_pks},
    ).all()
    wanted = set(refs)
    return {ref for row in rows for ref in row if ref in wanted}


def clear_photo_refs(
    db: Session, rows: list[ExpiredPhotoRow], clearable: set[str]
) -> int:
    """Обнулить разрешённые ссылки; число событий, у которых что-то обнулено.

    UPDATE условный (``= :old``): если ссылку успели перезаписать новой загрузкой
    между чтением и записью, новая не теряется. Коммит — на вызывающем.
    """
    touched = 0
    for row in rows:
        params = {"pk": row.event_pk}
        sets = []
        for column, ref in zip(_COLUMNS, (row.plate_ref, row.overview_ref)):
            if ref and ref in clearable:
                sets.append(
                    f"{column} = CASE WHEN {column} = :{column} THEN NULL "
                    f"ELSE {column} END"
                )
                params[column] = ref
        if sets:
            db.execute(
                text(f"UPDATE camera_events SET {', '.join(sets)} WHERE id = :pk"),
                params,
            )
            touched += 1
    return touched


async def retire_media_files(
    media_ids: list[int], client: AccessMediaClient
) -> dict[int, MediaRetireOutcome]:
    """Последовательно удалить файлы в медиа-сервисе; исход по каждому id."""
    return {media_id: await retire_media_file(client, media_id) for media_id in media_ids}


@dataclass(frozen=True)
class RetentionPass:
    """Итог одного прохода: обнулено событий, осталось событий, курсор."""

    cleared: int
    pending: int
    last_pk: int


@dataclass(frozen=True)
class RetentionState:
    """Состояние воркера между тиками (в памяти процесса; рестарт — с начала)."""

    after_pk: int = 0
    stuck_ticks: int = 0


def retention_pass(
    session_factory: Callable[[], Session],
    *,
    client: AccessMediaClient | None = None,
    older_than_days: int = PHOTO_RETENTION_DAYS,
    now: dt.datetime | None = None,
    limit: int = PHOTO_RETENTION_BATCH,
    after_pk: int = 0,
) -> RetentionPass:
    """Один проход ретеншна фото (§11, A9-P2-16).

    Синхронный (исполняется в потоке воркера, без своего event loop): SQL — две
    короткие сессии, сетевые вызовы — между ними, без открытой транзакции.
    """
    with session_factory() as db:
        rows = select_expired_photos(
            db, older_than_days=older_than_days, now=now, limit=limit, after_pk=after_pk
        )
        media_refs = sorted(
            {ref for row in rows for ref in row.refs if _media_id(ref) is not None}
        )
        shared = refs_used_elsewhere(db, media_refs, [row.event_pk for row in rows])
        db.rollback()
    if not rows:
        return RetentionPass(cleared=0, pending=0, last_pk=0)

    to_retire = [_media_id(ref) for ref in media_refs if ref not in shared]
    outcomes = (
        asyncio.run(retire_media_files(to_retire, client or get_access_media_client()))
        if to_retire
        else {}
    )
    clearable = {
        ref
        for row in rows
        for ref in row.refs
        if _media_id(ref) is None  # legacy сырой URL: удалять негде
        or ref in shared  # файл нужен другому событию — у этого только ссылка
        or outcomes.get(_media_id(ref)) in _CLEARABLE
    }
    with session_factory() as db:
        cleared = clear_photo_refs(db, rows, clearable)
        db.commit()
    pending = sum(1 for row in rows if any(ref not in clearable for ref in row.refs))
    return RetentionPass(cleared=cleared, pending=pending, last_pk=rows[-1].event_pk)


def run_photo_retention(
    session_factory: Callable[[], Session],
    *,
    client: AccessMediaClient | None = None,
    older_than_days: int = PHOTO_RETENTION_DAYS,
    now: dt.datetime | None = None,
    limit: int = PHOTO_RETENTION_BATCH,
) -> int:
    """Проход с начала (без курсора); число событий с обнулёнными ссылками."""
    return retention_pass(
        session_factory,
        client=client,
        older_than_days=older_than_days,
        now=now,
        limit=limit,
    ).cleared


def advance_photo_retention(
    session_factory: Callable[[], Session],
    state: RetentionState,
    **kwargs,
) -> tuple[int, RetentionState]:
    """Тик воркера: проход от курсора ``state`` + учёт «застрявших» тиков.

    Возвращает (обнулено событий, новое состояние). Если в пачке остаются
    события с неудалёнными файлами ``STUCK_WARN_TICKS`` тиков подряд — WARNING
    в лог (и gauge ``access_photo_retention_stuck_ticks`` для алерта).
    """
    result = retention_pass(session_factory, after_pk=state.after_pk, **kwargs)
    stuck_ticks = state.stuck_ticks + 1 if result.pending else 0
    set_photo_retention_gauges(stuck_ticks=stuck_ticks, pending_events=result.pending)
    if stuck_ticks >= STUCK_WARN_TICKS:
        logger.warning(
            "photo retention: %d тиков подряд остаются события с неудалёнными "
            "файлами (в последней пачке %d) — проверить медиа-сервис",
            stuck_ticks,
            result.pending,
        )
    return result.cleared, RetentionState(after_pk=result.last_pk, stuck_ticks=stuck_ticks)
