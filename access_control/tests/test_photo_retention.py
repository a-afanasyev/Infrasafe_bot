"""Retention фото (§11): отбор и анонимизация фото старше 30 дней.

Базовая техническая политика §11: «Фото номера и автомобиля — 30 дней».
Пилот синтетический и реального object-storage нет: механизм обнуляет
``*_photo_url`` у старых ``camera_events`` (ссылки на фото) — реальное удаление
байтов в приватном storage остаётся инфра-задачей (прод-долг, S3/MinIO).

``camera_events`` — НЕ append-only (сырой слой, §9.7 hash-chain только на
бизнес-журнале/аудите), поэтому UPDATE разрешён DB grants.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import text

from access_control.services import photo_retention as pr
from access_control.tests.conftest import utcnow
from access_control.tests.test_operator_read_api import _seed_camera_event


def _has_photos(db, ce_id: int) -> bool:
    row = db.execute(
        text(
            "SELECT plate_photo_url, overview_photo_url FROM camera_events WHERE id=:i"
        ),
        {"i": ce_id},
    ).mappings().first()
    return bool(row["plate_photo_url"] or row["overview_photo_url"])


def test_select_expired_picks_only_old_with_photos(pg_db, pilot) -> None:
    now = utcnow()
    old = _seed_camera_event(
        pg_db, pilot, event_id="ev-old", plate="01OLD00",
        captured_at=now - dt.timedelta(days=31),
        plate_photo_url="https://cdn.example/old.jpg",
    )
    # старое, но без фото → не кандидат
    _seed_camera_event(
        pg_db, pilot, event_id="ev-old-nophoto", plate="01OLN00",
        captured_at=now - dt.timedelta(days=40),
    )
    # свежее с фото → не кандидат
    _seed_camera_event(
        pg_db, pilot, event_id="ev-new", plate="01NEW00",
        captured_at=now - dt.timedelta(days=1),
        plate_photo_url="https://cdn.example/new.jpg",
    )
    pg_db.commit()

    ids = pr.select_expired_photo_event_ids(pg_db, older_than_days=30, now=now)
    assert ids == [old]


def test_purge_nulls_old_photo_urls_only(pg_db, pilot) -> None:
    now = utcnow()
    old = _seed_camera_event(
        pg_db, pilot, event_id="ev-old2", plate="01OLD22",
        captured_at=now - dt.timedelta(days=31),
        plate_photo_url="https://cdn.example/old2-plate.jpg",
        overview_photo_url="https://cdn.example/old2-overview.jpg",
    )
    new = _seed_camera_event(
        pg_db, pilot, event_id="ev-new2", plate="01NEW22",
        captured_at=now - dt.timedelta(days=2),
        plate_photo_url="https://cdn.example/new2.jpg",
    )
    pg_db.commit()

    purged = pr.purge_expired_photos(pg_db, older_than_days=30, now=now)
    pg_db.commit()
    assert purged == 1
    assert _has_photos(pg_db, old) is False
    assert _has_photos(pg_db, new) is True


def test_purge_default_retention_days_constant() -> None:
    assert pr.PHOTO_RETENTION_DAYS == 30
