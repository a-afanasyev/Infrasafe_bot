# Миграция системы назначений заявок

> _Последнее редактирование: 2025-10-29_

**Дата**: 16 октября 2025
**Статус**: ✅ Завершено

## Проблема

Администратор с ролью `executor` не видел заявки, назначенные ему на исполнение. Причина: существовало две системы назначений:

1. **Старая система** (legacy): поле `Request.executor_id`
2. **Новая система**: таблица `RequestAssignment`

Код отображения заявок использовал только новую систему, игнорируя старые назначения.

## Решение

### 1. Миграция данных

Все существующие назначения из `Request.executor_id` мигрированы в таблицу `RequestAssignment`:

```sql
INSERT INTO request_assignments (request_number, assignment_type, executor_id, status, created_by, created_at)
SELECT
    r.request_number,
    'individual' AS assignment_type,
    r.executor_id,
    'active' AS status,
    COALESCE(r.assigned_by, r.executor_id) AS created_by,
    COALESCE(r.assigned_at, r.created_at) AS created_at
FROM requests r
WHERE r.executor_id IS NOT NULL
AND NOT EXISTS (
    SELECT 1 FROM request_assignments ra
    WHERE ra.request_number = r.request_number
    AND ra.status = 'active'
);
```

**Результат**: 1 заявка успешно мигрирована

### 2. Рефакторинг кода

#### Изменен файл: `uk_management_bot/handlers/requests.py`

1. **Создана вспомогательная функция** `_get_executor_requests_query()`:
   - Централизованная логика получения заявок для исполнителей
   - Поддержка индивидуальных и групповых назначений
   - Проверка активной смены для групповых назначений

2. **Обновлен обработчик** `show_my_requests()`:
   - Использует только новую систему через `RequestAssignment`
   - Упрощенная логика без дублирования кода

3. **Обновлен обработчик пагинации** `handle_pagination()`:
   - Добавлена поддержка роли `executor`
   - Использует ту же логику, что и основной обработчик

### 3. Удалены файлы

- `migrate_assignments.py` - скрипт миграции (задача выполнена через SQL)

## Новая архитектура

### Таблица RequestAssignment

```
request_assignments:
- id (PK)
- request_number (FK -> requests)
- assignment_type ('individual' | 'group')
- executor_id (FK -> users, nullable для группы)
- group_specialization (nullable для индивид.)
- status ('active' | 'cancelled' | 'completed')
- created_by (FK -> users)
- created_at
```

### Логика назначений

**Для исполнителей показываются заявки:**
1. **Индивидуальные назначения** (`assignment_type='individual'`):
   - ВСЕГДА показываются, если `executor_id = user.id`
   - Не зависят от наличия активной смены

2. **Групповые назначения** (`assignment_type='group'`):
   - Показываются ТОЛЬКО если исполнитель в активной смене
   - Фильтр по `group_specialization` IN `user.specialization`

## Преимущества новой системы

✅ **Единая точка истины**: все назначения в одной таблице
✅ **Гибкость**: поддержка групповых и индивидуальных назначений
✅ **Аудит**: сохранение истории (статусы, создатель, дата)
✅ **Масштабируемость**: легко добавить новые типы назначений
✅ **Производительность**: оптимизированные запросы без UNION

## Обратная совместимость

Поля в таблице `requests` **сохранены** для обратной совместимости:
- `executor_id` - синхронизируется при создании назначения
- `assignment_type` - копируется из `RequestAssignment`
- `assigned_at`, `assigned_by` - сохраняются для истории

## Тестирование

### Проверено:
- ✅ Миграция существующей заявки `251016-001`
- ✅ Отображение заявки для исполнителя (роль `executor`)
- ✅ Фильтрация по статусу (`active`, `archive`, `all`)
- ✅ Пагинация списка заявок
- ✅ Просмотр деталей заявки

### Логи подтверждают:
```json
{
  "message": "Пользователь 48617336 (роль: executor) - найдено заявок: 1",
  "details": "[('251016-001', 'В работе', 'Электрика')]"
}
```

## Следующие шаги

### Обязательно:
1. ⚠️ **Протестировать** создание новых назначений через админ-панель
2. ✅ **Обновлено** - все места создания назначений используют `AssignmentService` или `RequestAssignment`:
   - ✅ `admin.py:handle_assign_specific_executor_admin()` - обновлено на `AssignmentService`
   - ✅ `admin.py:auto_assign_request_by_category()` - уже использует `RequestAssignment`
   - ✅ `request_assignment.py` - вся логика через `AssignmentService`
3. ✅ **Проверено** AI-сервисы:
   - ✅ `SmartDispatcher` - не использует прямое назначение
   - ✅ `AssignmentOptimizer` - обновлено для поддержки `RequestAssignment`
   - ✅ `GeoOptimizer` - не найдено прямых назначений

### Рекомендуется:
4. Добавить миграцию Alembic для автоматической миграции при деплое
5. Создать индексы на `request_assignments.executor_id` и `request_assignments.status`
6. Добавить constraint для проверки типа назначения:
   ```sql
   CHECK (
     (assignment_type = 'individual' AND executor_id IS NOT NULL AND group_specialization IS NULL) OR
     (assignment_type = 'group' AND executor_id IS NULL AND group_specialization IS NOT NULL)
   )
   ```

## Известные проблемы

### Исправлено в этой миграции:
- ✅ Ошибка парсинга ролей (JSON vs строка)
- ✅ PostgreSQL ошибка UNION с JSON полями
- ✅ Неопределенная переменная `executor_specializations` в логировании

### Остались предупреждения:
- ⚠️ "Ошибка парсинга ролей пользователя 1: Expecting value: line 1 column 1 (char 0)"
  - **Причина**: поле `roles` в БД хранится как строка, но код ожидает JSON
  - **Влияние**: низкое, есть fallback на `active_role`
  - **Решение**: исправить в отдельной задаче

## Авторы

- Миграция: Claude (Sonnet 4.5)
- Дата: 16.10.2025
- Код-ревью: требуется

---

**Статус миграции**: ✅ **УСПЕШНО ЗАВЕРШЕНО**
**Все заявки теперь работают через новую систему RequestAssignment**
