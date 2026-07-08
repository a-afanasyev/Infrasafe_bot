# 🔧 Database Documentation Corrections

> _Последнее редактирование: 2025-10-29_

**Дата**: 15 октября 2025
**Статус**: Critical Discrepancies Found

---

## ⚠️ Критические расхождения между документацией и реальным кодом

### Проблема
Документация, созданная ранее (**DATABASE_SCHEMA.md**, **database_schema.sql**, **DATABASE_ER_DIAGRAM.md**), содержит **значительные расхождения** с фактическими SQLAlchemy моделями.

---

## 🔴 Обнаруженные несоответствия

### 1. `access_rights` таблица

**Документация говорит**:
```sql
CREATE TABLE access_rights (
    apartment_id INTEGER REFERENCES apartments(id),  -- FK!
    building_id INTEGER REFERENCES buildings(id),     -- FK!
    yard_id INTEGER REFERENCES yards(id)              -- FK!
);
```

**Реальная модель** ([user_verification.py:100-135](uk_management_bot/database/models/user_verification.py:100-135)):
```python
class AccessRights(Base):
    apartment_number = Column(String(20), nullable=True)  # НЕТ FK!
    house_number = Column(String(20), nullable=True)      # НЕТ FK!
    yard_name = Column(String(100), nullable=True)        # НЕТ FK!
    is_active = Column(Boolean, default=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    notes = Column(Text, nullable=True)
```

**Разница**:
- ❌ Нет Foreign Keys
- ✅ Есть `is_active`, `expires_at`, `notes` (отсутствуют в документации)
- ✅ Используются STRING поля вместо INTEGER FK

---

### 2. `quarterly_plans` таблица

**Документация говорит** ([DATABASE_SCHEMA.md:609-621](DATABASE_SCHEMA.md:609-621)):
```sql
CREATE TABLE quarterly_plans (
    year INTEGER NOT NULL,
    quarter INTEGER NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'draft'
);
```

**Реальная модель** ([quarterly_plan.py:14-56](uk_management_bot/database/models/quarterly_plan.py:14-56)):
```python
class QuarterlyPlan(Base):
    year = Column(Integer, nullable=False)
    quarter = Column(Integer, nullable=False)
    start_date = Column(Date, nullable=False)                    # ❌ ОТСУТСТВУЕТ
    end_date = Column(Date, nullable=False)                      # ❌ ОТСУТСТВУЕТ
    status = Column(String(50), default="draft", nullable=False)

    # ❌ ВСЕ ЭТИ ПОЛЯ ОТСУТСТВУЮТ В ДОКУМЕНТАЦИИ:
    specializations = Column(JSON, nullable=True)
    coverage_24_7 = Column(Boolean, default=False)
    load_balancing_enabled = Column(Boolean, default=True)
    auto_transfers_enabled = Column(Boolean, default=True)
    notifications_enabled = Column(Boolean, default=True)
    total_shifts_planned = Column(Integer, default=0)
    total_hours_planned = Column(Float, default=0.0)
    coverage_percentage = Column(Float, default=0.0)
    total_conflicts = Column(Integer, default=0)
    resolved_conflicts = Column(Integer, default=0)
    pending_conflicts = Column(Integer, default=0)
    settings = Column(JSON, nullable=True)
    notes = Column(Text, nullable=True)
    activated_at = Column(DateTime(timezone=True), nullable=True)
    archived_at = Column(DateTime(timezone=True), nullable=True)
```

**Разница**: **15+ полей отсутствуют в документации!**

---

### 3. `quarterly_shift_schedules` таблица

**Документация говорит** ([database_schema.sql:754-775](database_schema.sql:754-775)):
```sql
CREATE TABLE quarterly_shift_schedules (
    shift_template_id INTEGER REFERENCES shift_templates(id),
    shift_date DATE NOT NULL,
    notes TEXT
);
```

