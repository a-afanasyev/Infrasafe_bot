"""ARCH-107: graceful-ротация JWT_SECRET через `kid` + набор {primary, next}.

Сценарии повторяют фазы процедуры ротации (uk-deploy SKILL.md):
  steady   — только primary (OLD);
  window   — NEXT=NEW добавлен, подписант ещё на OLD (флаг off);
  flip     — JWT_USE_NEXT_SECRET=true, подписант на NEW, верификатор держит оба;
  finalize — NEW перенесён в primary, NEXT очищен, флаг снят.

Ключевые инварианты AC:
  * токен, подписанный OLD, живёт через window и flip (нет force-logout);
  * после finalize OLD-токены отклоняются;
  * токены эпохи flip (kid="next", подпись NEW) живут и после finalize,
    когда их ключ уже числится как "primary";
  * токены без `kid` (выпущенные до раската ARCH-107) верифицируются.

Настройки читаются сервисом лениво — тесты просто мутируют service.SECRET_KEY
и service.settings через monkeypatch, без reload модуля.
"""
from datetime import datetime, timedelta, timezone

from jose import jwt as jose_jwt

from uk_management_bot.api.auth import service
from uk_management_bot.api.registration import tickets

OLD = "old-jwt-secret-0123456789abcdef0123456789abcdef"
NEW = "new-jwt-secret-fedcba9876543210fedcba9876543210"


def _phase(monkeypatch, *, primary: str, next_key: str, use_next: bool) -> None:
    monkeypatch.setattr(service, "SECRET_KEY", primary)
    monkeypatch.setattr(service.settings, "JWT_SECRET_NEXT", next_key, raising=False)
    monkeypatch.setattr(service.settings, "JWT_USE_NEXT_SECRET", use_next, raising=False)


def steady(mp):
    _phase(mp, primary=OLD, next_key="", use_next=False)


def window(mp):
    _phase(mp, primary=OLD, next_key=NEW, use_next=False)


def flip(mp):
    _phase(mp, primary=OLD, next_key=NEW, use_next=True)


def finalize(mp):
    _phase(mp, primary=NEW, next_key="", use_next=False)


def _future_exp() -> datetime:
    return datetime.now(timezone.utc) + timedelta(minutes=5)


def _raw_token(key: str, kid: str | None, **claims) -> str:
    payload = {"sub": "7", "roles": ["applicant"], "exp": _future_exp(), **claims}
    headers = {"kid": kid} if kid is not None else None
    return jose_jwt.encode(payload, key, algorithm="HS256", headers=headers)


class TestSigningKid:
    def test_steady_signs_with_primary_kid(self, monkeypatch):
        steady(monkeypatch)
        token = service.create_access_token(7, ["applicant"])
        assert jose_jwt.get_unverified_header(token)["kid"] == "primary"
        assert service.verify_access_token(token)["sub"] == "7"

    def test_window_still_signs_with_primary(self, monkeypatch):
        window(monkeypatch)
        token = service.create_access_token(7, ["applicant"])
        assert jose_jwt.get_unverified_header(token)["kid"] == "primary"

    def test_flip_signs_with_next(self, monkeypatch):
        flip(monkeypatch)
        token = service.create_access_token(7, ["applicant"])
        assert jose_jwt.get_unverified_header(token)["kid"] == "next"
        assert service.verify_access_token(token)["sub"] == "7"


class TestRotationGrace:
    def test_old_token_survives_window_and_flip(self, monkeypatch):
        """AC: токен, подписанный OLD, продолжает проходить verify всю ротацию."""
        steady(monkeypatch)
        token = service.create_access_token(7, ["applicant"])
        window(monkeypatch)
        assert service.verify_access_token(token) is not None
        flip(monkeypatch)
        assert service.verify_access_token(token) is not None

    def test_next_signed_token_accepted_before_flip(self, monkeypatch):
        """Окно открыто, флаг ещё off (другой узел уже мог флипнуться)."""
        window(monkeypatch)
        assert service.verify_access_token(_raw_token(NEW, "next")) is not None

    def test_old_token_rejected_after_finalize(self, monkeypatch):
        """AC: после полной ротации (OLD удалён) старые токены отклоняются."""
        steady(monkeypatch)
        token = service.create_access_token(7, ["applicant"])
        finalize(monkeypatch)
        assert service.verify_access_token(token) is None

    def test_flip_era_token_survives_finalize(self, monkeypatch):
        """kid="next", но его ключ теперь числится primary — верификатор обязан
        перебрать весь набор, а не верить kid буквально."""
        flip(monkeypatch)
        token = service.create_access_token(7, ["applicant"])
        assert jose_jwt.get_unverified_header(token)["kid"] == "next"
        finalize(monkeypatch)
        assert service.verify_access_token(token) is not None


class TestTokenPopulations:
    def test_legacy_token_without_kid_verifies(self, monkeypatch):
        """Токены, выпущенные до раската ARCH-107, не несут kid вовсе."""
        window(monkeypatch)
        assert service.verify_access_token(_raw_token(OLD, None)) is not None
        assert service.verify_access_token(_raw_token(NEW, None)) is not None

    def test_unknown_kid_falls_back_to_key_set(self, monkeypatch):
        window(monkeypatch)
        assert service.verify_access_token(_raw_token(OLD, "wat")) is not None

    def test_foreign_key_rejected_regardless_of_kid(self, monkeypatch):
        window(monkeypatch)
        forged = _raw_token("attacker-key-0123456789abcdef0123456789ab", "primary")
        assert service.verify_access_token(forged) is None

    def test_expired_token_rejected_mid_window(self, monkeypatch):
        window(monkeypatch)
        expired = jose_jwt.encode(
            {"sub": "7", "roles": [], "exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
            OLD, algorithm="HS256", headers={"kid": "primary"},
        )
        assert service.verify_access_token(expired) is None

    def test_purpose_scoped_token_still_rejected_as_access(self, monkeypatch):
        """SEC-01 не размывается ротацией: mfa-токен не проходит как access ни
        под одним ключом набора."""
        flip(monkeypatch)
        mfa = service.create_mfa_token(7)
        assert service.verify_access_token(mfa) is None

    def test_malformed_token_returns_none(self, monkeypatch):
        window(monkeypatch)
        assert service.verify_access_token("not.a.jwt") is None


class TestPurposeTokensRotate:
    def test_mfa_token_survives_flip(self, monkeypatch):
        steady(monkeypatch)
        token = service.create_mfa_token(42)
        flip(monkeypatch)
        assert service.verify_mfa_token(token) == 42

    def test_registration_ticket_survives_flip(self, monkeypatch):
        steady(monkeypatch)
        ticket = tickets.create_registration_ticket(99001)
        flip(monkeypatch)
        assert tickets.verify_registration_ticket(ticket) == 99001

    def test_registration_ticket_rejected_after_finalize(self, monkeypatch):
        steady(monkeypatch)
        ticket = tickets.create_registration_ticket(99001)
        finalize(monkeypatch)
        assert tickets.verify_registration_ticket(ticket) is None
