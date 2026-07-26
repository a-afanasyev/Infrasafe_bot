> ⚫ **УСТАРЕЛО.** Актуальная версия: [docs/tech/REQUESTS.md](./tech/REQUESTS.md).
> Документ ниже сохранён для истории и может расходиться с кодом. Оптимизаторы
> `AssignmentOptimizer`/`GeoOptimizer` удалены (ARC-04); единственный диспетчер —
> `SmartDispatcher`.

# 🔧 ТЕХНИЧЕСКОЕ РУКОВОДСТВО: СИСТЕМА ПЕРЕДАЧИ ЗАЯВОК НА ИСПОЛНЕНИЕ

> _Последнее редактирование: 2026-07-06_

## 🏗️ АРХИТЕКТУРА СИСТЕМЫ

### Общая структура
```
uk_management_bot/
├── models/                    # Модели базы данных
│   ├── request.py            # Модель заявок
│   ├── assignment.py         # Модель назначений
│   ├── comment.py            # Модель комментариев
│   └── user.py               # Модель пользователей
├── services/                 # Бизнес-логика
│   ├── assignment_service.py # Сервис назначений
│   ├── comment_service.py    # Сервис комментариев
│   └── request_service.py    # Сервис заявок
├── handlers/                 # Обработчики команд
│   ├── assignment_handlers.py # Обработчики назначений
│   ├── comment_handlers.py   # Обработчики комментариев
│   └── request_handlers.py   # Обработчики заявок
├── keyboards/                # Клавиатуры
│   ├── assignment_keyboards.py # Клавиатуры назначений
│   ├── comment_keyboards.py  # Клавиатуры комментариев
│   └── request_keyboards.py  # Клавиатуры заявок
└── states/                   # Состояния FSM
    ├── assignment_states.py  # Состояния назначений
    ├── comment_states.py     # Состояния комментариев
    └── request_states.py     # Состояния заявок
```

## 🗄️ МОДЕЛИ БАЗЫ ДАННЫХ

### Request (Заявка)
```python
class Request(Base):
    __tablename__ = 'requests'
    
    id = Column(Integer, primary_key=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    status = Column(String(50), default=REQUEST_STATUS_NEW)
    priority = Column(String(20), default=REQUEST_PRIORITY_NORMAL)
    applicant_id = Column(Integer, ForeignKey('users.id'))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    
    # Связи
    applicant = relationship("User", back_populates="requests")
    assignments = relationship("Assignment", back_populates="request")
    comments = relationship("Comment", back_populates="request")
```

### Assignment (Назначение)
```python
class Assignment(Base):
    __tablename__ = 'assignments'
    
    id = Column(Integer, primary_key=True)
    request_id = Column(Integer, ForeignKey('requests.id'))
    executor_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    assignment_type = Column(String(20), default=ASSIGNMENT_TYPE_INDIVIDUAL)
    specialization = Column(String(100), nullable=True)
    status = Column(String(20), default=ASSIGNMENT_STATUS_ACTIVE)
    assigned_by = Column(Integer, ForeignKey('users.id'))
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Связи
    request = relationship("Request", back_populates="assignments")
    executor = relationship("User", foreign_keys=[executor_id])
    assigned_by_user = relationship("User", foreign_keys=[assigned_by])
```

### Comment (Комментарий)
```python
class Comment(Base):
    __tablename__ = 'comments'
    
    id = Column(Integer, primary_key=True)
    request_id = Column(Integer, ForeignKey('requests.id'))
    user_id = Column(Integer, ForeignKey('users.id'))
    comment_type = Column(String(20), default=COMMENT_TYPE_GENERAL)
    text = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Связи
    request = relationship("Request", back_populates="comments")
    user = relationship("User", back_populates="comments")
```

## 🔧 СЕРВИСЫ

### AssignmentService
Основной сервис для управления назначениями заявок.

#### Ключевые методы:
```python
class AssignmentService:
    def assign_to_group(self, request_id: int, specialization: str, assigned_by: int) -> Assignment
    """Назначить заявку группе исполнителей по специализации"""
    
    def assign_to_executor(self, request_id: int, executor_id: int, assigned_by: int) -> Assignment
    """Назначить заявку конкретному исполнителю"""
    
    def get_executor_assignments(self, executor_id: int) -> List[Assignment]
    """Получить все назначения исполнителя"""
    
    def get_request_assignments(self, request_id: int) -> List[Assignment]
    """Получить все назначения заявки"""
    
    def cancel_previous_assignments(self, request_id: int, new_assignment_id: int) -> None
    """Отменить предыдущие назначения при создании нового"""
```

### CommentService
Сервис для управления комментариями к заявкам.

