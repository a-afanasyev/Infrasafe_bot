"""Согласие на обработку персональных данных (ЗРУ-547, ст. 18, 21, 31).

Два пути:

* новый житель ставит флажок в форме регистрации — сервер пишет время и версию
  текста (``api/registration/router.py``);
* уже зарегистрированному бот один раз показывает уведомление, и следующее его
  действие засчитывается как согласие (``middlewares/pd_consent.py``).

Каждое согласие — запись ``pd_consent_given`` в журнале аудита с версией текста
и источником: это доказательство, которое оператор обязан хранить.

При изменении текста согласия (локали ``pd_consent.*``) поднять
``PD_CONSENT_VERSION``.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from uk_management_bot.database.models.audit import AuditLog
from uk_management_bot.database.models.user import User

PD_CONSENT_VERSION = "2026-11-16"
SOURCE_REGISTRATION = "registration"
SOURCE_CONTINUED_USE = "continued_use"
# Пачка апдейтов (альбом фото) сразу за уведомлением — не «продолжил пользоваться».
ACCEPT_GRACE = timedelta(minutes=1)


def grant(user: User, source: str, now: datetime) -> Optional[AuditLog]:
    """Ставит согласие, если его ещё нет. → запись журнала для ``db.add`` или None."""
    if user.pd_consent_at is not None:
        return None
    user.pd_consent_at = now
    user.pd_consent_version = PD_CONSENT_VERSION
    return AuditLog(
        action="pd_consent_given",
        user_id=user.id,
        telegram_user_id=user.telegram_id,
        details={"version": PD_CONSENT_VERSION, "source": source},
    )


def accept_sync(db: Session, user_id: int, source: str) -> None:
    # FOR UPDATE: два параллельных апдейта не пишут две записи в журнал.
    user = db.query(User).filter(User.id == user_id).with_for_update().first()
    if user is None:
        return
    log = grant(user, source, datetime.now(timezone.utc))
    if log is not None:
        db.add(log)
        db.commit()


def claim_notice_sync(db: Session, user_id: int) -> bool:
    """Атомарно занимает право показать уведомление. → True только у одного из
    параллельных апдейтов (альбом фото приходит пачкой), остальные молчат."""
    claimed = db.query(User).filter(
        User.id == user_id, User.pd_consent_notified_at.is_(None)
    ).update({User.pd_consent_notified_at: datetime.now(timezone.utc)}, synchronize_session=False)
    db.commit()
    return claimed == 1


def release_notice_sync(db: Session, user_id: int) -> None:
    """Уведомление не доставлено — снять отметку, чтобы оно ушло при следующем обращении."""
    db.query(User).filter(
        User.id == user_id, User.pd_consent_at.is_(None)
    ).update({User.pd_consent_notified_at: None}, synchronize_session=False)
    db.commit()
