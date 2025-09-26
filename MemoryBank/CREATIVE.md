# 🎨 CREATIVE: Система передачи заявок на исполнение

## 📅 ДАТА ПРОЕКТИРОВАНИЯ
**Дата**: 25 августа 2025  
**Время**: 08:35 UTC  
**Сложность**: Level 4 (Enterprise Development)

## 🎯 ДЕТАЛЬНЫЙ АНАЛИЗ ТРЕБОВАНИЙ

### 📋 **1️⃣ ПРОБЛЕМА: Система назначения заявок**

#### **Текущее состояние:**
- Заявки создаются заявителями
- Нет системы назначения исполнителям
- Нет группового назначения по специализациям
- Нет адресного назначения конкретным исполнителям

#### **Требования:**
- **Групповое назначение**: заявка назначается группе исполнителей с нужной компетенцией
- **Адресное назначение**: заявка прикрепляется к конкретному исполнителю
- **Условная видимость**: заявки в "Мои заявки" только после статуса "В работе"

### 📋 **2️⃣ ПРОБЛЕМА: Управление статусами заявок**

#### **Текущие статусы:**
- Новая, Принята, В работе, Выполнена, Отменена

#### **Новые требования:**
- **"Закуп"**: исполнитель указывает необходимые материалы
- **"В работе"**: возврат после закупки
- **"Уточнение"**: запрос дополнительной информации
- **"Исполнено"**: завершение работы с отчетом
- **"Принято"**: финальное принятие заявителем

### 📋 **3️⃣ ПРОБЛЕМА: Система комментариев**

#### **Текущее состояние:**
- Нет системы комментариев
- Нет истории изменений
- Нет связи комментариев со статусами

#### **Требования:**
- Сохранение всех комментариев
- Привязка к изменениям статуса
- История доступна всем участникам

### 📋 **4️⃣ ПРОБЛЕМА: Отчеты и уведомления**

#### **Текущее состояние:**
- Базовые уведомления о статусах
- Нет отчетов о выполнении
- Нет системы принятия работ

#### **Требования:**
- Отчет при статусе "Исполнено"
- Предложение "принять" заявку
- Уведомления о всех изменениях

## 🏗️ **2️⃣ ОПЦИИ: Архитектурные подходы**

### 🎯 **ОПЦИЯ A: Минимальные изменения существующей системы**

#### **Преимущества:**
- ✅ Быстрая реализация
- ✅ Минимальные риски
- ✅ Совместимость с существующим кодом

#### **Недостатки:**
- ❌ Ограниченная функциональность
- ❌ Неполное покрытие требований
- ❌ Сложность расширения в будущем

#### **Реализация:**
- Расширение существующей модели Request
- Добавление полей для комментариев и назначений
- Модификация существующих сервисов

### 🎯 **ОПЦИЯ B: Модульная архитектура с новыми компонентами**

#### **Преимущества:**
- ✅ Полное покрытие требований
- ✅ Масштабируемость
- ✅ Четкое разделение ответственности
- ✅ Легкость тестирования

#### **Недостатки:**
- ❌ Больше времени на разработку
- ❌ Сложность интеграции
- ❌ Больше файлов и компонентов

#### **Реализация:**
- Новые модели: RequestComment, RequestAssignment
- Новые сервисы: AssignmentService, CommentService
- Расширение существующих сервисов

### 🎯 **ОПЦИЯ C: Микросервисная архитектура**

#### **Преимущества:**
- ✅ Максимальная масштабируемость
- ✅ Независимое развертывание
- ✅ Технологическая гибкость

#### **Недостатки:**
- ❌ Избыточная сложность для текущих требований
- ❌ Сложность развертывания
- ❌ Высокие требования к инфраструктуре

## 📊 **3️⃣ АНАЛИЗ: Сравнение опций**

| Критерий | Опция A | Опция B | Опция C |
|----------|---------|---------|---------|
| **Время реализации** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐ |
| **Покрытие требований** | ⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| **Масштабируемость** | ⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| **Сложность интеграции** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐ |
| **Совместимость** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐ |
| **Тестируемость** | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| **Поддержка** | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐ |

### 🔍 **Ключевые инсайты:**
- **Опция A** слишком ограничена для требований
- **Опция C** избыточна для текущих потребностей
- **Опция B** обеспечивает оптимальный баланс