#### Ключевые методы:
```python
class CommentService:
    def add_comment(self, request_id: int, user_id: int, comment_type: str, text: str) -> Comment
    """Добавить комментарий к заявке"""
    
    def get_request_comments(self, request_id: int) -> List[Comment]
    """Получить все комментарии заявки"""
    
    def get_comments_by_type(self, request_id: int, comment_type: str) -> List[Comment]
    """Получить комментарии определенного типа"""
    
    def format_comments_for_display(self, comments: List[Comment]) -> str
    """Форматировать комментарии для отображения"""
```

### RequestService
Сервис для управления заявками и их статусами.

#### Ключевые методы:
```python
class RequestService:
    def update_request_status(self, request_id: int, new_status: str) -> Optional[Request]
    """Обновить статус заявки"""
    
    def get_user_requests(self, user_id: int, role: str) -> List[Request]
    """Получить заявки пользователя в зависимости от роли"""
    
    def get_request_by_id(self, request_id: int) -> Optional[Request]
    """Получить заявку по ID"""
    
    def create_status_change_comment(self, request_id: int, user_id: int, 
                                   old_status: str, new_status: str, 
                                   additional_comment: str = None) -> Comment
    """Создать комментарий об изменении статуса"""
```

## 🎮 ОБРАБОТЧИКИ

### AssignmentHandlers
Обработчики для управления назначениями заявок.

#### Основные обработчики:
```python
@router.callback_query(lambda c: c.data.startswith("assign_request_"))
async def handle_assign_request(callback: CallbackQuery, state: FSMContext):
    """Обработчик начала процесса назначения заявки"""

@router.callback_query(lambda c: c.data.startswith("assign_to_group_"))
async def handle_assign_to_group(callback: CallbackQuery, state: FSMContext):
    """Обработчик назначения заявки группе"""

@router.callback_query(lambda c: c.data.startswith("assign_to_executor_"))
async def handle_assign_to_executor(callback: CallbackQuery, state: FSMContext):
    """Обработчик назначения заявки исполнителю"""
```

### CommentHandlers
Обработчики для управления комментариями.

#### Основные обработчики:
```python
@router.callback_query(lambda c: c.data.startswith("add_comment_"))
async def handle_add_comment(callback: CallbackQuery, state: FSMContext):
    """Обработчик добавления комментария"""

@router.message(CommentStates.waiting_for_comment_text)
async def handle_comment_text(message: Message, state: FSMContext):
    """Обработчик текста комментария"""

@router.callback_query(lambda c: c.data.startswith("view_comments_"))
async def handle_view_comments(callback: CallbackQuery, state: FSMContext):
    """Обработчик просмотра комментариев"""
```

### RequestHandlers
Обработчики для управления заявками.

#### Основные обработчики:
```python
@router.callback_query(lambda c: c.data.startswith("change_status_"))
async def handle_change_status(callback: CallbackQuery, state: FSMContext):
    """Обработчик изменения статуса заявки"""

@router.callback_query(lambda c: c.data.startswith("view_request_"))
async def handle_view_request(callback: CallbackQuery, state: FSMContext):
    """Обработчик просмотра заявки"""

@router.callback_query(lambda c: c.data.startswith("my_requests_"))
async def handle_my_requests(callback: CallbackQuery, state: FSMContext):
    """Обработчик просмотра своих заявок"""
```

## ⌨️ КЛАВИАТУРЫ

### AssignmentKeyboards
Клавиатуры для управления назначениями.

```python
def get_assignment_type_keyboard(request_id: int) -> InlineKeyboardMarkup:
    """Клавиатура выбора типа назначения"""
    
def get_specialization_keyboard(request_id: int) -> InlineKeyboardMarkup:
    """Клавиатура выбора специализации"""
    
def get_executor_selection_keyboard(request_id: int, executors: List[User]) -> InlineKeyboardMarkup:
    """Клавиатура выбора исполнителя"""
```

### CommentKeyboards
Клавиатуры для управления комментариями.

```python
def get_comment_type_keyboard(request_id: int) -> InlineKeyboardMarkup:
    """Клавиатура выбора типа комментария"""
    
def get_comment_confirmation_keyboard(request_id: int, comment_type: str) -> InlineKeyboardMarkup:
    """Клавиатура подтверждения комментария"""
```

### RequestKeyboards
Клавиатуры для управления заявками.

```python
def get_request_actions_keyboard(request_id: int, user_role: str) -> InlineKeyboardMarkup:
    """Клавиатура действий с заявкой"""
    
def get_status_selection_keyboard(request_id: int, current_status: str) -> InlineKeyboardMarkup:
    """Клавиатура выбора статуса"""
```

