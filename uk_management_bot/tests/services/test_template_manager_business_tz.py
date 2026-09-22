"""A9-P3-8: утилизация шаблона считает «последние 30 дней» по бизнес-дате.

Было: `date.today()` (UTC-дата контейнера) и сравнение `created_at >= date` —
граница месяца проходила по полуночи UTC (05:00 по Ташкенту), а «сегодня»
с 19:00Z уже было завтрашним по местному. Стало: бизнес-«сегодня» и UTC-окно
от полуночи бизнес-зоны (канон `utils/business_time`). Проверяется на
настоящей sqlite-сессии: предмет — сам SQL-предикат.
"""
from datetime import date, datetime, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from uk_management_bot.database.session import Base
import uk_management_bot.database.models  # noqa: F401 — регистрация таблиц
from uk_management_bot.database.models.shift import Shift
from uk_management_bot.database.models.shift_template import ShiftTemplate
from uk_management_bot.utils.business_time import BUSINESS_TZ


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)


def test_utilization_window_starts_at_business_midnight(db):
    if getattr(BUSINESS_TZ, "key", "") != "Asia/Tashkent":
        pytest.skip("ожидания посчитаны для Asia/Tashkent")
    from uk_management_bot.services.template_manager import TemplateManager

    tpl = ShiftTemplate(
        id=1, name="t", start_hour=8, duration_hours=8, auto_create=True,
        days_of_week=[1, 2, 3, 4, 5, 6, 7],
    )
    db.add(tpl)
    db.flush()
    start = datetime(2026, 9, 23, 3, 0, tzinfo=timezone.utc)
    # 2026-08-24 00:30 по Ташкенту — ВНУТРИ окна «30 дней от 2026-09-23».
    inside = datetime(2026, 8, 23, 19, 30, tzinfo=timezone.utc)
    # 2026-08-23 23:30 по Ташкенту — СНАРУЖИ.
    outside = datetime(2026, 8, 23, 18, 30, tzinfo=timezone.utc)
    for sid, created in ((1, inside), (2, outside)):
        db.add(Shift(id=sid, status="planned", start_time=start,
                     shift_template_id=1, created_at=created))
    db.commit()

    with patch(
        "uk_management_bot.services.template_manager.business_today",
        return_value=date(2026, 9, 23),
    ):
        utilization = TemplateManager(db)._calculate_template_utilization(tpl)

    # 31 ожидаемый день (24.08–23.09 включительно), 1 фактическая смена.
    assert utilization == pytest.approx(100.0 / 31)
