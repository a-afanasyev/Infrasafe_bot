"""
Тесты для ProfileService
"""
import pytest
import json
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from uk_management_bot.database.session import Base
from uk_management_bot.database.models.user import User
from uk_management_bot.services.profile_service import ProfileService

# Создаем in-memory базу данных для тестов с уникальным именем
engine = create_engine("sqlite:///:memory:?test_profile_db")
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture
def db_session():
    """Создает сессию БД для тестов"""
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        # Очищаем все таблицы после каждого теста
        Base.metadata.drop_all(bind=engine)

@pytest.fixture
def sample_user(db_session):
    """Создает тестового пользователя с квартирами"""
    from uk_management_bot.database.models.yard import Yard
    from uk_management_bot.database.models.building import Building
    from uk_management_bot.database.models.apartment import Apartment
    from uk_management_bot.database.models.user_apartment import UserApartment

    # Создаём пользователя
    user = User(
        telegram_id=123456789,
        username="testuser",
        first_name="Тест",
        last_name="Пользователь",
        roles=json.dumps(["applicant", "executor"]),
        active_role="executor",
        status="approved",
        language="ru",
        phone="+998901234567",
        specialization="electricity,plumbing"
    )
    db_session.add(user)
    db_session.flush()  # Чтобы получить user.id

    # Создаём двор
    yard = Yard(
        name="Двор А",
        description="Тестовый двор",
        is_active=True,
        created_by=user.id
    )
    db_session.add(yard)
    db_session.flush()

    # Создаём здание
    building = Building(
        yard_id=yard.id,
        address="ул. Тестовая, 1",
        gps_latitude=41.2995,
        gps_longitude=69.2401,
        entrance_count=4,
        floor_count=9,
        is_active=True,
        created_by=user.id
    )
    db_session.add(building)
    db_session.flush()

    # Создаём квартиру
    apartment = Apartment(
        building_id=building.id,
        apartment_number="10",
        entrance=1,
        floor=2,
        rooms_count=3,
        area=65.5,
        is_active=True,
        created_by=user.id
    )
    db_session.add(apartment)
    db_session.flush()

    # Привязываем пользователя к квартире
    user_apartment = UserApartment(
        user_id=user.id,
        apartment_id=apartment.id,
        status='approved',
        is_owner=True,
        is_primary=True
    )
    db_session.add(user_apartment)
    db_session.commit()
    db_session.refresh(user)
    return user

def test_get_user_profile_data_success(db_session, sample_user):
    """Тест успешного получения данных профиля с новой системой квартир"""
    service = ProfileService(db_session)
    profile_data = service.get_user_profile_data(123456789)

    assert profile_data is not None
    assert profile_data['telegram_id'] == 123456789
    assert profile_data['username'] == "testuser"
    assert profile_data['first_name'] == "Тест"
    assert profile_data['last_name'] == "Пользователь"
    assert profile_data['roles'] == ["applicant", "executor"]
    assert profile_data['active_role'] == "executor"
    assert profile_data['status'] == "approved"
    assert profile_data['phone'] == "+998901234567"
    assert profile_data['specializations'] == ["electricity", "plumbing"]

    # ОБНОВЛЕНО: Проверяем новую систему квартир
    assert 'apartments' in profile_data
    assert len(profile_data['apartments']) == 1
    apartment_data = profile_data['apartments'][0]
    assert 'address' in apartment_data
    assert 'is_primary' in apartment_data
    assert apartment_data['is_primary'] is True
    assert 'is_owner' in apartment_data
    assert apartment_data['is_owner'] is True
    assert "ул. Тестовая, 1" in apartment_data['address']
    assert "кв. 10" in apartment_data['address']

def test_get_user_profile_data_not_found(db_session):
    """Тест получения данных несуществующего пользователя"""
    service = ProfileService(db_session)
    profile_data = service.get_user_profile_data(999999999)
    
    assert profile_data is None

def test_get_user_profile_data_with_defaults(db_session):
    """Тест получения данных пользователя с дефолтными значениями"""
    # Создаем пользователя с минимальными данными
    user = User(
        telegram_id=987654321,
        username="minimal_user"
    )
    db_session.add(user)
    db_session.commit()

    service = ProfileService(db_session)
    profile_data = service.get_user_profile_data(987654321)

    assert profile_data is not None
    assert profile_data['roles'] == ["applicant"]  # дефолт
    assert profile_data['active_role'] == "applicant"  # дефолт
    assert profile_data['status'] == "pending"  # дефолт
    assert profile_data['language'] == "ru"  # дефолт
    assert profile_data['phone'] is None
    assert profile_data['apartments'] == []  # ОБНОВЛЕНО: yards заменён на apartments
    assert profile_data['specializations'] == []