## 🔄 СОСТОЯНИЯ FSM

### AssignmentStates
Состояния для процесса назначения заявок.

```python
class AssignmentStates(StatesGroup):
    waiting_for_assignment_type = State()    # Ожидание выбора типа назначения
    waiting_for_specialization = State()     # Ожидание выбора специализации
    waiting_for_executor = State()           # Ожидание выбора исполнителя
    confirming_assignment = State()          # Подтверждение назначения
```

### CommentStates
Состояния для процесса добавления комментариев.

```python
class CommentStates(StatesGroup):
    waiting_for_comment_type = State()       # Ожидание выбора типа комментария
    waiting_for_comment_text = State()       # Ожидание текста комментария
    confirming_comment = State()             # Подтверждение комментария
```

### RequestStates
Состояния для управления заявками.

```python
class RequestStates(StatesGroup):
    waiting_for_status = State()             # Ожидание выбора статуса
    waiting_for_status_comment = State()     # Ожидание комментария к изменению статуса
    viewing_request = State()                # Просмотр заявки
```

## 🔐 СИСТЕМА РОЛЕЙ И ПРАВ

### Роли пользователей:
- **applicant** - Заявитель
- **executor** - Исполнитель
- **manager** - Менеджер
- **admin** - Администратор

### Права доступа:
```python
# Назначение заявок
ASSIGNMENT_PERMISSIONS = {
    'manager': ['assign_to_group', 'assign_to_executor'],
    'admin': ['assign_to_group', 'assign_to_executor'],
    'executor': [],
    'applicant': []
}

# Изменение статусов
STATUS_CHANGE_PERMISSIONS = {
    'manager': ['new', 'in_progress', 'purchase', 'clarification', 'completed'],
    'executor': ['purchase', 'clarification', 'completed'],
    'applicant': ['accepted'],
    'admin': ['new', 'in_progress', 'purchase', 'clarification', 'completed', 'accepted']
}

# Добавление комментариев
COMMENT_PERMISSIONS = {
    'manager': ['clarification', 'purchase', 'report', 'status_change'],
    'executor': ['clarification', 'purchase', 'report'],
    'applicant': ['general'],
    'admin': ['clarification', 'purchase', 'report', 'status_change', 'general']
}
```

## 📊 СТАТУСЫ И ПЕРЕХОДЫ

### Статусы заявок:
```python
REQUEST_STATUSES = {
    'new': 'Новая',
    'in_progress': 'В работе',
    'purchase': 'Закуп',
    'clarification': 'Уточнение',
    'completed': 'Исполнено',
    'accepted': 'Принято'
}
```

### Допустимые переходы статусов:
```python
STATUS_TRANSITIONS = {
    'new': ['in_progress'],
    'in_progress': ['purchase', 'clarification', 'completed'],
    'purchase': ['in_progress'],
    'clarification': ['in_progress'],
    'completed': ['accepted'],
    'accepted': []  # Финальный статус
}
```

### Типы назначений:
```python
ASSIGNMENT_TYPES = {
    'group': 'Группа',
    'individual': 'Индивидуальное'
}
```

### Статусы назначений:
```python
ASSIGNMENT_STATUSES = {
    'active': 'Активное',
    'cancelled': 'Отменено',
    'completed': 'Завершено'
}
```

## 💬 ТИПЫ КОММЕНТАРИЕВ

```python
COMMENT_TYPES = {
    'general': 'Общий',
    'clarification': 'Уточнение',
    'purchase': 'Закупка',
    'report': 'Отчет',
    'status_change': 'Изменение статуса'
}
```

## 🔔 СИСТЕМА УВЕДОМЛЕНИЙ

### Типы уведомлений:
```python
NOTIFICATION_TYPES = {
    'assignment_created': 'Создано назначение',
    'status_changed': 'Изменен статус',
    'comment_added': 'Добавлен комментарий',
    'work_completed': 'Работы завершены',
    'request_accepted': 'Заявка принята'
}
```

### Отправка уведомлений:
```python
async def send_notification(user_id: int, notification_type: str, data: dict):
    """Отправить уведомление пользователю"""
    message = format_notification_message(notification_type, data)
    await bot.send_message(user_id, message)
```

## 🧪 ТЕСТИРОВАНИЕ

### Структура тестов:
```
tests/
├── test_request_assignment_system.py    # Модульные тесты
├── test_integration_full_cycle.py       # Интеграционные тесты
└── conftest.py                          # Конфигурация тестов
```

### Запуск тестов:
```bash
# Все тесты
python -m pytest tests/ -v

# Модульные тесты
python -m pytest tests/test_request_assignment_system.py -v

# Интеграционные тесты
python -m pytest tests/test_integration_full_cycle.py -v

# С покрытием
python -m pytest tests/ --cov=uk_management_bot --cov-report=html
```

