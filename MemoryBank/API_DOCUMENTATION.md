# 🔌 API ДОКУМЕНТАЦИЯ UK MANAGEMENT BOT

## 📋 ОБЗОР API

UK Management Bot предоставляет множественные API интерфейсы для взаимодействия с различными компонентами системы. API разделены на внутренние (для компонентов бота) и внешние (для интеграций).

---

## 🏗️ ВНУТРЕННИЕ API

### 🔐 AuthService API

Сервис авторизации и управления пользователями.

#### Управление пользователями:
```python
class AuthService:
    async def get_or_create_user(self, telegram_id: int, username: str, 
                                first_name: str, last_name: str) -> User:
        """Получение или создание пользователя"""
    
    async def get_user_by_telegram_id(self, telegram_id: int) -> User | None:
        """Получение пользователя по Telegram ID"""
    
    async def update_user_language(self, telegram_id: int, language_code: str) -> bool:
        """Обновление языка пользователя"""
    
    async def update_user_phone(self, telegram_id: int, phone: str) -> bool:
        """Обновление телефона пользователя"""
    
    async def add_user_address(self, telegram_id: int, address: str, 
                              address_type: str = "home") -> bool:
        """Добавление адреса пользователю"""
```

#### Система ролей:
```python
class AuthService:
    async def set_active_role(self, telegram_id: int, role: str) -> bool:
        """Установка активной роли пользователя"""
    
    async def try_set_active_role_with_rate_limit(self, telegram_id: int, 
                                                 role: str, window_seconds: int = 10) -> tuple[bool, str | None]:
        """Установка роли с проверкой rate limit"""
    
    async def get_user_roles(self, telegram_id: int) -> list[str]:
        """Получение списка ролей пользователя"""
    
    async def add_user_role(self, telegram_id: int, role: str, 
                           specialization: str = None) -> bool:
        """Добавление роли пользователю"""
    
    async def remove_user_role(self, telegram_id: int, role: str) -> bool:
        """Удаление роли у пользователя"""
```

#### Проверки и валидация:
```python
class AuthService:
    async def is_user_manager(self, telegram_id: int) -> bool:
        """Проверка, является ли пользователь менеджером"""
    
    async def is_user_admin(self, telegram_id: int) -> bool:
        """Проверка, является ли пользователь администратором"""
    
    async def is_user_executor(self, telegram_id: int) -> bool:
        """Проверка, является ли пользователь исполнителем"""
    
    async def has_role(self, telegram_id: int, role: str) -> bool:
        """Проверка наличия конкретной роли"""
```

#### Модерация:
```python
class AuthService:
    async def approve_user(self, telegram_id: int, approver_id: int) -> bool:
        """Одобрение пользователя"""
    
    async def block_user(self, telegram_id: int, blocker_id: int, reason: str) -> bool:
        """Блокировка пользователя"""
    
    async def unblock_user(self, telegram_id: int, unblocker_id: int) -> bool:
        """Разблокировка пользователя"""
```

---

### 📝 RequestService API

Сервис управления заявками.

#### CRUD операции:
```python
class RequestService:
    async def create_request(self, user_id: int, category: str, address: str,
                            description: str, urgency: str = "normal") -> Request:
        """Создание новой заявки"""
    
    async def get_request_by_id(self, request_id: int) -> Request | None:
        """Получение заявки по ID"""
    
    async def update_request_status(self, request_id: int, status: str, 
                                   updater_id: int, comment: str = None) -> bool:
        """Обновление статуса заявки"""
    
    async def update_request_notes(self, request_id: int, notes: str) -> bool:
        """Обновление заметок к заявке"""
    
    async def delete_request(self, request_id: int, deleter_id: int) -> bool:
        """Удаление заявки (с аудитом)"""
```

