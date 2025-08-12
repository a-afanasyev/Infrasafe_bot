from uk_management_bot.utils.helpers import get_text


def test_get_text_ru_basic():
    text = get_text("roles.executor", language="ru")
    assert isinstance(text, str)
    assert "Сотрудник" in text


def test_get_text_uz_basic():
    text = get_text("roles.manager", language="uz")
    assert isinstance(text, str)
    assert "Menejer" in text


def test_get_text_fallback_to_ru_for_unknown_language():
    # Язык 'kk' не поддерживается → должен сработать фолбэк на RU
    text = get_text("role.switched", language="kk")
    # В RU ключ существует и содержит русское слово "Режим"
    assert isinstance(text, str)
    assert "Режим" in text


def test_get_text_with_placeholder():
    # Проверяем подстановку плейсхолдера {role}
    role_name = get_text("roles.executor", language="ru")
    text = get_text("role.switched_notify", language="ru", role=role_name)
    assert role_name in text