## 🎯 **4️⃣ РЕШЕНИЕ: Модульная архитектура (Опция B)**

### ✅ **Выбранная архитектура:**
Модульная архитектура с новыми компонентами, обеспечивающая полное покрытие требований при разумной сложности реализации.

### 🏗️ **Архитектурные принципы:**
1. **Разделение ответственности** - каждый компонент отвечает за свою область
2. **Слабая связанность** - компоненты взаимодействуют через четко определенные интерфейсы
3. **Высокая когезия** - связанная функциональность группируется вместе
4. **Расширяемость** - легко добавлять новые функции
5. **Тестируемость** - каждый компонент можно тестировать независимо

## 🗄️ **5️⃣ ГИДЫ РЕАЛИЗАЦИИ: Детальные спецификации**

### 📊 **Модели базы данных:**

#### **1. Расширение модели Request:**
```python
class Request(Base):
    __tablename__ = "requests"
    
    # Существующие поля...
    
    # Новые поля для назначений
    assignment_type = Column(String(20), nullable=True)  # 'group' или 'individual'
    assigned_group = Column(String(100), nullable=True)  # специализация группы
    assigned_at = Column(DateTime(timezone=True), nullable=True)
    assigned_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    # Новые поля для материалов и отчетов
    purchase_materials = Column(Text, nullable=True)  # материалы для закупки
    completion_report = Column(Text, nullable=True)   # отчет о выполнении
    completion_media = Column(JSON, default=list)     # медиафайлы отчета
    
    # Связи
    comments = relationship("RequestComment", back_populates="request")
    assignments = relationship("RequestAssignment", back_populates="request")
```

#### **2. Модель RequestComment:**
```python
class RequestComment(Base):
    __tablename__ = "request_comments"
    
    id = Column(Integer, primary_key=True, index=True)
    request_id = Column(Integer, ForeignKey("requests.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Содержимое комментария
    comment_text = Column(Text, nullable=False)
    comment_type = Column(String(50), nullable=False)  # 'status_change', 'clarification', 'purchase', 'report'
    
    # Контекст комментария
    previous_status = Column(String(50), nullable=True)
    new_status = Column(String(50), nullable=True)
    
    # Системные поля
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Связи
    request = relationship("Request", back_populates="comments")
    user = relationship("User")
```

#### **3. Модель RequestAssignment:**
```python
class RequestAssignment(Base):
    __tablename__ = "request_assignments"
    
    id = Column(Integer, primary_key=True, index=True)
    request_id = Column(Integer, ForeignKey("requests.id"), nullable=False)
    
    # Тип назначения
    assignment_type = Column(String(20), nullable=False)  # 'group' или 'individual'
    
    # Для группового назначения
    group_specialization = Column(String(100), nullable=True)
    
    # Для индивидуального назначения
    executor_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    # Статус назначения
    status = Column(String(20), default="active")  # 'active', 'cancelled', 'completed'
    
    # Системные поля
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Связи
    request = relationship("Request", back_populates="assignments")
    executor = relationship("User", foreign_keys=[executor_id])
    creator = relationship("User", foreign_keys=[created_by])
```

### 🔧 **Сервисы:**

#### **1. AssignmentService:**
```python
class AssignmentService:
    """Сервис для управления назначениями заявок"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def assign_to_group(self, request_id: int, specialization: str, assigned_by: int) -> RequestAssignment:
        """Назначение заявки группе исполнителей по специализации"""
        
    def assign_to_executor(self, request_id: int, executor_id: int, assigned_by: int) -> RequestAssignment:
        """Назначение заявки конкретному исполнителю"""
        
    def get_executor_assignments(self, executor_id: int, status: str = "active") -> List[RequestAssignment]:
        """Получение назначений исполнителя"""
        
    def get_request_assignments(self, request_id: int) -> List[RequestAssignment]:
        """Получение всех назначений заявки"""
        
    def cancel_assignment(self, assignment_id: int, cancelled_by: int) -> bool:
        """Отмена назначения"""
        
    def get_available_executors(self, specialization: str) -> List[User]:
        """Получение доступных исполнителей по специализации"""
```