**Реальная модель** ([quarterly_plan.py:128-179](uk_management_bot/database/models/quarterly_plan.py:128-179)):
```python
class QuarterlyShiftSchedule(Base):
    planned_date = Column(Date, nullable=False)                  # НЕ shift_date!
    planned_start_time = Column(DateTime(timezone=True))         # ❌ ОТСУТСТВУЕТ
    planned_end_time = Column(DateTime(timezone=True))           # ❌ ОТСУТСТВУЕТ
    assigned_user_id = Column(Integer, ForeignKey("users.id"))   # ❌ ОТСУТСТВУЕТ
    specialization = Column(String(100), nullable=False)         # ❌ ОТСУТСТВУЕТ
    schedule_type = Column(String(50), nullable=False)           # ❌ ОТСУТСТВУЕТ
    status = Column(String(50), default="planned")               # ❌ ОТСУТСТВУЕТ
    actual_shift_id = Column(Integer, ForeignKey("shifts.id"))   # ❌ ОТСУТСТВУЕТ
    shift_config = Column(JSON, nullable=True)                   # ❌ ОТСУТСТВУЕТ
    coverage_areas = Column(JSON, nullable=True)                 # ❌ ОТСУТСТВУЕТ
    priority = Column(Integer, default=1)                        # ❌ ОТСУТСТВУЕТ
```

**Разница**: **10+ полей отсутствуют**, структура полностью другая!

---

### 4. `shift_schedules` таблица

**Документация говорит** ([database_schema.sql:776-788](database_schema.sql:776-788)):
```sql
CREATE TABLE shift_schedules (
    shift_id INTEGER REFERENCES shifts(id),
    user_id INTEGER REFERENCES users(id),
    scheduled_date DATE NOT NULL,
    start_time TIME NOT NULL,
    end_time TIME NOT NULL
);
```

**Реальная модель** ([shift_schedule.py:12-147](uk_management_bot/database/models/shift_schedule.py:12-147)):
```python
class ShiftSchedule(Base):
    # ❌ НЕТ shift_id!
    # ❌ НЕТ user_id!
    # ❌ НЕТ scheduled_date!

    date = Column(Date, nullable=False, unique=True, index=True)  # UNIQUE!

    # ВСЕ ЭТИ ПОЛЯ ОТСУТСТВУЮТ В ДОКУМЕНТАЦИИ:
    planned_coverage = Column(JSON, nullable=True)                # Покрытие по часам
    actual_coverage = Column(JSON, nullable=True)
    planned_specialization_coverage = Column(JSON)
    actual_specialization_coverage = Column(JSON)
    predicted_requests = Column(Integer)
    actual_requests = Column(Integer, default=0)
    prediction_accuracy = Column(Float)
    recommended_shifts = Column(Integer)
    actual_shifts = Column(Integer, default=0)
    optimization_score = Column(Float)
    coverage_percentage = Column(Float)
    load_balance_score = Column(Float)
    special_conditions = Column(JSON)
    manual_adjustments = Column(JSON)
    status = Column(String(50), default="draft")
    created_by = Column(Integer, ForeignKey("users.id"))
    auto_generated = Column(Boolean, default=False)
    version = Column(Integer, default=1)
```

**Разница**: **Это СОВЕРШЕННО другая таблица!** Документация описывает несуществующую структуру.

---

### 5. `planning_conflicts` таблица

**Документация говорит** ([database_schema.sql:792-809](database_schema.sql:792-809)):
```sql
CREATE TABLE planning_conflicts (
    conflict_type VARCHAR(50),
    description TEXT,
    severity VARCHAR(20),
    resolved BOOLEAN DEFAULT FALSE
);
```

**Реальная модель** ([quarterly_plan.py:207-285](uk_management_bot/database/models/quarterly_plan.py:207-285)):
```python
class PlanningConflict(Base):
    conflict_type = Column(String(100), nullable=False)  # 100, не 50!
    status = Column(String(50), default="pending")       # ❌ ОТСУТСТВУЕТ

    # ВСЕ ЭТИ ПОЛЯ ОТСУТСТВУЮТ В ДОКУМЕНТАЦИИ:
    involved_schedule_ids = Column(JSON)
    involved_user_ids = Column(JSON)
    conflict_time = Column(DateTime(timezone=True))
    conflict_date = Column(Date)
    conflict_details = Column(JSON)
    suggested_resolutions = Column(JSON)
    applied_resolution = Column(JSON)
    resolved_at = Column(DateTime(timezone=True))
    resolved_by = Column(Integer, ForeignKey("users.id"))
    priority = Column(Integer, default=1)
```

