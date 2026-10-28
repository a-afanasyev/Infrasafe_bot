"""Переопределяемые тексты пингов ИИ-менеджера (services/ai_manager/templates.py).

Контракт: только простые подстановки ``{имя}`` из набора стандартного
шаблона, HTML — теги Telegram и только сбалансированные, результат после
подстановки ограничен, любой сбой переопределения → стандартный текст локали.
"""
import pytest

from uk_management_bot.services.ai_manager import templates as T


def test_keys_and_placeholders_from_locale():
    assert len(T.TEMPLATE_KEYS) == 12 and "sla.executor_overdue" in T.TEMPLATE_KEYS
    assert {"request_number", "category", "address", "hours"} <= T.placeholders("sla.executor_overdue")
    d = T.defaults()["public.assigned"]
    assert "{request_number}" in d["ru"] and "{request_number}" in d["uz"]
    assert d["placeholders"] == sorted(T.placeholders("public.assigned"))


@pytest.mark.parametrize("key", T.TEMPLATE_KEYS)
def test_ru_and_uz_defaults_share_placeholders(key):
    """Гейт локалей: набор {подстановок} в ru.json и uz.json обязан совпадать."""
    assert T.placeholders_of(T.default_text(key, "ru")) == T.placeholders_of(T.default_text(key, "uz"))


def test_validate_overrides_subset_and_simple_placeholders_only():
    ok = T.validate_overrides({"sla.auto_accepted": {"ru": "Принято: <b>№{request_number}</b>", "uz": "  "}})
    assert ok == {"sla.auto_accepted": {"ru": "Принято: <b>№{request_number}</b>"}}
    assert T.validate_overrides({}) == {} and T.validate_overrides(None) == {}
    with pytest.raises(ValueError, match="executor_name"):
        T.validate_overrides({"sla.auto_accepted": {"ru": "{executor_name}"}})
    for bad in ("{request_number:>5}", "{request_number!r}", "{}", "{0}", "{{request_number}}", "{ request_number }"):
        with pytest.raises(ValueError):
            T.validate_overrides({"sla.auto_accepted": {"ru": bad}})
    with pytest.raises(ValueError):
        T.validate_overrides({"sla.auto_accepted": "строка"})


@pytest.mark.parametrize("bad_html", [
    "<div>x</div>", "<b>x", "x</b>", "<a onclick='x'>x</a>", "<b><i>x</b></i>", "a < b", "x > y", "<br/>",
])
def test_validate_overrides_rejects_invalid_telegram_html(bad_html):
    with pytest.raises(ValueError):
        T.validate_overrides({"sla.auto_accepted": {"ru": bad_html}})


@pytest.mark.parametrize("good_html", [
    "<b>x</b>", "<i>x</i> <code>y</code>", '<a href="https://t.me/x">x</a>', "a &lt; b", "<tg-spoiler>x</tg-spoiler>",
])
def test_validate_overrides_accepts_telegram_html(good_html):
    assert T.validate_overrides({"sla.auto_accepted": {"ru": good_html}})["sla.auto_accepted"]["ru"] == good_html


def test_render_prefers_override_within_context_and_falls_back():
    kw = dict(request_number="261028-001", days=3)
    default = T.render("sla.auto_accepted", "ru", **kw)
    assert "261028-001" in default
    with T.overrides({"sla.auto_accepted": {"ru": "Авто-принято №{request_number}", "uz": "Avto: {request_number}"}}):
        assert T.render("sla.auto_accepted", "ru", **kw) == "Авто-принято №261028-001"
        assert T.render("sla.auto_accepted", "uz_cyrl", **kw) == "Avto: 261028-001"   # uz_cyrl → uz
    assert T.render("sla.auto_accepted", "ru", **kw) == default


def test_render_falls_back_to_locale_when_result_too_long():
    kw = dict(request_number="x" * 4000, days=3)
    default = T.render("sla.auto_accepted", "ru", **kw)   # без контекста = локаль
    with T.overrides({"sla.auto_accepted": {"ru": "ПЕРЕОПРЕДЕЛЕНИЕ №{request_number}"}}):
        assert T.render("sla.auto_accepted", "ru", **kw) == default   # > RENDERED_MAX → стандартный текст


def test_render_falls_back_to_locale_when_value_missing():
    with T.overrides({"sla.auto_accepted": {"ru": "ПЕРЕОПРЕДЕЛЕНИЕ №{request_number} {days}"}}):
        text = T.render("sla.auto_accepted", "ru", request_number="261028-001", days=3)
        assert text.startswith("ПЕРЕОПРЕДЕЛЕНИЕ")
        text = T.render("sla.auto_accepted", "ru", request_number="261028-001")   # days не передан
    assert "261028-001" in text and "ПЕРЕОПРЕДЕЛЕНИЕ" not in text   # локаль, не KeyError
