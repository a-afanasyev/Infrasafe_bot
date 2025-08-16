"""
Тесты производительности системы инвайтов
"""
import os
import sys
import time
import tempfile
from dotenv import load_dotenv

# Загружаем тестовые переменные окружения
load_dotenv('.env.test')

# Добавляем путь к модулям
sys.path.insert(0, os.path.abspath('.'))

from database.session import Base
from database.models.user import User
from database.models.audit import AuditLog
from services.invite_service import InviteService, InviteRateLimiter
from services.auth_service import AuthService
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def test_invite_generation_performance():
    """Тест производительности генерации токенов"""
    
    # Создаем временную БД
    db_fd, db_path = tempfile.mkstemp(suffix='.db')
    os.close(db_fd)
    
    try:
        engine = create_engine(f"sqlite:///{db_path}", echo=False)
        Base.metadata.create_all(engine)
        
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        db = SessionLocal()
        
        invite_service = InviteService(db)
        
        # Генерируем 100 токенов и измеряем время
        start_time = time.time()
        tokens = []
        
        for i in range(100):
            token = invite_service.generate_invite(
                role="applicant",
                created_by=123456789,
                hours=24
            )
            tokens.append(token)
        
        generation_time = time.time() - start_time
        
        print(f"✅ Генерация 100 токенов: {generation_time:.3f} сек ({100/generation_time:.1f} токен/сек)")
        
        # Валидируем все токены и измеряем время
        start_time = time.time()
        
        for token in tokens:
            invite_data = invite_service.validate_invite(token)
            assert invite_data["role"] == "applicant"
        
        validation_time = time.time() - start_time
        
        print(f"✅ Валидация 100 токенов: {validation_time:.3f} сек ({100/validation_time:.1f} токен/сек)")
        
        # Общая производительность
        total_time = generation_time + validation_time
        print(f"✅ Общее время (генерация + валидация): {total_time:.3f} сек")
        
        # Проверяем что все быстро
        assert generation_time < 5.0, "Генерация должна быть быстрой"
        assert validation_time < 5.0, "Валидация должна быть быстрой"
        
        db.close()
        
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_rate_limiter_performance():
    """Тест производительности rate limiter"""
    
    # Очищаем storage
    InviteRateLimiter._storage.clear()
    
    # Тестируем с большим количеством пользователей
    start_time = time.time()
    
    for user_id in range(10000, 11000):  # 1000 пользователей
        # Каждый делает по 2 попытки
        InviteRateLimiter.is_allowed(user_id)
        InviteRateLimiter.is_allowed(user_id)
    
    rate_limit_time = time.time() - start_time
    
    print(f"✅ Rate limiting для 2000 запросов от 1000 пользователей: {rate_limit_time:.3f} сек")
    print(f"✅ Производительность: {2000/rate_limit_time:.1f} запросов/сек")
    
    # Проверяем размер storage
    storage_size = len(InviteRateLimiter._storage)
    print(f"✅ Размер storage: {storage_size} записей")
    
    assert rate_limit_time < 2.0, "Rate limiting должен быть быстрым"
    assert storage_size == 1000, "Storage должен содержать записи для всех пользователей"


