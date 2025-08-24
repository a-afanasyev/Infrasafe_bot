#!/usr/bin/env python3
"""
Скрипт миграции данных из SQLite в PostgreSQL
Переносит все данные из uk_management.db в PostgreSQL
"""

import sqlite3
import psycopg2
import json
import logging
from datetime import datetime
from typing import Any, Dict, List

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Конфигурация подключений
SQLITE_DB_PATH = "uk_management.db"
POSTGRES_CONFIG = {
    "host": "postgres",  # Имя контейнера PostgreSQL
    "port": 5432,
    "database": "uk_management",
    "user": "uk_bot",
    "password": "uk_bot_password"
}

def connect_sqlite():
    """Подключение к SQLite"""
    try:
        conn = sqlite3.connect(SQLITE_DB_PATH)
        conn.row_factory = sqlite3.Row  # Для доступа к колонкам по имени
        return conn
    except Exception as e:
        logger.error(f"Ошибка подключения к SQLite: {e}")
        raise

def connect_postgres():
    """Подключение к PostgreSQL"""
    try:
        conn = psycopg2.connect(**POSTGRES_CONFIG)
        return conn
    except Exception as e:
        logger.error(f"Ошибка подключения к PostgreSQL: {e}")
        raise

def get_table_data(sqlite_conn, table_name: str) -> List[Dict[str, Any]]:
    """Получение всех данных из таблицы SQLite"""
    try:
        cursor = sqlite_conn.cursor()
        cursor.execute(f"SELECT * FROM {table_name}")
        rows = cursor.fetchall()
        
        # Конвертируем в список словарей
        data = []
        for row in rows:
            row_dict = dict(row)
            data.append(row_dict)
        
        logger.info(f"Получено {len(data)} записей из таблицы {table_name}")
        return data
    except Exception as e:
        logger.error(f"Ошибка получения данных из {table_name}: {e}")
        raise

def migrate_users(sqlite_conn, postgres_conn):
    """Миграция пользователей"""
    logger.info("Начинаем миграцию пользователей...")
    
    users_data = get_table_data(sqlite_conn, "users")
    
    cursor = postgres_conn.cursor()
    
    for user in users_data:
        try:
            # Подготавливаем данные для вставки
            cursor.execute("""
                INSERT INTO users (
                    telegram_id, username, first_name, last_name,
                    role, roles, active_role, status, language,
                    phone, address, home_address, apartment_address,
                    yard_address, address_type, specialization,
                    created_at, updated_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s
                ) ON CONFLICT (telegram_id) DO UPDATE SET
                    username = EXCLUDED.username,
                    first_name = EXCLUDED.first_name,
                    last_name = EXCLUDED.last_name,
                    role = EXCLUDED.role,
                    roles = EXCLUDED.roles,
                    active_role = EXCLUDED.active_role,
                    status = EXCLUDED.status,
                    language = EXCLUDED.language,
                    phone = EXCLUDED.phone,
                    address = EXCLUDED.address,
                    home_address = EXCLUDED.home_address,
                    apartment_address = EXCLUDED.apartment_address,
                    yard_address = EXCLUDED.yard_address,
                    address_type = EXCLUDED.address_type,
                    specialization = EXCLUDED.specialization,
                    updated_at = NOW()
            """, (
                user['telegram_id'], user['username'], user['first_name'], user['last_name'],
                user['role'], user.get('roles'), user.get('active_role'), user['status'], user['language'],
                user.get('phone'), user.get('address'), user.get('home_address'), user.get('apartment_address'),
                user.get('yard_address'), user.get('address_type'), user.get('specialization'),
                user['created_at'], user.get('updated_at', user['created_at'])
            ))
            
        except Exception as e:
            logger.error(f"Ошибка миграции пользователя {user.get('telegram_id')}: {e}")
            postgres_conn.rollback()
            raise
    
    postgres_conn.commit()
    logger.info(f"Успешно мигрировано {len(users_data)} пользователей")

