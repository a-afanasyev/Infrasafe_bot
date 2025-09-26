# Константы для проекта UK Management Bot

# Максимальные размеры файлов (в байтах)
MAX_PHOTO_SIZE = 10 * 1024 * 1024  # 10 MB
MAX_VIDEO_SIZE = 50 * 1024 * 1024  # 50 MB
MAX_DOCUMENT_SIZE = 20 * 1024 * 1024  # 20 MB

# Максимальное количество медиафайлов в заявке
MAX_MEDIA_FILES_PER_REQUEST = 10

# Максимальная длина текстовых полей
MAX_ADDRESS_LENGTH = 500
MAX_DESCRIPTION_LENGTH = 2000
MAX_APARTMENT_LENGTH = 20
MAX_NOTES_LENGTH = 1000

# Типы адресов пользователя
ADDRESS_TYPE_HOME = "home"
ADDRESS_TYPE_APARTMENT = "apartment"
ADDRESS_TYPE_YARD = "yard"

ADDRESS_TYPES = [ADDRESS_TYPE_HOME, ADDRESS_TYPE_APARTMENT, ADDRESS_TYPE_YARD]

# Отображаемые названия типов адресов
ADDRESS_TYPE_DISPLAYS = {
    ADDRESS_TYPE_HOME: "🏠 Мой дом",
    ADDRESS_TYPE_APARTMENT: "🏢 Моя квартира",
    ADDRESS_TYPE_YARD: "🌳 Мой двор"
}

# Таймауты (в секундах)
REQUEST_TIMEOUT = 300  # 5 минут на создание заявки
MEDIA_UPLOAD_TIMEOUT = 60  # 1 минута на загрузку медиа
SHIFT_TIMEOUT = 3600  # 1 час на смену

# Статусы пользователей
USER_STATUS_PENDING = "pending"
USER_STATUS_APPROVED = "approved"
USER_STATUS_BLOCKED = "blocked"

# Роли пользователей
ROLE_APPLICANT = "applicant"
ROLE_EXECUTOR = "executor"
ROLE_MANAGER = "manager"
USER_ROLES = [ROLE_APPLICANT, ROLE_EXECUTOR, ROLE_MANAGER]

# Статусы заявок
REQUEST_STATUS_NEW = "Новая"
REQUEST_STATUS_ACCEPTED = "Принята"
REQUEST_STATUS_IN_PROGRESS = "В работе"
REQUEST_STATUS_PURCHASE = "Закуп"
REQUEST_STATUS_CLARIFICATION = "Уточнение"
REQUEST_STATUS_COMPLETED = "Исполнено"
REQUEST_STATUS_EXECUTED = "Выполнена"
REQUEST_STATUS_CONFIRMED = "Подтверждена"
REQUEST_STATUS_APPROVED = "Принято"
REQUEST_STATUS_CANCELLED = "Отменена"
REQUEST_STATUSES = [
    REQUEST_STATUS_NEW,
    REQUEST_STATUS_ACCEPTED,
    REQUEST_STATUS_IN_PROGRESS,
    REQUEST_STATUS_CLARIFICATION,
    REQUEST_STATUS_PURCHASE,
    REQUEST_STATUS_COMPLETED,
    REQUEST_STATUS_EXECUTED,
    REQUEST_STATUS_CONFIRMED,
    REQUEST_STATUS_APPROVED,
    REQUEST_STATUS_CANCELLED,
]

# Типы назначений заявок
ASSIGNMENT_TYPE_GROUP = "group"
ASSIGNMENT_TYPE_INDIVIDUAL = "individual"
ASSIGNMENT_TYPES = [ASSIGNMENT_TYPE_GROUP, ASSIGNMENT_TYPE_INDIVIDUAL]

