"""
Система кодов ошибок для Media Service
"""

from enum import Enum
from typing import Dict, Any


class MediaErrorCode(Enum):
    """Коды ошибок Media Service"""
    
    # === ОБЩИЕ ОШИБКИ ===
    INTERNAL_SERVER_ERROR = "MEDIA_001"
    VALIDATION_ERROR = "MEDIA_002"
    PERMISSION_DENIED = "MEDIA_003"
    RESOURCE_NOT_FOUND = "MEDIA_004"
    RATE_LIMIT_EXCEEDED = "MEDIA_005"
    
    # === ОШИБКИ ЗАГРУЗКИ ФАЙЛОВ ===
    FILE_UPLOAD_FAILED = "MEDIA_101"
    INVALID_FILE_TYPE = "MEDIA_102"
    FILE_TOO_LARGE = "MEDIA_103"
    FILE_CORRUPTED = "MEDIA_104"
    FILE_PROCESSING_ERROR = "MEDIA_105"
    STORAGE_QUOTA_EXCEEDED = "MEDIA_106"
    
    # === ОШИБКИ TELEGRAM ===
    TELEGRAM_UPLOAD_FAILED = "MEDIA_201"
    TELEGRAM_API_ERROR = "MEDIA_202"
    TELEGRAM_CHANNEL_NOT_FOUND = "MEDIA_203"
    TELEGRAM_BOT_TOKEN_INVALID = "MEDIA_204"
    TELEGRAM_RATE_LIMIT = "MEDIA_205"
    
    # === ОШИБКИ БАЗЫ ДАННЫХ ===
    DATABASE_CONNECTION_ERROR = "MEDIA_301"
    DATABASE_QUERY_ERROR = "MEDIA_302"
    DUPLICATE_RECORD = "MEDIA_303"
    CONSTRAINT_VIOLATION = "MEDIA_304"
    TRANSACTION_FAILED = "MEDIA_305"
    
    # === ОШИБКИ ПОИСКА И ФИЛЬТРАЦИИ ===
    INVALID_SEARCH_QUERY = "MEDIA_401"
    INVALID_DATE_RANGE = "MEDIA_402"
    INVALID_CATEGORY = "MEDIA_403"
    INVALID_TAGS_FORMAT = "MEDIA_404"
    SEARCH_TIMEOUT = "MEDIA_405"
    
    # === ОШИБКИ ДУБЛИКАТОВ ===
    DUPLICATE_FILE_DETECTED = "MEDIA_501"
    DUPLICATE_CHECK_FAILED = "MEDIA_502"
    DUPLICATE_POLICY_VIOLATION = "MEDIA_503"
    HASH_CALCULATION_ERROR = "MEDIA_504"
    
    # === ОШИБКИ АУТЕНТИФИКАЦИИ ===
    UNAUTHORIZED = "MEDIA_601"
    TOKEN_EXPIRED = "MEDIA_602"
    INVALID_TOKEN = "MEDIA_603"
    USER_NOT_FOUND = "MEDIA_604"
    
    # === ОШИБКИ КОНФИГУРАЦИИ ===
    MISSING_CONFIG = "MEDIA_701"
    INVALID_CONFIG = "MEDIA_702"
    SERVICE_UNAVAILABLE = "MEDIA_703"
    
    # === ОШИБКИ СЕТИ ===
    NETWORK_TIMEOUT = "MEDIA_801"
    NETWORK_CONNECTION_ERROR = "MEDIA_802"
    DNS_RESOLUTION_ERROR = "MEDIA_803"
    
    # === ОШИБКИ ФАЙЛОВОЙ СИСТЕМЫ ===
    FILE_NOT_FOUND = "MEDIA_901"
    FILE_ACCESS_DENIED = "MEDIA_902"
    DISK_SPACE_INSUFFICIENT = "MEDIA_903"
    FILE_LOCKED = "MEDIA_904"


