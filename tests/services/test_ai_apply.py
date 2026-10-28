"""Применение триажа (services/ai_manager/apply.py) на sqlite: реальный
run_command_sync, маркеры audit, идемпотентность, деградация.

LLM подменяется на уровне `triage.llm_payload_sync` (сырой payload или None =
сбой), предохранитель — на уровне функций `breaker`, Telegram — спаями.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import uk_management_bot.utils.constants as C
from uk_management_bot.config.settings import settings
from uk_management_bot.database.models.audit import AuditLog
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.user import User
from uk_management_bot.database.session import Base
from uk_management_bot.services import workflow_notifications
from uk_management_bot.services.ai_manager import apply, breaker, triage
from uk_management_bot.services.ai_manager.apply import (
    AUDIT_APPLIED,
    AUDIT_FAILED,
    apply_triage_sync,
)

NUM = "261028-001"
AI_CFG = {"min_confidence": 0.7, "clarify_enabled": True, "dedup_enabled": True,
          "triage_instructions": "", "news_instructions": "", "extra_emergency_keywords": [], "templates": {}}


@pytest.fixture()
def SF():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    s = factory()
    s.add_all([
        User(id=1, telegram_id=settings.INFRASAFE_SYSTEM_USER_TELEGRAM_ID, first_name="System",
             roles='["manager"]', active_role="manager", status="approved", language="ru"),
        User(id=2, telegram_id=2, first_name="Owner", roles='["applicant"]',
             active_role="applicant", status="approved", language="uz"),
    ])
    s.commit()
    s.close()
    yield factory
    engine.dispose()


def _seed(SF, *, description="нет света в подъезде", category="plumbing", urgency="low",
          apartment_id=10, number=NUM, created_at=None, status=C.REQUEST_STATUS_NEW):
    s = SF()
    s.add(Request(request_number=number, user_id=2, category=category, description=description,
                  urgency=urgency, status=status, apartment_id=apartment_id,
                  created_at=created_at or datetime.now(timezone.utc)))
    s.commit()
    s.close()


def _req(SF, number=NUM) -> Request:
    s = SF()
    try:
        return s.execute(select(Request).where(Request.request_number == number)).scalar_one()
    finally:
        s.close()


def _audits(SF, action):
    s = SF()
    try:
        return [a.details for a in s.execute(select(AuditLog).where(AuditLog.action == action)).scalars()]
    finally:
        s.close()


def _payload(**over):
    base = {"category": "plumbing", "urgency": "low", "needs_clarification": False,
            "clarification_question_ru": "", "clarification_question_uz": "",
            "duplicate_of": None, "confidence": 0.9, "reasoning": "ок"}
    base.update(over)
    return base


@pytest.fixture(autouse=True)
def quiet(monkeypatch):
    """Breaker закрыт, Telegram — спаи."""
    calls = {"failure": 0, "success": 0, "manager": [], "clarify": []}
    monkeypatch.setattr(breaker, "is_open", lambda: False)
    monkeypatch.setattr(breaker, "record_failure", lambda: calls.__setitem__("failure", calls["failure"] + 1) or False)
    monkeypatch.setattr(breaker, "record_success", lambda: calls.__setitem__("success", calls["success"] + 1))
    monkeypatch.setattr(apply, "_notify_manager",
                        lambda sf, title, body, **fmt: calls["manager"].append((title, fmt)))
    notify = AsyncMock(return_value=1)
    monkeypatch.setattr(workflow_notifications, "dispatch_notify_intents_sync", notify)
    calls["notify"] = notify
    return calls


def _llm(monkeypatch, payload):
    captured = {}

    def fake(text, *, category, lang, open_same_address, instructions=""):
        captured.update(text=text, category=category, lang=lang, open=open_same_address,
                        instructions=instructions)
        return payload

    monkeypatch.setattr(triage, "llm_payload_sync", fake)
    return captured


# ───────────── применение подсказок ─────────────


def test_no_change_writes_applied_marker(SF, monkeypatch, quiet):
    _seed(SF)
    captured = _llm(monkeypatch, _payload())
    out = apply_triage_sync(NUM, AI_CFG, SF)
    assert out == apply.TriageOutcome()
    req = _req(SF)
    assert (req.category, req.urgency, req.status) == ("plumbing", "low", C.REQUEST_STATUS_NEW)
    marker = _audits(SF, AUDIT_APPLIED)
    assert len(marker) == 1 and marker[0]["request_number"] == NUM
    assert marker[0]["confidence"] == 0.9 and marker[0]["clarified"] is False
    assert captured["lang"] == "uz" and captured["category"] == "plumbing"
    assert quiet["success"] == 1


def test_category_change_goes_through_workflow(SF, monkeypatch):
    _seed(SF)
    _llm(monkeypatch, _payload(category="electricity", urgency="high"))
    out = apply_triage_sync(NUM, AI_CFG, SF)
    assert out.category == "electricity" and out.clarified is False
    req = _req(SF)
    assert req.category == "electricity" and req.urgency == "high"
    assert req.status == C.REQUEST_STATUS_NEW
    assert _audits(SF, C.AUDIT_ACTION_REQUEST_CATEGORY_CHANGED), "смена категории — канон-переход с audit"
    assert _audits(SF, AUDIT_APPLIED)[0]["category"] == "electricity"


def test_clarification_moves_request_and_asks_in_user_language(SF, monkeypatch, quiet):
    _seed(SF, description="что-то не работает")
    _llm(monkeypatch, _payload(needs_clarification=True,
                               clarification_question_ru="Что именно не работает?",
                               clarification_question_uz="Aynan nima ishlamayapti?"))
    out = apply_triage_sync(NUM, AI_CFG, SF)
    assert out.clarified is True
    req = _req(SF)
    assert req.status == C.REQUEST_STATUS_CLARIFICATION
    assert "Aynan nima ishlamayapti?" in (req.notes or "")
    assert "ИИ-менеджер" in (req.notes or "")
    assert _audits(SF, AUDIT_APPLIED)[0]["clarified"] is True
    quiet["notify"].assert_awaited_once()
    assert quiet["notify"].await_args.kwargs["clarification_text"] == "Aynan nima ishlamayapti?"


def test_clarify_disabled_by_config(SF, monkeypatch, quiet):
    _seed(SF)
    _llm(monkeypatch, _payload(needs_clarification=True, clarification_question_ru="?",
                               clarification_question_uz="?"))
    out = apply_triage_sync(NUM, {**AI_CFG, "clarify_enabled": False}, SF)
    assert out.clarified is False
    assert _req(SF).status == C.REQUEST_STATUS_NEW
    quiet["notify"].assert_not_awaited()


def test_duplicate_notifies_manager_and_leaves_request_alone(SF, monkeypatch, quiet):
    _seed(SF, number="261027-005", description="свет моргает")
    _seed(SF)
    captured = _llm(monkeypatch, _payload(duplicate_of="261027-005"))
    apply_triage_sync(NUM, AI_CFG, SF)
    assert [n for n, _, _ in captured["open"]] == ["261027-005"]
    assert quiet["manager"] == [("ai_manager.duplicate_title",
                                 {"request_number": NUM, "duplicate_of": "261027-005"})]
    assert _req(SF).status == C.REQUEST_STATUS_NEW
    assert _audits(SF, AUDIT_APPLIED)[0]["duplicate_of"] == "261027-005"


def test_dedup_candidates_exclude_closed_old_and_other_addresses(SF, monkeypatch):
    _seed(SF, number="261027-001", status=C.REQUEST_STATUS_APPROVED)
    _seed(SF, number="261027-002", created_at=datetime.now(timezone.utc) - timedelta(days=30))
    _seed(SF, number="261027-003", apartment_id=99)
    _seed(SF, number="261027-004")
    _seed(SF)
    captured = _llm(monkeypatch, _payload())
    apply_triage_sync(NUM, AI_CFG, SF)
    assert [n for n, _, _ in captured["open"]] == ["261027-004"]


def test_dedup_disabled_sends_no_candidates(SF, monkeypatch):
    _seed(SF, number="261027-004")
    _seed(SF)
    captured = _llm(monkeypatch, _payload())
    apply_triage_sync(NUM, {**AI_CFG, "dedup_enabled": False}, SF)
    assert captured["open"] == ()


# ───────────── деградация и идемпотентность ─────────────


def test_emergency_applied_even_when_llm_fails(SF, monkeypatch, quiet):
    _seed(SF, description="запах газа в квартире")
    _llm(monkeypatch, None)
    out = apply_triage_sync(NUM, AI_CFG, SF)
    assert out == apply.TriageOutcome()
    assert _req(SF).urgency == "critical"
    marker = _audits(SF, AUDIT_APPLIED)[0]
    assert marker["emergency"] == "critical" and marker["confidence"] is None
    assert quiet["failure"] == 1


def test_breaker_open_skips_llm_but_keeps_emergency(SF, monkeypatch, quiet):
    _seed(SF, description="подвал затопило")
    monkeypatch.setattr(breaker, "is_open", lambda: True)
    called = _llm(monkeypatch, _payload(urgency="high"))
    apply_triage_sync(NUM, AI_CFG, SF)
    assert called == {}
    assert _req(SF).urgency == "critical"


def test_breaker_trip_notifies_manager_once(SF, monkeypatch, quiet):
    _seed(SF)
    _llm(monkeypatch, None)
    monkeypatch.setattr(breaker, "record_failure", lambda: True)
    apply_triage_sync(NUM, AI_CFG, SF)
    assert quiet["manager"] == [("ai_manager.breaker_title", {})]


def test_low_confidence_changes_nothing_but_marks_applied(SF, monkeypatch):
    _seed(SF)
    _llm(monkeypatch, _payload(category="electricity", urgency="critical", confidence=0.3))
    apply_triage_sync(NUM, AI_CFG, SF)
    req = _req(SF)
    assert (req.category, req.urgency) == ("plumbing", "low")
    assert len(_audits(SF, AUDIT_APPLIED)) == 1


def test_already_applied_is_skipped(SF, monkeypatch):
    _seed(SF)
    captured = _llm(monkeypatch, _payload())
    apply_triage_sync(NUM, AI_CFG, SF)
    captured.clear()
    apply_triage_sync(NUM, AI_CFG, SF)
    assert captured == {}
    assert len(_audits(SF, AUDIT_APPLIED)) == 1


def test_missing_request_is_noop(SF, monkeypatch):
    captured = _llm(monkeypatch, _payload())
    assert apply_triage_sync("000000-000", AI_CFG, SF) == apply.TriageOutcome()
    assert captured == {}


def test_failure_writes_failed_marker_and_retry_applies(SF, monkeypatch):
    _seed(SF)
    _llm(monkeypatch, _payload(category="electricity"))

    def boom(*a, **k):
        raise RuntimeError("db gone")

    monkeypatch.setattr(apply, "_run", boom)
    out = apply_triage_sync(NUM, AI_CFG, SF)
    assert out == apply.TriageOutcome()
    assert _audits(SF, AUDIT_APPLIED) == []
    failed = _audits(SF, AUDIT_FAILED)
    assert failed and failed[0]["step"] == "category" and failed[0]["error"] == "RuntimeError"

    monkeypatch.undo()  # вернуть настоящий _run (и остальные патчи — фикстура переустановит)
    monkeypatch.setattr(triage, "llm_payload_sync",
                        lambda text, **kw: _payload(category="electricity"))
    monkeypatch.setattr(breaker, "is_open", lambda: False)
    monkeypatch.setattr(breaker, "record_success", lambda: None)
    out = apply_triage_sync(NUM, AI_CFG, SF)
    assert out.category == "electricity"
    assert _req(SF).category == "electricity"
    assert len(_audits(SF, AUDIT_APPLIED)) == 1


def test_clarified_before_failure_still_stops_dispatch(SF, monkeypatch, quiet):
    _seed(SF)
    _llm(monkeypatch, _payload(needs_clarification=True, clarification_question_ru="Где?",
                               clarification_question_uz="Qayerda?", category="electricity"))
    real_run = apply._run

    def flaky(sf, number, action, payload):
        if action.value == "manager_change_category":
            raise RuntimeError("boom")
        return real_run(sf, number, action, payload)

    monkeypatch.setattr(apply, "_run", flaky)
    out = apply_triage_sync(NUM, AI_CFG, SF)
    assert out.clarified is True and out.category is None
    assert _req(SF).status == C.REQUEST_STATUS_CLARIFICATION
    assert _audits(SF, AUDIT_FAILED)[0]["step"] == "category"



# ───────────── ответ жителя на вопрос ИИ ─────────────


def _ai_asked(SF):
    s = SF()
    s.add(AuditLog(user_id=None, action=AUDIT_APPLIED,
                   details={"request_number": NUM, "actor": "ai_manager", "clarified": True}))
    s.commit()
    s.close()


def test_resume_after_answer_retriages_and_returns_to_new(SF, monkeypatch, quiet):
    _seed(SF, description="что-то не работает", category="other", status=C.REQUEST_STATUS_CLARIFICATION)
    _ai_asked(SF)
    captured = _llm(monkeypatch, _payload(category="electricity", urgency="high"))
    assert apply.resume_after_answer_sync(NUM, "нет света в 3 подъезде", AI_CFG, SF) == "electricity"
    req = _req(SF)
    assert (req.status, req.category, req.urgency) == (C.REQUEST_STATUS_NEW, "electricity", "high")
    assert "что-то не работает" in captured["text"] and "нет света в 3 подъезде" in captured["text"]
    markers = _audits(SF, AUDIT_APPLIED)
    assert markers[-1]["resumed"] is True and markers[-1]["clarified"] is False
    # повторный ответ — уже не «Уточнение», ничего не делаем
    assert apply.resume_after_answer_sync(NUM, "ещё раз", AI_CFG, SF) is None


def test_resume_ignores_human_clarification(SF, monkeypatch, quiet):
    _seed(SF, status=C.REQUEST_STATUS_CLARIFICATION)  # маркера ИИ нет — спрашивал менеджер
    _llm(monkeypatch, _payload())
    assert apply.resume_after_answer_sync(NUM, "ответ", AI_CFG, SF) is None
    assert _req(SF).status == C.REQUEST_STATUS_CLARIFICATION


def test_question_for_uz_cyrl_is_transliterated():
    q = {"ru": "Что не работает?", "uz": "Nima ishlamayapti?"}
    assert apply._question_for(q, "uz") == "Nima ishlamayapti?"
    assert apply._question_for(q, "ru") == "Что не работает?"
    assert apply._question_for(q, "uz_cyrl") == "Нима ишламаяпти?"
    assert apply._question_for({"ru": "Что?", "uz": ""}, "uz_cyrl") == "Что?"


# ───────────── правила со страницы «Правила ИИ» ─────────────


def test_extra_emergency_keyword_raises_urgency_and_instructions_reach_llm(SF, monkeypatch, quiet):
    _seed(SF, description="сломался шлагбаум на въезде")
    captured = _llm(monkeypatch, None)
    apply_triage_sync(NUM, {**AI_CFG, "extra_emergency_keywords": ["шлагбаум"],
                            "triage_instructions": "Шлагбаум — срочно."}, SF)
    assert _req(SF).urgency == "critical"
    assert _audits(SF, AUDIT_APPLIED)[0]["emergency"] == "critical"
    assert captured["instructions"] == "Шлагбаум — срочно."
