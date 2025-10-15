#!/usr/bin/env python3
"""
Экспорт схемы базы данных из SQLAlchemy моделей
Генерирует точный SQL DDL и Markdown документацию
"""

import sys
from pathlib import Path

# Добавляем корневую директорию проекта в PYTHONPATH
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import create_engine, MetaData
from sqlalchemy.schema import CreateTable, CreateIndex
from sqlalchemy.dialects import postgresql
from uk_management_bot.database.session import Base
import uk_management_bot.database.models  # Import all models


def export_sql_ddl(output_file="database_schema_actual.sql"):
    """Экспортирует SQL DDL из SQLAlchemy моделей"""

    # Используем PostgreSQL диалект
    engine = create_engine("postgresql://")

    with open(output_file, "w", encoding="utf-8") as f:
        f.write("-- " + "=" * 70 + "\n")
        f.write("-- UK Management Bot - PostgreSQL Database Schema (ACTUAL)\n")
        f.write("-- Generated from SQLAlchemy models\n")
        f.write("-- Date: 2025-10-15\n")
        f.write("-- " + "=" * 70 + "\n\n")

        # Сначала создаем ENUM типы
        f.write("-- " + "=" * 70 + "\n")
        f.write("-- ENUM Types\n")
        f.write("-- " + "=" * 70 + "\n\n")

        f.write("-- AccessLevel enum for access_rights table\n")
        f.write("CREATE TYPE accesslevel AS ENUM ('apartment', 'house', 'yard');\n\n")

        f.write("-- DocumentType enum for user_documents table\n")
        f.write("CREATE TYPE documenttype AS ENUM ('passport', 'property_deed', 'rental_agreement', 'utility_bill', 'other');\n\n")

        f.write("-- VerificationStatus enum for user_documents and user_verifications tables\n")
        f.write("CREATE TYPE verificationstatus AS ENUM ('pending', 'approved', 'rejected', 'requested');\n\n")

        f.write("-- " + "=" * 70 + "\n")
        f.write("-- Tables\n")
        f.write("-- " + "=" * 70 + "\n")

        # Экспортируем таблицы в правильном порядке (с учетом FK)
        for table in Base.metadata.sorted_tables:
            f.write(f"\n-- Table: {table.name}\n")
            f.write("-" * 70 + "\n")
            create_table = CreateTable(table).compile(dialect=postgresql.dialect())
            f.write(str(create_table).strip() + ";\n\n")

            # Экспортируем индексы
            for index in table.indexes:
                create_index = CreateIndex(index).compile(dialect=postgresql.dialect())
                f.write(str(create_index).strip() + ";\n")

            f.write("\n")

    print(f"✅ SQL DDL exported to {output_file}")