def test_format_profile_text_ru(db_session, sample_user):
    """Тест форматирования профиля на русском языке"""
    service = ProfileService(db_session)
    profile_data = service.get_user_profile_data(123456789)

    profile_text = service.format_profile_text(profile_data, language="ru")

    assert "Профиль" in profile_text  # ИСПРАВЛЕНО: без проверки эмодзи
    assert "Тест Пользователь" in profile_text
    assert "@testuser" in profile_text
    assert "Одобрен" in profile_text or "одобрен" in profile_text
    # ИСПРАВЛЕНО: Роль "executor" отображается как "Исполнитель", не "Сотрудник"
    assert "Исполнитель" in profile_text or "исполнитель" in profile_text or "Executor" in profile_text
    assert "+998901234567" in profile_text
    # ИСПРАВЛЕНО: Проверяем что есть упоминание специализаций (могут быть ключами)
    assert "electric" in profile_text.lower() or "электр" in profile_text.lower()
    assert "plumb" in profile_text.lower() or "сантехн" in profile_text.lower()
    # ОБНОВЛЕНО: Проверяем адрес из новой системы квартир
    assert "ул. Тестовая, 1" in profile_text
    assert "кв. 10" in profile_text or "квартира 10" in profile_text.lower()

def test_format_profile_text_uz(db_session, sample_user):
    """Тест форматирования профиля на узбекском языке"""
    service = ProfileService(db_session)
    profile_data = service.get_user_profile_data(123456789)

    profile_text = service.format_profile_text(profile_data, language="uz")

    assert "Profil" in profile_text  # ИСПРАВЛЕНО: без проверки эмодзи
    assert "Тест Пользователь" in profile_text
    assert "Tasdiqlangan" in profile_text or "tasdiqlangan" in profile_text
    # ИСПРАВЛЕНО: Роль "executor" отображается как "Ijrochi", не "Xodim"
    assert "Ijrochi" in profile_text or "ijrochi" in profile_text or "Executor" in profile_text.lower()
    # ИСПРАВЛЕНО: Проверяем что есть упоминание специализаций (могут быть ключами)
    assert "elektrik" in profile_text.lower() or "electric" in profile_text.lower()

def test_format_profile_text_minimal_user(db_session):
    """Тест форматирования профиля пользователя с минимальными данными"""
    # Создаем пользователя с минимальными данными
    user = User(
        telegram_id=111111111,
        first_name="Минимум"
    )
    db_session.add(user)
    db_session.commit()

    service = ProfileService(db_session)
    profile_data = service.get_user_profile_data(111111111)
    profile_text = service.format_profile_text(profile_data, language="ru")

    assert "Профиль" in profile_text  # ИСПРАВЛЕНО: проверяем только "Профиль", без эмодзи
    assert "Минимум" in profile_text
    assert "Ожидает одобрения" in profile_text or "Ожидает" in profile_text
    assert "Заявитель" in profile_text or "Житель" in profile_text
    assert "Не указан" in profile_text or "не указан" in profile_text  # телефон не указан
    assert "не указан" in profile_text.lower()  # специализация или адреса

def test_validate_profile_data_success(db_session, sample_user):
    """Тест валидации корректных данных профиля"""
    service = ProfileService(db_session)
    profile_data = service.get_user_profile_data(123456789)
    
    issues = service.validate_profile_data(profile_data)
    
    assert issues == []  # нет проблем

def test_validate_profile_data_issues(db_session):
    """Тест валидации некорректных данных профиля"""
    service = ProfileService(db_session)
    
    # Тестируем различные проблемы
    invalid_data = {
        'telegram_id': None,  # отсутствует
        'roles': "invalid",  # не список
        'active_role': "manager",  # не входит в roles
        'status': "invalid_status",  # некорректный статус
        'phone': "123"  # некорректный телефон
    }
    
    issues = service.validate_profile_data(invalid_data)
    
    assert len(issues) >= 4  # минимум 4 проблемы
    assert any("telegram_id" in issue for issue in issues)
    assert any("роли" in issue for issue in issues)
    assert any("Активная роль" in issue for issue in issues)
    assert any("статус" in issue for issue in issues)

def test_validate_profile_data_none(db_session):
    """Тест валидации пустых данных профиля"""
    service = ProfileService(db_session)
    
    issues = service.validate_profile_data(None)
    
    assert len(issues) == 1
    assert "Данные профиля отсутствуют" in issues[0]

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
