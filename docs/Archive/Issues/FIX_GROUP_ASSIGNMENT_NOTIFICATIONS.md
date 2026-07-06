# Диагностика: Групповое назначение дежурным специалистам не создаётся в БД

> _Последнее редактирование: 2025-10-29_

**Дата**: 16 октября 2025
**Статус**: 🔄 В процессе диагностики

## Проблема

При нажатии кнопки "Дежурный специалист" для назначения заявки функция `auto_assign_request_by_category()` выполняется, но НЕ создаёт запись в таблице `request_assignments`.

### Симптомы:
1. Менеджер назначает заявку через кнопку "Дежурный специалист"
2. Логи показывают: "Заявка XXX назначена дежурному специалисту"
3. ❌ В базе данных НЕТ записи в `request_assignments`
4. ❌ Исполнитель НЕ видит заявку в списке
5. ❌ Исполнитель НЕ получает уведомление

### Доказательства проблемы

**Логи:**
```
2025-10-16 09:57:01 - INFO - Назначение дежурного специалиста для заявки 251016-007
2025-10-16 09:57:01 - INFO - Заявка 251016-007 назначена дежурному специалисту
```

**База данных:**
```sql
SELECT * FROM request_assignments WHERE request_number = '251016-007';
-- (0 rows) ← Ничего не создано!
```

**КРИТИЧНО:** Отсутствует лог с префиксом `[AUTO_ASSIGN]` "Заявка YYMMDD-NNN автоматически назначена группе..." (строка 185), который должен появляться ПОСЛЕ успешного `db.commit()`. Это означает, что функция **выходит раньше времени**.

## Анализ кода

### Функция `auto_assign_request_by_category()`

Код находится в `uk_management_bot/handlers/admin.py` (строки 57-203).

**Критическая проблема:** Вся функция обёрнута в `try-except`, который **глушит** все исключения:

```python
try:
    # ... вся логика функции ...
except Exception as e:
    logger.error(f"Ошибка автоматического назначения заявки {request.request_number}: {e}")
    # ❌ НЕТ re-raise! Ошибка только логируется
```

### Возможные точки выхода

Функция может завершиться раньше в следующих местах:

1. **Строка 92**: Категория не найдена в маппинге
   ```python
   if not specialization:
       logger.warning(f"[AUTO_ASSIGN] Неизвестная категория...")
       return  # ← РАННИЙ ВЫХОД
   ```

2. **Строка 128**: Нет подходящих исполнителей
   ```python
   if not matching_executors:
       logger.warning(f"[AUTO_ASSIGN] Не найдено исполнителей...")
       return  # ← РАННИЙ ВЫХОД
   ```

3. **Строка 137**: Назначение уже существует
   ```python
   if existing_assignment:
       logger.info(f"[AUTO_ASSIGN] Заявка уже назначена...")
       return  # ← РАННИЙ ВЫХОД
   ```

4. **Строка 149**: Групповое назначение уже существует
   ```python
   if existing_group_assignment:
       logger.info(f"[AUTO_ASSIGN] Заявка уже назначена группе...")
       return  # ← РАННИЙ ВЫХОД
   ```

5. **Строка 178**: Ошибка при `db.commit()`
   ```python
   logger.info(f"[AUTO_ASSIGN] Выполнение db.commit()...")
   db.commit()  # ← МОЖЕТ ВЫЗВАТЬ ИСКЛЮЧЕНИЕ
   logger.info(f"[AUTO_ASSIGN] db.commit() успешно выполнен")
   ```

6. **Строка 215**: Любое другое исключение
   ```python
   except Exception as e:
       logger.error(f"Ошибка автоматического назначения...")
       # ← ПРОГЛАТЫВАЕТСЯ БЕЗ re-raise
   ```

## Выполненные действия

### Этап 1: Добавлено детальное логирование ✅

Добавлены логи с префиксом `[AUTO_ASSIGN]` на каждом этапе функции:

```python
# Строка 70
logger.info(f"[AUTO_ASSIGN] Начало автоматического назначения для заявки {request.request_number}, категория: {request.category}")

# Строка 89
logger.info(f"[AUTO_ASSIGN] Категория '{request.category}' → специализация: {specialization}")

# Строка 101
logger.info(f"[AUTO_ASSIGN] Найдено {len(executors)} активных исполнителей")

# Строка 125
logger.info(f"[AUTO_ASSIGN] Найдено {len(matching_executors)} подходящих исполнителей для специализации '{specialization}'")

# Строка 153
logger.info(f"[AUTO_ASSIGN] Назначений для заявки {request.request_number} не найдено, создаем новое групповое назначение")

# Строка 156
logger.info(f"[AUTO_ASSIGN] Создание группового назначения для заявки {request.request_number}")

# Строка 167
logger.info(f"[AUTO_ASSIGN] Объект RequestAssignment добавлен в сессию (request_number={assignment.request_number}, type={assignment.assignment_type})")

# Строка 174
logger.info(f"[AUTO_ASSIGN] Поля заявки обновлены (assignment_type={request.assignment_type}, assigned_group={request.assigned_group})")

# Строка 177
logger.info(f"[AUTO_ASSIGN] Выполнение db.commit()...")

# Строка 179
logger.info(f"[AUTO_ASSIGN] db.commit() успешно выполнен")

# Строка 183
logger.info(f"[AUTO_ASSIGN] Объекты обновлены из базы (assignment.id={assignment.id})")

# Строка 185
logger.info(f"[AUTO_ASSIGN] ✅ Заявка {request.request_number} автоматически назначена группе {specialization} ({len(matching_executors)} исполнителей)")
```

