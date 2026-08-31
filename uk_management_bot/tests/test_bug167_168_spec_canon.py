"""BUG-167 + BUG-168 — последние два места мимо канона специализаций BUG-166.

BUG-167: метрика покрытия в аналитике смен считалась от зашитого legacy-набора
{electric, plumbing, hvac, maintenance, security} — четырёх из пяти токенов
после миграции 010 не существует, метрика физически не поднималась выше 20%.
Решение владельца 2026-08-19: все девять канон-специализаций равнозначны —
знаменатель = полный канон-набор.

BUG-168: предикат ДОСТУПА к заявке (групповое назначение) сравнивал множества
голым пересечением: universal-джокер не действовал, а group_specialization из
БД читался сырым — legacy-строка не совпала бы с каноном исполнителя. Решение
владельца 2026-08-19: канон BUG-166 и здесь (расширение видимости универсалов
одобрено); нерезолвимое требование fail-closed. Паритет sync/async обязателен.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from uk_management_bot.database.session import Base
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.request_assignment import RequestAssignment
from uk_management_bot.database.models.shift import Shift
from uk_management_bot.database.models.user import User
from uk_management_bot.utils.request_access import RequestAccessFacts, access_reason


# ══════════════════════════════════════════════════════════════════════════════
# BUG-167 — метрика покрытия по канон-набору
# ══════════════════════════════════════════════════════════════════════════════

def _score(shifts) -> float:
    from uk_management_bot.services.shift_planning_service.scoring import ScoringMixin

    class _Svc(ScoringMixin):
        pass

    return _Svc()._calculate_specialization_coverage_score(shifts)


def _shift(focus):
    return SimpleNamespace(specialization_focus=focus)


class TestBug167CoverageCanon:
    def test_two_canonical_specs_cover_two_ninths(self):
        score = _score([_shift(["electrician"]), _shift(["cleaning"])])
        assert score == pytest.approx(2 / 9 * 100, abs=0.01)

    def test_legacy_hvac_resolves_to_canon(self):
        # hvac (сторона «умеет/покрывает») → heating + ventilation = 2 из 9.
        score = _score([_shift(["hvac"])])
        assert score == pytest.approx(2 / 9 * 100, abs=0.01)

    def test_universal_shift_covers_everything(self):
        assert _score([_shift(["universal"])]) == 100.0

    def test_full_canon_is_100(self):
        from uk_management_bot.constants.specializations import CANONICAL_SPECIALIZATIONS
        shifts = [_shift([s]) for s in CANONICAL_SPECIALIZATIONS]
        assert _score(shifts) == 100.0

    def test_garbage_focus_counts_as_nothing(self):
        assert _score([_shift(["blackmagic"])]) == 0.0

    def test_empty_is_zero(self):
        assert _score([]) == 0.0


# ══════════════════════════════════════════════════════════════════════════════
# BUG-168 — предикат доступа: чистая матрица на фактах
# ══════════════════════════════════════════════════════════════════════════════

def _facts(**over) -> RequestAccessFacts:
    base = dict(
        roles=frozenset({"executor"}),
        user_id=2,
        request_owner_id=1,
        request_executor_id=None,
        request_status="Новая",
        request_apartment_id=None,
        has_individual_assignment=False,
        group_specializations=frozenset(),
        user_specializations=frozenset(),
        has_active_shift=True,
        is_approved_resident=False,
    )
    base.update(over)
    return RequestAccessFacts(**base)


class TestBug168FactsPredicate:
    def test_universal_executor_gets_group_access(self):
        f = _facts(user_specializations=frozenset({"universal"}),
                   group_specializations=frozenset({"plumber"}))
        assert access_reason(f) == "executor_group_assignment_on_shift"

    def test_universal_requirement_admits_anyone(self):
        f = _facts(user_specializations=frozenset({"cleaning"}),
                   group_specializations=frozenset({"universal"}))
        assert access_reason(f) == "executor_group_assignment_on_shift"

    def test_plain_intersection_still_works(self):
        f = _facts(user_specializations=frozenset({"plumber"}),
                   group_specializations=frozenset({"plumber"}))
        assert access_reason(f) == "executor_group_assignment_on_shift"

    def test_mismatch_denied(self):
        f = _facts(user_specializations=frozenset({"cleaning"}),
                   group_specializations=frozenset({"plumber"}))
        assert access_reason(f) is None

    def test_empty_group_specs_do_not_admit(self):
        # Пустое «требование» здесь означает «группового назначения нет» —
        # правило 1 канона (пусто не ограничивает) сюда переноситься НЕ должно.
        f = _facts(user_specializations=frozenset({"universal"}),
                   group_specializations=frozenset())
        assert access_reason(f) is None


# ══════════════════════════════════════════════════════════════════════════════
# BUG-168 — нормализация на чтении + паритет sync/async (живые запросы)
# ══════════════════════════════════════════════════════════════════════════════

def _seed(session_or_none=None):
    """Матрица: (спец. исполнителя, group_specialization в БД, ждём доступ?)."""
    return [
        ("electrician", "electric", True),    # legacy в БД → канон исполнителя
        ("universal", "plumber", True),       # джокер исполнителя
        ("cleaning", "universal", True),      # джокер требования
        ("cleaning", "plumber", False),       # мимо
        ("electrician", "blackmagic", False), # мусор — fail-closed
    ]


def _make_sync_db():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)()


def _seed_case(db, idx, user_spec, group_spec):
    applicant = User(id=idx * 10 + 1, telegram_id=idx * 100 + 1, username=f"a{idx}",
                     first_name="A", roles='["applicant"]', status="approved")
    executor = User(id=idx * 10 + 2, telegram_id=idx * 100 + 2, username=f"e{idx}",
                    first_name="E", roles='["executor"]', status="approved",
                    specialization=user_spec)
    req = Request(request_number=f"2609{idx:02d}-001", user_id=applicant.id,
                  category="Электрика", description="d", address="Дом 1",
                  status="Новая")
    db.add_all([applicant, executor, req])
    db.commit()
    db.add(RequestAssignment(request_number=req.request_number,
                             assignment_type="group",
                             group_specialization=group_spec,
                             status="active", created_by=applicant.id))
    db.add(Shift(user_id=executor.id, status="active",
                 start_time=__import__("datetime").datetime.now()))
    db.commit()
    return executor, req


class TestBug168SyncPath:
    @pytest.mark.parametrize("user_spec,group_spec,expect", _seed())
    def test_sync_matrix(self, user_spec, group_spec, expect):
        from uk_management_bot.services.request_access import (
            request_access_reason_sync,
        )

        db = _make_sync_db()
        try:
            executor, req = _seed_case(db, 1, user_spec, group_spec)
            reason = request_access_reason_sync(db, executor, req)
            assert (reason == "executor_group_assignment_on_shift") is expect
        finally:
            db.close()


class TestBug168AsyncParity:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("user_spec,group_spec,expect", _seed())
    async def test_async_matrix_matches_sync(self, user_spec, group_spec, expect):
        from sqlalchemy.ext.asyncio import (
            AsyncSession, create_async_engine,
        )

        from uk_management_bot.services.request_access import (
            request_access_reason_async,
        )

        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with AsyncSession(engine, expire_on_commit=False) as adb:
            # Сидим через sync-хелпер на run_sync — та же матрица байт-в-байт.
            executor_req = await adb.run_sync(
                lambda s: _seed_case(s, 2, user_spec, group_spec))
            executor, req = executor_req
            reason = await request_access_reason_async(adb, executor, req)
            assert (reason == "executor_group_assignment_on_shift") is expect
        await engine.dispose()
