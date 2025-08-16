"""
Тесты для компонентов AUTH P3 (Wave 3) - Панель управления пользователями

Тестирует:
- UserManagementService
- SpecializationService
- Методы модерации в AuthService
- Клавиатуры и форматирование
"""

import asyncio
import pytest
import json
import os
import time
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Настройка путей и импортов
import sys
sys.path.append('uk_management_bot')

from uk_management_bot.database.session import Base
from uk_management_bot.services.user_management_service import UserManagementService
from uk_management_bot.services.specialization_service import SpecializationService
from uk_management_bot.services.auth_service import AuthService
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.audit import AuditLog
from uk_management_bot.keyboards.user_management import (
    get_user_management_main_keyboard,
    get_user_list_keyboard,
    get_user_actions_keyboard
)


@pytest.fixture
def test_db():
    """Создает изолированную in-memory базу данных для каждого теста."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(engine)


class TestUserManagementService:
    """Тесты для UserManagementService"""
    
    def test_user_stats(self, test_db):
        print("\n1️⃣ Тест статистики пользователей...")
        
        # Создаем тестовых пользователей
        users = [
            User(telegram_id=1001, first_name="John", status="pending", roles='["applicant"]'),
            User(telegram_id=1002, first_name="Jane", status="approved", roles='["executor"]'),
            User(telegram_id=1003, first_name="Bob", status="blocked", roles='["applicant"]'),
            User(telegram_id=1004, first_name="Alice", status="approved", roles='["manager"]'),
        ]
        
        for user in users:
            test_db.add(user)
        test_db.commit()
        
        service = UserManagementService(test_db)
        stats = service.get_user_stats()
        
        assert stats['pending'] == 1
        assert stats['approved'] == 2 
        assert stats['blocked'] == 1
        assert stats['total'] == 4
        assert stats['staff'] == 2  # executor + manager
        
        print("✅ Статистика пользователей работает корректно")
    
    def test_users_by_status(self, test_db):
        print("\n2️⃣ Тест получения пользователей по статусу...")
        
        # Создаем пользователей с разными статусами
        for i in range(15):
            status = "pending" if i < 7 else "approved" if i < 12 else "blocked"
            user = User(
                telegram_id=2000 + i,
                first_name=f"User{i}",
                status=status,
                roles='["applicant"]'
            )
            test_db.add(user)
        test_db.commit()
        
        service = UserManagementService(test_db)
        
        # Тест пагинации
        result = service.get_users_by_status("pending", page=1, limit=5)
        
        assert len(result['users']) == 5
        assert result['total'] == 7
        assert result['total_pages'] == 2
        assert result['has_next'] == True
        assert result['has_prev'] == False
        
        # Вторая страница
        result2 = service.get_users_by_status("pending", page=2, limit=5)
        assert len(result2['users']) == 2
        assert result2['has_next'] == False
        assert result2['has_prev'] == True
        
        print("✅ Пагинация по статусам работает корректно")
    
    def test_user_formatting(self, test_db):
        print("\n3️⃣ Тест форматирования информации о пользователе...")
        
        user = User(
            telegram_id=3001,
            first_name="Test",
            last_name="User",
            username="testuser",
            status="approved",
            roles='["executor", "applicant"]',
            active_role="executor",
            phone="+998901234567",
            specialization="plumber,electrician"
        )
        test_db.add(user)
        test_db.commit()
        
        service = UserManagementService(test_db)
        formatted = service.format_user_info(user, detailed=True)
        
        assert "Test User" in formatted
        assert "@testuser" in formatted
        assert "✅" in formatted  # approved status emoji
        assert "+998901234567" in formatted
        assert str(user.telegram_id) in formatted
        
        print("✅ Форматирование информации о пользователе работает корректно")


class TestSpecializationService:
    """Тесты для SpecializationService"""
    
    def test_available_specializations(self, test_db):
        print("\n4️⃣ Тест доступных специализаций...")
        
        service = SpecializationService(test_db)
        specializations = service.get_available_specializations()
        
        assert isinstance(specializations, list)
        assert len(specializations) > 0
        assert "plumber" in specializations
        assert "electrician" in specializations
        assert "hvac" in specializations
        
        print(f"✅ Найдено {len(specializations)} доступных специализаций")
    
    def test_user_specializations(self, test_db):
        print("\n5️⃣ Тест управления специализациями пользователя...")
        
        # Создаем исполнителя
        user = User(
            telegram_id=4001,
            first_name="Executor",
            roles='["executor"]',
            specialization="plumber,electrician"
        )
        test_db.add(user)
        test_db.commit()
        
        service = SpecializationService(test_db)
        
        # Получаем специализации
        specs = service.get_user_specializations(user.id)
        assert "plumber" in specs
        assert "electrician" in specs
        assert len(specs) == 2
        
        # Обновляем специализации
        success = service.set_user_specializations(
            user.id, 
            ["plumber", "hvac"], 
            updated_by=1, 
            comment="Тестовое обновление"
        )
        assert success == True
        
        # Проверяем обновление
        updated_specs = service.get_user_specializations(user.id)
        assert "plumber" in updated_specs
        assert "hvac" in updated_specs
        assert "electrician" not in updated_specs
        
        print("✅ Управление специализациями работает корректно")
    
    def test_specialization_stats(self, test_db):
        print("\n6️⃣ Тест статистики специализаций...")
        
        # Создаем исполнителей с разными специализациями
        users = [
            User(telegram_id=5001, roles='["executor"]', specialization="plumber,general"),
            User(telegram_id=5002, roles='["executor"]', specialization="electrician,plumber"),
            User(telegram_id=5003, roles='["executor"]', specialization="hvac"),
        ]
        
        for user in users:
            test_db.add(user)
        test_db.commit()
        
        service = SpecializationService(test_db)
        stats = service.get_specialization_stats()
        
        assert stats["plumber"] == 2
        assert stats["electrician"] == 1
        assert stats["hvac"] == 1
        assert stats["general"] == 1
        
        print("✅ Статистика специализаций работает корректно")


class TestAuthServiceModeration:
    """Тесты для методов модерации в AuthService"""
    
    async def test_user_moderation(self, test_db):
        print("\n7️⃣ Тест методов модерации пользователей...")
        
        # Создаем пользователя для модерации
        user = User(
            telegram_id=6001,
            first_name="TestUser",
            status="pending",
            roles='["applicant"]'
        )
        test_db.add(user)
        test_db.commit()
        
        service = AuthService(test_db)
        manager_id = 999  # ID менеджера
        
        # Тест одобрения
        success = service.approve_user(user.id, manager_id, "Тестовое одобрение")
        assert success == True
        
        test_db.refresh(user)
        assert user.status == "approved"
        
        # Проверяем аудит лог
        audit_logs = test_db.query(AuditLog).filter(AuditLog.action == "user_approved").all()
        assert len(audit_logs) == 1
        assert audit_logs[0].user_id == manager_id
        
        # Тест блокировки
        success = service.block_user(user.id, manager_id, "Тестовая блокировка")
        assert success == True
        
        test_db.refresh(user)
        assert user.status == "blocked"
        
        # Тест разблокировки
        success = service.unblock_user(user.id, manager_id, "Тестовая разблокировка")
        assert success == True
        
        test_db.refresh(user)
        assert user.status == "approved"
        
        print("✅ Методы модерации работают корректно")
    
    async def test_role_management(self, test_db):
        print("\n8️⃣ Тест управления ролями...")
        
        # Создаем пользователя
        user = User(
            telegram_id=7001,
            first_name="RoleTest",
            roles='["applicant"]',
            active_role="applicant"
        )
        test_db.add(user)
        test_db.commit()
        
        service = AuthService(test_db)
        manager_id = 999
        
        # Добавляем роль executor
        success = service.assign_role(user.id, "executor", manager_id, "Назначение роли")
        assert success == True
        
        # Проверяем роли
        roles = service.get_user_roles(user.id)
        assert "applicant" in roles
        assert "executor" in roles
        assert len(roles) == 2
        
        # Удаляем роль applicant
        success = service.remove_role(user.id, "applicant", manager_id, "Удаление роли")
        assert success == True
        
        roles = service.get_user_roles(user.id)
        assert "applicant" not in roles
        assert "executor" in roles
        assert len(roles) == 1
        
        print("✅ Управление ролями работает корректно")


class TestKeyboards:
    """Тесты для клавиатур"""
    
    def test_main_keyboard(self, test_db):
        print("\n9️⃣ Тест основной клавиатуры...")
        
        stats = {
            'pending': 5,
            'approved': 10,
            'blocked': 2,
            'staff': 8,
            'total': 17
        }
        
        keyboard = get_user_management_main_keyboard(stats, 'ru')
        
        assert keyboard is not None
        assert hasattr(keyboard, 'inline_keyboard')
        assert len(keyboard.inline_keyboard) > 0
        
        # Проверяем наличие кнопок с счетчиками
        buttons_text = []
        for row in keyboard.inline_keyboard:
            for button in row:
                buttons_text.append(button.text)
        
        # Должны быть кнопки с числами из статистики
        assert any("(5)" in text for text in buttons_text)  # pending
        assert any("(10)" in text for text in buttons_text)  # approved
        
        print("✅ Клавиатуры генерируются корректно")
    
    def test_user_actions_keyboard(self, test_db):
        print("\n🔟 Тест клавиатуры действий с пользователем...")
        
        # Тест для пользователя pending
        pending_user = User(
            telegram_id=8001,
            status="pending",
            roles='["applicant"]'
        )
        
        keyboard = get_user_actions_keyboard(pending_user, 'ru')
        
        buttons_text = []
        for row in keyboard.inline_keyboard:
            for button in row:
                buttons_text.append(button.text)
        
        # Для pending должны быть кнопки одобрения и блокировки
        assert any("Одобрить" in text for text in buttons_text)
        assert any("Заблокировать" in text for text in buttons_text)
        
        print("✅ Клавиатуры действий работают корректно")


class TestPerformance:
    """Тесты производительности"""
    
    def test_large_dataset_performance(self, test_db):
        print("\n1️⃣1️⃣ Тест производительности с большим dataset...")
        
        start_time = time.time()
        
        # Создаем 1000 пользователей
        users = []
        for i in range(1000):
            status = "pending" if i % 3 == 0 else "approved" if i % 3 == 1 else "blocked"
            role = "executor" if i % 2 == 0 else "applicant"
            
            user = User(
                telegram_id=9000 + i,
                first_name=f"User{i}",
                status=status,
                roles=f'["{role}"]',
                specialization="plumber,electrician" if role == "executor" else None
            )
            users.append(user)
        
        test_db.add_all(users)
        test_db.commit()
        
        creation_time = time.time() - start_time
        
        # Тестируем производительность запросов
        service = UserManagementService(test_db)
        
        # Статистика
        stats_start = time.time()
        stats = service.get_user_stats()
        stats_time = time.time() - stats_start
        
        # Пагинация
        pagination_start = time.time()
        result = service.get_users_by_status("pending", page=1, limit=50)
        pagination_time = time.time() - pagination_start
        
        # Поиск
        search_start = time.time()
        search_result = service.search_users("User1", page=1, limit=20)
        search_time = time.time() - search_start
        
        total_time = time.time() - start_time
        
        print(f"✅ Производительность (1000 пользователей):")
        print(f"   Создание: {creation_time:.3f} сек")
        print(f"   Статистика: {stats_time:.3f} сек")
        print(f"   Пагинация: {pagination_time:.3f} сек")
        print(f"   Поиск: {search_time:.3f} сек")
        print(f"   Общее время: {total_time:.3f} сек")
        
        # Проверяем что все операции выполняются быстро
        assert stats_time < 1.0  # Статистика должна быть быстрой
        assert pagination_time < 0.5  # Пагинация должна быть быстрой
        assert search_time < 1.0  # Поиск должен быть быстрым
        
        # Проверяем корректность результатов
        assert stats['total'] == 1000
        assert len(result['users']) <= 50
        assert search_result['total'] > 0  # Должны найтись пользователи с "User1"


async def run_async_tests():
    """Запускает асинхронные тесты"""
    
    # Создаем тестовую базу данных
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    test_db = TestingSessionLocal()
    
    try:
        test_auth = TestAuthServiceModeration()
        await test_auth.test_user_moderation(test_db)
        await test_auth.test_role_management(test_db)
        
    finally:
        test_db.close()
        Base.metadata.drop_all(engine)


def main():
    """Основная функция запуска тестов"""
    print("🧪 ТЕСТИРОВАНИЕ AUTH P3 (Wave 3) - ПАНЕЛЬ УПРАВЛЕНИЯ ПОЛЬЗОВАТЕЛЯМИ")
    print("=" * 80)
    
    # Создаем тестовую базу данных
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    test_db = TestingSessionLocal()
    
    try:
        # Запускаем синхронные тесты
        print("\n📋 ТЕСТИРОВАНИЕ СЕРВИСОВ:")
        
        test_user_mgmt = TestUserManagementService()
        test_user_mgmt.test_user_stats(test_db)
        test_user_mgmt.test_users_by_status(test_db)
        test_user_mgmt.test_user_formatting(test_db)
        
        test_spec = TestSpecializationService()
        test_spec.test_available_specializations(test_db)
        test_spec.test_user_specializations(test_db)
        test_spec.test_specialization_stats(test_db)
        
        print("\n🎯 ТЕСТИРОВАНИЕ КЛАВИАТУР:")
        
        test_keyboards = TestKeyboards()
        test_keyboards.test_main_keyboard(test_db)
        test_keyboards.test_user_actions_keyboard(test_db)
        
        print("\n⚡ ТЕСТИРОВАНИЕ ПРОИЗВОДИТЕЛЬНОСТИ:")
        
        test_perf = TestPerformance()
        test_perf.test_large_dataset_performance(test_db)
        
        print("\n🔄 ЗАПУСК АСИНХРОННЫХ ТЕСТОВ:")
        
        # Запускаем асинхронные тесты
        asyncio.run(run_async_tests())
        
        print("\n" + "=" * 80)
        print("🎉 ВСЕ ТЕСТЫ AUTH P3 УСПЕШНО ПРОЙДЕНЫ!")
        print("✅ UserManagementService: Работает корректно")
        print("✅ SpecializationService: Работает корректно") 
        print("✅ AuthService (модерация): Работает корректно")
        print("✅ Клавиатуры: Генерируются корректно")
        print("✅ Производительность: Соответствует требованиям")
        print("✅ Аудит логирование: Работает корректно")
        print("\n🚀 ПАНЕЛЬ УПРАВЛЕНИЯ ПОЛЬЗОВАТЕЛЯМИ ГОТОВА К PRODUCTION!")
        
    except Exception as e:
        print(f"\n❌ ОШИБКА В ТЕСТАХ: {e}")
        import traceback
        traceback.print_exc()
        return False
        
    finally:
        test_db.close()
        Base.metadata.drop_all(engine)
    
    return True


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