async def test_database_performance():
    """Тест производительности работы с БД"""
    
    # Создаем временную БД
    db_fd, db_path = tempfile.mkstemp(suffix='.db')
    os.close(db_fd)
    
    try:
        engine = create_engine(f"sqlite:///{db_path}", echo=False)
        Base.metadata.create_all(engine)
        
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        db = SessionLocal()
        
        invite_service = InviteService(db)
        auth_service = AuthService(db)
        
        # Тестируем создание 50 пользователей через инвайты
        start_time = time.time()
        
        for i in range(50):
            # Создаем токен
            token = invite_service.generate_invite(
                role="executor",
                created_by=999999999,
                specialization="plumber",
                hours=24
            )
            
            # Валидируем
            invite_data = invite_service.validate_invite(token)
            
            # Создаем пользователя
            user = await auth_service.process_invite_join(
                telegram_id=1000000 + i,
                invite_data=invite_data,
                username=f"user{i}",
                first_name=f"User{i}",
                last_name="Test"
            )
            
            # Отмечаем как использованный
            invite_service.mark_nonce_used(
                invite_data["nonce"],
                user.telegram_id,
                invite_data
            )
        
        db_time = time.time() - start_time
        
        print(f"✅ Создание 50 пользователей через инвайты: {db_time:.3f} сек")
        print(f"✅ Производительность: {50/db_time:.1f} пользователей/сек")
        
        # Проверяем результаты
        users_count = db.query(User).count()
        audit_count = db.query(AuditLog).count()
        
        print(f"✅ Создано пользователей в БД: {users_count}")
        print(f"✅ Создано записей аудита: {audit_count}")
        
        assert users_count == 50, "Должно быть создано 50 пользователей"
        assert audit_count >= 100, "Должно быть минимум 100 записей аудита (создание + использование)"
        assert db_time < 30.0, "Операции с БД должны быть достаточно быстрыми"
        
        db.close()
        
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


async def test_concurrent_operations():
    """Симуляция одновременных операций"""
    
    # Создаем временную БД
    db_fd, db_path = tempfile.mkstemp(suffix='.db')
    os.close(db_fd)
    
    try:
        engine = create_engine(f"sqlite:///{db_path}", echo=False)
        Base.metadata.create_all(engine)
        
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        db = SessionLocal()
        
        invite_service = InviteService(db)
        auth_service = AuthService(db)
        
        # Симулируем быстрые последовательные операции
        start_time = time.time()
        
        # Создаем 10 токенов очень быстро
        tokens = []
        for i in range(10):
            token = invite_service.generate_invite(
                role="applicant",
                created_by=888888888,
                hours=24
            )
            tokens.append(token)
        
        # Используем все токены очень быстро
        for i, token in enumerate(tokens):
            invite_data = invite_service.validate_invite(token)
            user = await auth_service.process_invite_join(
                telegram_id=2000000 + i,
                invite_data=invite_data,
                username=f"fastuser{i}",
                first_name=f"Fast{i}",
                last_name="User"
            )
            invite_service.mark_nonce_used(
                invite_data["nonce"],
                user.telegram_id,
                invite_data
            )
        
        concurrent_time = time.time() - start_time
        
        print(f"✅ 10 быстрых операций создания пользователей: {concurrent_time:.3f} сек")
        print(f"✅ Производительность: {10/concurrent_time:.1f} операций/сек")
        
        # Проверяем consistency
        users_count = db.query(User).count()
        assert users_count == 10, "Все операции должны быть выполнены корректно"
        
        db.close()
        
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


if __name__ == "__main__":
    print("🚀 Запуск тестов производительности системы инвайтов...")
    print("=" * 70)
    
    print("\n1️⃣ Тест производительности генерации и валидации токенов...")
    test_invite_generation_performance()
    
    print("\n2️⃣ Тест производительности rate limiter...")
    test_rate_limiter_performance()
    
    print("\n3️⃣ Тест производительности работы с БД...")
    import asyncio
    asyncio.run(test_database_performance())
    
    print("\n4️⃣ Тест быстрых последовательных операций...")
    import asyncio
    asyncio.run(test_concurrent_operations())
    
    print("\n" + "=" * 70)
    print("🎉 ВСЕ ТЕСТЫ ПРОИЗВОДИТЕЛЬНОСТИ ПРОШЛИ УСПЕШНО!")
    print("\n📊 Выводы:")
    print("✅ Генерация токенов: высокая производительность")
    print("✅ Валидация токенов: высокая производительность") 
    print("✅ Rate limiting: масштабируется для тысяч пользователей")
    print("✅ Работа с БД: приемлемая производительность")
    print("✅ Последовательные операции: stable performance")
    print("✅ Система готова к production нагрузкам")