# Статусы назначений
ASSIGNMENT_STATUS_ACTIVE = "active"
ASSIGNMENT_STATUS_CANCELLED = "cancelled"
ASSIGNMENT_STATUS_COMPLETED = "completed"
ASSIGNMENT_STATUSES = [ASSIGNMENT_STATUS_ACTIVE, ASSIGNMENT_STATUS_CANCELLED, ASSIGNMENT_STATUS_COMPLETED]

# Типы комментариев
COMMENT_TYPE_STATUS_CHANGE = "status_change"
COMMENT_TYPE_CLARIFICATION = "clarification"
COMMENT_TYPE_PURCHASE = "purchase"
COMMENT_TYPE_REPORT = "report"
COMMENT_TYPES = [COMMENT_TYPE_STATUS_CHANGE, COMMENT_TYPE_CLARIFICATION, COMMENT_TYPE_PURCHASE, COMMENT_TYPE_REPORT]

# Срочность заявок
URGENCY_LOW = "Обычная"
URGENCY_MEDIUM = "Средняя"
URGENCY_HIGH = "Срочная"
URGENCY_CRITICAL = "Критическая"

# Категории заявок
REQUEST_CATEGORIES = [
    "Электрика",
    "Сантехника",
    "Отопление",
    "Вентиляция",
    "Лифт",
    "Уборка",
    "Благоустройство",
    "Безопасность",
    "Интернет/ТВ",
    "Другое"
]

# Срочность заявок
REQUEST_URGENCIES = [
    URGENCY_LOW,
    URGENCY_MEDIUM,
    URGENCY_HIGH,
    URGENCY_CRITICAL
]

# Статусы смен
SHIFT_STATUS_ACTIVE = "active"
SHIFT_STATUS_COMPLETED = "completed"
SHIFT_STATUS_CANCELLED = "cancelled"
SHIFT_STATUS_PLANNED = "planned"
SHIFT_STATUS_PAUSED = "paused"

SHIFT_STATUSES = [
    SHIFT_STATUS_ACTIVE,
    SHIFT_STATUS_COMPLETED,
    SHIFT_STATUS_CANCELLED,
    SHIFT_STATUS_PLANNED,
    SHIFT_STATUS_PAUSED
]

# Типы смен
SHIFT_TYPE_REGULAR = "regular"
SHIFT_TYPE_EMERGENCY = "emergency" 
SHIFT_TYPE_OVERTIME = "overtime"
SHIFT_TYPE_MAINTENANCE = "maintenance"
SHIFT_TYPE_SECURITY = "security"

SHIFT_TYPES = [
    SHIFT_TYPE_REGULAR,
    SHIFT_TYPE_EMERGENCY,
    SHIFT_TYPE_OVERTIME,
    SHIFT_TYPE_MAINTENANCE,
    SHIFT_TYPE_SECURITY
]

# Типы уведомлений
NOTIFICATION_TYPE_NEW_REQUEST = "new_request"
NOTIFICATION_TYPE_STATUS_CHANGED = "status_changed"
NOTIFICATION_TYPE_PURCHASE = "purchase"
NOTIFICATION_TYPE_CLARIFICATION = "clarification"
NOTIFICATION_TYPE_COMPLETED = "completed"
NOTIFICATION_TYPE_SHIFT_STARTED = "shift_started"
NOTIFICATION_TYPE_SHIFT_ENDED = "shift_ended"

# Действия для аудита
AUDIT_ACTION_USER_REGISTERED = "user_registered"
AUDIT_ACTION_USER_APPROVED = "user_approved"
AUDIT_ACTION_USER_BLOCKED = "user_blocked"
AUDIT_ACTION_REQUEST_CREATED = "request_created"
AUDIT_ACTION_REQUEST_STATUS_CHANGED = "request_status_changed"
AUDIT_ACTION_REQUEST_ASSIGNED = "request_assigned"
AUDIT_ACTION_SHIFT_STARTED = "shift_started"
AUDIT_ACTION_SHIFT_ENDED = "shift_ended"
AUDIT_ACTION_RATING_SUBMITTED = "rating_submitted"

