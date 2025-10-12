"""
HTTP исключения для Media Service с кодами ошибок
"""

from typing import Any, Dict, Optional
from fastapi import HTTPException, status
from .error_codes import MediaErrorCode, MediaError, MediaErrorMessages


class MediaHTTPException(HTTPException):
    """HTTP исключение с кодом ошибки Media Service"""
    
    def __init__(
        self,
        error_code: MediaErrorCode,
        status_code: int,
        message: Optional[str] = None,
        details: Any = None,
        language: str = "ru"
    ):
        self.error_code = error_code
        self.details = details
        self.language = language
        
        # Получаем сообщение об ошибке
        error_message = message or MediaErrorMessages.get_message(error_code, language)
        error_description = MediaErrorMessages.get_description(error_code)
        
        # Формируем детали ошибки
        error_details = {
            "error_code": error_code.value,
            "message": error_message,
            "description": error_description,
            "category": MediaErrorMessages._get_category(error_code)
        }
        
        if details is not None:
            error_details["details"] = details
        
        super().__init__(status_code=status_code, detail=error_details)


# === ПРЕДОПРЕДЕЛЕННЫЕ ИСКЛЮЧЕНИЯ ===

class InternalServerError(MediaHTTPException):
    """Внутренняя ошибка сервера"""
    def __init__(self, details: Any = None, language: str = "ru"):
        super().__init__(
            error_code=MediaErrorCode.INTERNAL_SERVER_ERROR,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            details=details,
            language=language
        )


class ValidationError(MediaHTTPException):
    """Ошибка валидации данных"""
    def __init__(self, details: Any = None, language: str = "ru"):
        super().__init__(
            error_code=MediaErrorCode.VALIDATION_ERROR,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details=details,
            language=language
        )


class PermissionDenied(MediaHTTPException):
    """Доступ запрещен"""
    def __init__(self, details: Any = None, language: str = "ru"):
        super().__init__(
            error_code=MediaErrorCode.PERMISSION_DENIED,
            status_code=status.HTTP_403_FORBIDDEN,
            details=details,
            language=language
        )


class ResourceNotFound(MediaHTTPException):
    """Ресурс не найден"""
    def __init__(self, details: Any = None, language: str = "ru"):
        super().__init__(
            error_code=MediaErrorCode.RESOURCE_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
            details=details,
            language=language
        )


class RateLimitExceeded(MediaHTTPException):
    """Превышен лимит запросов"""
    def __init__(self, details: Any = None, language: str = "ru"):
        super().__init__(
            error_code=MediaErrorCode.RATE_LIMIT_EXCEEDED,
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            details=details,
            language=language
        )


class FileUploadFailed(MediaHTTPException):
    """Ошибка загрузки файла"""
    def __init__(self, details: Any = None, language: str = "ru"):
        super().__init__(
            error_code=MediaErrorCode.FILE_UPLOAD_FAILED,
            status_code=status.HTTP_400_BAD_REQUEST,
            details=details,
            language=language
        )


class InvalidFileType(MediaHTTPException):
    """Неподдерживаемый тип файла"""
    def __init__(self, details: Any = None, language: str = "ru"):
        super().__init__(
            error_code=MediaErrorCode.INVALID_FILE_TYPE,
            status_code=status.HTTP_400_BAD_REQUEST,
            details=details,
            language=language
        )


class FileTooLarge(MediaHTTPException):
    """Файл слишком большой"""
    def __init__(self, details: Any = None, language: str = "ru"):
        super().__init__(
            error_code=MediaErrorCode.FILE_TOO_LARGE,
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            details=details,
            language=language
        )


class TelegramUploadFailed(MediaHTTPException):
    """Ошибка загрузки в Telegram"""
    def __init__(self, details: Any = None, language: str = "ru"):
        super().__init__(
            error_code=MediaErrorCode.TELEGRAM_UPLOAD_FAILED,
            status_code=status.HTTP_502_BAD_GATEWAY,
            details=details,
            language=language
        )


class TelegramAPIError(MediaHTTPException):
    """Ошибка API Telegram"""
    def __init__(self, details: Any = None, language: str = "ru"):
        super().__init__(
            error_code=MediaErrorCode.TELEGRAM_API_ERROR,
            status_code=status.HTTP_502_BAD_GATEWAY,
            details=details,
            language=language
        )


class DatabaseError(MediaHTTPException):
    """Ошибка базы данных"""
    def __init__(self, details: Any = None, language: str = "ru"):
        super().__init__(
            error_code=MediaErrorCode.DATABASE_QUERY_ERROR,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            details=details,
            language=language
        )


