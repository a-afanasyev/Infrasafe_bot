# Система верификации пользователей - Руководство разработчика

## Обзор

Система верификации пользователей предоставляет администраторам и менеджерам возможность проверять данные пользователей, запрашивать дополнительную информацию и управлять правами доступа для подачи заявок.

## Архитектура

### Модели данных

#### UserDocument
```python
class UserDocument(Base):
    """Модель документов пользователя"""
    __tablename__ = "user_documents"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    document_type = Column(Enum(DocumentType), nullable=False)
    file_id = Column(String(255), nullable=False)  # Telegram file_id
    verification_status = Column(Enum(VerificationStatus), default=VerificationStatus.PENDING)
    # ... другие поля
```

#### UserVerification
```python
class UserVerification(Base):
    """Модель процесса верификации пользователя"""
    __tablename__ = "user_verifications"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    status = Column(Enum(VerificationStatus), default=VerificationStatus.PENDING)
    requested_info = Column(JSON, default=dict)
    # ... другие поля
```

#### AccessRights
```python
class AccessRights(Base):
    """Модель прав доступа для подачи заявок"""
    __tablename__ = "access_rights"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    access_level = Column(Enum(AccessLevel), nullable=False)
    apartment_number = Column(String(20), nullable=True)
    house_number = Column(String(20), nullable=True)
    yard_name = Column(String(100), nullable=True)
    # ... другие поля
```

### Сервисы

#### UserVerificationService
Основной сервис для управления верификацией:

```python
class UserVerificationService:
    def __init__(self, db: Session):
        self.db = db
    
    # Управление верификацией
    def create_verification_request(self, user_id: int, admin_id: int, requested_info: Dict[str, Any]) -> UserVerification
    def approve_verification(self, user_id: int, admin_id: int, notes: str = None) -> bool
    def reject_verification(self, user_id: int, admin_id: int, notes: str = None) -> bool
    
    # Управление документами
    def add_document(self, user_id: int, document_type: DocumentType, file_id: str, file_name: str = None) -> UserDocument
    def verify_document(self, document_id: int, admin_id: int, approved: bool, notes: str = None) -> bool
    def get_user_documents(self, user_id: int) -> List[UserDocument]
    
    # Управление правами доступа
    def grant_access_rights(self, user_id: int, access_level: AccessLevel, admin_id: int, details: Dict[str, str] = None) -> AccessRights
    def revoke_access_rights(self, rights_id: int, admin_id: int, notes: str = None) -> bool
    def get_user_access_rights(self, user_id: int) -> List[AccessRights]
    
    # Статистика
    def get_verification_stats(self) -> Dict[str, int]
```

### Обработчики

#### Основные обработчики верификации

```python
@router.callback_query(F.data == "user_verification_panel")
async def show_verification_panel(callback: CallbackQuery, db: Session, roles: list = None):
    """Показать панель верификации пользователей"""

@router.callback_query(F.data.startswith("verification_user_"))
async def show_user_verification(callback: CallbackQuery, db: Session, roles: list = None):
    """Показать информацию о верификации пользователя"""

@router.callback_query(F.data.startswith("verification_request_"))
async def request_additional_info(callback: CallbackQuery, db: Session, roles: list = None):
    """Запросить дополнительную информацию"""

@router.callback_query(F.data.startswith("document_verify_"))
async def verify_document(callback: CallbackQuery, db: Session, roles: list = None):
    """Проверить документ"""

@router.callback_query(F.data.startswith("access_rights_"))
async def manage_access_rights(callback: CallbackQuery, db: Session, roles: list = None):
    """Управление правами доступа"""
```

### Состояния FSM

```python
class UserVerificationStates(StatesGroup):
    """Состояния для системы верификации пользователей"""
    
    # Запрос дополнительной информации
    enter_request_comment = State()
    
    # Управление правами доступа
    enter_apartment_number = State()
    enter_house_number = State()
    enter_yard_name = State()
    enter_access_notes = State()
    
    # Проверка документов
    enter_document_comment = State()
    
    # Отклонение верификации
    enter_rejection_reason = State()
```

## Уровни доступа

### Иерархия прав доступа

1. **APARTMENT** - Квартира (максимум 2 заявителя)
   - Пользователь может подавать заявки только для своей квартиры
   - Ограничение: максимум 2 заявителя на квартиру

2. **HOUSE** - Дом (много квартир)
   - Пользователь может подавать заявки для всего дома
   - Включает все квартиры в доме

3. **YARD** - Двор (много домов)
   - Пользователь может подавать заявки для всего двора
   - Включает все дома и квартиры во дворе

### Логика предоставления прав