### Примеры тестов:
```python
def test_assign_to_group(self):
    """Тест назначения заявки группе"""
    result = self.assignment_service.assign_to_group(
        request_id=1, 
        specialization="Сантехник", 
        assigned_by=2
    )
    assert result is not None
    assert result.assignment_type == ASSIGNMENT_TYPE_GROUP
    assert result.specialization == "Сантехник"

def test_add_comment(self):
    """Тест добавления комментария"""
    result = self.comment_service.add_comment(
        request_id=1,
        user_id=2,
        comment_type=COMMENT_TYPE_CLARIFICATION,
        text="Тестовый комментарий"
    )
    assert result is not None
    assert result.text == "Тестовый комментарий"
```

## 🚀 РАЗВЕРТЫВАНИЕ

### Docker Compose:
```yaml
version: '3.8'
services:
  app:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://user:pass@db:5432/dbname
      - REDIS_URL=redis://redis:6379
    depends_on:
      - db
      - redis
  
  db:
    image: postgres:13
    environment:
      - POSTGRES_DB=dbname
      - POSTGRES_USER=user
      - POSTGRES_PASSWORD=pass
    volumes:
      - postgres_data:/var/lib/postgresql/data
  
  redis:
    image: redis:6-alpine
    volumes:
      - redis_data:/data
```

### Переменные окружения:
```bash
# База данных
DATABASE_URL=postgresql://user:pass@localhost:5432/dbname

# Redis
REDIS_URL=redis://localhost:6379

# Telegram Bot
BOT_TOKEN=your_bot_token_here

# Логирование
LOG_LEVEL=INFO
```

## 📈 МОНИТОРИНГ И ЛОГИРОВАНИЕ

### Логирование:
```python
import logging

logger = logging.getLogger(__name__)

def log_assignment_creation(assignment: Assignment):
    """Логирование создания назначения"""
    logger.info(f"Created assignment {assignment.id} for request {assignment.request_id}")

def log_status_change(request: Request, old_status: str, new_status: str):
    """Логирование изменения статуса"""
    logger.info(f"Request {request.id} status changed from {old_status} to {new_status}")
```

### Метрики:
```python
from prometheus_client import Counter, Histogram

# Счетчики
assignments_created = Counter('assignments_created_total', 'Total assignments created')
comments_added = Counter('comments_added_total', 'Total comments added')
status_changes = Counter('status_changes_total', 'Total status changes')

# Гистограммы
assignment_processing_time = Histogram('assignment_processing_seconds', 
                                     'Time spent processing assignments')
```

## 🔧 ОТЛАДКА

### Общие проблемы:

#### 1. Ошибка импорта модулей
```bash
# Проверьте структуру проекта
ls -la uk_management_bot/

# Проверьте __init__.py файлы
find uk_management_bot/ -name "__init__.py"
```

#### 2. Ошибки базы данных
```python
# Проверьте подключение
from sqlalchemy import create_engine
engine = create_engine(DATABASE_URL)
try:
    connection = engine.connect()
    print("Database connection successful")
except Exception as e:
    print(f"Database connection failed: {e}")
```

#### 3. Ошибки Redis
```python
# Проверьте подключение к Redis
import redis
r = redis.from_url(REDIS_URL)
try:
    r.ping()
    print("Redis connection successful")
except Exception as e:
    print(f"Redis connection failed: {e}")
```

### Отладочные команды:
```python
# Включение отладочного режима
import logging
logging.basicConfig(level=logging.DEBUG)

# Проверка состояния FSM
@router.message(commands=['debug_state'])
async def debug_state(message: Message, state: FSMContext):
    current_state = await state.get_state()
    data = await state.get_data()
    await message.answer(f"State: {current_state}\nData: {data}")
```

## 📚 ДОПОЛНИТЕЛЬНЫЕ РЕСУРСЫ

### Документация:
- [Aiogram 3.x Documentation](https://docs.aiogram.dev/)
- [SQLAlchemy Documentation](https://docs.sqlalchemy.org/)
- [PostgreSQL Documentation](https://www.postgresql.org/docs/)
- [Redis Documentation](https://redis.io/documentation)

### Полезные ссылки:
- [Telegram Bot API](https://core.telegram.org/bots/api)
- [Python FSM Patterns](https://python-patterns.guide/gang-of-four/state/)
- [Database Design Patterns](https://martinfowler.com/eaaCatalog/)

---

**Версия руководства**: 1.0  
**Дата обновления**: 30 августа 2025  
**Автор**: AI Assistant
