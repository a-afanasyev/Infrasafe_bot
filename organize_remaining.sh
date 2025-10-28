#!/bin/bash
# Скрипт для организации оставшихся файлов в корне проекта

echo "📚 Организация оставшихся файлов UK Management Bot"
echo "=============================================="
echo ""

# Создаем дополнительные папки в архиве
mkdir -p docs/Archive/{Features,Deployment,Integration,SQL_Scripts,Config_Files}

echo "📋 Категоризация оставшихся файлов..."
echo ""

# Feature documentation -> docs/Archive/Features
FEATURE_DOCS=(
    "ADD_ASSIGNMENT_INFO_TO_REQUEST_VIEW.md"
    "ADMIN_ALL_ROLES_UPDATE.md"
    "ADMIN_INITIALIZATION.md"
    "DUTY_ASSIGNMENT_SYSTEM.md"
    "MIGRATION_REQUEST_ASSIGNMENTS.md"
    "SYNC_REQUEST_STATUSES.md"
    "USER_YARDS_FEATURE.md"
)

# Deployment documentation -> docs/Archive/Deployment
DEPLOYMENT_DOCS=(
    "DEPLOYMENT_ANALYSIS_REPORT.md"
    "DEPLOYMENT_FIXES.md"
    "SERVER_SETUP_GUIDE.md"
    "QUICK_DEV_START.md"
    "QUICK_MIGRATION.md"
)

# Integration documentation -> docs/Archive/Integration
INTEGRATION_DOCS=(
    "GOOGLE_SHEETS_IMPORT_GUIDE.md"
    "SHEETS_INTEGRATION_PLAN.md"
)



# Audit and analysis -> docs/Archive
AUDIT_DOCS=(
    "SQL_FILES_AUDIT.md"
    "codex_mc.md"
)

# SQL scripts -> docs/Archive/SQL_Scripts
SQL_FILES=(
    "REMOVE_ACCEPTED_STATUS.sql"
    "add_media_record.sql"
    "database_schema_actual.sql"
    "backup_phase2b_20251020_194140.sql"
    "migrate_assignments.py"
)

# Project files -> docs/
PROJECT_DOCS=(
    "project.md"
    "UNIFIED_FILES_SUMMARY.txt"
    "GIT_COMMIT_FILES.txt"
)

# Move feature docs
echo "📦 Перемещение feature документации..."
for file in "${FEATURE_DOCS[@]}"; do
    if [ -f "$file" ]; then
        echo "  📄 $file -> docs/Archive/Features/"
        mv "$file" "docs/Archive/Features/"
    fi
done

echo ""
echo "📦 Перемещение deployment документации..."
for file in "${DEPLOYMENT_DOCS[@]}"; do
    if [ -f "$file" ]; then
        echo "  📄 $file -> docs/Archive/Deployment/"
        mv "$file" "docs/Archive/Deployment/"
    fi
done

echo ""
echo "📦 Перемещение integration документации..."
for file in "${INTEGRATION_DOCS[@]}"; do
    if [ -f "$file" ]; then
        echo "  📄 $file -> docs/Archive/Integration/"
        mv "$file" "docs/Archive/Integration/"
    fi
done

echo ""
echo "📦 Перемещение manager документации..."
for file in "${MANAGER_DOCS[@]}"; do
    if [ -f "$file" ]; then
        echo "  📄 $file -> docs/Archive/Features/Manager/"
        mv "$file" "docs/Archive/Features/Manager/"
    fi
done

echo ""
echo "📦 Перемещение audit документации..."
for file in "${AUDIT_DOCS[@]}"; do
    if [ -f "$file" ]; then
        echo "  📄 $file -> docs/Archive/Old_Docs/"
        mv "$file" "docs/Archive/Old_Docs/"
    fi
done

echo ""
echo "📦 Перемещение SQL скриптов..."
for file in "${SQL_FILES[@]}"; do
    if [ -f "$file" ]; then
        echo "  📄 $file -> docs/Archive/SQL_Scripts/"
        mv "$file" "docs/Archive/SQL_Scripts/"
    fi
done

echo ""
echo "📦 Перемещение project файлов..."
for file in "${PROJECT_DOCS[@]}"; do
    if [ -f "$file" ]; then
        echo "  📄 $file -> docs/"
        mv "$file" "docs/"
    fi
done

echo ""
echo "✅ Организация завершена!"
echo ""
echo "📊 Итоговая структура:"
echo "  docs/ - актуальные и project файлы"
echo "  docs/Archive/ - архивные документы"
echo "    ├── Features/ - документация по фичам"
echo "    │   └── Manager/ - документация менеджера"
echo "    ├── Deployment/ - документация по развертыванию"
echo "    ├── Integration/ - документация по интеграциям"
echo "    ├── SQL_Scripts/ - SQL скрипты"
echo "    └── ... другие категории"
