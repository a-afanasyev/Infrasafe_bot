# 📋 Аудит SQL файлов в корневой директории

> _Последнее редактирование: 2025-10-29_

**Дата проверки**: 15 октября 2025
**Директория**: `/Users/.../Code/UK/`
**Найдено файлов**: 9

---

## 📊 Список файлов

| Файл | Размер | Дата изменения | Статус |
|------|--------|----------------|--------|
| `database_schema_actual.sql` | 21K | Oct 15 22:13 | ✅ **АКТУАЛЬНЫЙ** |
| `database_schema.sql` | 36K | Oct 15 21:37 | ⚠️ **УСТАРЕВШИЙ** |
| `SQL_Startup.sql` | 34K | Sep 23 16:00 | ⚠️ **УСТАРЕВШИЙ** |
| `apply_shift_migration.sql` | 8.8K | Sep 9 13:18 | ❌ **УДАЛИТЬ** |
| `create_full_test_data.sql` | 11K | Sep 9 13:19 | ❌ **УДАЛИТЬ** |
| `create_working_test_data.sql` | 5.3K | Sep 9 13:20 | ❌ **УДАЛИТЬ** |
| `create_test_data.sql` | 7.7K | Sep 9 13:16 | ❌ **УДАЛИТЬ** |
| `create_simple_test_data.sql` | 4.4K | Sep 9 13:17 | ❌ **УДАЛИТЬ** |
| `add_media_record.sql` | 1.2K | Oct 14 12:47 | ⚠️ **ВРЕМЕННЫЙ** |

**Общий размер**: ~133 KB

---

## 📁 Категоризация файлов

### ✅ Актуальные (использовать)

#### 1. `database_schema_actual.sql` (21K)
**Статус**: ✅ **ЕДИНСТВЕННЫЙ ПРАВИЛЬНЫЙ ФАЙЛ**

**Описание**:
- Автоматически генерируется из SQLAlchemy моделей
- Содержит CREATE TYPE для всех ENUM типов
- Содержит правильный DDL для всех 27 таблиц
- Обновлен 15 октября 2025

**Использование**:
```bash
# Создание базы данных из SQL
psql -U uk_bot -d uk_management < database_schema_actual.sql

# ИЛИ использовать SQLAlchemy (рекомендуется)
python -c "from uk_management_bot.database.session import Base, engine; \
           import uk_management_bot.database.models; \
           Base.metadata.create_all(bind=engine)"
```

**Обновление**:
```bash
docker exec uk-bot python3 /app/scripts/export_schema.py
docker cp uk-bot:/app/database_schema_actual.sql ./
```

---

### ⚠️ Устаревшие (не использовать, но не удалять пока)

#### 2. `database_schema.sql` (36K)
**Статус**: ⚠️ **СОДЕРЖИТ ОШИБКИ**

**Проблема**:
- Содержит НЕПРАВИЛЬНЫЙ DDL для 5 таблиц
- НЕ содержит CREATE TYPE для ENUM типов
- Создан вручную, не автоматически

**Ошибки**:
```
✗ access_rights - неверные FK
✗ quarterly_plans - неверные поля
✗ quarterly_shift_schedules - неверные поля
✗ shift_schedules - неверная структура
✗ planning_conflicts - неверные поля
```

**Предупреждение в файле**:
```sql
-- WARNING: THIS SQL SCRIPT CONTAINS INCORRECT DDL!
-- DO NOT USE THIS FILE TO CREATE DATABASE!
-- Use database_schema_actual.sql instead.
```

**Рекомендация**:
- 🔄 **Переименовать** в `database_schema.sql.old`
- 📝 **Задокументировать** в `.gitignore`
- ⏳ **Удалить через 2 недели** если не нужен

#### 3. `SQL_Startup.sql` (34K)
**Статус**: ⚠️ **УСТАРЕВШИЙ**

**Описание**:
- Старый скрипт инициализации БД
- Создан 23 сентября (1 месяц назад)
- Заменен на `database_schema_actual.sql`

**Проблема**:
- Не содержит CREATE TYPE для ENUM
- Может содержать устаревшую структуру таблиц
- Не обновляется автоматически

**Рекомендация**:
- 🔄 **Переименовать** в `SQL_Startup.sql.old`
- ⏳ **Удалить через 2 недели**

---

### ❌ Временные тестовые файлы (удалить)

#### 4. `apply_shift_migration.sql` (8.8K)
**Дата**: Sep 9 13:18 (месяц назад)
**Назначение**: Применение миграции системы смен
**Статус**: ❌ Миграция уже применена, файл больше не нужен

#### 5. `create_test_data.sql` (7.7K)
**Дата**: Sep 9 13:16
**Назначение**: Создание тестовых данных для системы смен
**Статус**: ❌ Тестовый файл, не используется

#### 6. `create_simple_test_data.sql` (4.4K)
**Дата**: Sep 9 13:17
**Назначение**: Упрощенные тестовые данные
**Статус**: ❌ Тестовый файл, не используется

#### 7. `create_full_test_data.sql` (11K)
**Дата**: Sep 9 13:19
**Назначение**: Полные тестовые данные для системы смен
**Статус**: ❌ Тестовый файл, не используется

#### 8. `create_working_test_data.sql` (5.3K)
**Дата**: Sep 9 13:20
**Назначение**: Рабочие тестовые данные
**Статус**: ❌ Тестовый файл, не используется

**Общее у всех**: Созданы в сентябре для тестирования системы смен. Сейчас не используются.

#### 9. `add_media_record.sql` (1.2K)
**Дата**: Oct 14 12:47 (вчера)
**Назначение**: Добавление медиафайла для конкретной заявки 250917-002
**Статус**: ⚠️ **ВРЕМЕННЫЙ** - специфичный для одной задачи

