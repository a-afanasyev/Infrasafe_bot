"""
Bot Integration API endpoints
UK Management Bot - Request Management System

API endpoints specifically designed for Telegram bot integration.
These endpoints handle bot-specific data formats and operations.
"""

from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Body
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_session
from app.integrations.bot_integration import BotIntegrationService
from app.core.auth import verify_internal_token

router = APIRouter()


@router.post("/requests/create")
async def create_request_from_bot(
    request_data: Dict[str, Any] = Body(...),
    db: AsyncSession = Depends(get_async_session),
    _: str = Depends(verify_internal_token)
):
    """
    Create request from Telegram bot

    Expected bot format:
    {
        "user_id": "123456789",
        "title": "Заявка на ремонт",
        "description": "Описание проблемы",
        "address": "ул. Примерная, д. 1",
        "apartment": "123",
        "category": "сантехника",
        "priority": "обычный",
        "phone": "+998901234567",
        "contact_name": "Иван Иванов",
        "is_emergency": false,
        "estimated_cost": 100000,
        "preferred_time": "2025-09-28T10:00:00"
    }
    """
    bot_service = BotIntegrationService(db)

    try:
        result = await bot_service.create_request_from_bot(request_data)
        return {
            "success": True,
            "request_number": result["request_number"],
            "status": result["status"],
            "message": f"Заявка {result['request_number']} успешно создана"
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка создания заявки: {str(e)}"
        )

    finally:
        await bot_service.close()


@router.put("/requests/{request_number}/update")
async def update_request_from_bot(
    request_number: str,
    update_data: Dict[str, Any] = Body(...),
    db: AsyncSession = Depends(get_async_session),
    _: str = Depends(verify_internal_token)
):
    """
    Update request from Telegram bot

    Expected bot format:
    {
        "user_id": "123456789",
        "title": "Новый заголовок",  # optional
        "description": "Новое описание",  # optional
        "priority": "высокий",  # optional
        ... other fields to update
    }
    """
    bot_service = BotIntegrationService(db)

    try:
        result = await bot_service.update_request_from_bot(request_number, update_data)
        return {
            "success": True,
            "request_number": request_number,
            "status": result["status"],
            "message": f"Заявка {request_number} обновлена"
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка обновления заявки: {str(e)}"
        )

    finally:
        await bot_service.close()


@router.post("/requests/{request_number}/comments")
async def add_comment_from_bot(
    request_number: str,
    comment_data: Dict[str, Any] = Body(...),
    db: AsyncSession = Depends(get_async_session),
    _: str = Depends(verify_internal_token)
):
    """
    Add comment from Telegram bot

    Expected bot format:
    {
        "user_id": "123456789",
        "message": "Текст комментария",
        "visibility": "public",  # optional: "public", "internal"
        "is_internal": false  # optional
    }
    """
    bot_service = BotIntegrationService(db)

    try:
        result = await bot_service.add_comment_from_bot(request_number, comment_data)
        return {
            "success": True,
            "comment_id": result["comment_id"],
            "message": "Комментарий добавлен"
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка добавления комментария: {str(e)}"
        )

    finally:
        await bot_service.close()


@router.put("/requests/{request_number}/status")
async def update_status_from_bot(
    request_number: str,
    status_data: Dict[str, Any] = Body(...),
    db: AsyncSession = Depends(get_async_session),
    _: str = Depends(verify_internal_token)
):
    """
    Update request status from Telegram bot

    Expected bot format:
    {
        "user_id": "123456789",
        "new_status": "в работе",
        "comment": "Взял в работу"  # optional
    }
    """
    bot_service = BotIntegrationService(db)

    try:
        result = await bot_service.handle_bot_status_change(request_number, status_data)
        return {
            "success": True,
            "request_number": request_number,
            "new_status": result["status"],
            "message": f"Статус заявки {request_number} изменен на '{result['status']}'"
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка изменения статуса: {str(e)}"
        )

    finally:
        await bot_service.close()