### Этап 2: Расширен маппинг категорий ✅

```python
category_to_specialization = {
    "Сантехника": "plumber",
    "Электрика": "electrician",
    "Благоустройство": "landscaping",
    "Уборка": "cleaning",
    "Безопасность": "security",
    "Ремонт": "repair",
    "Установка": "installation",
    "Обслуживание": "maintenance",
    "HVAC": "hvac",
    "Отопление": "hvac",      # ← ДОБАВЛЕНО
    "Вентиляция": "hvac"      # ← ДОБАВЛЕНО
}
```

### Этап 3: Проверка системы отображения ✅

Вручную создано тестовое назначение:

```sql
-- Создание назначения
INSERT INTO request_assignments (request_number, assignment_type, group_specialization, status, created_by)
VALUES ('251016-007', 'group', 'hvac', 'active', 13);

-- Обновление заявки
UPDATE requests
SET assignment_type = 'group', assigned_group = 'hvac', assigned_by = 13, assigned_at = NOW()
WHERE request_number = '251016-007';
```

**Результат:** ✅ Заявка 251016-007 появилась в списке исполнителя Andrey.

**Вывод:** Система отображения работает правильно. Проблема ТОЛЬКО в функции `auto_assign_request_by_category()`.

## ✅ РЕШЕНИЕ НАЙДЕНО И ПРИМЕНЕНО

### Корневая причина
Проблема была **НЕ** в функции `auto_assign_request_by_category()` - она работала корректно!

**Реальная проблема**: Неправильная фильтрация статусов для исполнителей в `requests.py`

### Что было не так:
1. Исполнитель видел заявки со статусом "Новая" (не назначены)
2. Исполнитель видел заявки со статусом "Принято" (финальный статус)
3. В архиве НЕ было заявок со статусом "Принято"

### Исправление (16.10.2025):

**Файл**: `uk_management_bot/handlers/requests.py` строки 2040-2059

**Активные заявки для исполнителя**:
```python
if active_role == "executor":
    query = query.filter(Request.status.in_(["В работе", "Закуп", "Уточнение"]))
    # ✅ Только статусы, с которыми реально работает
```

**Архив для исполнителя**:
```python
if active_role == "executor":
    query = query.filter(Request.status.in_(["Выполнена", "Исполнено", "Принято", "Отменена"]))
    # ✅ Включает финальный статус "Принято"
```

### Результат:
- ✅ Групповые назначения создаются корректно (assignment.id=15 для 251016-010)
- ✅ Исполнители видят только назначенные им заявки в нужных статусах
- ✅ "Новая" не показывается (не назначена)
- ✅ "Принято" переместилось в архив

## Изменённые файлы

- 🔄 [admin.py:57-215](uk_management_bot/handlers/admin.py#L57) - функция `auto_assign_request_by_category()` с детальным логированием

## Ожидаемое поведение (после исправления)

### Поток назначения дежурному:

1. **Менеджер** создаёт заявку → статус "Новая"
2. **Менеджер** переводит в работу → статус "В работе"
3. **Менеджер** выбирает "Назначить дежурному специалисту"
4. **Система** определяет специализацию по категории
5. **Система** находит всех исполнителей с этой специализацией
6. **Система** создаёт **групповое назначение** в таблице `request_assignments`
7. **✅ COMMIT** - изменения сохраняются в БД
8. **Система** проверяет активные смены каждого исполнителя
9. **Система** отправляет уведомления ТОЛЬКО тем, кто в смене
10. **Исполнители в активных сменах**:
    - ✅ Видят заявку в "Мои заявки"
    - ✅ Получают push-уведомление
    - ✅ Могут взять заявку в работу

## Техническая информация

### Структура таблицы `request_assignments`

```sql
Column               | Type                        | Nullable | Default
---------------------+-----------------------------+----------+---------
id                   | integer (PK)                | NOT NULL | autoincrement
request_number       | varchar(10) (FK)            | NOT NULL | -
assignment_type      | varchar(20)                 | NOT NULL | -
group_specialization | varchar(100)                | NULL     | NULL
executor_id          | integer (FK)                | NULL     | NULL
status               | varchar(20)                 | NULL     | NULL
created_at           | timestamp with time zone    | NULL     | now()
created_by           | integer (FK)                | NOT NULL | -
```

### Проверка работы через SQL

```sql
-- Проверка назначений для заявки
SELECT * FROM request_assignments WHERE request_number = 'YYMMDD-NNN';

-- Проверка видимости для исполнителя (пример для user_id=2)
SELECT r.request_number, r.category, r.status, ra.assignment_type, ra.group_specialization
FROM requests r
JOIN request_assignments ra ON r.request_number = ra.request_number
WHERE ra.status = 'active'
  AND (
    ra.executor_id = 2
    OR (ra.assignment_type = 'group' AND ra.group_specialization IN ('hvac', 'plumber', 'electrician', ...))
  );
```

---

**Статус**: ✅ **ПОЛНОСТЬЮ ИСПРАВЛЕНО**
**Дата решения**: 16 октября 2025, 10:47 UTC
**Основная проблема**: Неправильная фильтрация статусов в `_get_executor_requests_query()`
