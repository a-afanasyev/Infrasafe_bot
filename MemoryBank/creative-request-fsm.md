# CREATIVE PHASE: FSM для создания заявок

## 📌 CREATIVE PHASE START: Request FSM Architecture
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

### 1️⃣ PROBLEM
**Description**: Проектирование FSM (Finite State Machine) для создания заявок с 7 состояниями
**Requirements**: 
- Удобный пользовательский интерфейс с клавиатурами
- Валидация всех вводимых данных
- Сохранение промежуточных данных в FSM
- Обработка медиафайлов (опционально)
- Подтверждение заявки перед сохранением
**Constraints**: 
- Должно работать с существующей моделью Request
- Совместимость с Aiogram 3.x
- Поддержка отмены и возврата на любом этапе

### 2️⃣ OPTIONS
**Option A**: Простая FSM с линейным потоком - последовательные состояния без ветвления
**Option B**: FSM с условными переходами - возможность пропуска опциональных состояний
**Option C**: Модульная FSM с отдельными обработчиками - разделение логики по файлам

### 3️⃣ ANALYSIS
| Criterion | Linear FSM | Conditional FSM | Modular FSM |
|-----------|------------|-----------------|-------------|
| Complexity | ⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ |
| Maintainability | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| User Experience | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| Extensibility | ⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| Testing | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ |

**Key Insights**:
- Модульная FSM обеспечивает лучшую масштабируемость и тестируемость
- Условные переходы улучшают пользовательский опыт
- Линейный подход проще для реализации, но менее гибкий

### 4️⃣ DECISION
**Selected**: Option C: Модульная FSM с отдельными обработчиками
**Rationale**: Лучший баланс между сложностью, поддерживаемостью и расширяемостью. Позволяет легко добавлять новые состояния и тестировать компоненты отдельно.

### 5️⃣ IMPLEMENTATION NOTES
- Создать отдельный файл `handlers/requests.py` для FSM обработчиков
- Использовать `keyboards/requests.py` для клавиатур выбора
- Реализовать валидацию в `utils/validators.py`
- Сохранять промежуточные данные в FSM context
- Добавить обработку отмены на каждом этапе

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📌 CREATIVE PHASE END

## 📋 ДЕТАЛЬНОЕ ПРОЕКТИРОВАНИЕ

### 🏗️ АРХИТЕКТУРА FSM

#### Структура файлов:
```
handlers/
├── requests.py          # Основные FSM обработчики
├── base.py             # Базовые команды (уже существует)
└── __init__.py

keyboards/
├── requests.py         # Клавиатуры для заявок
├── base.py            # Базовые клавиатуры (уже существует)
└── __init__.py

utils/
├── validators.py       # Валидация данных заявок
├── constants.py        # Константы (уже существует)
└── helpers.py         # Вспомогательные функции (уже существует)
```

#### FSM Состояния и переходы:
```python
class RequestStates(StatesGroup):
    category = State()      # Выбор категории
    address = State()       # Ввод адреса
    description = State()   # Описание проблемы
    urgency = State()       # Выбор срочности
    apartment = State()     # Номер квартиры
    media = State()         # Медиафайлы (опционально)
    confirm = State()       # Подтверждение
```

#### Структура данных FSM:
```python
# Данные, сохраняемые в FSM context
class RequestData:
    category: str = None
    address: str = None
    description: str = None
    urgency: str = None
    apartment: str = None
    media_files: List[str] = []  # file_ids
    user_id: int = None
```

### 🎮 ОБРАБОТЧИКИ FSM

#### 1. Начало создания заявки:
```python
@router.message(F.text == "📝 Создать заявку")
async def start_request_creation(message: Message, state: FSMContext):
    """Начало создания заявки"""
    await state.set_state(RequestStates.category)
    await message.answer(
        "Выберите категорию заявки:",
        reply_markup=get_categories_keyboard()
    )
```