#### Назначение и управление:
```python
class RequestService:
    async def assign_request(self, request_id: int, executor_id: int, 
                            assigner_id: int, comment: str = None) -> bool:
        """Назначение заявки исполнителю"""
    
    async def unassign_request(self, request_id: int, unassigner_id: int) -> bool:
        """Снятие назначения с заявки"""
    
    async def complete_request(self, request_id: int, executor_id: int,
                              completion_notes: str = None) -> bool:
        """Завершение выполнения заявки"""
    
    async def cancel_request(self, request_id: int, canceller_id: int,
                            cancellation_reason: str) -> bool:
        """Отмена заявки"""
    
    async def request_clarification(self, request_id: int, requester_id: int,
                                   clarification_text: str) -> bool:
        """Запрос уточнения по заявке"""
```

#### Поиск и фильтрация:
```python
class RequestService:
    async def get_user_requests(self, user_id: int, status: str = None,
                               limit: int = 10, offset: int = 0) -> list[Request]:
        """Получение заявок пользователя"""
    
    async def get_requests_by_status(self, status: str, limit: int = 10) -> list[Request]:
        """Получение заявок по статусу"""
    
    async def get_assigned_requests(self, executor_id: int) -> list[Request]:
        """Получение назначенных исполнителю заявок"""
    
    async def search_requests(self, query: str, filters: dict = None) -> list[Request]:
        """Поиск заявок по запросу и фильтрам"""
    
    async def get_requests_by_category(self, category: str, limit: int = 10) -> list[Request]:
        """Получение заявок по категории"""
```

#### Статистика:
```python
class RequestService:
    async def get_request_statistics(self, period: str = "month") -> dict:
        """Получение статистики по заявкам"""
    
    async def get_executor_performance(self, executor_id: int, period: str = "month") -> dict:
        """Получение статистики производительности исполнителя"""
    
    async def get_category_statistics(self, period: str = "month") -> dict:
        """Получение статистики по категориям"""
```

---

### 🎫 InviteService API

Сервис управления инвайт-токенами.

#### Создание и валидация токенов:
```python
class InviteService:
    def create_invite_token(self, role: str, specialization: str = None,
                           expires_in: int = 7200, max_uses: int = 1,
                           created_by: int = None) -> dict:
        """Создание инвайт-токена"""
        # Возвращает: {"token": "...", "expires_at": "...", "nonce": "..."}
    
    def validate_invite_token(self, token: str) -> dict:
        """Валидация инвайт-токена"""
        # Возвращает: {"role": "...", "specialization": "...", "nonce": "..."}
        # Или raises ValueError при невалидном токене
    
    def get_token_info(self, token: str) -> dict:
        """Получение информации о токене без валидации"""
```

#### Управление использованием:
```python
class InviteService:
    def mark_nonce_used(self, nonce: str, telegram_id: int, invite_data: dict) -> bool:
        """Отметка nonce как использованного"""
    
    def is_nonce_used(self, nonce: str) -> bool:
        """Проверка, использован ли nonce"""
    
    def get_token_usage_stats(self, nonce: str) -> dict:
        """Получение статистики использования токена"""
```

#### Аудит и логирование:
```python
class InviteService:
    def log_invite_creation(self, admin_id: int, invite_data: dict) -> None:
        """Логирование создания инвайта"""
    
    def log_invite_usage(self, telegram_id: int, invite_data: dict) -> None:
        """Логирование использования инвайта"""
    
    def get_invite_audit_log(self, nonce: str = None) -> list[dict]:
        """Получение аудит-лога инвайтов"""
```

---

### ⏰ ShiftService API

Сервис управления сменами.

#### Управление сменами:
```python
class ShiftService:
    async def create_shift(self, executor_id: int, shift_type: str,
                          start_time: datetime, end_time: datetime,
                          created_by: int) -> Shift:
        """Создание новой смены"""
    
    async def start_shift(self, executor_id: int) -> bool:
        """Начало смены исполнителя"""
    
    async def end_shift(self, executor_id: int, shift_notes: str = None) -> bool:
        """Завершение смены исполнителя"""
    
    async def get_active_shift(self, executor_id: int) -> Shift | None:
        """Получение активной смены исполнителя"""
```

