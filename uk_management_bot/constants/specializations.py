"""Единый словарь специализаций исполнителей.

Словарей было семь, и главное — набор формы выдачи приглашений почти не
пересекался с тем, что вычисляет диспетчер: менеджер выбирал «Лифт» (ключ
КАТЕГОРИИ), а `CATEGORY_TO_SPECIALIZATION` для категории `elevator` отдавал
`maintenance`. Строгое сравнение в `rule_engine` не совпадало никогда, и
лифтовые заявки назначались только вручную.

Канон — набор формы: девять человекопонятных позиций. Категория маппится сама
в себя везде, где возможно, поэтому «что выбрал менеджер» и «что вычислил
диспетчер» совпадают по построению, а не по договорённости.
"""

from __future__ import annotations

# Порядок значим: в этом же порядке позиции показываются в формах.
CANONICAL_SPECIALIZATIONS: tuple[str, ...] = (
    "electrician",   # ⚡ Электрика
    "plumber",       # 🔧 Сантехника
    "heating",       # 🔥 Отопление
    "ventilation",   # 💨 Вентиляция
    "elevator",      # 🛗 Лифт
    "cleaning",      # 🧹 Уборка
    "security",      # 🔒 Безопасность
    "landscaping",   # 🌳 Благоустройство
    "repair",        # 🔨 Ремонт / разнорабочий
)

CANONICAL_SET = frozenset(CANONICAL_SPECIALIZATIONS)

# Wildcard смены/шаблона: «ограничений нет». Не навык, поэтому вне канона —
# исполнителю его не выдают, в формах он не показывается.
UNIVERSAL_SPECIALIZATION = "universal"

# Legacy → канон. Значения — множества: один устаревший токен может покрывать
# два современных (см. `hvac`).
SPECIALIZATION_ALIASES: dict[str, frozenset[str]] = {
    # Старые ключи из utils/constants.py и сид-шаблонов.
    "electric": frozenset({"electrician"}),
    "plumbing": frozenset({"plumber"}),
    "patrol": frozenset({"security"}),
    # «Отопление/вентиляция» одним токеном — разворачивается в две позиции.
    "hvac": frozenset({"heating", "ventilation"}),
    # Решение владельца: техобслуживание — это про лифты.
    "maintenance": frozenset({"elevator"}),
    # Разнорабочий и есть «Ремонт»: общие работы, установка, аварийка и всё,
    # что не попало в конкретную специализацию.
    "general": frozenset({"repair"}),
    "installation": frozenset({"repair"}),
    "emergency": frozenset({"repair"}),
    "other": frozenset({"repair"}),
    # Ключи КАТЕГОРИЙ, просочившиеся в поле специализации (тот же класс, что
    # и `elevator`): резолвим их так же, как их резолвит диспетчер.
    "electricity": frozenset({"electrician"}),
    "internet": frozenset({"electrician"}),
}

# Какой из нескольких вариантов берём, когда токен нельзя развернуть в два
# значения (скалярные поля и сторона «требуется» — см. normalize_specialization).
_COLLAPSE_TO: dict[str, str] = {
    "hvac": "heating",
}


def normalize_specialization(value: object, *, side: str = "have") -> set[str]:
    """Привести значение к канону.

    Args:
        value: сырой токен из БД/формы (регистр и пробелы не важны).
        side: ``"have"`` — набор навыков исполнителя, ``"need"`` — требование
            смены/шаблона либо скалярное group-поле.

    Асимметрия обязательна. Списки играют две разные роли, и `hvac` —
    единственный токен, который сталкивает их лбами: расширение в «умею»
    безопасно всегда (навыков становится больше), а в «требуется» — наоборот
    СУЖАЕТ пул, потому что проверка соответствия требует ВСЕ значения
    (`has_required_specs` → `issubset`). Смена, требовавшая `hvac`, начала бы
    требовать отопление И вентиляцию одновременно.

    Returns:
        Множество канон-значений; пустое — если токен неизвестен (осознанно:
        мусор не должен превращаться в случайную специализацию).
    """
    if not isinstance(value, str):
        return set()
    token = value.strip().lower()
    if not token:
        return set()
    if token in CANONICAL_SET:
        return {token}
    resolved = SPECIALIZATION_ALIASES.get(token)
    if resolved is None:
        return set()
    if side == "need" and token in _COLLAPSE_TO:
        return {_COLLAPSE_TO[token]}
    return set(resolved)


def is_canonical(value: str) -> bool:
    return value in CANONICAL_SET