#### 2. Обработка выбора категории:
```python
@router.message(RequestStates.category)
async def process_category(message: Message, state: FSMContext):
    """Обработка выбора категории"""
    if message.text == "❌ Отмена":
        await cancel_request(message, state)
        return
    
    if message.text not in REQUEST_CATEGORIES:
        await message.answer("Пожалуйста, выберите категорию из списка")
        return
    
    await state.update_data(category=message.text)
    await state.set_state(RequestStates.address)
    await message.answer(
        "Введите адрес:",
        reply_markup=get_cancel_keyboard()
    )
```

#### 3. Обработка ввода адреса:
```python
@router.message(RequestStates.address)
async def process_address(message: Message, state: FSMContext):
    """Обработка ввода адреса"""
    if message.text == "❌ Отмена":
        await cancel_request(message, state)
        return
    
    if not validate_address(message.text):
        await message.answer("Адрес должен содержать минимум 10 символов")
        return
    
    await state.update_data(address=message.text)
    await state.set_state(RequestStates.description)
    await message.answer(
        "Опишите проблему:",
        reply_markup=get_cancel_keyboard()
    )
```

### ⌨️ КЛАВИАТУРЫ

#### Категории заявок:
```python
def get_categories_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура с категориями заявок"""
    keyboard = []
    categories = [
        "⚡ Электрика", "🚰 Сантехника", "🔥 Отопление",
        "💨 Вентиляция", "🛗 Лифт", "🧹 Уборка",
        "🌳 Благоустройство", "🔒 Безопасность",
        "📺 Интернет/ТВ", "📋 Другое"
    ]
    
    # Размещаем по 2 кнопки в ряду
    for i in range(0, len(categories), 2):
        row = [categories[i]]
        if i + 1 < len(categories):
            row.append(categories[i + 1])
        keyboard.append(row)
    
    keyboard.append(["❌ Отмена"])
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)
```

#### Уровни срочности:
```python
def get_urgency_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура с уровнями срочности"""
    keyboard = [
        ["🟢 Обычная"],
        ["🟡 Срочная"],
        ["🔴 Критическая"],
        ["❌ Отмена"]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)
```

### 🔍 ВАЛИДАЦИЯ ДАННЫХ

#### Функции валидации:
```python
def validate_address(address: str) -> bool:
    """Валидация адреса"""
    return len(address.strip()) >= 10

def validate_description(description: str) -> bool:
    """Валидация описания"""
    return len(description.strip()) >= 20

def validate_apartment(apartment: str) -> bool:
    """Валидация номера квартиры"""
    return apartment.isdigit() and len(apartment) > 0

def validate_media_file(file_size: int, file_type: str) -> bool:
    """Валидация медиафайла"""
    max_size = 20 * 1024 * 1024  # 20MB
    allowed_types = ['photo', 'video']
    return file_size <= max_size and file_type in allowed_types
```

### 📸 ОБРАБОТКА МЕДИАФАЙЛОВ

#### Обработчик медиафайлов:
```python
@router.message(RequestStates.media, F.photo | F.video)
async def process_media(message: Message, state: FSMContext):
    """Обработка медиафайлов"""
    data = await state.get_data()
    media_files = data.get('media_files', [])
    
    if len(media_files) >= 5:
        await message.answer("Максимум 5 файлов")
        return
    
    # Получаем file_id
    if message.photo:
        file_id = message.photo[-1].file_id
    else:
        file_id = message.video.file_id
    
    media_files.append(file_id)
    await state.update_data(media_files=media_files)
    
    await message.answer(
        f"Файл добавлен ({len(media_files)}/5). Отправьте еще файлы или нажмите 'Продолжить'",
        reply_markup=get_media_keyboard()
    )
```

### ✅ ПОДТВЕРЖДЕНИЕ ЗАЯВКИ