#### Планирование:
```python
class ShiftService:
    async def schedule_shift(self, executor_id: int, date: datetime,
                            shift_type: str, duration_hours: int) -> Shift:
        """Планирование смены на будущее"""
    
    async def get_weekly_schedule(self, executor_id: int, week_start: datetime) -> list[Shift]:
        """Получение расписания на неделю"""
    
    async def update_shift_schedule(self, shift_id: int, new_start: datetime,
                                   new_end: datetime) -> bool:
        """Обновление расписания смены"""
```

#### Мониторинг и статистика:
```python
class ShiftService:
    async def get_active_shifts(self) -> list[Shift]:
        """Получение всех активных смен"""
    
    async def get_shift_statistics(self, period: str = "month") -> dict:
        """Получение статистики по сменам"""
    
    async def get_executor_workload(self, executor_id: int, period: str = "month") -> dict:
        """Получение загрузки исполнителя"""
    
    async def get_shift_performance(self, shift_id: int) -> dict:
        """Получение статистики производительности смены"""
```

---

### 👥 UserManagementService API

Сервис управления пользователями для администраторов.

#### Статистика пользователей:
```python
class UserManagementService:
    async def get_user_statistics(self) -> dict:
        """Получение общей статистики пользователей"""
        # Возвращает: {"total": 100, "pending": 5, "approved": 90, "blocked": 5}
    
    async def get_users_by_status(self, status: str, limit: int = 10, 
                                 offset: int = 0) -> list[User]:
        """Получение пользователей по статусу"""
    
    async def search_users(self, query: str, filters: dict = None) -> list[User]:
        """Поиск пользователей"""
```

#### Управление специализациями:
```python
class SpecializationService:
    def get_all_specializations(self) -> list[dict]:
        """Получение всех специализаций"""
    
    def add_specialization(self, name: str, description: str) -> bool:
        """Добавление новой специализации"""
    
    def update_specialization(self, name: str, new_description: str) -> bool:
        """Обновление специализации"""
    
    def delete_specialization(self, name: str) -> bool:
        """Удаление специализации"""
```

---

## 🌐 ВНЕШНИЕ API И ИНТЕГРАЦИИ

### 🔗 Google Sheets Integration API

Интеграция с Google Sheets для экспорта данных.

#### Экспорт данных:
```python
class SheetsService:
    async def export_requests_to_sheets(self, spreadsheet_id: str, 
                                       requests_data: list[dict]) -> bool:
        """Экспорт заявок в Google Sheets"""
    
    async def export_users_to_sheets(self, spreadsheet_id: str,
                                    users_data: list[dict]) -> bool:
        """Экспорт пользователей в Google Sheets"""
    
    async def export_statistics_to_sheets(self, spreadsheet_id: str,
                                         stats_data: dict) -> bool:
        """Экспорт статистики в Google Sheets"""
    
    async def export_shifts_to_sheets(self, spreadsheet_id: str,
                                     shifts_data: list[dict]) -> bool:
        """Экспорт смен в Google Sheets"""
```

#### Автоматическая синхронизация:
```python
class SheetsService:
    async def setup_auto_sync(self, spreadsheet_id: str, sync_frequency: str,
                             data_types: list[str]) -> bool:
        """Настройка автоматической синхронизации"""
    
    async def sync_data_to_sheets(self, spreadsheet_id: str) -> dict:
        """Выполнение синхронизации данных"""
    
    async def get_sync_status(self, spreadsheet_id: str) -> dict:
        """Получение статуса синхронизации"""
```

#### Конфигурация:
```python
class SheetsService:
    def configure_sheets_access(self, credentials_path: str) -> bool:
        """Настройка доступа к Google Sheets"""
    
    def test_sheets_connection(self) -> bool:
        """Тестирование подключения к Google Sheets"""
    
    def get_spreadsheet_info(self, spreadsheet_id: str) -> dict:
        """Получение информации о таблице"""
```

