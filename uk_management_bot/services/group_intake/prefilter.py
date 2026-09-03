"""Эвристический префильтр Group Intake — дешёвый отсев ДО LLM.

Чистая функция без I/O. Решает одно: стоит ли звать LLM-классификатор.
Инварианты:
- текст короче 10 символов НИКОГДА не проходит (гарантия для
  ``Validator.validate_description`` в save_request-пути) — даже если
  содержит словарный маркер;
- команды и «голые ссылки» не проходят;
- дальше пропуск по любому из признаков: словарный маркер проблемы (ru/uz),
  достаточная длина, фото с содержательной подписью.

Словарь маркеров — намеренно широкий и дешёвый: он не решает «заявка ли это»
(это работа LLM), а лишь отсекает явную болтовню.
"""
import re

from uk_management_bot.services.group_intake.category_keywords import guess_category

# Минимальная длина описания заявки (= Validator.validate_description).
MIN_TEXT_LEN = 10
# Достаточно длинный текст пропускается и без словарного маркера.
LONG_TEXT_LEN = 25

# Текст, состоящий из одной ссылки (± мусор вокруг до пары символов).
_LINK_ONLY_RE = re.compile(r"^\W*(?:https?://|t\.me/|www\.)\S+\W*$", re.IGNORECASE)

# Маркеры проблем: русский + узбекский (латиница). Подстрочное совпадение
# по нижнему регистру — стемминга достаточно на уровне усечённых основ.
_MARKERS = (
    # ru — глаголы/состояния
    "не работает", "не горит", "не греет", "не едет", "не открыва",
    "сломал", "слома", "теч", "течёт", "протек", "прорва", "затопи",
    "капает", "залив", "засор", "забил", "воняет", "запах",
    "искрит", "коротит", "отключ", "пропал", "нет света", "нет воды",
    "нет отоплен", "нет газа", "холодн", "мусор", "грязн", "разбит",
    "трещин", "дыра", "упал", "шум", "авари",
    # ru — объекты
    "лифт", "стояк", "подъезд", "подвал", "крыша", "кровл",
    "канализац", "труб", "батаре", "отоплен", "розетк", "провод",
    "домофон", "дверь", "окно", "кран", "унитаз", "счетчик", "счётчик",
    # uz (latin)
    "ishlamayapti", "ishlamaydi", "buzildi", "buzilgan", "oqyapti",
    "oqmoqda", "to'kil", "tushib", "hidi", "suv yo'q", "svet yo'q",
    "chiroq", "lift", "kanalizatsiya", "quvur", "isitish", "axlat",
    "chiqindi", "eshik", "deraza", "jo'mrak", "hojatxona",
)


def prefilter(text: str, has_photo: bool) -> bool:
    """True — кандидат, зовём LLM; False — точно не заявка, тишина."""
    stripped = (text or "").strip()
    if len(stripped) < MIN_TEXT_LEN:
        return False

    lowered = stripped.lower()
    if lowered.startswith("/"):
        return False
    if _LINK_ONLY_RE.match(stripped):
        return False

    if any(marker in lowered for marker in _MARKERS):
        return True
    # Ключевое слово категории — тоже сигнал заявки: короткие «25v poliv
    # yoqilsin» / «20v elektrik kerak» без маркеров проблемы и короче
    # LONG_TEXT_LEN резались здесь и до LLM не доходили (прод, 2026-09).
    if guess_category(stripped) is not None:
        return True
    if len(stripped) >= LONG_TEXT_LEN:
        return True
    if has_photo:
        # Фото с содержательной подписью (>=10 симв. — уже гарантировано выше).
        return True
    return False
