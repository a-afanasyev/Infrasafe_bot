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
    """Тест обработки контакта"""
    # Создаем мок контакта
    contact = MagicMock(spec=Contact)
    contact.phone_number = "998901234567"
    mock_message.contact = contact
    
    await process_contact(mock_message, mock_state, db_session)
    
    # Проверяем что телефон сохранен
    updated_user = db_session.query(User).filter(User.telegram_id == 123456789).first()
    assert updated_user.phone == "+998901234567"
    
    # Проверяем что отправлено подтверждение
    assert mock_message.answer.call_count >= 2  # подтверждение + запрос адреса
    
    # Проверяем что установлено состояние ожидания адреса
    mock_state.set_state.assert_called_with(OnboardingStates.waiting_for_home_address)

@pytest.mark.asyncio
async def test_process_manual_phone_valid(mock_message, mock_state, db_session, sample_user):
    """Тест ручного ввода валидного телефона"""
    mock_message.text = "+998901234567"
    
    await process_manual_phone(mock_message, mock_state, db_session)
    
    # Проверяем что телефон сохранен
    updated_user = db_session.query(User).filter(User.telegram_id == 123456789).first()
    assert updated_user.phone == "+998901234567"
    
    # Проверяем что установлено состояние ожидания адреса
    mock_state.set_state.assert_called_with(OnboardingStates.waiting_for_home_address)

@pytest.mark.asyncio
async def test_process_manual_phone_invalid(mock_message, mock_state, db_session, sample_user):
    """Тест ручного ввода невалидного телефона"""
    mock_message.text = "123"
    
    await process_manual_phone(mock_message, mock_state, db_session)
    
    # Проверяем что телефон НЕ сохранен
    updated_user = db_session.query(User).filter(User.telegram_id == 123456789).first()
    assert updated_user.phone is None
    
    # Проверяем что отправлено сообщение об ошибке
    mock_message.answer.assert_called_once()
    call_args = mock_message.answer.call_args
    assert "формат" in call_args[0][0] or "format" in call_args[0][0]
    
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
async def test_process_home_address_valid(mock_message, mock_state, db_session, sample_user):
    """Тест ввода валидного адреса"""
    # Сначала добавим телефон пользователю
    sample_user.phone = "+998901234567"
    db_session.commit()
    
    mock_message.text = "ул. Тестовая, дом 123"
    
    await process_home_address(mock_message, mock_state, db_session)
    
    # Проверяем что адрес сохранен
    updated_user = db_session.query(User).filter(User.telegram_id == 123456789).first()
    assert updated_user.home_address == "ул. Тестовая, дом 123"
    
    # Проверяем что состояние очищено (онбординг завершен)
    mock_state.clear.assert_called_once()

@pytest.mark.asyncio
async def test_process_home_address_invalid(mock_message, mock_state, db_session, sample_user):
    """Тест ввода невалидного адреса"""
    mock_message.text = "12"  # слишком короткий
    
    await process_home_address(mock_message, mock_state, db_session)
    
    # Проверяем что адрес НЕ сохранен
    updated_user = db_session.query(User).filter(User.telegram_id == 123456789).first()
    assert updated_user.home_address is None
    
    # Проверяем что отправлено сообщение об ошибке
    mock_message.answer.assert_called_once()
    call_args = mock_message.answer.call_args
    assert "короткий" in call_args[0][0] or "qisqa" in call_args[0][0]

@pytest.mark.asyncio
async def test_complete_onboarding(mock_message, mock_state, db_session):
    """Тест завершения онбординга"""
    # Создаем пользователя с полными данными
    user = User(
        telegram_id=123456789,
        username="testuser",
        first_name="Test",
        last_name="User",
        phone="+998901234567",
        home_address="ул. Тестовая, дом 123",
        status="pending"
    )
    db_session.add(user)
    db_session.commit()
    
    await complete_onboarding(mock_message, mock_state, db_session, user)
    
    # Проверяем что отправлено сообщение о завершении
    mock_message.answer.assert_called_once()
    call_args = mock_message.answer.call_args
    assert "завершен" in call_args[0][0] or "tugallandi" in call_args[0][0]
    
    # Проверяем что состояние очищено
    mock_state.clear.assert_called_once()

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