#### **2. CommentService:**
```python
class CommentService:
    """Сервис для управления комментариями к заявкам"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def add_comment(self, request_id: int, user_id: int, comment_text: str, 
                   comment_type: str, previous_status: str = None, 
                   new_status: str = None) -> RequestComment:
        """Добавление комментария к заявке"""
        
    def get_request_comments(self, request_id: int) -> List[RequestComment]:
        """Получение всех комментариев заявки"""
        
    def format_comments_for_display(self, comments: List[RequestComment], language: str = "ru") -> str:
        """Форматирование комментариев для отображения"""
        
    def add_status_change_comment(self, request_id: int, user_id: int, 
                                previous_status: str, new_status: str, 
                                additional_comment: str = None) -> RequestComment:
        """Добавление комментария при изменении статуса"""
```

#### **3. Расширение RequestService:**
```python
class RequestService:
    """Расширенный сервис для работы с заявками"""
    
    # Существующие методы...
    
    def assign_request(self, request_id: int, assignment_type: str, 
                      target: Union[str, int], assigned_by: int) -> Request:
        """Назначение заявки (группе или исполнителю)"""
        
    def change_status_with_comment(self, request_id: int, new_status: str, 
                                 user_id: int, comment: str = None) -> Request:
        """Изменение статуса с комментарием"""
        
    def get_executor_requests(self, executor_id: int, status: str = None) -> List[Request]:
        """Получение заявок исполнителя"""
        
    def create_completion_report(self, request_id: int, executor_id: int, 
                               report_text: str, media_files: List[str] = None) -> Request:
        """Создание отчета о выполнении"""
        
    def approve_request(self, request_id: int, user_id: int) -> Request:
        """Принятие заявки заявителем"""
```

### 🎨 **Пользовательский интерфейс:**

#### **1. Клавиатуры для менеджеров:**
```python
def get_request_assignment_keyboard(request_id: int, language: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура назначения заявки"""
    
def get_executor_selection_keyboard(specialization: str, language: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура выбора исполнителя"""
    
def get_status_management_keyboard(request_id: int, current_status: str, language: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура управления статусами"""
```

#### **2. Клавиатуры для исполнителей:**
```python
def get_executor_requests_keyboard(language: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура 'Мои заявки'"""
    
def get_request_actions_keyboard(request_id: int, status: str, language: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура действий с заявкой"""
    
def get_status_change_keyboard(request_id: int, current_status: str, language: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура изменения статуса"""
```

#### **3. FSM состояния:**
```python
class RequestAssignmentStates(StatesGroup):
    """Состояния для назначения заявок"""
    waiting_for_assignment_type = State()
    waiting_for_specialization = State()
    waiting_for_executor = State()
    waiting_for_confirmation = State()

class RequestCommentStates(StatesGroup):
    """Состояния для комментариев"""
    waiting_for_comment = State()
    waiting_for_purchase_materials = State()
    waiting_for_completion_report = State()

class RequestApprovalStates(StatesGroup):
    """Состояния для принятия заявок"""
    waiting_for_approval = State()
    waiting_for_rating = State()
```

### 📝 **Обработчики:**

#### **1. Обработчики назначения заявок:**
```python
@router.callback_query(F.data.startswith("assign_request_"))
async def handle_request_assignment_start(callback: CallbackQuery, state: FSMContext, db: Session):
    """Начало процесса назначения заявки"""

@router.callback_query(F.data.startswith("assign_group_"))
async def handle_group_assignment(callback: CallbackQuery, state: FSMContext, db: Session):
    """Назначение заявки группе исполнителей"""

@router.callback_query(F.data.startswith("assign_executor_"))
async def handle_executor_assignment(callback: CallbackQuery, state: FSMContext, db: Session):
    """Назначение заявки конкретному исполнителю"""
```

#### **2. Обработчики управления статусами:**
```python
@router.callback_query(F.data.startswith("status_"))
async def handle_status_change(callback: CallbackQuery, state: FSMContext, db: Session):
    """Изменение статуса заявки"""

@router.callback_query(F.data == "status_purchase")
async def handle_purchase_status(callback: CallbackQuery, state: FSMContext, db: Session):
    """Перевод заявки в статус 'Закуп'"""

@router.callback_query(F.data == "status_completed")
async def handle_completion_status(callback: CallbackQuery, state: FSMContext, db: Session):
    """Перевод заявки в статус 'Исполнено'"""
```

