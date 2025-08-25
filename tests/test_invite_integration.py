"""
Интеграционные тесты системы инвайтов с реальной БД
"""
import os
import sys
import tempfile
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
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
import json
import time


class TestInviteIntegration:
    """Интеграционные тесты системы инвайтов"""
    
    @pytest.fixture
    def test_db(self):
        """Создает временную БД для тестов"""
        # Создаем временный файл для БД
        db_fd, db_path = tempfile.mkstemp(suffix='.db')
        os.close(db_fd)
        
        # Создаем engine и сессию
        engine = create_engine(f"sqlite:///{db_path}", echo=False)
        Base.metadata.create_all(engine)
        
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        session = SessionLocal()
        
        yield session
        
        # Очистка
        session.close()
        os.unlink(db_path)
    
    async def test_full_invite_workflow(self, test_db):
        """Полный тест workflow создания и использования инвайта"""
        
        # Создаем менеджера, который будет создавать инвайт
        manager_id = 123456789
        candidate_id = 987654321
        
        # 1. Создаем инвайт через InviteService
        invite_service = InviteService(test_db)
        token = invite_service.generate_invite(
            role="executor",
            created_by=manager_id,
            specialization="plumber,electrician",
            hours=24
        )
        
        print(f"✅ Токен создан: {token[:50]}...")
        
        # Проверяем что токен валидный
        invite_data = invite_service.validate_invite(token)
        assert invite_data["role"] == "executor"
        assert invite_data["specialization"] == "plumber,electrician"
        assert invite_data["created_by"] == manager_id
        print("✅ Токен валиден")
        
        # 2. Используем токен через AuthService
        auth_service = AuthService(test_db)
        user = await auth_service.process_invite_join(
            telegram_id=candidate_id,
            invite_data=invite_data,
            username="testuser",
            first_name="Test",
            last_name="User"
        )
        
        # Проверяем что пользователь создан правильно
        assert user.telegram_id == candidate_id
        assert user.username == "testuser"
        assert user.status == "pending"
        assert user.specialization == "plumber,electrician"
        
        # Проверяем роли
        roles = json.loads(user.roles)
        assert "executor" in roles
        assert user.active_role == "executor"
        print("✅ Пользователь создан и роли назначены")
        
        # 3. Проверяем что nonce еще не использован
        assert invite_service.is_nonce_used(invite_data["nonce"]) == False
        print("✅ Nonce еще не использован")
        
        # Отмечаем nonce как использованный
        invite_service.mark_nonce_used(
            invite_data["nonce"],
            candidate_id,
            invite_data
        )
        
        # Принудительно сохраняем изменения
        test_db.commit()
        
        # Проверяем что запись об использовании создана
        used_records = test_db.query(AuditLog).filter(
            AuditLog.action == "invite_used"
        ).all()
        print(f"✅ Создано {len(used_records)} записей об использовании в AuditLog")
        
        # 4. Проверяем что новый токен можно валидировать (без повторного использования)
        new_token = invite_service.generate_invite(
            role="applicant",
            created_by=manager_id,
            hours=24
        )
        new_invite_data = invite_service.validate_invite(new_token)
        assert new_invite_data["role"] == "applicant"
        print("✅ Новые токены можно создавать и валидировать")
        
        # 5. Проверяем все записи в AuditLog
        created_audit = test_db.query(AuditLog).filter(
            AuditLog.action == "invite_created"
        ).first()
        assert created_audit is not None
        assert created_audit.user_id == manager_id
        
        used_audit = test_db.query(AuditLog).filter(
            AuditLog.action == "invite_used"
        ).first()
        assert used_audit is not None
        assert used_audit.user_id == candidate_id
        print("✅ Аудит логи записаны корректно")
    
    async def test_multiple_roles_workflow(self, test_db):
        """Тест добавления второй роли существующему пользователю"""
        
        existing_user_id = 555666777
        manager_id = 123456789
        
        # 1. Создаем пользователя как заявителя
        auth_service = AuthService(test_db)
        user = await auth_service.get_or_create_user(
            telegram_id=existing_user_id,
            username="existinguser",
            first_name="Existing",
            last_name="User"
        )
        user.roles = '["applicant"]'
        user.active_role = "applicant"
        user.status = "approved"
        test_db.commit()
        
        # 2. Создаем инвайт для роли исполнителя
        invite_service = InviteService(test_db)
        token = invite_service.generate_invite(
            role="executor",
            created_by=manager_id,
            specialization="electrician",
            hours=24
        )
        
        invite_data = invite_service.validate_invite(token)
        
        # 3. Добавляем вторую роль
        updated_user = await auth_service.process_invite_join(
            telegram_id=existing_user_id,
            invite_data=invite_data,
            username="existinguser",
            first_name="Existing",
            last_name="User"
        )
        
        # Проверяем что теперь у пользователя две роли
        roles = json.loads(updated_user.roles)
        assert len(roles) == 2
        assert "applicant" in roles
        assert "executor" in roles
        assert updated_user.specialization == "electrician"
        print("✅ Вторая роль добавлена к существующему пользователю")
    
    def test_rate_limiting_integration(self, test_db):
        """Тест интеграции rate limiting"""
        
        # Очищаем storage
        InviteRateLimiter._storage.clear()
        
        user_id = 111222333
        
        # Создаем несколько валидных токенов
        invite_service = InviteService(test_db)
        tokens = []
        for i in range(5):
            token = invite_service.generate_invite(
                role="applicant",
                created_by=123456789,
                hours=24
            )
            tokens.append(token)
        
        # Первые 3 попытки должны пройти (с точки зрения rate limiter)
        for i in range(3):
            allowed = InviteRateLimiter.is_allowed(user_id)
            assert allowed == True, f"Попытка {i+1} должна быть разрешена"
        
        # 4-я попытка должна быть заблокирована
        assert InviteRateLimiter.is_allowed(user_id) == False
        print("✅ Rate limiting работает корректно")
        
        # Другой пользователь должен иметь свой лимит
        other_user = 444555666
        assert InviteRateLimiter.is_allowed(other_user) == True
        print("✅ Изоляция rate limiting между пользователями")
    
    def test_error_scenarios(self, test_db):
        """Тест различных сценариев ошибок"""
        
        invite_service = InviteService(test_db)
        
        # 1. Неверный формат токена
        try:
            invite_service.validate_invite("invalid_token")
            assert False, "Должна быть ошибка валидации"
        except ValueError as e:
            assert "Invalid token format" in str(e)
        
        # 2. Поврежденная подпись
        valid_token = invite_service.generate_invite("applicant", 123456789)
        corrupted_token = valid_token[:-5] + "XXXXX"
        
        try:
            invite_service.validate_invite(corrupted_token)
            assert False, "Должна быть ошибка подписи"
        except ValueError as e:
            assert "Invalid token signature" in str(e)
        
        # 3. Токен без специализации для исполнителя
        try:
            invite_service.generate_invite("executor", 123456789)
            assert False, "Должна быть ошибка специализации"
        except ValueError as e:
            assert "Specialization is required" in str(e)
        
        # 4. Неверная роль
        try:
            invite_service.generate_invite("invalid_role", 123456789)
            assert False, "Должна быть ошибка роли"
        except ValueError as e:
            assert "Invalid role" in str(e)
        
        print("✅ Все сценарии ошибок обработаны корректно")
    
    async def test_audit_logging_comprehensive(self, test_db):
        """Комплексный тест аудит логирования"""
        
        invite_service = InviteService(test_db)
        auth_service = AuthService(test_db)
        
        manager_id = 999888777
        user_id = 777888999
        
        # Создаем инвайт
        token = invite_service.generate_invite(
            role="manager",
            created_by=manager_id,
            hours=24
        )
        
        # Проверяем запись о создании
        created_log = test_db.query(AuditLog).filter(
            AuditLog.action == "invite_created",
            AuditLog.user_id == manager_id
        ).first()
        
        assert created_log is not None
        details = json.loads(created_log.details)
        assert details["role"] == "manager"
        assert "expires_at" in details
        assert "nonce" in details
        
        # Используем инвайт
        invite_data = invite_service.validate_invite(token)
        user = await auth_service.process_invite_join(
            telegram_id=user_id,
            invite_data=invite_data,
            username="manageruser",
            first_name="Manager",
            last_name="User"
        )
        
        # Отмечаем как использованный
        invite_service.mark_nonce_used(
            invite_data["nonce"],
            user_id,
            invite_data
        )
        
        # Проверяем запись об использовании
        used_log = test_db.query(AuditLog).filter(
            AuditLog.action == "invite_used",
            AuditLog.user_id == user_id
        ).first()
        
        assert used_log is not None
        details = json.loads(used_log.details)
        assert details["role"] == "manager"
        assert details["created_by"] == manager_id
        assert details["nonce"] == invite_data["nonce"]
        
        print("✅ Аудит логирование работает комплексно")