**Рекомендация**: Удалить после проверки, что задача выполнена

---

## 🧹 План очистки

### Шаг 1: Переименование устаревших файлов

```bash
# Сохраняем устаревшие файлы с суффиксом .old
mv database_schema.sql database_schema.sql.old
mv SQL_Startup.sql SQL_Startup.sql.old
```

### Шаг 2: Удаление тестовых файлов

```bash
# Удаляем тестовые данные (сентябрь)
rm -f apply_shift_migration.sql
rm -f create_test_data.sql
rm -f create_simple_test_data.sql
rm -f create_full_test_data.sql
rm -f create_working_test_data.sql
```

### Шаг 3: Проверка и удаление временного файла

```bash
# Проверить, выполнена ли задача 250917-002
# Если да, удалить:
rm -f add_media_record.sql
```

### Шаг 4: Обновление .gitignore

```bash
# Добавить в .gitignore
cat >> .gitignore << 'EOF'

# Устаревшие SQL файлы
*.sql.old

# Временные SQL скрипты
add_*.sql
create_*_test_data.sql
apply_*_migration.sql
EOF
```

---

## 📝 Итоговая структура (после очистки)

### Должно остаться:

```
UK/
├── database_schema_actual.sql     ✅ Единственный актуальный файл
├── scripts/
│   └── export_schema.py          ✅ Генератор актуальной схемы
└── uk_management_bot/
    └── database/
        ├── models/                ✅ Источник истины
        └── migrations/            ✅ Ручные миграции (16 шт.)
```

### Можно оставить (с суффиксом .old):
```
UK/
├── database_schema.sql.old        ⚠️ Для истории
└── SQL_Startup.sql.old            ⚠️ Для истории
```

**Через 2 недели удалить .old файлы если не понадобились.**

---

## ⚙️ Автоматизация

### Скрипт очистки

Создайте `scripts/cleanup_sql.sh`:

```bash
#!/bin/bash
# Скрипт очистки устаревших SQL файлов

set -e

echo "🧹 Очистка SQL файлов..."

# Переименование устаревших
if [ -f "database_schema.sql" ]; then
    echo "📦 Архивирование database_schema.sql -> database_schema.sql.old"
    mv database_schema.sql database_schema.sql.old
fi

if [ -f "SQL_Startup.sql" ]; then
    echo "📦 Архивирование SQL_Startup.sql -> SQL_Startup.sql.old"
    mv SQL_Startup.sql SQL_Startup.sql.old
fi

# Удаление тестовых файлов
echo "🗑️  Удаление тестовых SQL файлов..."
rm -f apply_shift_migration.sql
rm -f create_test_data.sql
rm -f create_simple_test_data.sql
rm -f create_full_test_data.sql
rm -f create_working_test_data.sql

# Проверка временных файлов
if [ -f "add_media_record.sql" ]; then
    echo "⚠️  Найден временный файл: add_media_record.sql"
    echo "   Проверьте, нужен ли он еще, и удалите вручную"
fi

echo "✅ Очистка завершена!"
echo ""
echo "Оставшиеся файлы:"
ls -lh *.sql 2>/dev/null || echo "  (только database_schema_actual.sql)"
```

**Использование**:
```bash
chmod +x scripts/cleanup_sql.sh
./scripts/cleanup_sql.sh
```

---

## 📊 Экономия места

| Категория | Размер | Действие |
|-----------|--------|----------|
| Актуальные | 21 KB | Оставить |
| Устаревшие | 70 KB | Переименовать в .old |
| Тестовые | 41 KB | **Удалить** |
| Временные | 1.2 KB | Проверить и удалить |

**Экономия после очистки**: ~42 KB (31%)

---

## ✅ Checklist

- [ ] Сделать резервную копию всех SQL файлов
- [ ] Проверить, что `database_schema_actual.sql` работает корректно
- [ ] Переименовать устаревшие файлы (`.old`)
- [ ] Удалить тестовые файлы (5 шт.)
- [ ] Проверить статус задачи 250917-002
- [ ] Удалить `add_media_record.sql` если задача выполнена
- [ ] Обновить `.gitignore`
- [ ] Создать скрипт `scripts/cleanup_sql.sh`
- [ ] Задокументировать изменения в commit message
- [ ] Через 2 недели удалить `.old` файлы

---

## 🔗 Связанные документы

- [database_schema_actual.sql](database_schema_actual.sql) - Актуальная схема
- [DATABASE_SCHEMA_ACTUAL.md](DATABASE_SCHEMA_ACTUAL.md) - Документация схемы
- [DATABASE_CORRECTIONS.md](DATABASE_CORRECTIONS.md) - Описание ошибок в старых файлах
- [scripts/export_schema.py](scripts/export_schema.py) - Генератор схемы
- [DATABASE_README.md](DATABASE_README.md) - Навигация по документации

---

## 🎯 Рекомендации

### Краткосрочные (сейчас)

1. ✅ **Оставить только** `database_schema_actual.sql`
2. ⚠️ **Переименовать** устаревшие файлы в `.old`
3. ❌ **Удалить** все тестовые файлы

### Долгосрочные (на будущее)

1. 📝 **Документировать** процесс создания временных SQL файлов
2. 📁 **Создать папку** `sql/temp/` для временных скриптов
3. 🔄 **Автоматизировать** генерацию схемы при изменении моделей
4. 🧪 **Использовать fixtures** вместо SQL файлов для тестовых данных

---

**Документ создан**: 15 октября 2025
**Автор**: Claude Code
**Статус**: ✅ Готов к применению
