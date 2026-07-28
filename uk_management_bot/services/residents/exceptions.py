"""Доменные исключения раздела «Жители».

Зеркало `services/addresses/exceptions.py`: сервис-слой бросает доменную
ошибку, а не HTTPException (services не должен зависеть от api/), а
`api/residents/exception_handlers.py` мапит её в HTTP-статус.
"""


class ResidentError(Exception):
    """База доменных ошибок раздела «Жители»."""

    def __init__(self, message: str = "", code: str | None = None):
        super().__init__(message)
        self.code = code


class ResidentNotFound(ResidentError):
    """Житель (или вложенный ресурс: привязка, документ) не найден.

    Сюда же попадает «пользователь существует, но не житель» и
    «soft-deleted» — снаружи раздела такой пользователь неотличим от
    отсутствующего, и раскрывать разницу незачем.
    """


class ResidentConflict(ResidentError):
    """Операция нарушает инвариант домена (недопустимый переход статуса и т.п.)."""


class ResidentValidationError(ResidentError):
    """Входные данные некорректны."""
