"""Публичный код лифта — идентификатор публичной страницы (``elevators.public_code``).

Непредсказуемый (``secrets``), без последовательности; URL-safe алфавит.
"""

import re
import secrets

# Ширина колонки ``elevators.public_code`` (String(32))
PUBLIC_CODE_MAX_LEN = 32
# Минимум для валидности: ~96 бит энтропии, отсекает мусор в URL
PUBLIC_CODE_MIN_LEN = 16
# token_urlsafe(16) → 22 символа; алфавит base64url без паддинга
_TOKEN_BYTES = 16
_PUBLIC_CODE_RE = re.compile(
    rf"^[A-Za-z0-9_-]{{{PUBLIC_CODE_MIN_LEN},{PUBLIC_CODE_MAX_LEN}}}$"
)


def generate_public_code() -> str:
    """Случайный код ``[A-Za-z0-9_-]`` длиной 16..32 (фактически 22)."""
    # Срез — страховка при смене _TOKEN_BYTES: код не должен превысить
    # ширину колонки elevators.public_code (String(32)).
    return secrets.token_urlsafe(_TOKEN_BYTES)[:PUBLIC_CODE_MAX_LEN]


def is_valid_public_code(code: str) -> bool:
    """Формат кода: строка из ``[A-Za-z0-9_-]`` длиной 16..32."""
    return isinstance(code, str) and _PUBLIC_CODE_RE.fullmatch(code) is not None
