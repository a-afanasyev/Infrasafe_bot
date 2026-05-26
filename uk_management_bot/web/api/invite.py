"""
API эндпоинты для работы с приглашениями
"""
from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
from uk_management_bot.web.limiter import web_limiter
from typing import Optional
import os
import sys

# Добавляем путь к основному приложению
sys.path.append(os.path.join(os.path.dirname(__file__), '../..'))

from uk_management_bot.database.session import get_db
from uk_management_bot.services.invite_service import InviteService, TokenAlreadyUsedError
from uk_management_bot.services.auth_service import AuthService
from uk_management_bot.database.models.user import User
from sqlalchemy.orm import Session

router = APIRouter()

class RegistrationData(BaseModel):
    """Данные для регистрации"""
    token: str
    full_name: str
    specialization: str
    telegram_id: Optional[int] = None

class TokenValidationResponse(BaseModel):
    """Ответ на валидацию токена"""
    valid: bool
    role: Optional[str] = None
    specialization: Optional[str] = None
    expires_at: Optional[str] = None
    message: Optional[str] = None

@router.get("/validate/{token}", response_model=TokenValidationResponse)
@web_limiter.limit("20/minute")
async def validate_invite_token(request: Request, token: str, db: Session = Depends(get_db)):
    """SEC-020: GET валидирует структуру/подпись/expiry токена, НЕ
    consum'ит nonce (форма регистрации может фетчить validate несколько
    раз — preview, refresh, ре-валидация после ввода имени). Consume
    nonce происходит только в POST `/register` через атомарный INSERT
    в `invite_nonces`. Rate-limit 20/мин/IP закрывает enumeration."""
    try:
        invite_service = InviteService(db)

        # Проверяем токен
        validation_result = invite_service.validate_invite_token(token)
        
        if not validation_result.get("valid"):
            return TokenValidationResponse(
                valid=False,
                message=validation_result.get("message", "Неверный токен")
            )
        
        # Получаем данные приглашения
        invite_data = validation_result.get("invite_data", {})
        
        return TokenValidationResponse(
            valid=True,
            role=invite_data.get("role"),
            specialization=invite_data.get("specialization"),
            expires_at=invite_data.get("expires_at"),
            message="Токен действителен"
        )
        
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Token validation error: {e}")
        return TokenValidationResponse(
            valid=False,
            message="Ошибка валидации"
        )

@router.post("/register")
@web_limiter.limit("3/minute")
async def register_via_invite(request: Request, data: RegistrationData, db: Session = Depends(get_db)):
    """Регистрация по приглашению"""
    try:
        invite_service = InviteService(db)
        auth_service = AuthService(db)
        
        # telegram_id is required for registration
        if not data.telegram_id:
            raise HTTPException(status_code=400, detail="telegram_id is required for registration")

        # Проверяем, что пользователь не зарегистрирован уже
        existing_user = db.query(User).filter(User.telegram_id == data.telegram_id).first()

        if existing_user:
            # Security: blocked users CANNOT re-register
            if existing_user.status == "blocked":
                raise HTTPException(status_code=403, detail="Пользователь заблокирован")

            # If already approved, reject
            if existing_user.status == "approved":
                raise HTTPException(status_code=400, detail="Пользователь уже зарегистрирован и одобрен")

            # Validate and atomically consume nonce in one step (fixes TOCTOU).
            # `validate_invite` returns the payload on success and raises on
            # failure (TokenAlreadyUsedError for the race-loser, ValueError
            # for other validation problems).
            try:
                invite_data = invite_service.validate_invite(
                    data.token, mark_used_by=existing_user.telegram_id
                )
            except TokenAlreadyUsedError as e:
                # SEC-020 AC (b): second of two simultaneous POSTs → 409 Conflict.
                raise HTTPException(status_code=409, detail=str(e))
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))

            # Pending users can update their info (but NOT role from invite — keep existing)
            existing_user.first_name = data.full_name.split()[0] if data.full_name else ""
            existing_user.last_name = " ".join(data.full_name.split()[1:]) if len(data.full_name.split()) > 1 else ""
            existing_user.specialization = data.specialization if existing_user.role == "executor" else None

            db.commit()

            return {
                "success": True,
                "message": "Данные пользователя обновлены",
                "user_id": existing_user.id
            }

        # New user: validate + consume nonce atomically via join_via_invite
        # (join_via_invite internally calls validate_invite with mark_used_by)
        result = invite_service.join_via_invite(
            token=data.token,
            telegram_id=data.telegram_id,
            first_name=data.full_name.split()[0] if data.full_name else "",
            last_name=" ".join(data.full_name.split()[1:]) if len(data.full_name.split()) > 1 else "",
            specialization=data.specialization
        )

        if not result.get("success"):
            # SEC-020 AC (b): nonce already consumed → 409 Conflict.
            if result.get("reason") == "already_used":
                raise HTTPException(status_code=409, detail=result.get("message", "Token already used"))
            raise HTTPException(status_code=400, detail=result.get("message", "Ошибка регистрации"))
        
        return {
            "success": True,
            "message": "Регистрация успешно завершена",
            "user_id": result.get("user_id")
        }
        
    except HTTPException:
        raise
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Registration error: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")

@router.get("/specializations")
async def get_specializations():
    """Получение списка специализаций"""
    specializations = [
        {"id": "plumber", "name": "Сантехник"},
        {"id": "electrician", "name": "Электрик"},
        {"id": "hvac", "name": "Отопление/вентиляция"},
        {"id": "cleaning", "name": "Уборка"},
        {"id": "security", "name": "Охрана"},
        {"id": "maintenance", "name": "Обслуживание"},
        {"id": "landscaping", "name": "Благоустройство"},
        {"id": "repair", "name": "Ремонт"},
        {"id": "installation", "name": "Установка"},
        {"id": "general", "name": "Общие работы"}
    ]
    
    return {"specializations": specializations}
