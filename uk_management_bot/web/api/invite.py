"""
API эндпоинты для работы с приглашениями
"""
from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
from typing import Optional
import os
import sys

# Добавляем путь к основному приложению
sys.path.append(os.path.join(os.path.dirname(__file__), '../..'))

from uk_management_bot.database.session import get_db
from uk_management_bot.services.invite_service import InviteService
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
async def validate_invite_token(token: str, db: Session = Depends(get_db)):
    """Валидация токена приглашения"""
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
        return TokenValidationResponse(
            valid=False,
            message=f"Ошибка валидации: {str(e)}"
        )

@router.post("/register")
async def register_via_invite(data: RegistrationData, db: Session = Depends(get_db)):
    """Регистрация по приглашению"""
    try:
        invite_service = InviteService(db)
        auth_service = AuthService(db)
        
        # Валидируем токен
        validation_result = invite_service.validate_invite_token(data.token)
        
        if not validation_result.get("valid"):
            raise HTTPException(status_code=400, detail=validation_result.get("message", "Неверный токен"))
        
        invite_data = validation_result.get("invite_data", {})
        
        # Проверяем, что пользователь не зарегистрирован уже
        if data.telegram_id:
            existing_user = db.query(User).filter(User.telegram_id == data.telegram_id).first()
            if existing_user:
                # Если пользователь уже одобрен, запрещаем повторную регистрацию
                if existing_user.status == "approved":
                    raise HTTPException(status_code=400, detail="Пользователь уже зарегистрирован и одобрен")
                # Если пользователь в статусе pending, разрешаем повторную регистрацию
                elif existing_user.status == "pending":
                    # Обновляем существующего пользователя вместо создания нового
                    existing_user.first_name = data.full_name.split()[0] if data.full_name else ""
                    existing_user.last_name = " ".join(data.full_name.split()[1:]) if len(data.full_name.split()) > 1 else ""
                    existing_user.role = invite_data.get("role")
                    existing_user.specialization = data.specialization if invite_data.get("role") == "executor" else None
                    existing_user.roles = [invite_data.get("role")]
                    existing_user.active_role = invite_data.get("role")
                    
                    db.commit()
                    
                    return {
                        "success": True,
                        "message": "Данные пользователя обновлены",
                        "user_id": existing_user.id
                    }
                # Для других статусов (blocked и т.д.) также разрешаем повторную регистрацию
                else:
                    # Обновляем существующего пользователя
                    existing_user.first_name = data.full_name.split()[0] if data.full_name else ""
                    existing_user.last_name = " ".join(data.full_name.split()[1:]) if len(data.full_name.split()) > 1 else ""
                    existing_user.role = invite_data.get("role")
                    existing_user.specialization = data.specialization if invite_data.get("role") == "executor" else None
                    existing_user.roles = [invite_data.get("role")]
                    existing_user.active_role = invite_data.get("role")
                    existing_user.status = "pending"  # Сбрасываем статус на pending
                    
                    db.commit()
                    
                    return {
                        "success": True,
                        "message": "Данные пользователя обновлены",
                        "user_id": existing_user.id
                    }
        
        # Создаем пользователя через веб-регистрацию
        user_data = {
            "telegram_id": data.telegram_id,
            "first_name": data.full_name.split()[0] if data.full_name else "",
            "last_name": " ".join(data.full_name.split()[1:]) if len(data.full_name.split()) > 1 else "",
            "role": invite_data.get("role"),
            "specialization": data.specialization if invite_data.get("role") == "executor" else None,
            "status": "pending"
        }
        
        # Используем существующий метод присоединения
        result = invite_service.join_via_invite(
            token=data.token,
            telegram_id=data.telegram_id,
            first_name=user_data["first_name"],
            last_name=user_data["last_name"],
            specialization=data.specialization
        )
        
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("message", "Ошибка регистрации"))
        
        return {
            "success": True,
            "message": "Регистрация успешно завершена",
            "user_id": result.get("user_id")
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Внутренняя ошибка сервера: {str(e)}")

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