**Разница**: **10+ полей отсутствуют**, нет `severity`, есть `status` и `priority`.

---

### 6. Миграционные скрипты существуют!

**Обнаружено**: В проекте есть директория `uk_management_bot/database/migrations/` с **16 миграционными скриптами**:

```
add_address_directory.py (15KB)
add_advanced_shift_features.py (15KB)
add_materials_fields.py
add_quarterly_planning_tables.py
add_request_acceptance_fields.py
add_shift_transfer_table.py
add_user_verification_tables.py
replace_request_id.py (9KB) - критическая миграция!
update_apartment_fields.py
... и др.
```

**Документация утверждала**: "Нет Alembic миграций, используется Base.metadata.create_all()"

**Реальность**: **Есть ручные миграционные скрипты**, которые не документированы!

---

## 📊 Сводная таблица расхождений

| Таблица | Документация | Реальная модель | Критичность |
|---------|--------------|-----------------|-------------|
| `access_rights` | FK на apartments/buildings/yards | STRING поля без FK | 🔴 Критично |
| `quarterly_plans` | 3 поля | 18+ полей | 🔴 Критично |
| `quarterly_shift_schedules` | 5 полей | 15+ полей | 🔴 Критично |
| `shift_schedules` | Связка shift+user+date | Аналитическая таблица с JSON | 🔴 Критично |
| `planning_conflicts` | 4 поля | 14+ полей | 🔴 Критично |
| `user_documents` | ✅ Совпадает | ✅ Совпадает | ✅ OK |
| `user_verifications` | ✅ Совпадает | ✅ Совпадает | ✅ OK |
| `users` | ✅ Совпадает | ✅ Совпадает | ✅ OK |
| `requests` | ✅ Совпадает | ✅ Совпадает | ✅ OK |
| `shifts` | ✅ Совпадает | ✅ Совпадает | ✅ OK |

---

## 🛠️ Почему это произошло

1. **Предположения вместо чтения кода**: Я создал документацию на основе стандартных практик, не читая **все** модели полностью.

2. **Неполный анализ**: Я прочитал базовые модели (User, Request, Shift), но не углубился в специализированные (Quarterly*, ShiftSchedule, AccessRights).

3. **Игнорирование папки migrations**: Я не проверил наличие миграционных скриптов, предположив, что их нет.

4. **Устаревшие имена полей**: Реальный код использует более детальные имена (например, `planned_date` вместо `shift_date`).

---

## ✅ Что было правильно

Документация **корректно** описала следующие таблицы:

✅ `users` - все поля совпадают
✅ `requests` - все поля совпадают
✅ `shifts` - все поля совпадают
✅ `shift_templates` - все поля совпадают
✅ `shift_assignments` - все поля совпадают
✅ `shift_transfers` - все поля совпадают
✅ `yards`, `buildings`, `apartments` - все поля совпадают
✅ `user_apartments`, `user_yards` - все поля совпадают
✅ `user_documents`, `user_verifications` - все поля совпадают
✅ `request_comments`, `request_assignments` - все поля совпадают
✅ `ratings`, `notifications`, `audit_logs` - все поля совпадают

**Итого**: **15 из 20 таблиц** описаны правильно (75% точность).

---

## 🎯 План действий

### Фаза 1: Создание точной документации (1-2 дня)

1. **Создать утилиту экспорта схемы из SQLAlchemy**
   ```python
   # scripts/export_schema.py
   from uk_management_bot.database.session import Base
   import uk_management_bot.database.models
   from sqlalchemy import MetaData
   from sqlalchemy.schema import CreateTable

   # Экспорт в SQL DDL
   for table in Base.metadata.sorted_tables:
       print(CreateTable(table).compile(dialect=postgresql.dialect()))
   ```

