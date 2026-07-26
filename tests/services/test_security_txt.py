"""PENT-F14 — контракт публикуемого `security.txt` (RFC 9116).

До 2026-07-26 `/.well-known/security.txt` на проде отдавал `200` с HTML-страницей
(SPA-заглушка корневого сайта). Владелец выбрал публикацию настоящего файла;
артефакт лежит в `docs/security/security.txt` и публикуется дословно.

Гейт держит три вещи, каждая из которых уже ломалась в подобных файлах у других:

* **обязательные поля** `Contact` и `Expires` — без них файл невалиден по спеке,
  а невалидный `security.txt` ничем не лучше SPA-заглушки;
* **срок не протух** — RFC 9116 §2.5.5 прямо говорит: файл с истёкшим `Expires`
  считать недействительным. Тест падает **за 30 дней до** срока, чтобы
  напоминание пришло в единственный момент, когда оно полезно;
* **это не HTML** — ровно та подмена, из-за которой пункт и появился.
"""
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

SECURITY_TXT = Path(__file__).resolve().parents[2] / "docs/security/security.txt"
RENEW_WINDOW = timedelta(days=30)


@pytest.fixture(scope="module")
def content() -> str:
    assert SECURITY_TXT.exists(), (
        f"нет артефакта {SECURITY_TXT}: файл публикуется дословно, "
        "значит он обязан существовать в репозитории"
    )
    return SECURITY_TXT.read_text(encoding="utf-8")


def _field(content: str, name: str) -> list[str]:
    """Значения поля. RFC 9116: имя поля регистро-независимо, полей может быть много."""
    return [
        m.group(1).strip()
        for m in re.finditer(rf"^{name}:\s*(.+)$", content, re.I | re.M)
    ]


def test_contact_present_and_is_uri(content: str):
    contacts = _field(content, "Contact")
    assert contacts, "поле Contact обязательно (RFC 9116 §2.5.3)"
    for c in contacts:
        assert re.match(r"^(https://|mailto:|tel:)", c), (
            f"Contact должен быть URI, а не свободным текстом: {c!r}"
        )


def test_expires_present_parseable_and_not_near_expiry(content: str):
    values = _field(content, "Expires")
    assert len(values) == 1, "Expires обязателен и должен быть ровно один (RFC 9116 §2.5.5)"

    raw = values[0]
    expires = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    assert expires.tzinfo is not None, f"Expires обязан быть с таймзоной: {raw!r}"

    now = datetime.now(timezone.utc)
    assert expires > now, (
        f"security.txt просрочен ({raw}) — по RFC его следует считать "
        "недействительным. Продлить: обновить Expires в docs/security/security.txt "
        "и опубликовать файл заново по чек-листу "
        "docs/audit/2026-07-26-pent-f14-owner-checklist.md"
    )
    assert expires - now > RENEW_WINDOW, (
        f"до истечения security.txt меньше {RENEW_WINDOW.days} дней ({raw}). "
        "Это не поломка теста, а напоминание: продлить Expires и переопубликовать файл."
    )


def test_expires_window_is_under_a_year(content: str):
    """RFC рекомендует срок меньше года — «выставил и забыл» здесь не работает."""
    expires = datetime.fromisoformat(_field(content, "Expires")[0].replace("Z", "+00:00"))
    assert expires - datetime.now(timezone.utc) < timedelta(days=366)


def test_canonical_covers_both_published_domains(content: str):
    """Файл один на два домена — оба обязаны быть в Canonical, иначе на одном из
    них он формально не свой (RFC 9116 §2.5.2)."""
    canonical = _field(content, "Canonical")
    assert "https://profk.uz/.well-known/security.txt" in canonical
    assert "https://infrasafe.uz/.well-known/security.txt" in canonical


def test_is_plain_text_not_html(content: str):
    lowered = content.lower()
    for marker in ("<!doctype", "<html", "<head", "<script", "index.html"):
        assert marker not in lowered, (
            f"HTML-маркер {marker!r} в security.txt — это ровно та подмена "
            "(SPA-заглушка вместо файла), из-за которой пункт и появился"
        )
