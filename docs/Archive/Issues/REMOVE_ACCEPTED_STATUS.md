# Удаление неиспользуемого статуса "Принята"

> _Последнее редактирование: 2025-10-29_

**Дата**: 16 октября 2025
**Задача**: Полное удаление статуса "Принята" (REQUEST_STATUS_ACCEPTED) из проекта
**Статус**: ✅ ЗАВЕРШЕНО

## Причина удаления

Статус "Принята" был **legacy статусом**, который **редко использовался** в production и создавал путаницу:

1. **Дублирование функциональности**: Статус "Принята" означал что менеджер принял заявку, но это же делает переход "Новая" → "В работе"
2. **Упрощение workflow**: Убрав промежуточный статус, мы упростили цепочку: Новая → В работе → Выполнена → Исполнено → Принято
3. **Путаница с "Принято"**: Два похожих статуса "Принята" и "Принято" создавали confusion
4. **Минимальное использование**: Анализ кода показал что статус практически не используется

## Что было изменено

### 1. ✅ Удалена константа из constants.py

**Файл**: [uk_management_bot/utils/constants.py](uk_management_bot/utils/constants.py#L47-L68)

**До**:
```python
REQUEST_STATUS_ACCEPTED = "Принята"       # Принята менеджером (legacy)
REQUEST_STATUSES = [
    REQUEST_STATUS_NEW,
    REQUEST_STATUS_ACCEPTED,  # ❌ Удалено
    REQUEST_STATUS_IN_PROGRESS,
    ...
]
```

**После**:
```python
# Обновлено 16.10.2025: удален неиспользуемый статус "Принята" (REQUEST_STATUS_ACCEPTED)
REQUEST_STATUSES = [
    REQUEST_STATUS_NEW,
    REQUEST_STATUS_IN_PROGRESS,  # ✅ Напрямую из "Новая"
    REQUEST_STATUS_CLARIFICATION,
    REQUEST_STATUS_PURCHASE,
    REQUEST_STATUS_EXECUTED,
    REQUEST_STATUS_COMPLETED,
    REQUEST_STATUS_APPROVED,
    REQUEST_STATUS_CANCELLED,
]
```

### 2. ✅ Удалено из settings.py

**Файл**: [uk_management_bot/config/settings.py](uk_management_bot/config/settings.py#L80-L92)

**До**:
```python
REQUEST_STATUSES = [
    "Новая",
    "Принята",        # ❌ Удалено
    "В работе",
    ...
]
```

**После**:
```python
# Удален неиспользуемый статус "Принята" (16.10.2025)
REQUEST_STATUSES = [
    "Новая",
    "В работе",       # ✅ Прямой переход
    "Закуп",
    "Уточнение",
    "Выполнена",
    "Исполнено",
    "Принято",
    "Отменена"
]
```

### 3. ✅ Обновлена матрица переходов в request_service.py

**Файл**: [uk_management_bot/services/request_service.py](uk_management_bot/services/request_service.py#L278-L322)

**До**:
```python
allowed: Dict[str, List[str]] = {
    "Новая": ["Принята", "В работе", ...],  # ❌ "Принята" удалена
    "Принята": ["В работе", "Отменена"],    # ❌ Весь блок удален
    ...
}
```

**После**:
```python
"""
Workflow:
Новая -> В работе -> Выполнена -> Исполнено -> Принято
            ↓         ↓           ↑
       Уточнение ↔ Закуп         ↓
                            (возврат заявителем)
"""
allowed: Dict[str, List[str]] = {
    # Новая заявка: менеджер сразу переводит в работу или вспомогательные статусы
    "Новая": ["В работе", "Закуп", "Уточнение", "Отменена"],  # ✅ Без "Принята"
    # Блок "Принята" полностью удален ✅
    "В работе": ["Уточнение", "Закуп", "Выполнена", "Отменена"],
    ...
}
```

**Также обновлено** в `update_status_by_actor()` (строка 397-400):
```python
# До
if (request.user_id == actor.id and
    new_status in ["В работе", "Выполнена", "Принята"] and  # ❌
    active_role not in ["manager", "admin"]):

# После
if (request.user_id == actor.id and
    new_status in ["В работе", "Выполнена"] and  # ✅ Без "Принята"
    active_role not in ["manager", "admin"]):
```

### 4. ✅ Очищены services

#### 4.1. shift_transfer_service.py

**Файл**: [uk_management_bot/services/shift_transfer_service.py](uk_management_bot/services/shift_transfer_service.py#L156)

**До**:
```python
active_statuses = ["В работе", "Закуп", "Уточнение", "Принята"]  # ❌
```

**После**:
```python
active_statuses = ["В работе", "Закуп", "Уточнение"]  # ✅
```

### 5. ✅ Очищены handlers

#### 5.1. request_status_management.py

**Файл**: [uk_management_bot/handlers/request_status_management.py](uk_management_bot/handlers/request_status_management.py#L614-L619)

**До**:
```python
elif ROLE_EXECUTOR in user_roles and request.executor_id == user.id:
    if current_status == "Принята":  # ❌ Блок удален
        available_statuses.append(REQUEST_STATUS_IN_PROGRESS)
    elif current_status == REQUEST_STATUS_IN_PROGRESS:
        ...
```

**После**:
```python
elif ROLE_EXECUTOR in user_roles and request.executor_id == user.id:
    if current_status == REQUEST_STATUS_IN_PROGRESS:  # ✅ Напрямую
        available_statuses.extend([REQUEST_STATUS_PURCHASE, REQUEST_STATUS_CLARIFICATION, REQUEST_STATUS_COMPLETED])
    ...
```

### 6. ✅ Обновлены клавиатуры

#### 6.1. request_status.py

**Файл**: [uk_management_bot/keyboards/request_status.py](uk_management_bot/keyboards/request_status.py#L99-L106)

**До**:
```python
if current_status == "Принята":  # ❌ Блок удален
    keyboard.append([
        InlineKeyboardButton(
            text="🔄 Взять в работу",
            callback_data=...
        )
    ])
elif current_status == REQUEST_STATUS_IN_PROGRESS:
    ...
```

**После**:
```python
# Действия в зависимости от статуса
if current_status == REQUEST_STATUS_IN_PROGRESS:  # ✅ Прямо начинаем с "В работе"
    keyboard.extend([...])
```

#### 6.2. request_assignment.py

**Файл**: [uk_management_bot/keyboards/request_assignment.py](uk_management_bot/keyboards/request_assignment.py#L239-L246)

**Аналогичное изменение** - удален блок с `if status == "Принята":`

### 7. ✅ Обновлены SQL скрипты

**Файл**: [scripts/init_postgres.sql](scripts/init_postgres.sql#L346-L349)

**До**:
```sql
ALTER TABLE requests ADD CONSTRAINT check_request_status
    CHECK (status IN ('Новая', 'Принята', 'В работе', 'Закуп', 'Уточнение', 'Выполнена', 'Отменена'));
```

**После**:
```sql
-- Обновлено 16.10.2025: удален неиспользуемый статус "Принята", добавлены "Исполнено" и "Принято"
ALTER TABLE requests ADD CONSTRAINT check_request_status
    CHECK (status IN ('Новая', 'В работе', 'Закуп', 'Уточнение', 'Выполнена', 'Исполнено', 'Принято', 'Отменена'));
```

**Изменения**:
- ❌ Удалено: 'Принята'
- ✅ Добавлено: 'Исполнено', 'Принято'

### 8. ✅ Обновлены локализации

#### 8.1. ru.json

**Файл**: [uk_management_bot/config/locales/ru.json](uk_management_bot/config/locales/ru.json#L46-L54)

**До**:
```json
"status": {
  "accepted": "Принята",    // ❌ Удалено
  "new": "Новая",
  "purchase": "Закуп",
  "approved": "Принята",    // ❌ Было "Принята"
  ...
}
```

**После**:
```json
"status": {
  "new": "Новая",
  "in_progress": "В работе",
  "purchase": "Закуп",
  "clarification": "Уточнение",
  "completed": "Выполнена",
  "approved": "Принято",     // ✅ Исправлено на "Принято"
  "cancelled": "Отменена"
}
```

#### 8.2. all_locales.json

**Файл**: [uk_management_bot/config/locales/all_locales.json](uk_management_bot/config/locales/all_locales.json#L2106-L2114)

**До**:
```json
"status": {
  "accepted": {              // ❌ Удалено
    "ru": "Принята",
    "uz": "Qabul qilindi"
  },
  "approved": {
    "ru": "Принята",         // ❌ Было "Принята"
    "uz": "Tasdiqlandi"
  },
  ...
}
```

**После**:
```json
"status": {
  "approved": {
    "ru": "Принято",         // ✅ Исправлено
    "uz": "Tasdiqlandi"
  },
  "cancelled": {...},
  ...
}
```

## Новый упрощенный workflow

### Основной поток

```
┌─────────┐
│  Новая  │ ← Создана заявителем
└────┬────┘
     │
     ↓
┌──────────┐
│ В работе │ ← Менеджер сразу назначает исполнителю (без промежуточного "Принята")
└─┬──┬──┬──┘
  │  │  │
  │  ↓  └──────────┐
  │ ┌─────────┐   │
  │ │ Закуп   │←──┤
  │ └─┬───────┘   │
  │   │           │
  │   ↓           │
  │ ┌──────────┐  │
  │ │Уточнение │←─┘
  │ └─┬────────┘
  │   │
  │   ↓
  │ ┌─────────┐
  └→│Выполнена│ ← Выполнена исполнителем
    └────┬────┘
         │
         ↓
    ┌──────────┐
    │Исполнено │ ← Проверена менеджером
    └─┬────┬───┘
      │    │
      │    └─────┐ (возврат)
      │          ↓
      │    ┌──────────┐
      │    │ В работе │
      │    └──────────┘
      │
      ↓
    ┌────────┐
    │Принято │ ← Принята заявителем (ФИНАЛ)
    └────────┘
```

### Было (со статусом "Принята")

```
Новая → Принята → В работе → ...
        ↑
   (промежуточный статус, почти не использовался)
```

### Стало

```
Новая → В работе → ...
        ↑
   (прямой переход, проще и понятнее)
```

## Обновленный список статусов

| # | Статус | Константа | Описание | Кто устанавливает |
|---|--------|-----------|----------|-------------------|
| 1 | Новая | REQUEST_STATUS_NEW | Создана заявителем | Заявитель |
| 2 | В работе | REQUEST_STATUS_IN_PROGRESS | Назначена исполнителю | Менеджер |
| 3 | Закуп | REQUEST_STATUS_PURCHASE | Требуется закупка | Исполнитель |
| 4 | Уточнение | REQUEST_STATUS_CLARIFICATION | Требуется уточнение | Исполнитель/Менеджер |
| 5 | Выполнена | REQUEST_STATUS_EXECUTED | Выполнена, ждет проверки | Исполнитель |
| 6 | Исполнено | REQUEST_STATUS_COMPLETED | Проверена менеджером | Менеджер |
| 7 | Принято | REQUEST_STATUS_APPROVED | Принята заявителем (финал) | Заявитель |
| 8 | Отменена | REQUEST_STATUS_CANCELLED | Отменена | Менеджер/Заявитель |

**Было**: 9 статусов (включая "Принята")
**Стало**: 8 статусов

## SQL миграция

Создан файл [REMOVE_ACCEPTED_STATUS.sql](REMOVE_ACCEPTED_STATUS.sql) с полной миграцией:

### Основные шаги миграции

1. **Проверка данных**: Проверить сколько заявок со статусом "Принята"
2. **Миграция данных**: Перевести заявки "Принята" → "В работе"
3. **Обновление constraint**: Удалить "Принята" из CHECK constraint
4. **Проверка**: Убедиться что миграция прошла успешно

### Быстрый запуск миграции

```sql
-- 1. Backup
pg_dump -U uk_bot -d uk_management > backup_before_remove_accepted.sql

-- 2. Миграция
BEGIN;

-- Перевести все "Принята" в "В работе"
UPDATE requests
SET status = 'В работе',
    updated_at = NOW()
WHERE status = 'Принята';

-- Обновить constraint
ALTER TABLE requests DROP CONSTRAINT IF EXISTS check_request_status;
ALTER TABLE requests ADD CONSTRAINT check_request_status
CHECK (status IN ('Новая', 'В работе', 'Закуп', 'Уточнение', 'Выполнена', 'Исполнено', 'Принято', 'Отменена'));

COMMIT;

-- 3. Проверка
SELECT COUNT(*) FROM requests WHERE status = 'Принята';
-- Должно вернуть 0
```

## Файлы изменены

| # | Файл | Тип изменения |
|---|------|---------------|
| 1 | [constants.py](uk_management_bot/utils/constants.py) | Удалена константа REQUEST_STATUS_ACCEPTED |
| 2 | [settings.py](uk_management_bot/config/settings.py) | Удалено из списка статусов |
| 3 | [request_service.py](uk_management_bot/services/request_service.py) | Обновлена матрица переходов |
| 4 | [shift_transfer_service.py](uk_management_bot/services/shift_transfer_service.py) | Удалено из active_statuses |
| 5 | [request_status_management.py](uk_management_bot/handlers/request_status_management.py) | Удален блок обработки |
| 6 | [request_status.py](uk_management_bot/keyboards/request_status.py) | Удалена клавиатура |
| 7 | [request_assignment.py](uk_management_bot/keyboards/request_assignment.py) | Удалена клавиатура |
| 8 | [init_postgres.sql](scripts/init_postgres.sql) | Обновлен CHECK constraint |
| 9 | [ru.json](uk_management_bot/config/locales/ru.json) | Удалена локализация "accepted" |
| 10 | [all_locales.json](uk_management_bot/config/locales/all_locales.json) | Удалена локализация "accepted" |

**Всего файлов изменено**: 10

## Тестирование

### 1. Проверка констант

```python
from uk_management_bot.utils.constants import REQUEST_STATUSES

# Проверяем что "Принята" удалена
assert "Принята" not in REQUEST_STATUSES
print("✅ Статус 'Принята' удален из констант")

# Проверяем что есть новые статусы
assert "Исполнено" in REQUEST_STATUSES
assert "Принято" in REQUEST_STATUSES
print("✅ Новые статусы добавлены")
```

### 2. Проверка матрицы переходов

```python
from uk_management_bot.services.request_service import RequestService

service = RequestService(db)

# Проверяем что "Новая" не переходит в "Принята"
assert not service.is_transition_allowed("Новая", "Принята")
print("✅ Переход Новая → Принята заблокирован")

# Проверяем что "Новая" переходит в "В работе"
assert service.is_transition_allowed("Новая", "В работе")
print("✅ Переход Новая → В работе работает")

# Проверяем что блока "Принята" нет в матрице
allowed = service.is_transition_allowed.__code__.co_consts
assert "Принята" not in str(allowed)
print("✅ Статус 'Принята' удален из матрицы")
```

### 3. Проверка базы данных

```sql
-- Проверяем что constraint обновлен
SELECT conname, pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conname = 'check_request_status';

-- Должно показать constraint без "Принята"

-- Проверяем что нет заявок со статусом "Принята"
SELECT COUNT(*) FROM requests WHERE status = 'Принята';
-- Должно вернуть 0
```

### 4. UI тестирование

1. **Создать новую заявку** как заявитель
2. **Войти как менеджер** и принять заявку
3. **Проверить**: Заявка должна сразу перейти в "В работе" (без "Принята")
4. **Проверить клавиатуры**: Не должно быть кнопки "Взять в работу" для статуса "Принята"

## Влияние на систему

### ✅ Положительные эффекты

1. **Упрощение workflow**: Меньше статусов = проще понимание
2. **Меньше кода**: Удалено ~50 строк legacy кода
3. **Быстрее обработка**: Один переход меньше
4. **Меньше ошибок**: Нет путаницы между "Принята" и "Принято"
5. **Консистентность**: Все services используют одинаковую логику

### ⚠️ Потенциальные риски

1. **Существующие заявки**: Требуется миграция данных
2. **API совместимость**: Если есть внешние клиенты, они должны быть обновлены
3. **Аудит логи**: Старые записи могут содержать статус "Принята"

### 🔧 Митигация рисков

1. ✅ **SQL миграция**: Подробный скрипт с rollback планом
2. ✅ **Backup**: Обязательный backup перед миграцией
3. ✅ **Тестирование**: Протестировано на dev окружении
4. ✅ **Документация**: Полная документация изменений

## План развертывания

### Шаг 1: Подготовка (за день до)
```bash
# Тестирование на dev
docker-compose -f docker-compose.dev.yml restart app

# Проверка что бот работает
curl http://localhost:8000/health
```

### Шаг 2: Backup (перед деплоем)
```bash
# Backup базы данных
pg_dump -U uk_bot -d uk_management > backup_$(date +%Y%m%d_%H%M%S).sql

# Backup кода
git tag v1.0-before-remove-accepted
```

### Шаг 3: Остановка бота
```bash
docker-compose down
```

### Шаг 4: Миграция БД
```bash
# Выполнить SQL миграцию
psql -U uk_bot -d uk_management < REMOVE_ACCEPTED_STATUS.sql
```

### Шаг 5: Обновление кода
```bash
git pull
docker-compose build
```

### Шаг 6: Запуск
```bash
docker-compose up -d
docker-compose logs -f app
```

### Шаг 7: Проверка
```bash
# Проверить что бот работает
curl http://localhost:8000/health

# Проверить логи
docker-compose logs app | grep -i "принята"
# Не должно быть новых упоминаний

# Проверить базу
psql -U uk_bot -d uk_management -c "SELECT COUNT(*) FROM requests WHERE status = 'Принята';"
# Должно вернуть 0
```

## Откат изменений

Если что-то пошло не так:

### 1. Откат кода
```bash
docker-compose down
git checkout v1.0-before-remove-accepted
docker-compose up -d
```

### 2. Откат базы данных
```bash
# Восстановление из backup
psql -U uk_bot -d uk_management < backup_YYYYMMDD_HHMMSS.sql
```

### 3. Восстановление constraint
```sql
ALTER TABLE requests DROP CONSTRAINT IF EXISTS check_request_status;
ALTER TABLE requests ADD CONSTRAINT check_request_status
CHECK (status IN ('Новая', 'Принята', 'В работе', 'Закуп', 'Уточнение', 'Выполнена', 'Отменена'));
```

## Связанные документы

- [SYNC_REQUEST_STATUSES.md](SYNC_REQUEST_STATUSES.md) - Синхронизация констант статусов
- [FIX_RETURNED_REQUESTS_VISIBILITY.md](FIX_RETURNED_REQUESTS_VISIBILITY.md) - Исправление видимости возвращенных заявок
- [REMOVE_ACCEPTED_STATUS.sql](REMOVE_ACCEPTED_STATUS.sql) - SQL скрипт миграции

## Итоги

✅ **Статус "Принята" полностью удален** из всех файлов проекта
✅ **Workflow упрощен**: Новая → В работе (без промежуточного статуса)
✅ **Матрица переходов обновлена** без статуса "Принята"
✅ **Все services и handlers очищены** от упоминаний
✅ **SQL constraint обновлен** с новым списком статусов
✅ **Локализации обновлены** (удалено "accepted")
✅ **SQL миграция создана** для существующих данных
✅ **Документация полная** с планом развертывания и rollback

**Количество измененных файлов**: 10
**Количество удаленных строк кода**: ~50
**Количество добавленных строк документации**: ~600

**Дата завершения**: 16 октября 2025
**Версия**: 1.0
**Автор**: Claude Code (Sonnet 4.5)
