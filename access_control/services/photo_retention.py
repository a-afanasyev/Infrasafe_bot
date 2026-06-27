"""Retention фото событий (§11): отбор и анонимизация ссылок старше срока.

Базовая техническая политика §11: «Фото номера и автомобиля — 30 дней». Механизм
обнуляет ``plate_photo_url``/``overview_photo_url`` у старых ``camera_events`` —
ссылок на приватный storage. ``camera_events`` — сырой слой, НЕ append-only (§9.7
hash-chain только на бизнес-журнале/аудите), поэтому UPDATE разрешён DB grants.

ПРОД-ДОЛГ (инфра, вне модели): фактическое необратимое удаление байтов в приватном
object-storage (S3/MinIO) по тем же кандидатам + регулярный запуск (cron/worker) +
legal hold. Здесь — только обнуление ссылок (анонимизация записи события).
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

# Срок хранения фото по умолчанию (§11), дней.
PHOTO_RETENTION_DAYS = 30


def _cutoff(older_than_days: int, now: dt.datetime | None) -> dt.datetime:
    base = now or dt.datetime.now(dt.timezone.utc)
    return base - dt.timedelta(days=older_than_days)


def select_expired_photo_event_ids(
    db: Session,
    *,
    older_than_days: int = PHOTO_RETENTION_DAYS,
    now: dt.datetime | None = None,
) -> list[int]:
    """ID ``camera_events`` старше срока, у которых ещё есть ссылка(и) на фото (§11).

    Кандидаты ретеншна: ``captured_at < now - older_than_days`` И хотя бы одна из
    ``*_photo_url`` непуста. Чистые/свежие события не возвращаются.
    """
    cutoff = _cutoff(older_than_days, now)
    rows = db.execute(
        text(
            "SELECT id FROM camera_events "
            "WHERE captured_at < :cutoff "
            "  AND (plate_photo_url IS NOT NULL OR overview_photo_url IS NOT NULL) "
            "ORDER BY id"
        ),
        {"cutoff": cutoff},
    ).scalars()
    return list(rows)


def purge_expired_photos(
    db: Session,
    *,
    older_than_days: int = PHOTO_RETENTION_DAYS,
    now: dt.datetime | None = None,
) -> int:
    """Анонимизировать (обнулить ссылки) фото событий старше срока (§11).

    Возвращает число затронутых строк. Коммит — на стороне вызывающего
    (команда/worker). Реальное удаление файлов в storage — прод-долг (инфра).
    """
    ids = select_expired_photo_event_ids(db, older_than_days=older_than_days, now=now)
    if not ids:
        return 0
    db.execute(
        text(
            "UPDATE camera_events "
            "SET plate_photo_url = NULL, overview_photo_url = NULL "
            "WHERE id IN :ids"
        ).bindparams(bindparam("ids", expanding=True)),
        {"ids": ids},
    )
    return len(ids)