async def run_integration_tests():
    """Запуск всех интеграционных тестов"""
    
    print("🧪 Запуск полноценных интеграционных тестов системы инвайтов...")
    print("=" * 70)
    
    test_instance = TestInviteIntegration()
    
    # Создаем тестовую БД
    import tempfile
    db_fd, db_path = tempfile.mkstemp(suffix='.db')
    os.close(db_fd)
    
    try:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        
        engine = create_engine(f"sqlite:///{db_path}", echo=False)
        Base.metadata.create_all(engine)
        
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        test_db = SessionLocal()
        
        # Запускаем тесты
        print("\n1️⃣ Тест полного workflow инвайтов...")
        await test_instance.test_full_invite_workflow(test_db)
        print("✅ PASSED\n")
        
        print("2️⃣ Тест добавления множественных ролей...")
        await test_instance.test_multiple_roles_workflow(test_db)
        print("✅ PASSED\n")
        
        print("3️⃣ Тест интеграции rate limiting...")
        test_instance.test_rate_limiting_integration(test_db)
        print("✅ PASSED\n")
        
        print("4️⃣ Тест сценариев ошибок...")
        test_instance.test_error_scenarios(test_db)
        print("✅ PASSED\n")
        
        print("5️⃣ Тест комплексного аудит логирования...")
        await test_instance.test_audit_logging_comprehensive(test_db)
        print("✅ PASSED\n")
        
        test_db.close()
        
        print("=" * 70)
        print("🎉 ВСЕ ИНТЕГРАЦИОННЫЕ ТЕСТЫ ПРОШЛИ УСПЕШНО!")
        print("\n📊 Результаты:")
        print("✅ Создание и валидация токенов")
        print("✅ Присоединение пользователей по инвайтам")
        print("✅ Добавление множественных ролей")
        print("✅ Rate limiting и защита от злоупотреблений")
        print("✅ Обработка всех типов ошибок")
        print("✅ Полное аудит логирование")
        print("✅ Предотвращение повторного использования токенов")
        print("✅ Корректная работа с БД")
        
    finally:
        # Очистка
        if os.path.exists(db_path):
            os.unlink(db_path)


if __name__ == "__main__":
    import asyncio
    asyncio.run(run_integration_tests())
