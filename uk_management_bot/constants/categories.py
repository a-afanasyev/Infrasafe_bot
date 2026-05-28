"""
Single source of truth: category → specialization mapping.

Used by:
- admin.py: auto_assign_request_by_category, assign specific executor
"""

CATEGORY_TO_SPECIALIZATION: dict[str, str] = {
    # Internal keys (new format)
    "plumbing": "plumber",
    "electricity": "electrician",
    "landscaping": "landscaping",
    "cleaning": "cleaning",
    "security": "security",
    "hvac": "hvac",
    "maintenance": "maintenance",
    "repair": "repair",
    "installation": "installation",
    # Legacy Russian names (backward compatibility)
    "Сантехника": "plumber",
    "Электрика": "electrician",
    "Благоустройство": "landscaping",
    "Уборка": "cleaning",
    "Безопасность": "security",
    "Охрана": "security",
    "Ремонт": "repair",
    "Установка": "installation",
    "Обслуживание": "maintenance",
    "HVAC": "hvac",
    "Отопление": "hvac",
    "Вентиляция": "hvac",
    "Лифт": "maintenance",
    "Интернет/ТВ": "electrician",
}


def get_specialization_for_category(category: str) -> str:
    """Return specialization for a category key, defaulting to 'other'."""
    return CATEGORY_TO_SPECIALIZATION.get(category, "other")