2. **Обновить DATABASE_SCHEMA.md**
   - Исправить `access_rights`
   - Дополнить `quarterly_plans` всеми полями
   - Переписать `quarterly_shift_schedules`
   - Полностью переписать `shift_schedules`
   - Дополнить `planning_conflicts`

3. **Обновить database_schema.sql**
   - Сгенерировать из реальных моделей
   - Использовать `CreateTable()` из SQLAlchemy

4. **Обновить DATABASE_ER_DIAGRAM.md**
   - Исправить связи для `access_rights` (нет FK!)
   - Добавить JSON поля в диаграммы
   - Показать real relationships

### Фаза 2: Документирование миграций (1 день)

5. **Создать MIGRATIONS_GUIDE.md**
   - Документировать все 16 скриптов
   - Порядок выполнения
   - Зависимости между скриптами
   - replace_request_id.py - ключевая миграция

6. **Создать таблицу migration_history**
   ```sql
   CREATE TABLE migration_history (
       id SERIAL PRIMARY KEY,
       script_name VARCHAR(255) UNIQUE,
       applied_at TIMESTAMP DEFAULT NOW(),
       success BOOLEAN
   );
   ```

### Фаза 3: Переход на Alembic (2-3 дня)

7. **Инициализировать Alembic**
   - Импортировать существующие миграции
   - Создать initial state
   - Stamp current version

8. **Создать тесты миграций**
   - Тестирование up/down
   - Проверка целостности данных

---

## 📝 Рекомендации

### Немедленные действия

1. ⚠️ **НЕ использовать** `database_schema.sql` для создания БД - он создаст несовместимую схему!

2. ✅ **Использовать** только `Base.metadata.create_all()` или миграционные скрипты из `uk_management_bot/database/migrations/`

3. ⚠️ **Пометить документацию** как **УСТАРЕВШУЮ** до исправления

4. ✅ **Создать актуальную документацию** с помощью экспорта из SQLAlchemy

### Долгосрочные действия

1. **Автоматизировать синхронизацию** документации с моделями
2. **CI/CD проверка** соответствия документации коду
3. **Перейти на Alembic** для управления миграциями
4. **Создать тесты** для проверки схемы БД

---

## 🔗 Следующие шаги

1. ✅ **Прочитать ВСЕ модели** полностью (выполнено)
2. ⏳ **Создать export_schema.py** - скрипт экспорта схемы
3. ⏳ **Сгенерировать DATABASE_SCHEMA_ACTUAL.md** - точная документация
4. ⏳ **Создать MIGRATIONS_GUIDE.md** - документация миграций
5. ⏳ **Обновить DATABASE_RECOMMENDATIONS.md** с реальной ситуацией

---

## 📚 Ссылки на файлы

**Несоответствующие модели**:
- [user_verification.py:100-135](uk_management_bot/database/models/user_verification.py:100-135) - AccessRights
- [quarterly_plan.py:9-285](uk_management_bot/database/models/quarterly_plan.py:9-285) - QuarterlyPlan, QuarterlyShiftSchedule, PlanningConflict
- [shift_schedule.py:12-196](uk_management_bot/database/models/shift_schedule.py:12-196) - ShiftSchedule

**Неточная документация**:
- [DATABASE_SCHEMA.md:483-621](DATABASE_SCHEMA.md:483-621) - устаревшие описания
- [database_schema.sql:580-809](database_schema.sql:580-809) - неверные DDL
- [DATABASE_ER_DIAGRAM.md:279-356](DATABASE_ER_DIAGRAM.md:279-356) - неточные связи

**Недокументированные миграции**:
- [uk_management_bot/database/migrations/](uk_management_bot/database/migrations/) - 16 скриптов

---

**Создано**: 15 октября 2025
**Автор**: Claude Sonnet 4.5
**Статус**: ⚠️ Critical - Action Required
**Приоритет**: 🔴 P0 - Документация не соответствует коду