def migrate_requests(sqlite_conn, postgres_conn):
    """Миграция заявок"""
    logger.info("Начинаем миграцию заявок...")
    
    requests_data = get_table_data(sqlite_conn, "requests")
    
    cursor = postgres_conn.cursor()
    
    # Создаем маппинг telegram_id -> id пользователей
    cursor.execute("SELECT id, telegram_id FROM users")
    user_mapping = {row[1]: row[0] for row in cursor.fetchall()}
    
    for request in requests_data:
        try:
            # Получаем правильный user_id из маппинга
            telegram_id = request['user_id']
            if telegram_id not in user_mapping:
                logger.warning(f"Пользователь с telegram_id {telegram_id} не найден, пропускаем заявку {request.get('id')}")
                continue
            
            user_id = user_mapping[telegram_id]
            
            # Получаем executor_id если есть
            executor_id = None
            if request.get('executor_id'):
                executor_telegram_id = request['executor_id']
                if executor_telegram_id in user_mapping:
                    executor_id = user_mapping[executor_telegram_id]
                else:
                    logger.warning(f"Исполнитель с telegram_id {executor_telegram_id} не найден")
            
            # Конвертируем JSON поля
            media_files = request.get('media_files')
            if media_files and isinstance(media_files, str):
                try:
                    media_files = json.loads(media_files)
                except:
                    media_files = []
            
            completion_media = request.get('completion_media')
            if completion_media and isinstance(completion_media, str):
                try:
                    completion_media = json.loads(completion_media)
                except:
                    completion_media = []
            
            cursor.execute("""
                INSERT INTO requests (
                    user_id, category, status, address, description,
                    apartment, urgency, media_files, executor_id,
                    notes, completion_report, completion_media,
                    created_at, updated_at, completed_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s
                ) ON CONFLICT (id) DO UPDATE SET
                    user_id = EXCLUDED.user_id,
                    category = EXCLUDED.category,
                    status = EXCLUDED.status,
                    address = EXCLUDED.address,
                    description = EXCLUDED.description,
                    apartment = EXCLUDED.apartment,
                    urgency = EXCLUDED.urgency,
                    media_files = EXCLUDED.media_files,
                    executor_id = EXCLUDED.executor_id,
                    notes = EXCLUDED.notes,
                    completion_report = EXCLUDED.completion_report,
                    completion_media = EXCLUDED.completion_media,
                    updated_at = NOW()
            """, (
                user_id, request['category'], request['status'], 
                request['address'], request['description'], request.get('apartment'),
                request['urgency'], json.dumps(media_files) if media_files else None,
                executor_id, request.get('notes'), request.get('completion_report'),
                json.dumps(completion_media) if completion_media else None,
                request['created_at'], request.get('updated_at', request['created_at']),
                request.get('completed_at')
            ))
            
        except Exception as e:
            logger.error(f"Ошибка миграции заявки {request.get('id')}: {e}")
            postgres_conn.rollback()
            raise
    
    postgres_conn.commit()
    logger.info(f"Успешно мигрировано {len(requests_data)} заявок")

def migrate_shifts(sqlite_conn, postgres_conn):
    """Миграция смен"""
    logger.info("Начинаем миграцию смен...")
    
    shifts_data = get_table_data(sqlite_conn, "shifts")
    
    cursor = postgres_conn.cursor()
    
    # Создаем маппинг telegram_id -> id пользователей
    cursor.execute("SELECT id, telegram_id FROM users")
    user_mapping = {row[1]: row[0] for row in cursor.fetchall()}
    
    for shift in shifts_data:
        try:
            # Получаем правильный user_id из маппинга
            telegram_id = shift['user_id']
            if telegram_id not in user_mapping:
                logger.warning(f"Пользователь с telegram_id {telegram_id} не найден, пропускаем смену {shift.get('id')}")
                continue
            
            user_id = user_mapping[telegram_id]
            
            cursor.execute("""
                INSERT INTO shifts (
                    user_id, start_time, end_time, status,
                    notes, created_at, updated_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s
                ) ON CONFLICT (id) DO UPDATE SET
                    user_id = EXCLUDED.user_id,
                    start_time = EXCLUDED.start_time,
                    end_time = EXCLUDED.end_time,
                    status = EXCLUDED.status,
                    notes = EXCLUDED.notes,
                    updated_at = NOW()
            """, (
                user_id, shift['start_time'], shift.get('end_time'),
                shift['status'], shift.get('notes'), shift['created_at'],
                shift.get('updated_at', shift['created_at'])
            ))
            
        except Exception as e:
            logger.error(f"Ошибка миграции смены {shift.get('id')}: {e}")
            postgres_conn.rollback()
            raise
    
    postgres_conn.commit()
    logger.info(f"Успешно мигрировано {len(shifts_data)} смен")