# Callback data префиксы
CALLBACK_PREFIX_CATEGORY = "category_"
CALLBACK_PREFIX_URGENCY = "urgency_"
CALLBACK_PREFIX_STATUS = "status_"
CALLBACK_PREFIX_RATING = "rate_"
CALLBACK_PREFIX_REQUEST = "request_"
CALLBACK_PREFIX_SHIFT = "shift_"
CALLBACK_PREFIX_ADMIN = "admin_"

# Сообщения об ошибках
ERROR_MESSAGES = {
    "permission_denied": "У вас нет прав для выполнения этого действия",
    "not_in_shift": "Вы не в смене. Смена необходима для выполнения этого действия",
    "invalid_data": "Неверные данные",
    "file_too_large": "Файл слишком большой",
    "unknown_error": "Произошла ошибка. Попробуйте позже",
    "request_not_found": "Заявка не найдена",
    "user_not_found": "Пользователь не найден",
    "shift_not_found": "Смена не найдена",
    "already_in_shift": "Вы уже в смене",
    "not_in_shift": "Вы не в смене"
}

# Успешные сообщения
SUCCESS_MESSAGES = {
    "request_created": "Заявка успешно создана!",
    "request_updated": "Заявка обновлена!",
    "user_approved": "Пользователь одобрен!",
    "user_blocked": "Пользователь заблокирован!",
    "shift_started": "Смена принята!",
    "shift_ended": "Смена сдана!",
    "rating_submitted": "Оценка отправлена!"
}

# Эмодзи для интерфейса
EMOJIS = {
    "welcome": "🏠",
    "help": "🤖",
    "create": "📝",
    "list": "📋",
    "profile": "👤",
    "admin": "🔧",
    "stats": "📊",
    "category": "🏷️",
    "address": "📍",
    "description": "📝",
    "apartment": "🏠",
    "urgency": "⚡",
    "status": "📊",
    "executor": "👤",
    "created": "🕐",
    "media": "📸",
    "shift": "🔄",
    "rating": "⭐",
    "error": "❌",
    "success": "✅",
    "warning": "⚠️",
    "info": "ℹ️",
    "cancel": "❌",
    "back": "🔙",
    "yes": "✅",
    "no": "❌",
    "skip": "⏭",
    "confirm": "✅",
    "edit": "✏️",
    "delete": "🗑"
}

# Специализации сотрудников
SPECIALIZATION_ELECTRIC = "electric"
SPECIALIZATION_PLUMBING = "plumbing"
SPECIALIZATION_SECURITY = "security"
SPECIALIZATION_CLEANING = "cleaning"
SPECIALIZATION_OTHER = "other"

SPECIALIZATION_HVAC = "hvac"
SPECIALIZATION_MAINTENANCE = "maintenance"
SPECIALIZATION_UNIVERSAL = "universal"

SPECIALIZATIONS = {
    SPECIALIZATION_ELECTRIC: "Электрика",
    SPECIALIZATION_PLUMBING: "Сантехника", 
    SPECIALIZATION_SECURITY: "Охрана",
    SPECIALIZATION_CLEANING: "Уборка",
    SPECIALIZATION_HVAC: "Отопление/Кондиционирование",
    SPECIALIZATION_MAINTENANCE: "Техническое обслуживание",
    SPECIALIZATION_UNIVERSAL: "Универсальный специалист",
    SPECIALIZATION_OTHER: "Разное",
}

SPECIALIZATION_DISPLAY = {
    SPECIALIZATION_ELECTRIC: "Электрика",
    SPECIALIZATION_PLUMBING: "Сантехника",
    SPECIALIZATION_SECURITY: "Охрана", 
    SPECIALIZATION_CLEANING: "Уборка",
    SPECIALIZATION_HVAC: "Отопление/Кондиционирование",
    SPECIALIZATION_MAINTENANCE: "Техническое обслуживание",
    SPECIALIZATION_UNIVERSAL: "Универсальный специалист",
    SPECIALIZATION_OTHER: "Разное",
}