class DuplicateRecordError(MediaHTTPException):
    """Дублирующаяся запись"""
    def __init__(self, details: Any = None, language: str = "ru"):
        super().__init__(
            error_code=MediaErrorCode.DUPLICATE_RECORD,
            status_code=status.HTTP_409_CONFLICT,
            details=details,
            language=language
        )


class DuplicateFileDetected(MediaHTTPException):
    """Обнаружен дубликат файла"""
    def __init__(self, details: Any = None, language: str = "ru"):
        super().__init__(
            error_code=MediaErrorCode.DUPLICATE_FILE_DETECTED,
            status_code=status.HTTP_409_CONFLICT,
            details=details,
            language=language
        )


class DuplicatePolicyViolation(MediaHTTPException):
    """Нарушение политики дубликатов"""
    def __init__(self, details: Any = None, language: str = "ru"):
        super().__init__(
            error_code=MediaErrorCode.DUPLICATE_POLICY_VIOLATION,
            status_code=status.HTTP_409_CONFLICT,
            details=details,
            language=language
        )


class InvalidSearchQuery(MediaHTTPException):
    """Некорректный поисковый запрос"""
    def __init__(self, details: Any = None, language: str = "ru"):
        super().__init__(
            error_code=MediaErrorCode.INVALID_SEARCH_QUERY,
            status_code=status.HTTP_400_BAD_REQUEST,
            details=details,
            language=language
        )


class Unauthorized(MediaHTTPException):
    """Не авторизован"""
    def __init__(self, details: Any = None, language: str = "ru"):
        super().__init__(
            error_code=MediaErrorCode.UNAUTHORIZED,
            status_code=status.HTTP_401_UNAUTHORIZED,
            details=details,
            language=language
        )


class ServiceUnavailable(MediaHTTPException):
    """Сервис недоступен"""
    def __init__(self, details: Any = None, language: str = "ru"):
        super().__init__(
            error_code=MediaErrorCode.SERVICE_UNAVAILABLE,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            details=details,
            language=language
        )


# === УТИЛИТЫ ДЛЯ СОЗДАНИЯ ОШИБОК ===

def create_http_error(
    error_code: MediaErrorCode,
    status_code: int,
    details: Any = None,
    language: str = "ru"
) -> MediaHTTPException:
    """Создать HTTP исключение с кодом ошибки"""
    return MediaHTTPException(
        error_code=error_code,
        status_code=status_code,
        details=details,
        language=language
    )


def handle_media_error(error: MediaError) -> MediaHTTPException:
    """Преобразовать MediaError в MediaHTTPException"""
    # Определяем статус код на основе типа ошибки
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    
    if error.error_code in [
        MediaErrorCode.VALIDATION_ERROR,
        MediaErrorCode.INVALID_FILE_TYPE,
        MediaErrorCode.FILE_TOO_LARGE,
        MediaErrorCode.INVALID_SEARCH_QUERY
    ]:
        status_code = status.HTTP_400_BAD_REQUEST
    elif error.error_code in [
        MediaErrorCode.RESOURCE_NOT_FOUND,
        MediaErrorCode.FILE_NOT_FOUND
    ]:
        status_code = status.HTTP_404_NOT_FOUND
    elif error.error_code in [
        MediaErrorCode.DUPLICATE_FILE_DETECTED,
        MediaErrorCode.DUPLICATE_RECORD,
        MediaErrorCode.DUPLICATE_POLICY_VIOLATION
    ]:
        status_code = status.HTTP_409_CONFLICT
    elif error.error_code in [
        MediaErrorCode.UNAUTHORIZED,
        MediaErrorCode.INVALID_TOKEN,
        MediaErrorCode.TOKEN_EXPIRED
    ]:
        status_code = status.HTTP_401_UNAUTHORIZED
    elif error.error_code == MediaErrorCode.PERMISSION_DENIED:
        status_code = status.HTTP_403_FORBIDDEN
    elif error.error_code == MediaErrorCode.RATE_LIMIT_EXCEEDED:
        status_code = status.HTTP_429_TOO_MANY_REQUESTS
    elif error.error_code in [
        MediaErrorCode.SERVICE_UNAVAILABLE,
        MediaErrorCode.TELEGRAM_UPLOAD_FAILED,
        MediaErrorCode.TELEGRAM_API_ERROR
    ]:
        status_code = status.HTTP_502_BAD_GATEWAY
    elif error.error_code == MediaErrorCode.FILE_TOO_LARGE:
        status_code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    
    return MediaHTTPException(
        error_code=error.error_code,
        status_code=status_code,
        details=error.details,
        language=error.language
    )