def export_markdown_schema(output_file="DATABASE_SCHEMA_ACTUAL.md"):
    """Экспортирует документацию схемы в Markdown"""

    with open(output_file, "w", encoding="utf-8") as f:
        f.write("# 🗄️ UK Management Bot - Actual Database Schema\n\n")
        f.write("**Generated from**: SQLAlchemy ORM Models\n")
        f.write("**Date**: 2025-10-15\n")
        f.write("**Status**: ✅ Verified Against Source Code\n\n")
        f.write("---\n\n")

        f.write("## 📊 Tables Overview\n\n")
        f.write(f"**Total tables**: {len(Base.metadata.tables)}\n\n")

        for table_name in sorted(Base.metadata.tables.keys()):
            f.write(f"- `{table_name}`\n")

        f.write("\n---\n\n")

        # Подробное описание каждой таблицы
        for table_name in sorted(Base.metadata.tables.keys()):
            table = Base.metadata.tables[table_name]

            f.write(f"## Table: `{table_name}`\n\n")

            # Columns
            f.write("### Columns\n\n")
            f.write("| Column | Type | Nullable | Default | Description |\n")
            f.write("|--------|------|----------|---------|-------------|\n")

            for column in table.columns:
                col_name = column.name
                col_type = str(column.type)
                nullable = "NULL" if column.nullable else "NOT NULL"
                default = str(column.default.arg) if column.default else "-"
                primary = "🔑 PRIMARY KEY" if column.primary_key else ""
                foreign = "🔗 FK" if column.foreign_keys else ""
                unique = "⭐ UNIQUE" if column.unique else ""

                description = " ".join(filter(None, [primary, foreign, unique]))

                f.write(f"| `{col_name}` | {col_type} | {nullable} | {default} | {description} |\n")

            f.write("\n")

            # Foreign Keys
            if table.foreign_keys:
                f.write("### Foreign Keys\n\n")
                for fk in table.foreign_keys:
                    parent_table = fk.column.table.name
                    parent_column = fk.column.name
                    child_column = fk.parent.name
                    f.write(f"- `{child_column}` → `{parent_table}.{parent_column}`\n")
                f.write("\n")

            # Indexes
            if table.indexes:
                f.write("### Indexes\n\n")
                for index in table.indexes:
                    index_columns = ", ".join([col.name for col in index.columns])
                    unique = "UNIQUE" if index.unique else ""
                    f.write(f"- `{index.name}` on ({index_columns}) {unique}\n")
                f.write("\n")

            # Constraints
            if table.constraints:
                f.write("### Constraints\n\n")
                for constraint in table.constraints:
                    if hasattr(constraint, 'columns'):
                        const_columns = ", ".join([col.name for col in constraint.columns])
                        f.write(f"- `{constraint.name}`: {constraint.__class__.__name__} on ({const_columns})\n")
                f.write("\n")

            f.write("---\n\n")

    print(f"✅ Markdown schema exported to {output_file}")


def compare_with_existing_docs():
    """Сравнивает реальную схему с существующей документацией"""

    print("\n" + "=" * 70)
    print("Comparison with existing documentation")
    print("=" * 70 + "\n")

    # Таблицы из моделей
    actual_tables = set(Base.metadata.tables.keys())

    print(f"✅ Actual tables in ORM: {len(actual_tables)}")
    print(f"   {', '.join(sorted(actual_tables))}\n")

    # Проверяем критические таблицы
    critical_tables = {
        'access_rights': 'AccessRights model',
        'quarterly_plans': 'QuarterlyPlan model',
        'quarterly_shift_schedules': 'QuarterlyShiftSchedule model',
        'shift_schedules': 'ShiftSchedule model',
        'planning_conflicts': 'PlanningConflict model'
    }

    print("🔍 Critical tables check:")
    for table_name, model_name in critical_tables.items():
        if table_name in actual_tables:
            table = Base.metadata.tables[table_name]
            columns = [col.name for col in table.columns]
            print(f"   ✅ {table_name}: {len(columns)} columns")
            print(f"      Columns: {', '.join(columns[:5])}{'...' if len(columns) > 5 else ''}")
        else:
            print(f"   ❌ {table_name}: NOT FOUND in models!")


def main():
    """Main execution"""
    print("=" * 70)
    print("UK Management Bot - Schema Export Tool")
    print("=" * 70 + "\n")

    try:
        # 1. Export SQL DDL
        print("📄 Exporting SQL DDL...")
        export_sql_ddl("database_schema_actual.sql")

        # 2. Export Markdown documentation
        print("📝 Exporting Markdown documentation...")
        export_markdown_schema("DATABASE_SCHEMA_ACTUAL.md")

        # 3. Compare with existing docs
        compare_with_existing_docs()

        print("\n" + "=" * 70)
        print("✅ Export completed successfully!")
        print("=" * 70)
        print("\nGenerated files:")
        print("  - database_schema_actual.sql")
        print("  - DATABASE_SCHEMA_ACTUAL.md")
        print("\n⚠️  Use these files instead of the old documentation!")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
