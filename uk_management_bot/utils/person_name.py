"""ФИО одной строкой — канон нормализации, валидации и раскладки по колонкам.

В системе ФИО вводится ОДНОЙ строкой (регистрация жителя через TWA —
``api/registration/router.py``; редактирование сотрудника менеджером в боте), а
хранится ДВУМЯ колонками ``users.first_name`` / ``users.last_name``. Правило
раскладки «первое слово → first_name, весь остаток → last_name» родилось в
регистрации и было скопировано в бота; показ (``utils/user_names.full_name``)
склеивает колонки обратно через пробел, поэтому пользователь видит ровно ту
строку, которую ввёл. Тождество «разложить → склеить» пиннится тестом.

Колонки НЕ несут семантику «имя» и «фамилия»: разложить «Иванов Иван Иванович»
на настоящие имя и фамилию нельзя, не зная порядка, а порядок вводящий выбирает
сам. Правило раскладки существует только ради двух исторических колонок — не
опирайтесь на него как на «в first_name лежит имя».

Нормализация выбрасывает невидимые символы (ZWSP, RLO и прочая категория C)
намеренно: подпись кнопки и текст уведомления с ними выглядят как чужое имя, а
на глаз отличить нельзя.
"""
from __future__ import annotations

import unicodedata

#: Предел длины ВСЕЙ строки ФИО. Одно слово целиком уходит в `first_name`,
#: поэтому лимит обязан быть заметно меньше `String(255)` обеих колонок.
MAX_FULL_NAME_LEN = 200


class InvalidFullName(ValueError):
    """Введённое ФИО не проходит валидацию.

    `code` — машинный повод (`empty` | `no_letters` | `too_long`), по нему
    вызывающий выбирает локализованный текст; сообщение исключения остаётся
    техническим и в UI не показывается.
    """

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


def normalize_full_name(raw) -> str:
    """Схлопнуть пробельное, выбросить невидимое, обрезать края.

    Не строка (None, число) — пустой результат: валидация отвергнет его как
    `empty`, и это честнее, чем str() над чем попало.
    """
    if not isinstance(raw, str):
        return ""
    chars = []
    for ch in raw:
        if ch.isspace():
            chars.append(" ")
            continue
        # Категория C — управляющие, форматирующие (ZWSP/RLO/LRO), суррогаты,
        # приватные и неназначенные. Ни одна из них не часть имени.
        if unicodedata.category(ch).startswith("C"):
            continue
        chars.append(ch)
    return " ".join("".join(chars).split())


def validate_full_name(raw) -> str:
    """Нормализованное ФИО или `InvalidFullName` с машинным `code`."""
    value = normalize_full_name(raw)
    if not value:
        raise InvalidFullName("empty", "full name must not be blank")
    if len(value) > MAX_FULL_NAME_LEN:
        raise InvalidFullName("too_long", f"full name exceeds {MAX_FULL_NAME_LEN} characters")
    if not any(ch.isalpha() for ch in value):
        raise InvalidFullName("no_letters", "full name must contain at least one letter")
    return value


def split_full_name(full: str) -> tuple[str, str | None]:
    """«Иванов Иван Иванович» → ("Иванов", "Иван Иванович").

    Хвост пустой → `None`, а не `""`: колонка nullable, и `None` — то же
    «имени нет», что у пользователя, который фамилию не вводил вовсе.
    """
    parts = full.split()
    if not parts:
        return "", None
    return parts[0], (" ".join(parts[1:]) or None)
