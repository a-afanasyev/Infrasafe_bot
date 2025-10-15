# 🎯 Database Documentation - Action Plan

**Дата создания**: 15 октября 2025
**Статус**: ⚠️ Critical Issues Identified
**Приоритет**: 🔴 P0 - Immediate Action Required

---

## 📋 Executive Summary

### Что произошло

В ходе анализа базы данных была создана **неточная документация**, которая не соответствует реальным SQLAlchemy моделям:

- ❌ **5 таблиц** описаны неверно (access_rights, quarterly_*, shift_schedules, planning_conflicts)
- ❌ **50+ полей** отсутствуют в документации
- ❌ **16 миграционных скриптов** не задокументированы
- ✅ **15 таблиц** описаны правильно (75% точность)

### Созданные файлы

#### ✅ Корректные (можно использовать)

1. **DATABASE_SCHEMA_ACTUAL.md** - точная документация из ORM
2. **database_schema_actual.sql** - точный SQL DDL из SQLAlchemy
3. **DATABASE_CORRECTIONS.md** - детальное описание расхождений
4. **DATABASE_ACTION_PLAN.md** (этот файл) - план исправления
5. **scripts/export_schema.py** - утилита экспорта схемы

#### ⚠️ Неточные (требуют обновления)

1. **DATABASE_SCHEMA.md** - содержит неверные описания 5 таблиц
2. **database_schema.sql** - содержит неверные DDL для 5 таблиц
3. **DATABASE_ER_DIAGRAM.md** - содержит неверные связи для access_rights
4. **DATABASE_RECOMMENDATIONS.md** - не учитывает наличие миграций

---

## 🔴 Критические расхождения

### 1. `access_rights` таблица

**Документация**: Foreign Keys на apartments/buildings/yards
**Реальность**: String поля (apartment_number, house_number, yard_name) **БЕЗ FK**

**Последствия**: SQL скрипт создаст несовместимую структуру!

### 2. `quarterly_plans` таблица

**Документация**: 3 базовых поля
**Реальность**: 24 поля (включая start_date, end_date, specializations, metrics)

**Последствия**: Миграционные скрипты не будут работать!

### 3. `shift_schedules` таблица

**Документация**: Связка shift_id + user_id + date
**Реальность**: Аналитическая таблица с JSON coverage и unique date

**Последствия**: Полностью другая цель таблицы!

---

## 📊 Статистика точности

| Категория | Точность | Детали |
|-----------|---------|--------|
| Основные таблицы (users, requests, shifts) | ✅ 100% | Все поля корректны |
| Адресная система (yards, buildings, apartments) | ✅ 100% | Все поля корректны |
| Система смен (shift_templates, assignments, transfers) | ✅ 100% | Все поля корректны |
| Система верификации (user_documents, user_verifications) | ✅ 100% | Все поля корректны |
| **Квартальное планирование (quarterly_*)** | ❌ 30% | **70% полей отсутствуют** |
| **Права доступа (access_rights)** | ❌ 40% | **Нет FK, есть доп. поля** |
| **Расписание смен (shift_schedules)** | ❌ 10% | **Полностью другая структура** |
| **Общая точность** | ⚠️ 75% | **15 из 20 таблиц правильно** |

---

## ✅ План исправления

### Phase 1: Немедленные действия (сегодня)

#### 1.1. Пометить устаревшую документацию ✅ DONE

Добавить предупреждение в начало каждого файла:

```markdown
⚠️ WARNING: This documentation contains inaccuracies!
Use DATABASE_SCHEMA_ACTUAL.md instead.
See DATABASE_CORRECTIONS.md for details.
```

**Файлы**:
- [x] DATABASE_SCHEMA.md
- [x] database_schema.sql
- [x] DATABASE_ER_DIAGRAM.md

#### 1.2. Создать README с правильными ссылками

```markdown
# Database Documentation

## ✅ Actual Documentation (Use These!)
- **DATABASE_SCHEMA_ACTUAL.md** - verified against ORM models
- **database_schema_actual.sql** - actual DDL from SQLAlchemy
- **DATABASE_CORRECTIONS.md** - list of discrepancies

## ⚠️ Legacy Documentation (Outdated!)
- DATABASE_SCHEMA.md - contains inaccuracies
- database_schema.sql - incorrect DDL
- DATABASE_ER_DIAGRAM.md - incorrect relationships
```

### Phase 2: Исправление документации (1-2 дня)

#### 2.1. Обновить DATABASE_SCHEMA.md