---

### 🤖 Telegram Bot API Integration

Расширенная интеграция с Telegram Bot API.

#### Отправка сообщений:
```python
class TelegramService:
    async def send_message(self, chat_id: int, text: str, 
                          parse_mode: str = "Markdown",
                          reply_markup=None) -> Message:
        """Отправка текстового сообщения"""
    
    async def send_photo(self, chat_id: int, photo, caption: str = None) -> Message:
        """Отправка фото с подписью"""
    
    async def send_document(self, chat_id: int, document, caption: str = None) -> Message:
        """Отправка документа"""
    
    async def edit_message(self, chat_id: int, message_id: int, 
                          new_text: str, reply_markup=None) -> bool:
        """Редактирование сообщения"""
```

#### Обработка файлов:
```python
class TelegramService:
    async def download_file(self, file_id: str, destination: str) -> str:
        """Скачивание файла от пользователя"""
    
    async def get_file_info(self, file_id: str) -> dict:
        """Получение информации о файле"""
    
    async def upload_file(self, file_path: str) -> str:
        """Загрузка файла на сервера Telegram"""
```

#### Управление клавиатурами:
```python
class KeyboardService:
    def create_inline_keyboard(self, buttons: list[list[dict]]) -> InlineKeyboardMarkup:
        """Создание inline клавиатуры"""
    
    def create_reply_keyboard(self, buttons: list[list[str]], 
                             resize: bool = True) -> ReplyKeyboardMarkup:
        """Создание reply клавиатуры"""
    
    def remove_keyboard(self) -> ReplyKeyboardRemove:
        """Удаление клавиатуры"""
```

---

## 🏥 HEALTH CHECK API

API для мониторинга состояния системы.

### Базовый Health Check:
```http
GET /health

Response 200 OK:
{
  "status": "healthy",
  "timestamp": "2024-12-07T10:30:00.000Z",
  "components": {
    "database": {
      "status": "healthy",
      "response_time_ms": 45.2,
      "timestamp": "2024-12-07T10:30:00.000Z"
    },
    "redis": {
      "status": "healthy",
      "response_time_ms": 12.8,
      "timestamp": "2024-12-07T10:30:00.000Z"
    }
  },
  "summary": {
    "healthy_components": 2,
    "total_components": 2,
    "uptime_seconds": 86400
  }
}
```

### Детальная диагностика:
```http
GET /health_detailed

Response 200 OK:
{
  "status": "healthy",
  "timestamp": "2024-12-07T10:30:00.000Z",
  "components": {
    "database": { ... },
    "redis": { ... },
    "system": {
      "uptime_seconds": 86400,
      "uptime_human": "1d 0h 0m 0s",
      "debug_mode": false,
      "log_level": "WARNING",
      "supported_languages": ["ru", "uz"]
    }
  },
  "configuration": {
    "invite_secret_set": true,
    "admin_password_secure": true,
    "redis_enabled": true,
    "notifications_enabled": true,
    "admin_users_count": 2
  }
}
```

### Быстрая проверка:
```http
GET /ping

Response 200 OK:
{
  "status": "pong",
  "timestamp": "2024-12-07T10:30:00.000Z"
}
```

---

## 🔒 RATE LIMITING API

API для управления ограничениями частоты запросов.

### Redis-based Rate Limiting:
```python
class RedisRateLimiter:
    @staticmethod
    async def is_allowed(key: str, max_requests: int, window_seconds: int) -> bool:
        """Проверка разрешенности запроса"""
    
    @staticmethod
    async def get_remaining_time(key: str, window_seconds: int) -> int:
        """Получение времени до сброса лимита"""
```

### In-memory Fallback:
```python
class InMemoryRateLimiter:
    @classmethod
    def is_allowed(cls, key: str, max_requests: int, window_seconds: int) -> bool:
        """In-memory проверка лимита"""
    
    @classmethod
    def get_remaining_time(cls, key: str, window_seconds: int) -> int:
        """Время до сброса in-memory лимита"""
```

