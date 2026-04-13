#!/usr/bin/env python3
"""
Простой скрипт для проверки и исправления базы данных

Проверяет наличие полей верификации и добавляет их при необходимости
"""

import sys
import os
from pathlib import Path

# Добавляем путь к проекту
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

# Добавляем путь к uk_management_bot
uk_bot_path = project_root / "uk_management_bot"
sys.path.append(str(uk_bot_path))

from uk_management_bot.database.session import engine
from sqlalchemy import text

def check_verification_fields():
    """Проверить наличие полей верификации"""
    print("🔍 Проверка полей верификации в таблице users...")
    
    try:
        with engine.connect() as conn:
            # Проверяем структуру таблицы users
            result = conn.execute(text("""
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns 
                WHERE table_name = 'users' 
                ORDER BY ordinal_position
            """))
            
            columns = [row[0] for row in result.fetchall()]
            print(f"📋 Найденные колонки: {columns}")
            
            # Проверяем наличие полей верификации
            verification_fields = [
                'verification_status',
                'verification_notes', 
                'verification_date',
                'verified_by',
                'passport_series',
                'passport_number',
                'birth_date'
            ]
            
            missing_fields = []
            for field in verification_fields:
                if field not in columns:
                    missing_fields.append(field)
            
            if missing_fields:
                print(f"❌ Отсутствуют поля: {missing_fields}")
                return False
            else:
                print("✅ Все поля верификации присутствуют")
                return True
                
    except Exception as e:
        print(f"❌ Ошибка при проверке: {e}")
        return False

def add_verification_fields():
    """Добавить поля верификации"""
    print("🔧 Добавление полей верификации...")
    
    try:
        with engine.connect() as conn:
            # Добавляем поля по одному
            fields_to_add = [
                ("verification_status", "VARCHAR(50) DEFAULT 'pending' NOT NULL"),
                ("verification_notes", "TEXT"),
                ("verification_date", "TIMESTAMP WITH TIME ZONE"),
                ("verified_by", "INTEGER"),
                ("passport_series", "VARCHAR(10)"),
                ("passport_number", "VARCHAR(10)"),
                ("birth_date", "TIMESTAMP WITH TIME ZONE")
            ]
            
            # Whitelist: field definitions are hardcoded above, not from user input.
            # Using f-string is safe here because both field_name and field_type
            # come from the fields_to_add tuple literal (not external input).
            # DDL identifiers (column names, types) cannot be parameterized in SQL.
            for field_name, field_type in fields_to_add:
                try:
                    conn.execute(text(f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {field_name} {field_type}"))
                    print(f"✅ Добавлено поле: {field_name}")
                except Exception as e:
                    print(f"⚠️ Ошибка при добавлении {field_name}: {e}")
            
            conn.commit()
            print("✅ Все поля добавлены")
            return True
            
    except Exception as e:
        print(f"❌ Ошибка при добавлении полей: {e}")
        return False

def check_verification_tables():
    """Проверить наличие таблиц верификации"""
    print("🔍 Проверка таблиц верификации...")
    
    try:
        with engine.connect() as conn:
            # Проверяем существование таблиц
            tables_to_check = [
                'user_documents',
                'user_verifications', 
                'access_rights'
            ]
            
            missing_tables = []
            for table in tables_to_check:
                result = conn.execute(
                    text("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = :tbl)"),
                    {"tbl": table}
                )
                
                if not result.scalar():
                    missing_tables.append(table)
                    print(f"❌ Таблица отсутствует: {table}")
                else:
                    print(f"✅ Таблица существует: {table}")
            
            return len(missing_tables) == 0
            
    except Exception as e:
        print(f"❌ Ошибка при проверке таблиц: {e}")
        return False

def create_verification_tables():
    """Создать таблицы верификации"""
    print("🔧 Создание таблиц верификации...")
    
    try:
        with engine.connect() as conn:
            # Создаем таблицу user_documents
            print("📄 Создание таблицы user_documents...")
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS user_documents (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    document_type VARCHAR(50) NOT NULL,
                    file_id VARCHAR(255) NOT NULL,
                    file_name VARCHAR(255),
                    file_size INTEGER,
                    verification_status VARCHAR(50) DEFAULT 'pending',
                    verification_notes TEXT,
                    verified_by INTEGER REFERENCES users(id),
                    verified_at TIMESTAMP WITH TIME ZONE,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                )
            """))
            
            # Создаем таблицу user_verifications
            print("🔍 Создание таблицы user_verifications...")
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS user_verifications (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    status VARCHAR(50) DEFAULT 'pending',
                    requested_info JSONB DEFAULT '{}',
                    requested_at TIMESTAMP WITH TIME ZONE,
                    requested_by INTEGER REFERENCES users(id),
                    admin_notes TEXT,
                    verified_by INTEGER REFERENCES users(id),
                    verified_at TIMESTAMP WITH TIME ZONE,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                )
            """))
            
            # Создаем таблицу access_rights
            print("🔐 Создание таблицы access_rights...")
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS access_rights (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    access_level VARCHAR(50) NOT NULL,
                    apartment_number VARCHAR(20),
                    house_number VARCHAR(20),
                    yard_name VARCHAR(100),
                    is_active BOOLEAN DEFAULT TRUE,
                    expires_at TIMESTAMP WITH TIME ZONE,
                    granted_by INTEGER NOT NULL REFERENCES users(id),
                    granted_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    notes TEXT,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                )
            """))
            
            conn.commit()
            print("✅ Все таблицы созданы")
            return True
            
    except Exception as e:
        print(f"❌ Ошибка при создании таблиц: {e}")
        return False

def main():
    """Главная функция"""
    print("🔧 ПРОВЕРКА И ИСПРАВЛЕНИЕ БАЗЫ ДАННЫХ")
    print("=" * 50)
    
    # Проверяем поля верификации
    fields_ok = check_verification_fields()
    
    if not fields_ok:
        print("\n🔧 Добавление недостающих полей...")
        add_verification_fields()
    
    # Проверяем таблицы верификации
    tables_ok = check_verification_tables()
    
    if not tables_ok:
        print("\n🔧 Создание недостающих таблиц...")
        create_verification_tables()
    
    # Финальная проверка
    print("\n🔍 Финальная проверка...")
    final_fields_ok = check_verification_fields()
    final_tables_ok = check_verification_tables()
    
    if final_fields_ok and final_tables_ok:
        print("\n✅ База данных готова к работе!")
        print("🔄 Перезапустите бота для применения изменений")
    else:
        print("\n❌ Проблемы с базой данных остались")

if __name__ == "__main__":
    main()
