"""Single source of truth: category → specialization mapping.

Категория маппится САМА В СЕБЯ везде, где канон специализаций это позволяет.
Так «что выбрал менеджер в форме» и «что вычислил диспетчер» совпадают по
построению. До единого словаря это было не так: категория `elevator` уезжала
в `maintenance`, а форма предлагала `elevator` — совпадения не было никогда.

Used by:
- services/dispatch.py (авто-dispatch новой заявки), admin-хендлеры назначения,
  api/requests/router.py (assign_to_duty), auto_manager/orchestrator.py.

⚠️ Значения ОБЯЗАНЫ входить в `CANONICAL_SPECIALIZATIONS` — это держит ратчет
`tests/test_specialization_canon.py`. Записи для КАЖДОГО канон-ключа категории
тоже обязательны: `dispatch.py` зовёт `.get()` напрямую, мимо хелпера, и на
дырке в карте молча оставляет заявку «Новая».
"""

CATEGORY_TO_SPECIALIZATION: dict[str, str] = {
    # Канон-ключи категорий (бот-меню + web/API).
    "electricity": "electrician",
    "plumbing": "plumber",
    "heating": "heating",
    "ventilation": "ventilation",
    "elevator": "elevator",
    "cleaning": "cleaning",
    "landscaping": "landscaping",
    "security": "security",
    "internet": "electrician",
    "repair": "repair",
    # «Другое» уходит к разнорабочему: раньше записи не было вовсе, и такие
    # заявки не назначались никому и никогда.
    "other": "repair",
    # Legacy Russian names (backward compatibility).
    "Сантехника": "plumber",
    "Электрика": "electrician",
    "Благоустройство": "landscaping",
    "Уборка": "cleaning",
    "Безопасность": "security",
    "Охрана": "security",
    "Ремонт": "repair",
    "Установка": "repair",
    "Обслуживание": "elevator",
    "HVAC": "heating",
    "Отопление": "heating",
    "Вентиляция": "ventilation",
    "Лифт": "elevator",
    "Интернет/ТВ": "electrician",
    "Другое": "repair",
}


def get_specialization_for_category(category: str) -> str:
    """Специализация по категории. Неизвестная категория → разнорабочий.

    Дефолт именно `repair`, а не «ничего»: незнакомая категория — это работа,
    которую всё равно кто-то должен взять, и разнорабочий тут ближе всех.
    """
    return CATEGORY_TO_SPECIALIZATION.get(category, "repair")