### Удобные функции:
```python
async def is_rate_limited(key: str, max_requests: int, window_seconds: int) -> bool:
    """Проверка превышения лимита (True = заблокирован)"""

async def get_rate_limit_remaining_time(key: str, window_seconds: int) -> int:
    """Получение времени до сброса лимита"""

async def get_rate_limiter():
    """Получение подходящего rate limiter (Redis или in-memory)"""
```

---

## 📊 NOTIFICATION SERVICE API

Сервис уведомлений для различных событий.

### Отправка уведомлений:
```python
class NotificationService:
    async def send_request_notification(self, user_id: int, request_id: int,
                                       notification_type: str) -> bool:
        """Отправка уведомления о заявке"""
    
    async def send_role_change_notification(self, user_id: int, old_role: str,
                                           new_role: str) -> bool:
        """Уведомление о смене роли"""
    
    async def send_shift_notification(self, user_id: int, shift_id: int,
                                     notification_type: str) -> bool:
        """Уведомление о смене"""
    
    async def send_system_notification(self, user_ids: list[int], message: str) -> dict:
        """Отправка системного уведомления"""
```

### Управление подписками:
```python
class NotificationService:
    async def subscribe_to_notifications(self, user_id: int, 
                                        notification_types: list[str]) -> bool:
        """Подписка на типы уведомлений"""
    
    async def unsubscribe_from_notifications(self, user_id: int,
                                            notification_types: list[str]) -> bool:
        """Отписка от уведомлений"""
    
    async def get_notification_preferences(self, user_id: int) -> dict:
        """Получение настроек уведомлений"""
```

---

## 🔍 AUDIT AND LOGGING API

API для аудита и логирования действий.

### Structured Logging:
```python
from utils.structured_logger import get_logger, StructuredLogger

# Создание логгера с контекстом
logger = get_logger(__name__, component="requests", user_id=123)

# Логирование с метаданными
logger.info("Request created", 
           request_id=456, 
           category="сантехника",
           urgency="срочная")

# Специализированные логгеры
auth_logger = get_auth_logger(user_id=123)
security_logger = get_security_logger(event_type="login_attempt")
performance_logger = get_performance_logger(component="database")
```

### Audit Trail:
```python
class AuditService:
    async def log_user_action(self, user_id: int, action: str, 
                             details: dict = None) -> bool:
        """Логирование действия пользователя"""
    
    async def log_admin_action(self, admin_id: int, action: str,
                              target_id: int = None, details: dict = None) -> bool:
        """Логирование административного действия"""
    
    async def get_user_audit_log(self, user_id: int, limit: int = 100) -> list[dict]:
        """Получение аудит-лога пользователя"""
    
    async def get_system_audit_log(self, filters: dict = None) -> list[dict]:
        """Получение системного аудит-лога"""
```

---

## 📈 ANALYTICS AND REPORTING API

API для аналитики и отчетности.

### Статистика по заявкам:
```python
class AnalyticsService:
    async def get_request_analytics(self, period: str = "month") -> dict:
        """Аналитика по заявкам"""
        # Возвращает: создано, завершено, среднее время выполнения, etc.
    
    async def get_category_distribution(self, period: str = "month") -> dict:
        """Распределение заявок по категориям"""
    
    async def get_urgency_statistics(self, period: str = "month") -> dict:
        """Статистика по срочности заявок"""
```

### Производительность исполнителей:
```python
class AnalyticsService:
    async def get_executor_performance(self, executor_id: int = None, 
                                      period: str = "month") -> dict:
        """Производительность исполнителей"""
    
    async def get_response_time_analytics(self, period: str = "month") -> dict:
        """Аналитика времени отклика"""
    
    async def get_completion_rate_analytics(self, period: str = "month") -> dict:
        """Аналитика уровня завершения заявок"""
```

