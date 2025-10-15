#!/bin/bash
# Скрипт очистки устаревших SQL файлов
# Использование: ./scripts/cleanup_sql.sh

set -e

echo "=============================================="
echo "🧹 Очистка устаревших SQL файлов"
echo "=============================================="
echo ""

# Переход в корневую директорию проекта
cd "$(dirname "$0")/.."

echo "📂 Текущая директория: $(pwd)"
echo ""

# Показываем текущее состояние
echo "📊 Текущие SQL файлы:"
ls -lh *.sql 2>/dev/null | awk '{print "  " $9, "-", $5}'
echo ""

# Подтверждение
read -p "❓ Продолжить очистку? (y/N): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "❌ Очистка отменена"
    exit 0
fi

echo ""
echo "🔄 Начинаем очистку..."
echo ""

# Переименование устаревших
if [ -f "database_schema.sql" ]; then
    echo "📦 Архивирование database_schema.sql -> database_schema.sql.old"
    mv database_schema.sql database_schema.sql.old
else
    echo "ℹ️  database_schema.sql не найден (уже удален?)"
fi

if [ -f "SQL_Startup.sql" ]; then
    echo "📦 Архивирование SQL_Startup.sql -> SQL_Startup.sql.old"
    mv SQL_Startup.sql SQL_Startup.sql.old
else
    echo "ℹ️  SQL_Startup.sql не найден (уже удален?)"
fi

echo ""

# Удаление тестовых файлов
echo "🗑️  Удаление тестовых SQL файлов..."

removed_count=0

for file in apply_shift_migration.sql create_test_data.sql create_simple_test_data.sql create_full_test_data.sql create_working_test_data.sql; do
    if [ -f "$file" ]; then
        echo "  ✓ Удален: $file"
        rm -f "$file"
        ((removed_count++))
    fi
done

if [ $removed_count -eq 0 ]; then
    echo "  ℹ️  Тестовые файлы не найдены (уже удалены?)"
else
    echo "  ✓ Удалено файлов: $removed_count"
fi

echo ""

# Проверка временных файлов
if [ -f "add_media_record.sql" ]; then
    echo "⚠️  Найден временный файл: add_media_record.sql"
    echo "   Дата: $(stat -f "%Sm" -t "%Y-%m-%d %H:%M" add_media_record.sql)"
    echo ""
    read -p "   Удалить этот файл? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        rm -f add_media_record.sql
        echo "  ✓ Удален: add_media_record.sql"
    else
        echo "  ℹ️  Оставлен: add_media_record.sql"
    fi
else
    echo "ℹ️  Временные файлы не найдены"
fi

echo ""
echo "=============================================="
echo "✅ Очистка завершена!"
echo "=============================================="
echo ""

# Показываем итоговое состояние
echo "📊 Оставшиеся SQL файлы:"
if ls *.sql 1> /dev/null 2>&1; then
    ls -lh *.sql | awk '{print "  " $9, "-", $5}'
else
    echo "  (SQL файлы не найдены)"
fi

echo ""

# Показываем архивированные файлы
if ls *.sql.old 1> /dev/null 2>&1; then
    echo "📦 Архивированные файлы (.old):"
    ls -lh *.sql.old | awk '{print "  " $9, "-", $5}'
    echo ""
    echo "💡 Эти файлы можно удалить через 2 недели если не понадобятся"
fi

echo ""
echo "📝 Рекомендации:"
echo "  1. Проверьте что database_schema_actual.sql на месте"
echo "  2. Добавьте *.sql.old в .gitignore"
echo "  3. Через 2 недели удалите .old файлы: rm -f *.sql.old"
echo ""