def migrate_ratings(sqlite_conn, postgres_conn):
    """Миграция оценок"""
    logger.info("Начинаем миграцию оценок...")
    
    ratings_data = get_table_data(sqlite_conn, "ratings")
    
    cursor = postgres_conn.cursor()
    
    # Создаем маппинг telegram_id -> id пользователей
    cursor.execute("SELECT id, telegram_id FROM users")
    user_mapping = {row[1]: row[0] for row in cursor.fetchall()}
    
    for rating in ratings_data:
        try:
            # Получаем правильный user_id из маппинга
            telegram_id = rating['user_id']
            if telegram_id not in user_mapping:
                logger.warning(f"Пользователь с telegram_id {telegram_id} не найден, пропускаем оценку {rating.get('id')}")
                continue
            
            user_id = user_mapping[telegram_id]
            
            cursor.execute("""
                INSERT INTO ratings (
                    request_id, user_id, rating, review, created_at
                ) VALUES (
                    %s, %s, %s, %s, %s
                ) ON CONFLICT (id) DO UPDATE SET
                    request_id = EXCLUDED.request_id,
                    user_id = EXCLUDED.user_id,
                    rating = EXCLUDED.rating,
                    review = EXCLUDED.review
            """, (
                rating['request_id'], user_id, rating['rating'],
                rating.get('review'), rating['created_at']
            ))
            
        except Exception as e:
            logger.error(f"Ошибка миграции оценки {rating.get('id')}: {e}")
            postgres_conn.rollback()
            raise
    
    postgres_conn.commit()
    logger.info(f"Успешно мигрировано {len(ratings_data)} оценок")

def migrate_audit_logs(sqlite_conn, postgres_conn):
    """Миграция аудита"""
    logger.info("Начинаем миграцию аудита...")
    
    audit_data = get_table_data(sqlite_conn, "audit_logs")
    
    cursor = postgres_conn.cursor()
    
    # Создаем маппинг telegram_id -> id пользователей
    cursor.execute("SELECT id, telegram_id FROM users")
    user_mapping = {row[1]: row[0] for row in cursor.fetchall()}
    
    for audit in audit_data:
        try:
            # Получаем правильный user_id из маппинга
            user_id = None
            if audit.get('user_id'):
                telegram_id = audit['user_id']
                if telegram_id in user_mapping:
                    user_id = user_mapping[telegram_id]
                else:
                    logger.warning(f"Пользователь с telegram_id {telegram_id} не найден для аудита {audit.get('id')}")
            
            # Конвертируем JSON поле
            details = audit.get('details')
            if details and isinstance(details, str):
                try:
                    details = json.loads(details)
                except:
                    details = None
            
            cursor.execute("""
                INSERT INTO audit_logs (
                    user_id, action, details, ip_address, created_at
                ) VALUES (
                    %s, %s, %s, %s, %s
                ) ON CONFLICT (id) DO UPDATE SET
                    user_id = EXCLUDED.user_id,
                    action = EXCLUDED.action,
                    details = EXCLUDED.details,
                    ip_address = EXCLUDED.ip_address
            """, (
                user_id, audit['action'], 
                json.dumps(details) if details else None,
                audit.get('ip_address'), audit['created_at']
            ))
            
        except Exception as e:
            logger.error(f"Ошибка миграции аудита {audit.get('id')}: {e}")
            postgres_conn.rollback()
            raise
    
    postgres_conn.commit()
    logger.info(f"Успешно мигрировано {len(audit_data)} записей аудита")

def main():
    """Основная функция миграции"""
    logger.info("🚀 Начинаем миграцию данных из SQLite в PostgreSQL")
    
    try:
        # Подключаемся к базам данных
        sqlite_conn = connect_sqlite()
        postgres_conn = connect_postgres()
        
        logger.info("✅ Подключения к базам данных установлены")
        
        # Выполняем миграцию по таблицам
        migrate_users(sqlite_conn, postgres_conn)
        migrate_requests(sqlite_conn, postgres_conn)
        migrate_shifts(sqlite_conn, postgres_conn)
        migrate_ratings(sqlite_conn, postgres_conn)
        migrate_audit_logs(sqlite_conn, postgres_conn)
        
        logger.info("🎉 Миграция завершена успешно!")
        
        # Выводим статистику
        cursor = postgres_conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users")
        users_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM requests")
        requests_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM shifts")
        shifts_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM ratings")
        ratings_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM audit_logs")
        audit_count = cursor.fetchone()[0]
        
        logger.info("📊 Статистика после миграции:")
        logger.info(f"   👥 Пользователи: {users_count}")
        logger.info(f"   📝 Заявки: {requests_count}")
        logger.info(f"   ⏰ Смены: {shifts_count}")
        logger.info(f"   ⭐ Оценки: {ratings_count}")
        logger.info(f"   📋 Аудит: {audit_count}")
        
    except Exception as e:
        logger.error(f"❌ Ошибка миграции: {e}")
        raise
    finally:
        # Закрываем соединения
        if 'sqlite_conn' in locals():
            sqlite_conn.close()
        if 'postgres_conn' in locals():
            postgres_conn.close()
        logger.info("🔒 Соединения с базами данных закрыты")

if __name__ == "__main__":
    main()