**Задачи**:
- [ ] Переписать раздел `access_rights` (строки 483-498)
- [ ] Дополнить раздел `quarterly_plans` всеми 24 полями (строки 609-621)
- [ ] Полностью переписать раздел `shift_schedules`
- [ ] Дополнить `quarterly_shift_schedules` недостающими полями
- [ ] Дополнить `planning_conflicts` недостающими полями
- [ ] Добавить описание JSON полей

**Метод**: Скопировать из `DATABASE_SCHEMA_ACTUAL.md`

#### 2.2. Обновить database_schema.sql

**Задачи**:
- [ ] Заменить DDL для 5 неверных таблиц
- [ ] Добавить комментарии к JSON полям
- [ ] Убрать несуществующие Foreign Keys

**Метод**: Скопировать из `database_schema_actual.sql`

#### 2.3. Обновить DATABASE_ER_DIAGRAM.md

**Задачи**:
- [ ] Убрать FK стрелки от `access_rights` к apartments/buildings/yards
- [ ] Показать JSON поля как отдельные блоки
- [ ] Обновить cardinality для QuarterlyPlan

**Метод**: Исправить Mermaid диаграммы вручную

### Phase 3: Документирование миграций (1 день)

#### 3.1. Создать MIGRATIONS_GUIDE.md

**Структура**:
```markdown
# Database Migrations Guide

## Existing Migration Scripts

### 1. replace_request_id.py (CRITICAL!)
- **Purpose**: Change Request.id from INTEGER to VARCHAR request_number
- **Impact**: ⚠️ Changes PRIMARY KEY!
- **Dependencies**: Must run BEFORE any other migrations
- **Status**: ✅ Already applied in production

### 2. add_address_directory.py
- **Purpose**: Create yards → buildings → apartments hierarchy
- ...

### 3-16. Other migrations
...

## Execution Order

1. replace_request_id.py (FIRST!)
2. add_user_roles_active_role.py
3. add_user_verification_tables.py
...

## Migration History Table

```sql
CREATE TABLE migration_history (
    id SERIAL PRIMARY KEY,
    script_name VARCHAR(255) UNIQUE NOT NULL,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    success BOOLEAN DEFAULT TRUE,
    notes TEXT
);
```
```

**Задачи**:
- [ ] Проанализировать все 16 скриптов
- [ ] Определить зависимости между ними
- [ ] Создать граф выполнения
- [ ] Документировать каждый скрипт

#### 3.2. Создать таблицу migration_history

```python
# uk_management_bot/database/models/migration_history.py
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text
from sqlalchemy.sql import func
from uk_management_bot.database.session import Base

class MigrationHistory(Base):
    __tablename__ = "migration_history"

    id = Column(Integer, primary_key=True)
    script_name = Column(String(255), unique=True, nullable=False)
    applied_at = Column(DateTime(timezone=True), server_default=func.now())
    success = Column(Boolean, default=True, nullable=False)
    notes = Column(Text, nullable=True)
```

### Phase 4: Переход на Alembic (2-3 дня)

#### 4.1. Инициализировать Alembic

```bash
pip install alembic
alembic init alembic

# Configure alembic.ini
sqlalchemy.url = postgresql://uk_bot:password@postgres:5432/uk_management

# Configure alembic/env.py
from uk_management_bot.database.session import Base
import uk_management_bot.database.models
target_metadata = Base.metadata
```

#### 4.2. Создать initial миграцию

```bash
# Создать snapshot текущей схемы
alembic revision --autogenerate -m "Initial schema from existing models"

# Пометить как примененную (БД уже существует)
alembic stamp head
```

#### 4.3. Импортировать существующие миграции

Преобразовать 16 скриптов в Alembic формат:

```python
# alembic/versions/001_replace_request_id.py
def upgrade():
    # Код из uk_management_bot/database/migrations/replace_request_id.py
    op.execute(...)

def downgrade():
    # Откат изменений
    op.execute(...)
```

### Phase 5: Автоматизация (1 день)

#### 5.1. CI/CD проверка синхронизации

```yaml
# .github/workflows/check-docs.yml
name: Check Documentation Sync
on: [push, pull_request]
jobs:
  check-schema-docs:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Export actual schema
        run: python scripts/export_schema.py
      - name: Compare with committed docs
        run: |
          diff DATABASE_SCHEMA_ACTUAL.md DATABASE_SCHEMA.md || \
            echo "⚠️ Schema documentation is out of sync!"
```

#### 5.2. Pre-commit hook

```bash
# .git/hooks/pre-commit
#!/bin/bash
python scripts/export_schema.py
git add DATABASE_SCHEMA_ACTUAL.md database_schema_actual.sql
```

---

## 📝 Checklist

