# Система назначения дежурных специалистов

> _Последнее редактирование: 2025-10-29_

**Дата**: 16.10.2025
**Версия**: 2.0 (Новая система через RequestAssignment)

## Обзор

Система автоматического назначения заявок дежурным специалистам использует новую таблицу `request_assignments` для гибкого управления назначениями.

## Как работает система

### 1. Создание заявки

Когда пользователь создает заявку:
1. Заявка создается со статусом **"Новая"**
2. Заявка **НЕ назначается автоматически**
3. Менеджер видит заявку в списке новых заявок
4. В таблице `request_assignments` **НЕТ записи** (заявка не назначена)

### 2. Назначение дежурному специалисту

Когда менеджер нажимает кнопку **"Дежурный специалист"**:

1. **Определение специализации по категории**:
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
    "HVAC": "hvac"
}
```

2. **Создание группового назначения**:
```sql
INSERT INTO request_assignments (
    request_number,
    assignment_type,
    group_specialization,
    status,
    created_by
) VALUES (
    '251016-007',
    'group',
    'hvac',
    'active',
    2  -- ID менеджера
);
```

3. **Обновление полей заявки**:
```python
request.assignment_type = "group"
request.assigned_group = "hvac"
request.assigned_at = datetime.now()
request.assigned_by = manager.id
request.status = "В работе"  # Переводится в работу
```

4. **Отправка уведомлений**:
   - Всем исполнителям с нужной специализацией
   - Только тем, кто **в активной смене**
   - Уведомление содержит краткую информацию о заявке

### 3. Отображение заявок исполнителю

Когда исполнитель открывает "Мои заявки", система ищет:

**Условия поиска**:
```sql
SELECT r.* FROM requests r
JOIN request_assignments ra ON r.request_number = ra.request_number
WHERE ra.status = 'active'
AND (
    -- 1. Индивидуальные назначения (ВСЕГДА показываем)
    ra.executor_id = 2

    -- 2. Групповые назначения (ТОЛЬКО если в активной смене)
    OR (
        ra.assignment_type = 'group'
        AND ra.group_specialization IN ('electrician', 'plumber', 'hvac', ...)
        AND [user has active shift]
    )
)
AND r.status IN ('Новая', 'В работе', 'Закуп', 'Уточнение')
ORDER BY r.created_at DESC;
```

**Важно**:
- Групповые назначения видны **ТОЛЬКО** исполнителям в активной смене
- Индивидуальные назначения видны **ВСЕГДА**
- Показываются только заявки в **активных статусах**

## Типы назначений

### 1. Групповое назначение (Group Assignment)

**Когда используется**: При нажатии "Дежурный специалист"

**Характеристики**:
- `assignment_type = 'group'`
- `group_specialization` = специализация (например, 'electrician')
- `executor_id` = NULL
- Видна **всем исполнителям** с данной специализацией **в активной смене**

**Пример**:
```sql
INSERT INTO request_assignments (
    request_number,
    assignment_type,
    group_specialization,
    status
) VALUES (
    '251016-007',
    'group',
    'hvac',
    'active'
);
```

### 2. Индивидуальное назначение (Individual Assignment)

**Когда используется**: При выборе конкретного исполнителя

**Характеристики**:
- `assignment_type = 'individual'`
- `executor_id` = ID конкретного исполнителя
- `group_specialization` = NULL
- Видна **только** этому исполнителю (независимо от смены)

**Пример**:
```sql
INSERT INTO request_assignments (
    request_number,
    assignment_type,
    executor_id,
    status
) VALUES (
    '251016-006',
    'individual',
    26,  -- ID Ivan Ivan
    'active'
);
```

## Активные смены

**Проверка активной смены**:
```sql
SELECT * FROM shifts
WHERE user_id = 2
  AND status = 'active'
  AND start_time <= NOW()
  AND (end_time IS NULL OR end_time >= NOW());
```

**Если смена активна**:
- Исполнитель видит ВСЕ групповые назначения своих специализаций
- Исполнитель видит ВСЕ индивидуальные назначения

**Если смены нет**:
- Исполнитель видит ТОЛЬКО индивидуальные назначения
- Групповые назначения **НЕ отображаются**

## Статусы заявок

### Активные статусы (показываются исполнителю)
- **"Новая"** - создана, ожидает начала работы
- **"В работе"** - исполнитель работает над ней
- **"Закуп"** - требуется закупка материалов
- **"Уточнение"** - требуется уточнение у заявителя

### Архивные статусы (НЕ показываются исполнителю)
- **"Выполнена"** - выполнена исполнителем, ожидает проверки
- **"Исполнено"** - проверена менеджером
- **"Принято"** - принята заявителем (финальный статус)
- **"Отменена"** - отменена

## Диагностика проблем

### Проблема: "У исполнителя активная смена, но нет заявок"

**Проверьте:**

1. **Есть ли активная смена?**
```sql
SELECT * FROM shifts
WHERE user_id = 2 AND status = 'active'
AND start_time <= NOW()
AND (end_time IS NULL OR end_time >= NOW());
```

2. **Есть ли заявки с групповыми назначениями?**
```sql
SELECT r.request_number, r.status, r.category, ra.group_specialization
FROM requests r
JOIN request_assignments ra ON r.request_number = ra.request_number
WHERE ra.assignment_type = 'group'
  AND ra.status = 'active'
  AND r.status IN ('Новая', 'В работе', 'Закуп', 'Уточнение')
ORDER BY r.created_at DESC;
```

3. **Совпадают ли специализации?**
```sql
-- Специализации исполнителя
SELECT id, first_name, specialization FROM users WHERE id = 2;