@router.post("/requests/{request_number}/assign")
async def assign_from_bot(
    request_number: str,
    assignment_data: Dict[str, Any] = Body(...),
    db: AsyncSession = Depends(get_async_session),
    _: str = Depends(verify_internal_token)
):
    """
    Assign executor from Telegram bot

    Expected bot format:
    {
        "assigned_by": "manager_123",
        "assigned_to": "executor_456",
        "assignment_type": "manual",
        "assignment_reason": "Специалист по этой категории"
    }
    """
    bot_service = BotIntegrationService(db)

    try:
        result = await bot_service.handle_bot_assignment(request_number, assignment_data)
        return {
            "success": True,
            "request_number": request_number,
            "assigned_to": result["assigned_to"],
            "message": f"Заявка {request_number} назначена исполнителю"
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка назначения исполнителя: {str(e)}"
        )

    finally:
        await bot_service.close()


@router.get("/requests/{request_number}")
async def get_request_for_bot(
    request_number: str,
    db: AsyncSession = Depends(get_async_session),
    _: str = Depends(verify_internal_token)
):
    """
    Get request data formatted for Telegram bot
    """
    bot_service = BotIntegrationService(db)

    try:
        result = await bot_service.get_request_for_bot(request_number)

        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Заявка {request_number} не найдена"
            )

        return {
            "success": True,
            "request": result
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка получения заявки: {str(e)}"
        )

    finally:
        await bot_service.close()


@router.get("/requests/search")
async def search_requests_for_bot(
    text: Optional[str] = None,
    status: Optional[str] = None,
    category: Optional[str] = None,
    assigned_to: Optional[str] = None,
    limit: int = 10,
    offset: int = 0,
    db: AsyncSession = Depends(get_async_session),
    _: str = Depends(verify_internal_token)
):
    """
    Search requests for Telegram bot
    """
    bot_service = BotIntegrationService(db)

    try:
        search_params = {
            "text": text,
            "status": status,
            "category": category,
            "assigned_to": assigned_to,
            "limit": limit,
            "offset": offset
        }

        result = await bot_service.search_requests_for_bot(search_params)

        return {
            "success": True,
            **result
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка поиска заявок: {str(e)}"
        )

    finally:
        await bot_service.close()


@router.get("/requests/user/{user_id}")
async def get_user_requests_for_bot(
    user_id: str,
    status: Optional[str] = None,
    limit: int = 10,
    offset: int = 0,
    db: AsyncSession = Depends(get_async_session),
    _: str = Depends(verify_internal_token)
):
    """
    Get user's requests for Telegram bot
    """
    bot_service = BotIntegrationService(db)

    try:
        search_params = {
            "assigned_to": user_id,
            "status": status,
            "limit": limit,
            "offset": offset
        }

        result = await bot_service.search_requests_for_bot(search_params)

        return {
            "success": True,
            "user_id": user_id,
            **result
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка получения заявок пользователя: {str(e)}"
        )

    finally:
        await bot_service.close()


@router.post("/migration/sync")
async def sync_request_from_monolith(
    request_data: Dict[str, Any] = Body(...),
    db: AsyncSession = Depends(get_async_session),
    _: str = Depends(verify_internal_token)
):
    """
    Sync specific request from monolith to microservice

    Expected format:
    {
        "request_number": "250927-001"
    }
    """
    from app.adapters.dual_write_adapter import DualWriteAdapter

    adapter = DualWriteAdapter(db)

    try:
        request_number = request_data["request_number"]
        success = await adapter.sync_request_from_monolith(request_number)

        if success:
            return {
                "success": True,
                "request_number": request_number,
                "message": f"Заявка {request_number} синхронизирована"
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Не удалось синхронизировать заявку {request_number}"
            )

    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Поле request_number обязательно"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка синхронизации: {str(e)}"
        )

    finally:
        await adapter.close()


@router.post("/migration/validate")
async def validate_data_consistency(
    request_data: Dict[str, Any] = Body(...),
    db: AsyncSession = Depends(get_async_session),
    _: str = Depends(verify_internal_token)
):
    """
    Validate data consistency between monolith and microservice

    Expected format:
    {
        "request_number": "250927-001"
    }
    """
    from app.adapters.dual_write_adapter import DualWriteAdapter

    adapter = DualWriteAdapter(db)

    try:
        request_number = request_data["request_number"]
        result = await adapter.validate_data_consistency(request_number)

        return {
            "success": True,
            **result
        }

    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Поле request_number обязательно"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка валидации: {str(e)}"
        )

    finally:
        await adapter.close()