"""PR-17 — address-кластер: BUG-028 / REFACTOR-032 / 088 / 089.

BUG-028 (уже выполнен ARCH-014): нет `except Exception`, инфра-ошибки →
logger.exception + opaque message, доменные (AddressError) → их текст. Тут —
regression-guard, чтобы широкий except / schema-leak не вернулись.
REFACTOR-032: нет eager f-string логов. REFACTOR-088: Optional-аннотация.
REFACTOR-089: UserApartmentStatus(str, Enum) — wire-совместим.
"""
import inspect
import re
import typing

from uk_management_bot.services import address_service as svc
from uk_management_bot.database.models.user_apartment import (
    UserApartment, UserApartmentStatus,
)


# ---------------------------------------------------------------------------
# BUG-028 — regression guard (ARCH-014 уже закрыл по сути)
# ---------------------------------------------------------------------------

class TestBug028NoBroadExceptOrLeak:
    def test_no_bare_except_exception(self):
        src = inspect.getsource(svc)
        assert "except Exception" not in src, "широкий except вернулся — BUG-028"

    def test_infra_errors_return_opaque_message(self):
        """SQLAlchemyError-ветки логируют traceback и отдают generic-текст,
        НЕ str(e) (без утечки схемы)."""
        src = inspect.getsource(svc)
        # каждая SQLAlchemyError-ветка должна звать logger.exception
        assert src.count("except SQLAlchemyError") >= 1
        assert src.count("logger.exception") >= src.count("except SQLAlchemyError")
        # generic user-facing message присутствует
        assert "Попробуйте позже" in src


# ---------------------------------------------------------------------------
# REFACTOR-032 — lazy logging (no eager f-strings)
# ---------------------------------------------------------------------------

class TestRefactor032LazyLogging:
    def test_no_fstring_logger_calls(self):
        src = inspect.getsource(svc)
        assert not re.search(r"logger\.(error|warning|info|exception|debug)\(f[\"']", src), \
            "eager f-string в логере — REFACTOR-032"

    def test_no_user_names_in_logs(self):
        """PII: имена (first_name/last_name) не должны форматироваться в логи."""
        src = inspect.getsource(svc)
        for line in src.splitlines():
            if "logger." in line:
                assert "first_name" not in line and "last_name" not in line


# ---------------------------------------------------------------------------
# REFACTOR-088 — Optional annotation
# ---------------------------------------------------------------------------

class TestRefactor088Optional:
    def test_add_user_yard_comment_is_optional(self):
        sig = inspect.signature(svc.AddressService.add_user_yard)
        ann = sig.parameters["comment"].annotation
        assert ann == typing.Optional[str], f"comment annotation = {ann!r}"


# ---------------------------------------------------------------------------
# REFACTOR-089 — UserApartmentStatus enum, wire-compatible
# ---------------------------------------------------------------------------

class TestRefactor089StatusEnum:
    def test_enum_values_match_wire_strings(self):
        assert UserApartmentStatus.PENDING.value == "pending"
        assert UserApartmentStatus.APPROVED.value == "approved"
        assert UserApartmentStatus.REJECTED.value == "rejected"

    def test_enum_is_str_subclass_equal_to_string(self):
        # str-подкласс → == с обычной строкой True (важно для SQLAlchemy-биндинга)
        assert UserApartmentStatus.APPROVED == "approved"
        assert isinstance(UserApartmentStatus.APPROVED, str)

    def test_model_helpers_use_enum(self):
        ua = UserApartment(user_id=1, apartment_id=1, status=UserApartmentStatus.APPROVED.value)
        assert ua.is_approved is True
        assert ua.is_pending is False
        ua.reject(reviewer_id=9, comment="нет")
        assert ua.status == "rejected"
        assert ua.is_rejected is True

    def test_reject_approve_comment_optional(self):
        for meth in (UserApartment.approve, UserApartment.reject):
            ann = inspect.signature(meth).parameters["comment"].annotation
            assert ann == typing.Optional[str]