-- Групповые назначения
SELECT DISTINCT group_specialization FROM request_assignments
WHERE assignment_type = 'group' AND status = 'active';
```

4. **В каком статусе заявки?**
```sql
SELECT r.request_number, r.status, ra.group_specialization
FROM requests r
JOIN request_assignments ra ON r.request_number = ra.request_number
WHERE ra.assignment_type = 'group'
  AND ra.group_specialization = 'electrician'
ORDER BY r.created_at DESC
LIMIT 10;
```

### Типичные причины

1. **Все заявки завершены** - статусы "Принято", "Отменена" не показываются
2. **Заявки не назначены** - менеджер не нажал "Дежурный специалист"
3. **Неправильная специализация** - категория заявки не соответствует специализации исполнителя
4. **Смена неактивна** - время смены не покрывает текущий момент

## Пример полного цикла

### Шаг 1: Создание заявки

**Заявитель**:
1. Нажимает "📝 Создать заявку"
2. Выбирает категорию: "Электрика"
3. Заполняет адрес, описание, срочность
4. Подтверждает создание

**Результат в БД**:
```sql
INSERT INTO requests (
    request_number,
    category,
    status,
    ...
) VALUES (
    '251016-010',
    'Электрика',
    'Новая',
    ...
);
-- НЕТ записи в request_assignments!
```

### Шаг 2: Назначение менеджером

**Менеджер**:
1. Открывает список "Новые заявки"
2. Просматривает заявку 251016-010
3. Нажимает "Назначить"
4. Выбирает "Дежурный специалист"

**Система**:
1. Определяет специализацию: "Электрика" → "electrician"
2. Находит исполнителей с специализацией "electrician"
3. Создает групповое назначение:
```sql
INSERT INTO request_assignments (
    request_number,
    assignment_type,
    group_specialization,
    status,
    created_by
) VALUES (
    '251016-010',
    'group',
    'electrician',
    'active',
    2
);
```
4. Обновляет заявку:
```sql
UPDATE requests SET
    assignment_type = 'group',
    assigned_group = 'electrician',
    assigned_at = NOW(),
    assigned_by = 2,
    status = 'В работе'
WHERE request_number = '251016-010';
```
5. Отправляет уведомления всем электрикам в активных сменах

### Шаг 3: Просмотр исполнителем

**Исполнитель (Andrey, user_id=2)**:
1. Переключается на роль "Исполнитель"
2. Нажимает "📋 Мои заявки"

**Система проверяет**:
```sql
-- 1. Есть ли активная смена?
SELECT * FROM shifts WHERE user_id = 2 AND status = 'active' AND ...;
-- Результат: ДА, смена активна

-- 2. Какие специализации у исполнителя?
SELECT specialization FROM users WHERE id = 2;
-- Результат: ['electrician', 'plumber', 'hvac', ...]

-- 3. Ищем заявки
SELECT r.* FROM requests r
JOIN request_assignments ra ON r.request_number = ra.request_number
WHERE ra.status = 'active'
AND (
    ra.executor_id = 2  -- Индивидуальные
    OR (
        ra.assignment_type = 'group'
        AND ra.group_specialization IN ('electrician', 'plumber', 'hvac', ...)
    )
)
AND r.status IN ('Новая', 'В работе', 'Закуп', 'Уточнение');
```

**Результат**: Исполнитель видит заявку 251016-010!

## Миграция старых назначений

Если используется старая система (поле `executor_id` в таблице `requests`), необходимо выполнить миграцию:

```sql
-- Скрипт миграции: migrate_assignments.py
-- Конвертирует старые назначения в новую систему RequestAssignment
```

См. файл: `MIGRATION_REQUEST_ASSIGNMENTS.md`

## Конфигурация

### Маппинг категорий → специализации

**Файл**: `uk_management_bot/handlers/admin.py`, строка 71

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
    "HVAC": "hvac"
}
```

**Добавление новой категории**:
1. Добавьте категорию в `REQUEST_CATEGORIES` (constants.py)
2. Добавьте маппинг в `category_to_specialization`
3. Убедитесь, что специализация существует в системе

### Активные статусы заявок

**Файл**: `uk_management_bot/handlers/requests.py`, строка ~1110

```python
r.status IN ('Новая', 'В работе', 'Закуп', 'Уточнение')
```

## Логирование

Все операции назначения логируются:

```python
logger.info(f"Исполнитель {user.id}: активная смена = {has_active_shift}")
logger.info(f"Исполнитель {user.id}: специализации = {executor_specializations}")
logger.info(f"Заявка {request_number} назначена группе {specialization}")
```

**Просмотр логов**:
```bash
docker-compose -f docker-compose.dev.yml logs app -f | grep -E "активная смена|назначена группе|RequestAssignment"
```

## Таблица request_assignments

**Структура**:
```sql
CREATE TABLE request_assignments (
    id SERIAL PRIMARY KEY,
    request_number VARCHAR(20) NOT NULL REFERENCES requests(request_number),
    assignment_type VARCHAR(20) NOT NULL,  -- 'individual' или 'group'
    executor_id INTEGER REFERENCES users(id),  -- Для individual
    group_specialization VARCHAR(50),  -- Для group
    status VARCHAR(20) DEFAULT 'active',  -- 'active', 'completed', 'cancelled'
    created_by INTEGER REFERENCES users(id),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

**Индексы**:
```sql
CREATE INDEX idx_request_assignments_request_number ON request_assignments(request_number);
CREATE INDEX idx_request_assignments_executor_id ON request_assignments(executor_id);
CREATE INDEX idx_request_assignments_status ON request_assignments(status);
CREATE INDEX idx_request_assignments_group_spec ON request_assignments(group_specialization);
```

## Автор

Claude Code (Sonnet 4.5)

## Дата последнего обновления

16.10.2025