class MediaErrorMessages:
    """Сообщения об ошибках для Media Service"""
    
    ERROR_MESSAGES: Dict[MediaErrorCode, Dict[str, str]] = {
        # === ОБЩИЕ ОШИБКИ ===
        MediaErrorCode.INTERNAL_SERVER_ERROR: {
            "ru": "Внутренняя ошибка сервера",
            "en": "Internal server error",
            "description": "Произошла непредвиденная ошибка при обработке запроса"
        },
        MediaErrorCode.VALIDATION_ERROR: {
            "ru": "Ошибка валидации данных",
            "en": "Data validation error",
            "description": "Переданные данные не соответствуют требованиям"
        },
        MediaErrorCode.PERMISSION_DENIED: {
            "ru": "Доступ запрещен",
            "en": "Permission denied",
            "description": "У вас нет прав для выполнения этого действия"
        },
        MediaErrorCode.RESOURCE_NOT_FOUND: {
            "ru": "Ресурс не найден",
            "en": "Resource not found",
            "description": "Запрашиваемый ресурс не существует"
        },
        MediaErrorCode.RATE_LIMIT_EXCEEDED: {
            "ru": "Превышен лимит запросов",
            "en": "Rate limit exceeded",
            "description": "Слишком много запросов, попробуйте позже"
        },
        
        # === ОШИБКИ ЗАГРУЗКИ ФАЙЛОВ ===
        MediaErrorCode.FILE_UPLOAD_FAILED: {
            "ru": "Ошибка загрузки файла",
            "en": "File upload failed",
            "description": "Не удалось загрузить файл"
        },
        MediaErrorCode.INVALID_FILE_TYPE: {
            "ru": "Неподдерживаемый тип файла",
            "en": "Unsupported file type",
            "description": "Данный тип файла не поддерживается системой"
        },
        MediaErrorCode.FILE_TOO_LARGE: {
            "ru": "Файл слишком большой",
            "en": "File too large",
            "description": "Размер файла превышает максимально допустимый"
        },
        MediaErrorCode.FILE_CORRUPTED: {
            "ru": "Поврежденный файл",
            "en": "Corrupted file",
            "description": "Файл поврежден и не может быть обработан"
        },
        MediaErrorCode.FILE_PROCESSING_ERROR: {
            "ru": "Ошибка обработки файла",
            "en": "File processing error",
            "description": "Не удалось обработать файл"
        },
        MediaErrorCode.STORAGE_QUOTA_EXCEEDED: {
            "ru": "Превышена квота хранилища",
            "en": "Storage quota exceeded",
            "description": "Достигнут лимит хранилища"
        },
        
        # === ОШИБКИ TELEGRAM ===
        MediaErrorCode.TELEGRAM_UPLOAD_FAILED: {
            "ru": "Ошибка загрузки в Telegram",
            "en": "Telegram upload failed",
            "description": "Не удалось загрузить файл в Telegram канал"
        },
        MediaErrorCode.TELEGRAM_API_ERROR: {
            "ru": "Ошибка API Telegram",
            "en": "Telegram API error",
            "description": "Ошибка при взаимодействии с Telegram API"
        },
        MediaErrorCode.TELEGRAM_CHANNEL_NOT_FOUND: {
            "ru": "Telegram канал не найден",
            "en": "Telegram channel not found",
            "description": "Указанный Telegram канал не существует или недоступен"
        },
        MediaErrorCode.TELEGRAM_BOT_TOKEN_INVALID: {
            "ru": "Неверный токен бота",
            "en": "Invalid bot token",
            "description": "Токен Telegram бота недействителен"
        },
        MediaErrorCode.TELEGRAM_RATE_LIMIT: {
            "ru": "Превышен лимит Telegram API",
            "en": "Telegram API rate limit exceeded",
            "description": "Превышен лимит запросов к Telegram API"
        },
        
        # === ОШИБКИ БАЗЫ ДАННЫХ ===
        MediaErrorCode.DATABASE_CONNECTION_ERROR: {
            "ru": "Ошибка подключения к базе данных",
            "en": "Database connection error",
            "description": "Не удалось подключиться к базе данных"
        },
        MediaErrorCode.DATABASE_QUERY_ERROR: {
            "ru": "Ошибка запроса к базе данных",
            "en": "Database query error",
            "description": "Ошибка при выполнении запроса к базе данных"
        },
        MediaErrorCode.DUPLICATE_RECORD: {
            "ru": "Дублирующаяся запись",
            "en": "Duplicate record",
            "description": "Запись с такими данными уже существует"
        },
        MediaErrorCode.CONSTRAINT_VIOLATION: {
            "ru": "Нарушение ограничения базы данных",
            "en": "Database constraint violation",
            "description": "Нарушено ограничение целостности базы данных"
        },
        MediaErrorCode.TRANSACTION_FAILED: {
            "ru": "Ошибка транзакции",
            "en": "Transaction failed",
            "description": "Не удалось выполнить транзакцию"
        },
        
        # === ОШИБКИ ПОИСКА И ФИЛЬТРАЦИИ ===
        MediaErrorCode.INVALID_SEARCH_QUERY: {
            "ru": "Некорректный поисковый запрос",
            "en": "Invalid search query",
            "description": "Поисковый запрос содержит некорректные данные"
        },
        MediaErrorCode.INVALID_DATE_RANGE: {
            "ru": "Некорректный диапазон дат",
            "en": "Invalid date range",
            "description": "Указанный диапазон дат некорректен"
        },
        MediaErrorCode.INVALID_CATEGORY: {
            "ru": "Некорректная категория",
            "en": "Invalid category",
            "description": "Указанная категория не существует"
        },
        MediaErrorCode.INVALID_TAGS_FORMAT: {
            "ru": "Некорректный формат тегов",
            "en": "Invalid tags format",
            "description": "Теги должны быть переданы в корректном формате"
        },
        MediaErrorCode.SEARCH_TIMEOUT: {
            "ru": "Таймаут поиска",
            "en": "Search timeout",
            "description": "Поиск занял слишком много времени"
        },
        
        # === ОШИБКИ ДУБЛИКАТОВ ===
        MediaErrorCode.DUPLICATE_FILE_DETECTED: {
            "ru": "Обнаружен дубликат файла",
            "en": "Duplicate file detected",
            "description": "Файл с таким содержимым уже существует"
        },
        MediaErrorCode.DUPLICATE_CHECK_FAILED: {
            "ru": "Ошибка проверки дубликатов",
            "en": "Duplicate check failed",
            "description": "Не удалось проверить файл на дубликаты"
        },
        MediaErrorCode.DUPLICATE_POLICY_VIOLATION: {
            "ru": "Нарушение политики дубликатов",
            "en": "Duplicate policy violation",
            "description": "Загрузка дубликата запрещена текущей политикой"
        },
        MediaErrorCode.HASH_CALCULATION_ERROR: {
            "ru": "Ошибка вычисления хеша",
            "en": "Hash calculation error",
            "description": "Не удалось вычислить хеш файла"
        },
        
        # === ОШИБКИ АУТЕНТИФИКАЦИИ ===
        MediaErrorCode.UNAUTHORIZED: {
            "ru": "Не авторизован",
            "en": "Unauthorized",
            "description": "Требуется авторизация для выполнения действия"
        },
        MediaErrorCode.TOKEN_EXPIRED: {
            "ru": "Токен истек",
            "en": "Token expired",
            "description": "Срок действия токена истек"
        },
        MediaErrorCode.INVALID_TOKEN: {
            "ru": "Неверный токен",
            "en": "Invalid token",
            "description": "Предоставленный токен недействителен"
        },
        MediaErrorCode.USER_NOT_FOUND: {
            "ru": "Пользователь не найден",
            "en": "User not found",
            "description": "Указанный пользователь не существует"
        },
        
        # === ОШИБКИ КОНФИГУРАЦИИ ===
        MediaErrorCode.MISSING_CONFIG: {
            "ru": "Отсутствует конфигурация",
            "en": "Missing configuration",
            "description": "Не настроен обязательный параметр конфигурации"
        },
        MediaErrorCode.INVALID_CONFIG: {
            "ru": "Некорректная конфигурация",
            "en": "Invalid configuration",
            "description": "Конфигурация содержит некорректные значения"
        },
        MediaErrorCode.SERVICE_UNAVAILABLE: {
            "ru": "Сервис недоступен",
            "en": "Service unavailable",
            "description": "Сервис временно недоступен"
        },
        
        # === ОШИБКИ СЕТИ ===
        MediaErrorCode.NETWORK_TIMEOUT: {
            "ru": "Таймаут сети",
            "en": "Network timeout",
            "description": "Превышено время ожидания сетевого соединения"
        },
        MediaErrorCode.NETWORK_CONNECTION_ERROR: {
            "ru": "Ошибка сетевого соединения",
            "en": "Network connection error",
            "description": "Не удалось установить сетевое соединение"
        },
        MediaErrorCode.DNS_RESOLUTION_ERROR: {
            "ru": "Ошибка разрешения DNS",
            "en": "DNS resolution error",
            "description": "Не удалось разрешить доменное имя"
        },
        
        # === ОШИБКИ ФАЙЛОВОЙ СИСТЕМЫ ===
        MediaErrorCode.FILE_NOT_FOUND: {
            "ru": "Файл не найден",
            "en": "File not found",
            "description": "Указанный файл не существует"
        },
        MediaErrorCode.FILE_ACCESS_DENIED: {
            "ru": "Доступ к файлу запрещен",
            "en": "File access denied",
            "description": "Нет прав для доступа к файлу"
        },
        MediaErrorCode.DISK_SPACE_INSUFFICIENT: {
            "ru": "Недостаточно места на диске",
            "en": "Insufficient disk space",
            "description": "На диске недостаточно свободного места"
        },
        MediaErrorCode.FILE_LOCKED: {
            "ru": "Файл заблокирован",
            "en": "File locked",
            "description": "Файл заблокирован другим процессом"
        }
    }
    
    @classmethod
    def get_message(cls, error_code: MediaErrorCode, language: str = "ru") -> str:
        """Получить сообщение об ошибке на указанном языке"""
        if error_code in cls.ERROR_MESSAGES:
            return cls.ERROR_MESSAGES[error_code].get(language, cls.ERROR_MESSAGES[error_code]["en"])
        return "Unknown error"
    
    @classmethod
    def get_description(cls, error_code: MediaErrorCode) -> str:
        """Получить описание ошибки"""
        if error_code in cls.ERROR_MESSAGES:
            return cls.ERROR_MESSAGES[error_code].get("description", "")
        return "No description available"
    
    @classmethod
    def get_full_info(cls, error_code: MediaErrorCode, language: str = "ru") -> Dict[str, str]:
        """Получить полную информацию об ошибке"""
        if error_code in cls.ERROR_MESSAGES:
            return {
                "code": error_code.value,
                "message": cls.ERROR_MESSAGES[error_code].get(language, cls.ERROR_MESSAGES[error_code]["en"]),
                "description": cls.ERROR_MESSAGES[error_code].get("description", ""),
                "category": cls._get_category(error_code)
            }
        return {
            "code": error_code.value,
            "message": "Unknown error",
            "description": "No description available",
            "category": "Unknown"
        }
    
    @classmethod
    def _get_category(cls, error_code: MediaErrorCode) -> str:
        """Получить категорию ошибки"""
        code_value = error_code.value
        
        if code_value.startswith("MEDIA_0"):
            return "Общие ошибки"
        elif code_value.startswith("MEDIA_1"):
            return "Ошибки загрузки файлов"
        elif code_value.startswith("MEDIA_2"):
            return "Ошибки Telegram"
        elif code_value.startswith("MEDIA_3"):
            return "Ошибки базы данных"
        elif code_value.startswith("MEDIA_4"):
            return "Ошибки поиска"
        elif code_value.startswith("MEDIA_5"):
            return "Ошибки дубликатов"
        elif code_value.startswith("MEDIA_6"):
            return "Ошибки аутентификации"
        elif code_value.startswith("MEDIA_7"):
            return "Ошибки конфигурации"
        elif code_value.startswith("MEDIA_8"):
            return "Ошибки сети"
        elif code_value.startswith("MEDIA_9"):
            return "Ошибки файловой системы"
        else:
            return "Неизвестная категория"


class MediaError(Exception):
    """Базовый класс для ошибок Media Service"""
    
    def __init__(
        self, 
        error_code: MediaErrorCode, 
        message: str = None, 
        details: Any = None,
        language: str = "ru"
    ):
        self.error_code = error_code
        self.message = message or MediaErrorMessages.get_message(error_code, language)
        self.description = MediaErrorMessages.get_description(error_code)
        self.details = details
        self.language = language
        
        super().__init__(self.message)
    
    def to_dict(self) -> Dict[str, Any]:
        """Преобразовать ошибку в словарь"""
        return {
            "error_code": self.error_code.value,
            "message": self.message,
            "description": self.description,
            "details": self.details,
            "category": MediaErrorMessages._get_category(self.error_code)
        }