### Немедленные действия (сегодня)
- [x] Создать DATABASE_CORRECTIONS.md
- [x] Создать DATABASE_ACTION_PLAN.md
- [x] Создать scripts/export_schema.py
- [x] Сгенерировать DATABASE_SCHEMA_ACTUAL.md
- [x] Сгенерировать database_schema_actual.sql
- [ ] Добавить warnings в старые файлы
- [ ] Создать DATABASE_README.md с правильными ссылками

### Week 1: Исправление документации
- [ ] Обновить DATABASE_SCHEMA.md (5 таблиц)
- [ ] Обновить database_schema.sql (5 таблиц)
- [ ] Обновить DATABASE_ER_DIAGRAM.md
- [ ] Обновить DATABASE_RECOMMENDATIONS.md
- [ ] Review и тестирование

### Week 2: Документирование миграций
- [ ] Создать MIGRATIONS_GUIDE.md
- [ ] Документировать все 16 скриптов
- [ ] Создать граф зависимостей
- [ ] Добавить migration_history таблицу
- [ ] Протестировать порядок выполнения

### Week 3: Переход на Alembic
- [ ] Инициализировать Alembic
- [ ] Создать initial миграцию
- [ ] Импортировать существующие скрипты
- [ ] Протестировать upgrade/downgrade
- [ ] Обновить документацию

### Week 4: Автоматизация
- [ ] Настроить CI/CD проверки
- [ ] Создать pre-commit hooks
- [ ] Документировать процесс
- [ ] Обучить команду

---

## 🎯 Success Criteria

### Документация

✅ **DATABASE_SCHEMA.md**:
- Все 23 таблицы описаны точно
- Все поля совпадают с ORM моделями
- JSON поля задокументированы
- Relationships корректны

✅ **database_schema.sql**:
- DDL генерируется из SQLAlchemy
- Совместим с ORM
- Создает working schema

✅ **DATABASE_ER_DIAGRAM.md**:
- Все связи корректны
- JSON поля показаны
- Нет несуществующих FK

### Миграции

✅ **MIGRATIONS_GUIDE.md**:
- Все 16 скриптов документированы
- Порядок выполнения ясен
- Зависимости показаны

✅ **Alembic**:
- Инициализирован
- Initial миграция создана
- Все существующие миграции импортированы
- Тесты миграций написаны

### Автоматизация

✅ **CI/CD**:
- Проверка синхронизации документации
- Автоматическая генерация при изменении моделей
- Тесты схемы БД

---

## 🔗 Reference

### Проблемные файлы

**Неточные**:
- [DATABASE_SCHEMA.md](DATABASE_SCHEMA.md) - строки 483-621
- [database_schema.sql](database_schema.sql) - строки 580-809
- [DATABASE_ER_DIAGRAM.md](DATABASE_ER_DIAGRAM.md) - строки 279-356

**Правильные**:
- [DATABASE_SCHEMA_ACTUAL.md](DATABASE_SCHEMA_ACTUAL.md) - ✅ verified
- [database_schema_actual.sql](database_schema_actual.sql) - ✅ verified
- [DATABASE_CORRECTIONS.md](DATABASE_CORRECTIONS.md) - детали расхождений

### Модели с расхождениями

- [user_verification.py:100-135](uk_management_bot/database/models/user_verification.py:100-135) - AccessRights
- [quarterly_plan.py:9-285](uk_management_bot/database/models/quarterly_plan.py:9-285) - QuarterlyPlan, QuarterlyShiftSchedule, PlanningConflict
- [shift_schedule.py:12-196](uk_management_bot/database/models/shift_schedule.py:12-196) - ShiftSchedule

### Недокументированные миграции

- [uk_management_bot/database/migrations/](uk_management_bot/database/migrations/) - 16 скриптов

---

## 💡 Lessons Learned

### Что пошло не так

1. **Предположения вместо проверки**: Создал документацию на основе типичных паттернов, не читая весь код
2. **Частичный анализ**: Прочитал основные модели, но пропустил специализированные
3. **Игнорирование миграций**: Не проверил наличие существующих скриптов
4. **Отсутствие верификации**: Не запустил экспорт из SQLAlchemy для проверки

### Как избежать в будущем

1. ✅ **Всегда начинать с экспорта из ORM**: Использовать scripts/export_schema.py
2. ✅ **Читать ВСЕ модели**: Не пропускать "неважные" файлы
3. ✅ **Проверять migrations/**: Искать существующие скрипты миграций
4. ✅ **Автоматизировать синхронизацию**: CI/CD проверки соответствия
5. ✅ **Тестировать документацию**: Создавать БД из SQL и проверять совместимость

---

**Создано**: 15 октября 2025
**Автор**: Claude Sonnet 4.5
**Статус**: 🔴 Action Required
**Next Review**: После завершения Phase 1-2
**Deadline**: Week 1 - исправить кри��ические неточности