```python
def grant_access_rights(self, user_id: int, access_level: AccessLevel, admin_id: int, details: Dict[str, str] = None) -> AccessRights:
    # Проверка ограничения на количество заявителей для квартиры
    if access_level == AccessLevel.APARTMENT:
        apartment_users = self.db.query(AccessRights).filter(
            and_(
                AccessRights.access_level == AccessLevel.APARTMENT,
                AccessRights.apartment_number == details.get('apartment_number'),
                AccessRights.is_active == True
            )
        ).count()
        
        if apartment_users >= 2:
            raise ValueError("Достигнут лимит заявителей для квартиры (максимум 2)")
```

## Типы документов

### Поддерживаемые типы документов

```python
class DocumentType(enum.Enum):
    """Типы документов для верификации"""
    PASSPORT = "passport"                    # Паспорт
    PROPERTY_DEED = "property_deed"          # Свидетельство о собственности
    RENTAL_AGREEMENT = "rental_agreement"    # Договор аренды
    UTILITY_BILL = "utility_bill"            # Квитанция ЖКХ
    OTHER = "other"                          # Другие документы
```

### Статусы верификации

```python
class VerificationStatus(enum.Enum):
    """Статусы верификации"""
    PENDING = "pending"      # Ожидает верификации
    APPROVED = "approved"    # Одобрено
    REJECTED = "rejected"    # Отклонено
    REQUESTED = "requested"  # Запрошена информация
```

## Уведомления

### Система уведомлений

```python
class NotificationService:
    async def send_verification_request_notification(self, user_id: int, info_type: str, comment: str) -> None
    async def send_verification_approved_notification(self, user_id: int) -> None
    async def send_verification_rejected_notification(self, user_id: int) -> None
    async def send_document_approved_notification(self, user_id: int, document_type: str) -> None
    async def send_document_rejected_notification(self, user_id: int, document_type: str, reason: str = None) -> None
    async def send_access_rights_granted_notification(self, user_id: int, access_level: str, details: str = None) -> None
    async def send_access_rights_revoked_notification(self, user_id: int, access_level: str, reason: str = None) -> None
```

## Миграция базы данных

### Применение миграции

Таблицы входят в baseline-миграцию alembic (`0001_prc05_initial_baseline`);
отдельного скрипта больше нет (`scripts/apply_verification_migration.py`
удалён, A9-P2-25). Применение — штатным `alembic upgrade head` (см.
`.claude/skills/uk-deploy/SKILL.md`).

### Созданные таблицы

1. **user_documents** - документы пользователей
2. **user_verifications** - процесс верификации
3. **access_rights** - права доступа

### Добавленные поля в users

- `verification_status` - статус верификации
- `verification_notes` - комментарии администратора
- `verification_date` - дата верификации
- `verified_by` - ID администратора
- `passport_series` - серия паспорта
- `passport_number` - номер паспорта
- `birth_date` - дата рождения

## Интеграция с существующей системой

### Обновленные компоненты

1. **User Management** - добавлена интеграция с верификацией
2. **Admin Panel** - добавлена панель верификации
3. **Notification Service** - добавлены уведомления верификации
4. **Main Application** - зарегистрирован новый роутер

### Клавиатуры

```python
# Основные клавиатуры верификации
get_verification_main_keyboard(stats: Dict[str, int], language: str = 'ru')
get_user_verification_keyboard(user_id: int, language: str = 'ru')
get_document_verification_keyboard(document_id: int, language: str = 'ru')
get_access_rights_keyboard(user_id: int, language: str = 'ru')
```

## Локализация

### Ключи локализации

```json
{
  "verification": {
    "main_title": "🔍 Панель верификации пользователей",
    "stats": "Статистика верификации",
    "pending_users": "Ожидают верификации",
    "verified_users": "Верифицированные",
    "rejected_users": "Отклоненные",
    "status": {
      "pending": "⏳ Ожидает верификации",
      "verified": "✅ Верифицирован",
      "rejected": "❌ Отклонен"
    }
  }
}
```

## Тестирование

### Рекомендуемые тесты

1. **Функциональные тесты:**
   - Создание запроса верификации
   - Загрузка документов
   - Предоставление прав доступа
   - Отправка уведомлений

2. **Тесты безопасности:**
   - Проверка прав доступа
   - Валидация входных данных
   - Защита от SQL injection

3. **Тесты производительности:**
   - Время отклика панели
   - Время загрузки списков
   - Использование памяти

## Известные ограничения

1. **Отсутствие кэширования** - статистика запрашивается каждый раз
2. **Отсутствие rate limiting** - нет ограничений на частоту операций
3. **Отсутствие валидации файлов** - нет проверки типов и размеров файлов

## Планы развития

1. **Кэширование** - добавление Redis для кэширования статистики
2. **Rate limiting** - ограничение частоты операций
3. **Валидация файлов** - проверка типов и размеров документов
4. **Аудит** - логирование всех операций верификации
5. **API** - REST API для интеграции с внешними системами

## Поддержка

При возникновении проблем:

1. Проверьте логи в `logs/verification.log`
2. Убедитесь в корректности миграции базы данных
3. Проверьте права доступа пользователя
4. Обратитесь к документации по API

---

*Документация обновлена: 2024-12-19*
