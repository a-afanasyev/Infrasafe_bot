#!/bin/bash
# Скрипт для организации документации проекта

echo "📚 Организация документации UK Management Bot"
echo "=============================================="
echo ""

# Создаем структуру папок если их нет
mkdir -p docs/Archive/{Migration,Phase_Reports,Old_Docs,Database,Issues}

echo "📋 Анализ и классификация документов..."
echo ""

# Категории документов (актуальные -> в docs, устаревшие -> в Archive)
# Актуальные документы - перемещаем в docs
ACTUAL_DOCS=(
    "CONTEXT7_COMPLIANCE_REPORT.md"
    "README.md"
    "QUICK_START.md"
    "UNIFIED_SUMMARY.md"
    "UNIFIED_DEPLOYMENT.md"
    "UNIFIED_INDEX.md"
    "README.UNIFIED.md"
    "QUICKSTART.md"
    "DATABASE_README.md"
    "DATABASE_SCHEMA_ACTUAL.md"
    "SECURITY_AUDIT_FINAL.md"
    "SECURITY_STATUS.md"
    "MANUAL_TESTING_GUIDE.md"
    "DEVELOPMENT.md"
    "DOCKER_SETUP.md"
)

# Migration reports -> Archive/Migration
MIGRATION_DOCS=(
    "ASYNC_MIGRATION_PHASE1_REPORT.md"
    "ASYNC_MIGRATION_PHASE2A_REPORT.md"
    "DATABASE_MIGRATION_COMPLETED.md"
    "DATABASE_MIGRATION_GUIDE.md"
)

# Phase reports -> Archive/Phase_Reports
PHASE_DOCS=(
    "PHASE2B_FINAL_REPORT.md"
    "PHASE2B_DAY1-4_SUMMARY.md"
    "PHASE2B_DAY1-8_COMPLETE.md"
    "PHASE2B_DEPLOYMENT_CHECKLIST.md"
    "PHASE2B_DEPLOYMENT_REPORT.md"
    "PHASE2B_MIGRATION_PLAN.md"
    "PHASE2B_PERFORMANCE_METRICS.md"
    "PHASE2B_QUICK_REFERENCE.md"
    "PHASE2B_SESSION_SUMMARY.txt"
    "PHASE2B_TEST_EXECUTION_REPORT.md"
    "PHASE2B_TEST_SUMMARY.md"
    "PHASE2A_DEPLOYMENT_SUMMARY.md"
    "PHASE2_AI_MIGRATION_STRATEGY.md"
    "PHASE3_PLANNING.md"
    "SESSION_SUMMARY_2025-10-16.md"
    "SESSION_SUMMARY_2025-10-20.md"
)

# Database docs -> Archive/Database
DB_DOCS=(
    "DATABASE_ACTION_PLAN.md"
    "DATABASE_CORRECTIONS.md"
    "DATABASE_ENUM_TYPES_FIX.md"
    "DATABASE_ER_DIAGRAM.md"
    "DATABASE_FINAL_SUMMARY.md"
    "DATABASE_RECOMMENDATIONS.md"
    "DATABASE_SCHEMA.md"
    "database_schema.sql.old"
    "SQL_Startup.sql.old"
)

# Fix issues -> Archive/Issues
FIX_DOCS=(
    "FIX_ASSIGNMENT_FOREIGN_KEY.md"
    "FIX_COMPLETED_REQUESTS_FILTERING.md"
    "FIX_DUTY_ASSIGNMENT_ERROR.md"
    "FIX_GROUP_ASSIGNMENT_NOTIFICATIONS.md"
    "FIX_MEDIA_SERVICE_CONNECTION.md"
    "FIX_MEDIA_UPLOAD_ERROR.md"
    "FIX_RETURNED_REQUESTS_VISIBILITY.md"
    "FIX_ROLE_SELECTION_BUTTON.md"
    "FIX_SPECIFIC_ASSIGNMENT_ERROR.md"
    "REMOVE_ACCEPTED_STATUS.md"
)

# Old docs
OLD_DOCS=(
    "Codex_audit.md"
    "CLAUDE.md"
    "AI_REALISTIC_TIMELINE.md"
    "ARCHITECTURE_COMPARISON.md"
    "main.file"
    "IMPLEMENTATION_PLAN.md"
    "MICROSERVICES_ANALYSIS.md"
    "MIGRATION_TASKS_ANALYSIS.md"
    "migration_tasks.md"
    "NEXT_ACTIONS.md"
    "NEXT_SESSION_GUIDE.md"
    "RESTORE_DATABASE_FROM_SCRATCH.md"
)

echo "✅ Категории определены"
echo ""

# Функция для перемещения с проверкой
move_file() {
    local file=$1
    local dest=$2
    if [ -f "$file" ]; then
        echo "  📄 $file -> $dest"
        mkdir -p "$dest"
        mv "$file" "$dest/"
    else
        echo "  ⚠️  Не найден: $file"
    fi
}

echo "📦 Перемещение актуальных документов в docs/..."
for file in "${ACTUAL_DOCS[@]}"; do
    move_file "$file" "docs/"
done

echo ""
echo "📦 Перемещение migration отчетов..."
for file in "${MIGRATION_DOCS[@]}"; do
    move_file "$file" "docs/Archive/Migration/"
done

echo ""
echo "📦 Перемещение phase отчетов..."
for file in "${PHASE_DOCS[@]}"; do
    move_file "$file" "docs/Archive/Phase_Reports/"
done

echo ""
echo "📦 Перемещение database документов..."
for file in "${DB_DOCS[@]}"; do
    move_file "$file" "docs/Archive/Database/"
done

echo ""
echo "📦 Перемещение fix документов..."
for file in "${FIX_DOCS[@]}"; do
    move_file "$file" "docs/Archive/Issues/"
done

echo ""
echo "📦 Перемещение устаревших документов..."
for file in "${OLD_DOCS[@]}"; do
    move_file "$file" "docs/Archive/Old_Docs/"
done

echo ""
echo "✅ Организация завершена!"
echo ""
echo "📊 Итоговая структура:"
echo "  docs/ - актуальные документы"
echo "  docs/Archive/ - архивные документы"
echo "    ├── Migration/ - отчеты по миграциям"
echo "    ├── Phase_Reports/ - отчеты по фазам"
echo "    ├── Database/ - документы по БД"
echo "    ├── Issues/ - документы по исправлениям"
echo "    └── Old_Docs/ - устаревшие документы"

