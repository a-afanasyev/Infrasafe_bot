# Функционал дополнительных дворов для жителей

> _Последнее редактирование: 2025-10-29_

## 📋 Описание

Реализован функционал для добавления дополнительным дворам для жителей. Это позволяет:
- Жителям создавать заявки в нескольких дворах
- Управляющим отвечать за несколько дворов
- Администраторам гибко управлять правами доступа

## 🎯 Логика работы

### По умолчанию:
- Житель имеет доступ **только к двору, где находится его квартира**
- Это определяется автоматически через цепочку: Квартира → Здание → Двор

### Дополнительные дворы:
- Администратор может добавить жителю **дополнительные дворы**
- Житель сможет создавать заявки во всех доступных дворах
- При выборе адреса показываются все дворы (основные + дополнительные)

## 🗄️ База данных

### Таблица `user_yards`
```sql
CREATE TABLE user_yards (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    yard_id INTEGER REFERENCES yards(id) ON DELETE CASCADE,
    granted_by INTEGER REFERENCES users(id),  -- Кто назначил
    comment TEXT,  -- Причина назначения
    granted_at TIMESTAMP DEFAULT NOW(),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP,
    UNIQUE(user_id, yard_id)
);
```

## 📁 Структура кода

### Модели
- `uk_management_bot/database/models/user_yard.py` - модель UserYard
- `User.user_yards` - relationship для доступа к дополнительным дворам
- `Yard.user_yards` - обратная связь

### Сервисы
`uk_management_bot/services/address_service.py`:
- `add_user_yard(session, user_telegram_id, yard_id, granted_by_id, comment)` - добавить двор
- `remove_user_yard(session, user_telegram_id, yard_id)` - удалить двор
- `get_user_additional_yards(session, user_telegram_id)` - получить дополнительные дворы
- `get_user_available_yards(session, user_telegram_id)` - получить ВСЕ дворы (основные + дополнительные)

### Handlers
`uk_management_bot/handlers/user_yards_management.py`:
- `manage_user_yards_{user_id}` - главный экран управления
- `add_user_yard_{user_id}` - добавление двора
- `confirm_add_yard_{user_id}_{yard_id}` - подтверждение добавления
- `remove_user_yard_{user_id}_{yard_id}` - удаление двора

## 🔧 Интеграция в админку

### Вариант 1: Добавить кнопку в просмотр пользователя

В `admin.py` найти функцию отображения детальной информации о пользователе и добавить кнопку:

```python
# В функции, где создается клавиатура для user_detail
buttons.append([InlineKeyboardButton(
    text="🏘️ Управление дворами",
    callback_data=f"manage_user_yards_{user_telegram_id}"
)])
```

### Вариант 2: Добавить в меню управления пользователями

В меню "Управление пользователями" добавить пункт:
```python
buttons.append([InlineKeyboardButton(
    text="🏘️ Дворы пользователей",
    callback_data="user_yards_management"
)])
```

## 📊 Пример использования

### Добавление двора пользователю
```python
from uk_management_bot.services.address_service import AddressService

# В админке, после выбора пользователя и двора
success = AddressService.add_user_yard(
    session=db,
    user_telegram_id=123456789,
    yard_id=5,
    granted_by_id=admin_user.id,
    comment="Управляющий нескольких дворов"
)
```

### Получение всех доступных дворов
```python
# Теперь возвращает основные + дополнительные дворы
yards = AddressService.get_user_available_yards(db, user_telegram_id)
# yards содержит все дворы, доступные пользователю
```

## ✅ Готовые компоненты

- ✅ Модель UserYard создана
- ✅ Relationships добавлены в User и Yard
- ✅ Методы в AddressService реализованы
- ✅ `get_user_available_yards` обновлен (учитывает дополнительные дворы)
- ✅ UI handlers созданы (`user_yards_management.py`)
- ✅ Router зарегистрирован в `handlers/__init__.py`

## 🔄 Следующие шаги

1. **Интеграция в admin.py**: Добавить кнопку "🏘️ Управление дворами" в просмотр пользователя
2. **Тестирование**: Проверить добавление/удаление дворов
3. **Миграция БД**: Запустить бот для автоматического создания таблицы `user_yards`

## 🚀 Запуск

После перезапуска бота:
1. SQLAlchemy автоматически создаст таблицу `user_yards`
2. Функционал сразу доступен через callbacks
3. Житель увидит дополнительные дворы при создании заявки

## 💡 Примеры использования

### Управляющий нескольких дворов
```
Житель Иванов И.И.:
- Основной двор: Двор А (через квартиру)
- Дополнительные: Двор Б, Двор В (добавлены администратором)

При создании заявки видит:
🏘️ Двор А
🏘️ Двор Б
🏘️ Двор В
```

### Обычный житель
```
Житель Петров П.П.:
- Основной двор: Двор А (через квартиру)
- Дополнительных нет

При создании заявки видит:
🏘️ Двор А
```

## 🔐 Безопасность

- ✅ Добавлять дворы могут только администраторы
- ✅ Логируется кто и когда добавил двор
- ✅ Unique constraint предотвращает дубликаты
- ✅ CASCADE DELETE автоматически очищает связи