#### **3. Обработчики комментариев:**
```python
@router.callback_query(F.data.startswith("add_comment_"))
async def handle_add_comment(callback: CallbackQuery, state: FSMContext, db: Session):
    """Добавление комментария к заявке"""

@router.message(RequestCommentStates.waiting_for_comment)
async def handle_comment_text(message: Message, state: FSMContext, db: Session):
    """Обработка текста комментария"""
```

### 🔔 **Система уведомлений:**

#### **1. Новые типы уведомлений:**
```python
# Константы для типов уведомлений
NOTIFICATION_TYPE_REQUEST_ASSIGNED = "request_assigned"
NOTIFICATION_TYPE_STATUS_CHANGED = "status_changed"
NOTIFICATION_TYPE_PURCHASE_REQUESTED = "purchase_requested"
NOTIFICATION_TYPE_COMPLETION_REPORT = "completion_report"
NOTIFICATION_TYPE_APPROVAL_REQUESTED = "approval_requested"
```

#### **2. Шаблоны уведомлений:**
```python
def get_assignment_notification_text(request: Request, assignment: RequestAssignment, language: str = "ru") -> str:
    """Текст уведомления о назначении заявки"""

def get_status_change_notification_text(request: Request, previous_status: str, new_status: str, language: str = "ru") -> str:
    """Текст уведомления об изменении статуса"""

def get_completion_report_notification_text(request: Request, language: str = "ru") -> str:
    """Текст уведомления о завершении работы"""
```

### 📊 **Локализация:**

#### **1. Новые ключи локализации:**
```json
{
  "request_assignment": {
    "title": "Назначение заявки",
    "select_type": "Выберите тип назначения:",
    "group_assignment": "Назначить группе исполнителей",
    "individual_assignment": "Назначить конкретному исполнителю",
    "select_specialization": "Выберите специализацию:",
    "select_executor": "Выберите исполнителя:",
    "assignment_confirmation": "Подтвердите назначение:",
    "assignment_success": "Заявка успешно назначена!"
  },
  "status_management": {
    "status_change": "Изменение статуса",
    "purchase_materials": "Укажите необходимые материалы:",
    "completion_report": "Создайте отчет о выполнении:",
    "status_changed": "Статус изменен на: {status}",
    "comment_required": "Комментарий обязателен для этого статуса"
  },
  "comments": {
    "add_comment": "Добавить комментарий",
    "comment_placeholder": "Введите ваш комментарий...",
    "comment_added": "Комментарий добавлен",
    "comments_history": "История комментариев"
  }
}
```

## 🎯 **КРИТЕРИИ УСПЕХА**

### ✅ **Функциональные критерии:**
- [ ] Возможность назначения заявок группам и конкретным исполнителям
- [ ] Корректная работа всех статусов заявок
- [ ] Сохранение всех комментариев с привязкой к статусам
- [ ] Отправка отчетов заявителям при завершении
- [ ] Система принятия работ заявителями

### ✅ **Технические критерии:**
- [ ] Все тесты проходят успешно
- [ ] Нет критических ошибок
- [ ] Производительность не снизилась
- [ ] Совместимость с существующими функциями
- [ ] Модульная архитектура легко расширяется

### ✅ **Пользовательские критерии:**
- [ ] Интуитивно понятный интерфейс
- [ ] Быстрая работа системы
- [ ] Корректные уведомления
- [ ] Полная функциональность через Telegram

## 🚀 **СЛЕДУЮЩИЕ ШАГИ**

### 📋 **Немедленные действия:**
1. **Создать миграции базы данных** для новых моделей
2. **Реализовать новые сервисы** (AssignmentService, CommentService)
3. **Расширить RequestService** новыми методами
4. **Создать обработчики** для всех функций

### 🔄 **Планирование реализации:**
- **День 1**: Миграции и модели
- **День 2**: Сервисы и бизнес-логика
- **День 3**: Обработчики и интерфейс
- **День 4**: Тестирование и интеграция

---
**Статус**: Детальное проектирование завершено  
**Следующий этап**: IMPLEMENT - реализация компонентов