#### Показ сводки:
```python
@router.message(RequestStates.confirm)
async def show_confirmation(message: Message, state: FSMContext):
    """Показать сводку заявки для подтверждения"""
    data = await state.get_data()
    
    summary = f"""
📋 **Сводка заявки:**

🏷️ **Категория**: {data['category']}
📍 **Адрес**: {data['address']}
📝 **Описание**: {data['description']}
⚡ **Срочность**: {data['urgency']}
🏠 **Квартира**: {data['apartment']}
📸 **Файлов**: {len(data.get('media_files', []))}

Подтвердите создание заявки:
    """
    
    await message.answer(
        summary,
        reply_markup=get_confirmation_keyboard()
    )
```

#### Сохранение заявки:
```python
async def save_request(data: dict, user_id: int, db: Session) -> bool:
    """Сохранение заявки в базу данных"""
    try:
        request = Request(
            category=data['category'],
            address=data['address'],
            description=data['description'],
            urgency=data['urgency'],
            apartment=data['apartment'],
            media_files=','.join(data.get('media_files', [])),
            user_id=user_id,
            status='Новая'
        )
        
        db.add(request)
        db.commit()
        return True
    except Exception as e:
        logger.error(f"Ошибка сохранения заявки: {e}")
        return False
```

### 🔄 ОБРАБОТКА ОТМЕНЫ И ВОЗВРАТА

#### Отмена заявки:
```python
async def cancel_request(message: Message, state: FSMContext):
    """Отмена создания заявки"""
    await state.clear()
    await message.answer(
        "Создание заявки отменено.",
        reply_markup=get_main_keyboard()
    )
```

#### Возврат к предыдущему состоянию:
```python
@router.message(F.text == "🔙 Назад")
async def go_back_in_fsm(message: Message, state: FSMContext):
    """Возврат к предыдущему состоянию в FSM"""
    current_state = await state.get_state()
    
    # Логика возврата к предыдущему состоянию
    if current_state == RequestStates.confirm:
        await state.set_state(RequestStates.media)
        await message.answer("Вернулись к загрузке файлов")
    elif current_state == RequestStates.media:
        await state.set_state(RequestStates.apartment)
        await message.answer("Вернулись к вводу номера квартиры")
    # ... и так далее
```

### 📊 КРИТЕРИИ УСПЕХА

#### Функциональные требования:
- [ ] Пользователь может начать создание заявки кнопкой "Создать заявку"
- [ ] Все 7 состояний FSM работают корректно
- [ ] Клавиатуры отображаются и обрабатываются
- [ ] Валидация данных работает на каждом этапе
- [ ] Промежуточные данные сохраняются в FSM
- [ ] Медиафайлы загружаются и сохраняются (опционально)
- [ ] Заявка сохраняется в базу данных после подтверждения
- [ ] Обработка отмены и возврата работает корректно

#### Технические требования:
- [ ] Код написан с учетом масштабируемости
- [ ] Обработка ошибок на всех этапах
- [ ] Логирование всех операций
- [ ] Совместимость с существующей архитектурой
- [ ] Готовность к тестированию

### ⏱️ ПЛАН РЕАЛИЗАЦИИ

#### День 1: Основные состояния (1-3)
- Создать FSM структуру
- Реализовать состояния category, address, description
- Создать клавиатуры для выбора

#### День 2: Дополнительные состояния (4-5)
- Реализовать состояния urgency, apartment
- Добавить валидацию данных
- Создать клавиатуры срочности

#### День 3: Медиафайлы (6)
- Реализовать состояние media
- Добавить обработку фото и видео
- Создать валидацию файлов

#### День 4: Подтверждение (7)
- Реализовать состояние confirm
- Создать сводку заявки
- Добавить сохранение в БД

#### День 5: Тестирование и отладка
- Протестировать все состояния
- Исправить ошибки
- Оптимизировать производительность

### 🎯 ГОТОВ К РЕАЛИЗАЦИИ

Детальное проектирование FSM для создания заявок завершено. Архитектура определена, технические решения приняты, план реализации составлен. Готов к переходу в IMPLEMENT режим для начала разработки. 