### Системная аналитика:
```python
class AnalyticsService:
    async def get_user_activity_analytics(self, period: str = "month") -> dict:
        """Аналитика активности пользователей"""
    
    async def get_system_performance_metrics(self, period: str = "day") -> dict:
        """Метрики производительности системы"""
    
    async def generate_custom_report(self, report_config: dict) -> dict:
        """Генерация кастомного отчета"""
```

---

## 🔧 CONFIGURATION API

API для управления конфигурацией системы.

### Системные настройки:
```python
class ConfigurationService:
    def get_system_config(self) -> dict:
        """Получение системной конфигурации"""
    
    def update_system_config(self, config: dict) -> bool:
        """Обновление системной конфигурации"""
    
    def validate_config(self, config: dict) -> tuple[bool, list[str]]:
        """Валидация конфигурации"""
```

### Настройки безопасности:
```python
class SecurityConfigService:
    def get_rate_limit_config(self) -> dict:
        """Получение настроек rate limiting"""
    
    def update_rate_limit_config(self, config: dict) -> bool:
        """Обновление настроек rate limiting"""
    
    def get_auth_config(self) -> dict:
        """Получение настроек авторизации"""
    
    def validate_security_config(self) -> tuple[bool, list[str]]:
        """Валидация настроек безопасности"""
```

---

## 📝 ПРИМЕРЫ ИСПОЛЬЗОВАНИЯ API

### Создание заявки через API:
```python
# Создание заявки
request_service = RequestService(db)
new_request = await request_service.create_request(
    user_id=123,
    category="сантехника",
    address="ул. Примерная, д.1, кв.10",
    description="Течет кран на кухне",
    urgency="срочная"
)

# Назначение заявки исполнителю
await request_service.assign_request(
    request_id=new_request.id,
    executor_id=456,
    assigner_id=789,
    comment="Назначено лучшему сантехнику"
)

# Логирование действия
audit_service = AuditService(db)
await audit_service.log_user_action(
    user_id=789,
    action="request_assigned",
    details={
        "request_id": new_request.id,
        "executor_id": 456,
        "category": "сантехника"
    }
)
```

### Работа с инвайт-токенами:
```python
# Создание инвайт-токена
invite_service = InviteService(db)
invite_data = invite_service.create_invite_token(
    role="executor",
    specialization="сантехник",
    expires_in=7200,  # 2 часа
    max_uses=1,
    created_by=admin_id
)

print(f"Инвайт-токен: {invite_data['token']}")

# Валидация токена
try:
    validated_data = invite_service.validate_invite_token(invite_data['token'])
    print(f"Токен валиден для роли: {validated_data['role']}")
except ValueError as e:
    print(f"Ошибка валидации: {e}")
```

### Мониторинг здоровья системы:
```python
# Получение статуса здоровья
from handlers.health import get_health_status

health_status = await get_health_status(db)
print(f"Статус системы: {health_status['status']}")

if health_status['status'] != 'healthy':
    # Отправка alert'а администраторам
    notification_service = NotificationService()
    await notification_service.send_system_notification(
        user_ids=admin_user_ids,
        message=f"⚠️ Проблема со здоровьем системы: {health_status['status']}"
    )
```

---

## 🔒 БЕЗОПАСНОСТЬ API

### Аутентификация и авторизация:
- Все API методы требуют валидной сессии пользователя
- RBAC проверки на уровне методов
- Rate limiting для всех критичных операций
- Comprehensive audit logging всех API вызовов

### Валидация данных:
- Строгая валидация всех входящих параметров
- Санитизация пользовательского ввода
- Защита от SQL injection через ORM
- XSS защита для всех текстовых полей

### Мониторинг безопасности:
- Автоматическое обнаружение подозрительной активности
- Логирование всех security events
- Real-time alerting при критичных событиях
- Regular security audit trails

---

Данная API документация предоставляет полный обзор всех доступных интерфейсов UK Management Bot для разработчиков и интеграторов. Все API следуют принципам RESTful дизайна и обеспечивают высокий уровень безопасности и производительности.
