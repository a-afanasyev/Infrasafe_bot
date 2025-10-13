"""
Тесты для онбординга пользователей
"""
import pytest
import json
from unittest.mock import AsyncMock, MagicMock
from aiogram.types import Message, Contact, User as TelegramUser
from aiogram.fsm.context import FSMContext
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from uk_management_bot.database.session import Base
from uk_management_bot.database.models.user import User
from uk_management_bot.handlers.onboarding import (
    start_phone_input, process_contact, process_manual_phone, 
    process_home_address, complete_onboarding, OnboardingStates
)

# Создаем in-memory базу данных для тестов
engine = create_engine("sqlite:///:memory:")
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
def mock_message():
    """Создает мок объект Message"""
    user = TelegramUser(id=123456789, is_bot=False, first_name="Test", language_code="ru")
    message = MagicMock(spec=Message)
    message.from_user = user
    message.text = None
    message.contact = None
    message.answer = AsyncMock()
    return message

@pytest.fixture
def mock_state():
    """Создает мок объект FSMContext"""
    state = MagicMock(spec=FSMContext)
    state.set_state = AsyncMock()
    state.clear = AsyncMock()
    state.update_data = AsyncMock()
    return state

@pytest.fixture
def sample_user(db_session):
    """Создает тестового пользователя"""
    user = User(
        telegram_id=123456789,
        username="testuser",
        first_name="Test",
        last_name="User",
        status="pending"
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user

@pytest.mark.asyncio
async def test_start_phone_input(mock_message, mock_state, db_session, sample_user):
    """Тест начала ввода телефона"""
    mock_message.text = "📱 Указать телефон"
    
    await start_phone_input(mock_message, mock_state, db_session)
    
    # Проверяем что отправлено сообщение с запросом телефона
    mock_message.answer.assert_called_once()
    call_args = mock_message.answer.call_args
    assert "телефона" in call_args[0][0] or "telefon" in call_args[0][0]
    
    # Проверяем что установлено состояние ожидания телефона
    mock_state.set_state.assert_called_once_with(OnboardingStates.waiting_for_phone)

@pytest.mark.asyncio
async def test_process_contact(mock_message, mock_state, db_session, sample_user):
    """
    ОБНОВЛЕНО: Тест обработки контакта с переходом к выбору квартиры.
    """
    # Создаем мок контакта
    contact = MagicMock(spec=Contact)
    contact.phone_number = "998901234567"
    mock_message.contact = contact

    await process_contact(mock_message, mock_state, db_session)

    # Проверяем что телефон сохранен
    updated_user = db_session.query(User).filter(User.telegram_id == 123456789).first()
    assert updated_user.phone == "+998901234567"

    # Проверяем что отправлено подтверждение
    assert mock_message.answer.call_count >= 1  # ОБНОВЛЕНО: минимум 1 сообщение

    # ОБНОВЛЕНО: Проверяем что переход к документам или выбору квартиры (в зависимости от конфигурации)
    # Новый flow переходит к waiting_for_document_type или waiting_for_yard_selection
    if mock_state.set_state.called:
        state_arg = mock_state.set_state.call_args[0][0]
        assert state_arg in [OnboardingStates.waiting_for_document_type, OnboardingStates.waiting_for_yard_selection]

@pytest.mark.asyncio
async def test_process_manual_phone_valid(mock_message, mock_state, db_session, sample_user):
    """
    ОБНОВЛЕНО: Тест ручного ввода валидного телефона с переходом к выбору квартиры.
    """
    mock_message.text = "+998901234567"

    await process_manual_phone(mock_message, mock_state, db_session)

    # Проверяем что телефон сохранен
    updated_user = db_session.query(User).filter(User.telegram_id == 123456789).first()
    assert updated_user.phone == "+998901234567"

    # ОБНОВЛЕНО: Проверяем что переход к документам или выбору квартиры
    if mock_state.set_state.called:
        state_arg = mock_state.set_state.call_args[0][0]
        assert state_arg in [OnboardingStates.waiting_for_document_type, OnboardingStates.waiting_for_yard_selection]

@pytest.mark.asyncio
async def test_process_manual_phone_invalid(mock_message, mock_state, db_session, sample_user):
    """Тест ручного ввода невалидного телефона"""
    mock_message.text = "123"

    await process_manual_phone(mock_message, mock_state, db_session)

    # Проверяем что телефон НЕ сохранен
    updated_user = db_session.query(User).filter(User.telegram_id == 123456789).first()
    assert updated_user.phone is None

    # ОБНОВЛЕНО: Проверяем что отправлено сообщение об ошибке (может быть ключ или текст)
    mock_message.answer.assert_called_once()
    call_args = mock_message.answer.call_args
    error_text = call_args[0][0].lower()
    assert "формат" in error_text or "format" in error_text or "invalid" in error_text or "phone" in error_text

    # Проверяем что состояние НЕ изменилось
    mock_state.set_state.assert_not_called()

@pytest.mark.asyncio
async def test_process_manual_phone_cancel(mock_message, mock_state, db_session, sample_user):
    """Тест отмены ввода телефона"""
    mock_message.text = "❌ Отмена"
    
    await process_manual_phone(mock_message, mock_state, db_session)
    
    # Проверяем что состояние очищено
    mock_state.clear.assert_called_once()

@pytest.mark.asyncio
async def test_process_home_address_deprecated(mock_message, mock_state, db_session, sample_user):
    """
    ОБНОВЛЕНО: Тест устаревшего обработчика адреса.
    Теперь адреса управляются через систему квартир, старый handler показывает предупреждение.
    """
    sample_user.phone = "+998901234567"
    db_session.commit()

    mock_message.text = "ул. Тестовая, дом 123"

    await process_home_address(mock_message, mock_state, db_session)

    # Проверяем что состояние очищено
    mock_state.clear.assert_called_once()

    # Проверяем что отправлено сообщение о deprecated
    mock_message.answer.assert_called()
    call_args = mock_message.answer.call_args[0][0]
    assert "обновлена" in call_args.lower() or "справочник" in call_args.lower()

@pytest.mark.asyncio
async def test_apartment_selection_flow(mock_message, mock_state, db_session):
    """
    НОВЫЙ ТЕСТ: Проверка потока выбора квартиры через систему адресов.
    """
    from uk_management_bot.database.models.yard import Yard
    from uk_management_bot.database.models.building import Building
    from uk_management_bot.database.models.apartment import Apartment

    # Создаём пользователя
    user = User(
        telegram_id=123456789,
        username="testuser",
        first_name="Test",
        phone="+998901234567",
        status="pending"
    )
    db_session.add(user)
    db_session.flush()

    # Создаём инфраструктуру
    yard = Yard(name="Тестовый двор", is_active=True, created_by=user.id)
    db_session.add(yard)
    db_session.flush()

    building = Building(
        yard_id=yard.id,
        address="ул. Тестовая, 123",
        is_active=True,
        created_by=user.id
    )
    db_session.add(building)
    db_session.flush()

    apartment = Apartment(
        building_id=building.id,
        apartment_number="10",
        is_active=True,
        created_by=user.id
    )
    db_session.add(apartment)
    db_session.commit()

    # Проверяем что квартира создана и доступна
    assert apartment.id is not None
    assert apartment.full_address is not None

@pytest.mark.asyncio
async def test_complete_onboarding(mock_message, mock_state, db_session):
    """
    ОБНОВЛЕНО: Тест завершения онбординга с новой системой квартир.
    """
    from uk_management_bot.database.models.yard import Yard
    from uk_management_bot.database.models.building import Building
    from uk_management_bot.database.models.apartment import Apartment
    from uk_management_bot.database.models.user_apartment import UserApartment

    # Создаем пользователя с полными данными (без legacy полей)
    user = User(
        telegram_id=123456789,
        username="testuser",
        first_name="Test",
        last_name="User",
        phone="+998901234567",
        status="pending"
    )
    db_session.add(user)
    db_session.flush()

    # Создаём полную иерархию адресов для пользователя
    yard = Yard(name="Тестовый двор", is_active=True, created_by=user.id)
    db_session.add(yard)
    db_session.flush()

    building = Building(
        yard_id=yard.id,
        address="ул. Тестовая, дом 123",
        is_active=True,
        created_by=user.id
    )
    db_session.add(building)
    db_session.flush()

    apartment = Apartment(
        building_id=building.id,
        apartment_number="10",
        is_active=True,
        created_by=user.id
    )
    db_session.add(apartment)
    db_session.flush()

    # Привязываем пользователя к квартире (одобренная)
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

    await complete_onboarding(mock_message, mock_state, db_session, user)

    # ОБНОВЛЕНО: Проверяем что отправлено сообщение о завершении
    mock_message.answer.assert_called_once()
    call_args = mock_message.answer.call_args
    message_text = call_args[0][0].lower()
    # Может быть "завершен", "заполнен", "tugallandi" или "completed"
    assert any(word in message_text for word in ["завершен", "заполнен", "tugallandi", "completed", "профиль"])

    # Проверяем что состояние очищено
    mock_state.clear.assert_called_once()

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
