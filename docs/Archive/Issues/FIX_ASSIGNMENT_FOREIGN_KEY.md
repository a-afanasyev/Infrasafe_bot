# Исправление: Foreign Key Constraint при назначении конкретного исполнителя

> _Последнее редактирование: 2025-10-29_

**Дата**: 16 октября 2025
**Статус**: ✅ Исправлено

## Проблема

При назначении заявки конкретному исполнителю возникали две ошибки:

1. **Foreign Key Constraint Violation**
2. **MESSAGE_TOO_LONG** при отправке уведомления

### Симптомы

```
ERROR - insert or update on table "requests" violates foreign key constraint "requests_assigned_by_fkey"
DETAIL: Key (assigned_by)=(48617336) is not present in table "users".

ERROR - Ошибка финального назначения исполнителя: Telegram server says - Bad Request: MESSAGE_TOO_LONG
```

## Причина 1: Неправильный assigned_by

В функции `handle_final_executor_assignment_admin()` (строка 2514) использовался `callback.from_user.id`, который является **telegram_id** (например, `48617336`), а не **id** из таблицы users (например, `2`).

```python
# БЫЛО (неправильно):
assignment = assignment_service.assign_to_executor(
    request_number=request_number,
    executor_id=executor_id,
    assigned_by=callback.from_user.id  # ❌ Это telegram_id, не id!
)
```

Foreign key `requests.assigned_by` ссылается на `users.id`, поэтому попытка вставить `telegram_id` вместо `id` вызывала ошибку constraint violation.

## Причина 2: Превышение лимита Telegram

Уведомление исполнителю превышало 4096 символов из-за очень длинных адресов и описаний заявок.

Предыдущие лимиты:
- Адрес: 200 символов
- Описание: 500 символов
- Итого: до 4000 символов

Но этого оказалось недостаточно для некоторых заявок.

## Решение

### 1. Исправлен параметр assigned_by

```python
# СТАЛО (правильно):
@router.callback_query(F.data.startswith("assign_executor_"))
async def handle_final_executor_assignment_admin(callback: CallbackQuery, db: Session, user: User = None):
    # Получаем менеджера (текущий пользователь)
    if not user:
        user = db.query(User).filter(User.telegram_id == callback.from_user.id).first()
        if not user:
            await callback.answer("Ошибка: пользователь не найден", show_alert=True)
            return

    # Используем user.id (из таблицы users)
    assignment = assignment_service.assign_to_executor(
        request_number=request_number,
        executor_id=executor_id,
        assigned_by=user.id  # ✅ Правильно: используем id из таблицы users
    )
```

### 2. Уменьшены лимиты длины текста

```python
# Новые лимиты (строки 2564-2565):
MAX_ADDRESS_LENGTH = 150      # Было: 200
MAX_DESCRIPTION_LENGTH = 300  # Было: 500

# Общий лимит (строка 2581):
if len(notification_text) > 3500:  # Было: 4000
    notification_text = notification_text[:3497] + "..."
```

### 3. Добавлено логирование

```python
logger.info(f"Отправка уведомления исполнителю {executor.telegram_id} (длина: {len(notification_text)} символов)")
```

Это позволяет отслеживать длину сообщений и предотвращать ошибки.

## Изменённые файлы

- ✅ [admin.py:2487-2590](uk_management_bot/handlers/admin.py#L2487) - функция `handle_final_executor_assignment_admin()`

## Связанные исправления

- [FIX_SPECIFIC_ASSIGNMENT_ERROR.md](FIX_SPECIFIC_ASSIGNMENT_ERROR.md) - предыдущее исправление MESSAGE_TOO_LONG

## Технические детали

### Разница между telegram_id и id

**telegram_id** (BIGINT):
- ID пользователя в системе Telegram
- Пример: `48617336`
- Используется для отправки сообщений через Telegram API

**id** (INTEGER):
- Primary key в таблице `users`
- Пример: `2`
- Используется для foreign key связей в базе данных

### Пример некорректного использования

```python
# ❌ НЕПРАВИЛЬНО:
callback.from_user.id  # Возвращает telegram_id (48617336)
# Используется в: assigned_by=48617336
# Результат: Foreign key constraint violation

# ✅ ПРАВИЛЬНО:
user = db.query(User).filter(User.telegram_id == callback.from_user.id).first()
user.id  # Возвращает id из таблицы users (2)
# Используется в: assigned_by=2
# Результат: Успешная вставка
```

---

**Автор**: Claude Code (Sonnet 4.5)
**Дата**: 16 октября 2025, 10:20 UTC
**Статус**: ✅ **ИСПРАВЛЕНО** (ожидает тестирования)
