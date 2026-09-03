"""Single source of truth: category → specialization mapping.

Категория маппится САМА В СЕБЯ везде, где канон специализаций это позволяет.
Так «что выбрал менеджер в форме» и «что вычислил диспетчер» совпадают по
построению. До единого словаря это было не так: категория `elevator` уезжала
в `maintenance`, а форма предлагала `elevator` — совпадения не было никогда.

Карта хранит ТОЛЬКО канон-ключи категорий (`CANONICAL_CATEGORY_KEYS`).
Legacy RU-лейблы из БД («Сантехника», «Интернет», «Инженерный разбор»)
резолвит `get_specialization_for_category` через `resolve_category_key` —
единственный публичный вход. Раньше карта вела свой legacy-список и
разъезжалась с каноном: канон знал «Интернет», карта — нет.

Used by (только через хелпер — ратчет `tests/test_category_spec_map_ratchet.py`):
- services/dispatch.py (авто-dispatch новой заявки), admin-хендлеры назначения,
  api/requests/router.py (assign_to_duty), auto_manager/orchestrator.py.

⚠️ Значения ОБЯЗАНЫ входить в `CANONICAL_SPECIALIZATIONS` — это держит ратчет
`tests/test_specialization_canon.py`; ключи обязаны совпадать с каноном
категорий в обе стороны (`constants/test_categories.py`).
"""

CATEGORY_TO_SPECIALIZATION: dict[str, str] = {
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
    # Служебная очередь InfraSafe (`alert.engineer_required`): «инженера» в
    # каноне специализаций нет, разбор берёт дежурный универсал — как «Другое».
    "engineering": "repair",
}

_DEFAULT_SPECIALIZATION = "repair"


def get_specialization_for_category(category: str) -> str:
    """Специализация по категории (канон-ключ ИЛИ legacy-лейбл).

    Неизвестная категория → разнорабочий. Дефолт именно `repair`, а не
    «ничего»: незнакомая категория — это работа, которую всё равно кто-то
    должен взять, и разнорабочий тут ближе всех.
    """
    # Ленивый импорт: keyboards.requests тянет aiogram, а константы должны
    # импортироваться без него (тот же приём, что в api/requests/schemas.py).
    from uk_management_bot.keyboards.requests import resolve_category_key

    key = resolve_category_key(category) if category else category
    return CATEGORY_TO_SPECIALIZATION.get(key, _DEFAULT_SPECIALIZATION)
