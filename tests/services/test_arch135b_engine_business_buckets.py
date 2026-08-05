"""ARCH-135(б): дневные бакеты ДВИЖКОВ планирования/назначения — по бизнес-дню.

В отличие от показа (ARCH-116) и дашборда (фаза 1), здесь бакет меняет РЕШЕНИЯ
алгоритмов: увидит ли проверка дубликатов уже созданную смену, к какому дню
отнесёт нагрузку прогноз, попадёт ли соседняя смена в окно штрафа за конфликт.
Каждый класс ниже — решение одной функции на граничном инстанте.

Граница везде одна: 21:00 UTC = 02:00 следующего дня по Ташкенту (+05).
Харнес честный без Postgres (память по ARCH-116): sqlite возвращает naive-UTC,
канон business_time трактует naive как UTC; предикаты — aware-UTC диапазоны.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.shift import Shift
from uk_management_bot.database.models.shift_template import ShiftTemplate
from uk_management_bot.database.models.user import User
from uk_management_bot.database.session import Base
from uk_management_bot.services import recommendation_engine as rec_mod
from uk_management_bot.services.shift_analytics import ShiftAnalytics
from uk_management_bot.services.shift_assignment_service import (
    ScoringEngine,
    ShiftAssignmentService,
    WorkloadBalancer,
)
from uk_management_bot.services.shift_planning_service import ShiftPlanningService

# 30.07 02:00 Ташкента; UTC-дата инстанта — ещё 29.07
CROSSOVER_UTC = datetime(2026, 7, 29, 21, 0, tzinfo=timezone.utc)
BUSINESS_DATE = date(2026, 7, 30)
UTC_DATE = date(2026, 7, 29)

_engine = create_engine("sqlite:///:memory:", echo=False)
_Session = sessionmaker(autocommit=False, autoflush=False, bind=_engine)


@pytest.fixture()
def db():
    Base.metadata.create_all(bind=_engine)
    session = _Session()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=_engine)


def _shift(db, start_utc: datetime, *, hours: int = 8, user_id: int | None = 1,
           status: str = "planned", template_id: int | None = None) -> Shift:
    end_utc = start_utc + timedelta(hours=hours)
    shift = Shift(user_id=user_id, status=status,
                  start_time=start_utc, end_time=end_utc,
                  planned_start_time=start_utc, planned_end_time=end_utc,
                  shift_template_id=template_id)
    db.add(shift)
    db.commit()
    return shift


def _user(db, telegram_id: int = 920001) -> User:
    user = User(telegram_id=telegram_id, roles='["executor"]',
                active_role="executor", status="approved",
                language="ru", first_name="Исполнитель")
    db.add(user)
    db.commit()
    return user


def _request(db, created_at: datetime, *, number: str, user_id: int,
             status: str = "Новая") -> Request:
    req = Request(request_number=number, user_id=user_id, category="elevator",
                  status=status, description="демо", urgency="low",
                  is_returned=False, manager_confirmed=False,
                  address="ул. Тестовая, 1", created_at=created_at)
    db.add(req)
    db.commit()
    return req


class TestCoverageGaps:
    """shift_planning_service.get_coverage_gaps: день И часы — бизнес-зона."""

    def test_crossover_shift_covers_business_hours_of_its_business_date(self, db):
        _shift(db, CROSSOVER_UTC)  # 02:00–10:00 по Ташкенту
        gaps = ShiftPlanningService(db).get_coverage_gaps(BUSINESS_DATE, BUSINESS_DATE)
        assert len(gaps) == 1
        entry = gaps[0]
        assert entry["total_shifts"] == 1, "смена 02:00 местного не попала в свой день"
        # Покрыты бизнес-часы 2..9 (не UTC-часы 21..4)
        for covered in range(2, 10):
            assert covered not in entry["uncovered_hours"]
        assert 21 in entry["uncovered_hours"], "покрытие посчитано UTC-часами"

    def test_crossover_shift_absent_from_previous_utc_date(self, db):
        _shift(db, CROSSOVER_UTC)
        gaps = ShiftPlanningService(db).get_coverage_gaps(UTC_DATE, UTC_DATE)
        assert gaps[0]["total_shifts"] == 0, (
            "func.date отнёс бы смену к UTC-дате 29.07 — регресс ARCH-135(б)")


class TestOptimizationScore:
    """_calculate_optimization_score: смена учитывается в своём бизнес-дне."""

    def test_score_positive_on_business_date_zero_on_utc_date(self, db):
        _shift(db, CROSSOVER_UTC)
        svc = ShiftPlanningService(db)
        assert svc._calculate_optimization_score(BUSINESS_DATE) > 0.0
        assert svc._calculate_optimization_score(UTC_DATE) == 0.0


class TestTemplateWallClock:
    """Шаблон «08:00» — стенка бизнес-зоны, а не UTC."""

    def _template(self, db) -> ShiftTemplate:
        tmpl = ShiftTemplate(name="Дневная", start_hour=8, start_minute=0,
                             duration_hours=9, is_active=True,
                             days_of_week=[1, 2, 3, 4, 5, 6, 7])
        db.add(tmpl)
        db.commit()
        return tmpl

    def test_created_shift_starts_at_business_wall_clock(self, db):
        tmpl = self._template(db)
        shift = ShiftPlanningService(db)._create_single_shift_from_template(
            tmpl, BUSINESS_DATE)
        assert shift is not None
        # 08:00 Ташкента 30.07 = 03:00Z 30.07 (раньше хранилось 08:00Z = 13:00 местного)
        assert shift.planned_start_time == datetime(2026, 7, 30, 3, 0, tzinfo=timezone.utc)

    def test_duplicate_check_sees_crossover_shift_on_its_business_date(self, db):
        tmpl = self._template(db)
        _shift(db, CROSSOVER_UTC, template_id=tmpl.id)  # смена бизнес-дня 30.07
        created = ShiftPlanningService(db).create_shift_from_template(
            tmpl.id, BUSINESS_DATE)
        assert created == [], (
            "дубликат не замечен: func.date отнёс бы существующую смену к 29.07")


class TestPredictWorkloadHistoryBuckets:
    """predict_workload: история и weekday-бакеты — по бизнес-дню заявки."""

    @pytest.mark.asyncio
    async def test_evening_utc_request_feeds_next_business_weekday(self, db):
        user = _user(db)
        # 20:30Z вторника 28.07 = 01:30 СРЕДЫ 29.07 по Ташкенту — единственная
        # заявка истории. Прогноз должен положить нагрузку на среды, не вторники.
        _request(db, datetime(2026, 7, 28, 20, 30, tzinfo=timezone.utc),
                 number="260728-001", user_id=user.id)
        forecast = await ShiftPlanningService(db).predict_workload(
            date(2026, 8, 5), days_ahead=7)
        by_weekday = {p["weekday"]: p["predicted_requests"]
                      for p in forecast["daily_predictions"]}
        assert by_weekday[2] > 0.0, "нагрузка не легла на бизнес-день (среду)"
        assert by_weekday[1] == 0.0, (
            "нагрузка легла на UTC-день недели (вторник) — регресс ARCH-135(б)")


class TestConflictPenaltiesWindow:
    """ScoringEngine._calculate_conflict_penalties: окно ±3 БИЗНЕС-дня."""

    def _engine(self, db) -> ScoringEngine:
        return ScoringEngine(db, ShiftAssignmentService(db).weights)

    def _seed_four_in_window(self, db, executor) -> Shift:
        """Якорь (бизнес-день 30.07, сам в окне) + 3 смены 27–29.07 12:00 местного.
        Итого 4 в окне [27.07..02.08]; порог штрафа — 5."""
        anchor = _shift(db, CROSSOVER_UTC, user_id=executor.id)
        for day in (27, 28, 29):
            _shift(db, datetime(2026, 7, day, 7, 0, tzinfo=timezone.utc),
                   user_id=executor.id)
        return anchor

    def test_business_window_edge_included(self, db):
        """5-я смена в 23:00 местного последнего дня окна: бизнес-бакет её видит
        (порог 5 срабатывает), старый func.date по UTC-дате 02.08 — нет."""
        executor = _user(db)
        anchor = self._seed_four_in_window(db, executor)
        # Граничная: 02.08 23:00 местного = 18:00Z — бизнес-день 02.08 (край окна
        # [27.07..02.08]); её UTC-дата 02.08 в старое окно [26.07..01.08] не входила
        _shift(db, datetime(2026, 8, 2, 18, 0, tzinfo=timezone.utc), user_id=executor.id)
        penalties = self._engine(db)._calculate_conflict_penalties(anchor, executor)
        assert penalties == pytest.approx(0.3), (
            "граничная смена выпала из окна — бакет считан не по бизнес-дню")

    def test_next_business_day_outside_window_excluded(self, db):
        """Смена 00:00 местного 03.08 (19:00Z 02.08) — уже ВНЕ окна ±3 бизнес-дня."""
        executor = _user(db)
        anchor = self._seed_four_in_window(db, executor)
        _shift(db, datetime(2026, 8, 2, 19, 0, tzinfo=timezone.utc), user_id=executor.id)
        penalties = self._engine(db)._calculate_conflict_penalties(anchor, executor)
        assert penalties == pytest.approx(0.0)


class TestWorkloadBalancerWindow:
    """WorkloadBalancer.balance_executor_workload: смены дня — бизнес-окно."""

    def test_crossover_shift_found_on_business_date_not_utc_date(self, db):
        executor = _user(db)
        _shift(db, CROSSOVER_UTC, user_id=executor.id)
        svc = ShiftAssignmentService(db)
        balancer = WorkloadBalancer(db, svc.scoring_engine)

        on_utc_date = balancer.balance_executor_workload(UTC_DATE)
        assert "Нет смен" in on_utc_date.get("message", ""), (
            "смена числится за UTC-датой — регресс ARCH-135(б)")

        on_business_date = balancer.balance_executor_workload(BUSINESS_DATE)
        assert "Нет смен" not in on_business_date.get("message", "")


class TestRebalanceDailyAssignments:
    """shift_planning_service.rebalance_daily_assignments: день — бизнес-окно."""

    def test_crossover_shift_found_on_business_date_not_utc_date(self, db):
        executor = _user(db)
        _shift(db, CROSSOVER_UTC, user_id=executor.id)
        svc = ShiftPlanningService(db)
        assert svc.rebalance_daily_assignments(UTC_DATE)["status"] == "no_shifts", (
            "смена числится за UTC-датой — регресс ARCH-135(б)")
        assert svc.rebalance_daily_assignments(BUSINESS_DATE)["status"] == "success"


class TestDailyLoadTrend:
    """recommendation_engine._get_daily_load_trend: бакет дня — бизнес-окно."""

    @pytest.mark.asyncio
    async def test_evening_utc_request_counts_in_its_business_day(self, db, monkeypatch):
        user = _user(db)
        _request(db, datetime(2026, 7, 29, 20, 30, tzinfo=timezone.utc),
                 number="260729-001", user_id=user.id)  # 01:30 местного 30.07
        # raising=False: на до-миграционном коде символа нет — RED должен
        # приходить из семантики бакета, а не из AttributeError монкипатча
        monkeypatch.setattr(rec_mod, "business_today", lambda: BUSINESS_DATE,
                            raising=False)
        trend = await rec_mod.RecommendationEngine(db)._get_daily_load_trend(1)
        assert trend == [1], (
            "func.date отнёс бы заявку к 29.07 и тренд за 30.07 был бы пустым")


class TestAnalyzeDailyPatterns:
    """shift_analytics.analyze_daily_patterns: окно и weekday/hour — бизнес-зона."""

    @pytest.mark.asyncio
    async def test_window_and_buckets_follow_business_day(self, db):
        user = _user(db)
        # 20:30Z вторника 04.08 = 01:30 СРЕДЫ 05.08 по Ташкенту
        _request(db, datetime(2026, 8, 4, 20, 30, tzinfo=timezone.utc),
                 number="260804-001", user_id=user.id)
        result = await ShiftAnalytics(db).analyze_daily_patterns(
            date(2026, 8, 5), date(2026, 8, 5))
        # Окно: UTC-окно [05.08T00:00Z..] заявку бы НЕ нашло (message-ветка)
        assert result.get("message") != "No data for analysis", (
            "окно осталось UTC-сутками — заявка выпала из периода")
        assert result["period"]["total_requests"] == 1
        # Бакеты: среда и час ночи местного, а не вторник/20:00
        assert result["weekday_analysis"]["peak_day"]["day"] == "Среда"
        assert result["hourly_analysis"]["peak_hour"]["hour"] == "1:00"
