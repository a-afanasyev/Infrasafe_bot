# Bot Handler Migration Examples

## Overview

This document provides specific examples of how to migrate Telegram bot handlers from monolith database access to Request Service API calls.

## Handler Migration Patterns

### 1. Request Creation Handler

#### Before (Monolith)
```python
# handlers/requests/create.py
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession

from services.request_service import RequestService
from database.models import Request
from states.request_states import RequestCreationState

router = Router()

@router.message(RequestCreationState.waiting_for_confirmation)
async def confirm_request_creation(message: Message, state: FSMContext, session: AsyncSession):
    data = await state.get_data()

    # Direct database access via monolith service
    request_service = RequestService(session)

    try:
        # Create request in monolith
        new_request = await request_service.create_request(
            title=data["title"],
            description=data["description"],
            address=data["address"],
            apartment_number=data.get("apartment"),
            category=data["category"],
            priority=data.get("priority", "обычный"),
            applicant_user_id=str(message.from_user.id),
            contact_phone=data.get("phone"),
            contact_name=data.get("contact_name"),
            is_emergency=data.get("is_emergency", False)
        )

        await message.answer(
            f"✅ Заявка создана!\n"
            f"📋 Номер: {new_request.request_number}\n"
            f"📊 Статус: {new_request.status}"
        )

    except Exception as e:
        await message.answer(f"❌ Ошибка создания заявки: {e}")

    await state.clear()
```

#### After (Request Service)
```python
# handlers/requests/create.py
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
import httpx
import logging

from config.settings import REQUEST_SERVICE_URL, INTERNAL_API_TOKEN
from states.request_states import RequestCreationState

router = Router()
logger = logging.getLogger(__name__)

@router.message(RequestCreationState.waiting_for_confirmation)
async def confirm_request_creation(message: Message, state: FSMContext):
    data = await state.get_data()

    # Prepare request data for Request Service
    request_data = {
        "user_id": str(message.from_user.id),
        "title": data["title"],
        "description": data["description"],
        "address": data["address"],
        "apartment": data.get("apartment"),
        "category": data["category"],
        "priority": data.get("priority", "обычный"),
        "phone": data.get("phone"),
        "contact_name": data.get("contact_name"),
        "is_emergency": data.get("is_emergency", False),
        "estimated_cost": data.get("estimated_cost"),
        "preferred_time": data.get("preferred_time")
    }

    async with httpx.AsyncClient() as client:
        try:
            # Call Request Service API
            response = await client.post(
                f"{REQUEST_SERVICE_URL}/api/v1/bot/requests/create",
                json=request_data,
                headers={"Authorization": f"Bearer {INTERNAL_API_TOKEN}"},
                timeout=30.0
            )

            response.raise_for_status()
            result = response.json()

            if result["success"]:
                await message.answer(
                    f"✅ Заявка создана!\n"
                    f"📋 Номер: {result['request_number']}\n"
                    f"📊 Статус: {result['status']}"
                )
                logger.info(f"Request created via API: {result['request_number']}")
            else:
                await message.answer(f"❌ Ошибка: {result.get('message', 'Неизвестная ошибка')}")

        except httpx.TimeoutException:
            await message.answer("❌ Превышено время ожидания. Попробуйте еще раз.")
            logger.error("Request Service timeout during request creation")

        except httpx.HTTPStatusError as e:
            error_detail = e.response.json().get("detail", "Ошибка сервиса")
            await message.answer(f"❌ Ошибка создания заявки: {error_detail}")
            logger.error(f"Request Service error: {e.response.status_code}, {error_detail}")

        except Exception as e:
            await message.answer("❌ Ошибка создания заявки. Попробуйте позже.")
            logger.error(f"Unexpected error during request creation: {e}")

    await state.clear()
```

### 2. Status Update Handler

#### Before (Monolith)
```python
# handlers/requests/status.py
@router.callback_query(F.data.startswith("update_status:"))
async def update_request_status(callback: CallbackQuery, session: AsyncSession):
    _, request_id, new_status = callback.data.split(":")

    request_service = RequestService(session)

    try:
        # Direct database update
        updated_request = await request_service.update_request_status(
            request_id=int(request_id),
            new_status=new_status,
            user_id=str(callback.from_user.id),
            comment=f"Статус изменен через бот"
        )

        await callback.message.edit_text(
            f"✅ Статус заявки #{updated_request.request_number} изменен на '{new_status}'"
        )

    except Exception as e:
        await callback.answer(f"Ошибка: {e}", show_alert=True)
```

#### After (Request Service)
```python
# handlers/requests/status.py
@router.callback_query(F.data.startswith("update_status:"))
async def update_request_status(callback: CallbackQuery):
    _, request_number, new_status = callback.data.split(":")

    status_data = {
        "user_id": str(callback.from_user.id),
        "new_status": new_status,
        "comment": "Статус изменен через бот"
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.put(
                f"{REQUEST_SERVICE_URL}/api/v1/bot/requests/{request_number}/status",
                json=status_data,
                headers={"Authorization": f"Bearer {INTERNAL_API_TOKEN}"},
                timeout=30.0
            )

            response.raise_for_status()
            result = response.json()

            if result["success"]:
                await callback.message.edit_text(
                    f"✅ {result['message']}"
                )
                logger.info(f"Status updated via API: {request_number} -> {new_status}")
            else:
                await callback.answer("❌ Ошибка обновления статуса", show_alert=True)

        except Exception as e:
            await callback.answer("❌ Ошибка обновления статуса", show_alert=True)
            logger.error(f"Status update error: {e}")
```

### 3. Comment Addition Handler

#### Before (Monolith)
```python
# handlers/requests/comments.py
@router.message(CommentState.waiting_for_comment)
async def add_comment(message: Message, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    request_id = data["request_id"]

    comment_service = CommentService(session)

    try:
        comment = await comment_service.add_comment(
            request_id=request_id,
            author_user_id=str(message.from_user.id),
            comment_text=message.text,
            visibility="public"
        )

        await message.answer(f"✅ Комментарий добавлен к заявке #{data['request_number']}")

    except Exception as e:
        await message.answer(f"❌ Ошибка добавления комментария: {e}")

    await state.clear()
```

#### After (Request Service)
```python
# handlers/requests/comments.py
@router.message(CommentState.waiting_for_comment)
async def add_comment(message: Message, state: FSMContext):
    data = await state.get_data()
    request_number = data["request_number"]

    comment_data = {
        "user_id": str(message.from_user.id),
        "message": message.text,
        "visibility": "public",
        "is_internal": False
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{REQUEST_SERVICE_URL}/api/v1/bot/requests/{request_number}/comments",
                json=comment_data,
                headers={"Authorization": f"Bearer {INTERNAL_API_TOKEN}"},
                timeout=30.0
            )

            response.raise_for_status()
            result = response.json()

            if result["success"]:
                await message.answer(f"✅ Комментарий добавлен к заявке #{request_number}")
            else:
                await message.answer("❌ Ошибка добавления комментария")

        except Exception as e:
            await message.answer("❌ Ошибка добавления комментария")
            logger.error(f"Comment addition error: {e}")

    await state.clear()
```

### 4. Request List Handler

#### Before (Monolith)
```python
# handlers/requests/list.py
@router.message(F.text == "📋 Мои заявки")
async def my_requests_list(message: Message, session: AsyncSession):
    request_service = RequestService(session)

    try:
        # Direct database query
        requests = await request_service.get_user_requests(
            user_id=str(message.from_user.id),
            limit=10
        )

        if not requests:
            await message.answer("У вас пока нет заявок")
            return

        text = "📋 Ваши заявки:\n\n"
        for req in requests:
            text += f"🔹 #{req.request_number}\n"
            text += f"   📝 {req.title}\n"
            text += f"   📊 {req.status}\n"
            text += f"   📅 {req.created_at.strftime('%d.%m.%Y %H:%M')}\n\n"

        await message.answer(text)

    except Exception as e:
        await message.answer(f"❌ Ошибка получения заявок: {e}")
```

#### After (Request Service)
```python
# handlers/requests/list.py
@router.message(F.text == "📋 Мои заявки")
async def my_requests_list(message: Message):
    user_id = str(message.from_user.id)

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                f"{REQUEST_SERVICE_URL}/api/v1/bot/requests/user/{user_id}",
                params={"limit": 10},
                headers={"Authorization": f"Bearer {INTERNAL_API_TOKEN}"},
                timeout=30.0
            )

            response.raise_for_status()
            result = response.json()

            if not result["success"] or not result["requests"]:
                await message.answer("У вас пока нет заявок")
                return

            text = "📋 Ваши заявки:\n\n"
            for req in result["requests"]:
                text += f"🔹 #{req['request_number']}\n"
                text += f"   📝 {req['title']}\n"
                text += f"   📊 {req['status']}\n"
                text += f"   📅 {req['created_at'][:19].replace('T', ' ')}\n\n"

            if result["has_more"]:
                text += "... и еще заявки. Используйте поиск для просмотра всех."

            await message.answer(text)

        except Exception as e:
            await message.answer("❌ Ошибка получения заявок")
            logger.error(f"Request list error: {e}")
```

### 5. Assignment Handler

#### Before (Monolith)
```python
# handlers/admin/assignment.py
@router.callback_query(F.data.startswith("assign:"))
async def assign_executor(callback: CallbackQuery, session: AsyncSession):
    _, request_id, executor_id = callback.data.split(":")

    assignment_service = AssignmentService(session)

    try:
        assignment = await assignment_service.assign_request(
            request_id=int(request_id),
            executor_user_id=executor_id,
            assigned_by_user_id=str(callback.from_user.id),
            assignment_reason="Назначено через бот"
        )

        await callback.message.edit_text(
            f"✅ Заявка назначена исполнителю"
        )

    except Exception as e:
        await callback.answer(f"Ошибка назначения: {e}", show_alert=True)
```

#### After (Request Service)
```python
# handlers/admin/assignment.py
@router.callback_query(F.data.startswith("assign:"))
async def assign_executor(callback: CallbackQuery):
    _, request_number, executor_id = callback.data.split(":")

    assignment_data = {
        "assigned_by": str(callback.from_user.id),
        "assigned_to": executor_id,
        "assignment_type": "manual",
        "assignment_reason": "Назначено через бот"
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{REQUEST_SERVICE_URL}/api/v1/bot/requests/{request_number}/assign",
                json=assignment_data,
                headers={"Authorization": f"Bearer {INTERNAL_API_TOKEN}"},
                timeout=30.0
            )

            response.raise_for_status()
            result = response.json()

            if result["success"]:
                await callback.message.edit_text(
                    f"✅ {result['message']}"
                )
            else:
                await callback.answer("❌ Ошибка назначения", show_alert=True)

        except Exception as e:
            await callback.answer("❌ Ошибка назначения", show_alert=True)
            logger.error(f"Assignment error: {e}")
```

## Utility Functions

### HTTP Client Setup
```python
# utils/request_service_client.py
import httpx
import logging
from typing import Dict, Any, Optional
from config.settings import REQUEST_SERVICE_URL, INTERNAL_API_TOKEN

logger = logging.getLogger(__name__)

class RequestServiceClient:
    def __init__(self):
        self.base_url = REQUEST_SERVICE_URL
        self.headers = {"Authorization": f"Bearer {INTERNAL_API_TOKEN}"}
        self.timeout = 30.0

    async def create_request(self, request_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.base_url}/api/v1/bot/requests/create",
                    json=request_data,
                    headers=self.headers,
                    timeout=self.timeout
                )
                response.raise_for_status()
                return response.json()
            except Exception as e:
                logger.error(f"Create request error: {e}")
                return None

    async def update_status(self, request_number: str, status_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        async with httpx.AsyncClient() as client:
            try:
                response = await client.put(
                    f"{self.base_url}/api/v1/bot/requests/{request_number}/status",
                    json=status_data,
                    headers=self.headers,
                    timeout=self.timeout
                )
                response.raise_for_status()
                return response.json()
            except Exception as e:
                logger.error(f"Update status error: {e}")
                return None

    async def get_request(self, request_number: str) -> Optional[Dict[str, Any]]:
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    f"{self.base_url}/api/v1/bot/requests/{request_number}",
                    headers=self.headers,
                    timeout=self.timeout
                )
                response.raise_for_status()
                result = response.json()
                return result["request"] if result["success"] else None
            except Exception as e:
                logger.error(f"Get request error: {e}")
                return None

# Usage in handlers
request_client = RequestServiceClient()

@router.message(F.text.startswith("/request"))
async def get_request_info(message: Message):
    request_number = message.text.split()[1]
    request_data = await request_client.get_request(request_number)

    if request_data:
        # Display request info
        pass
    else:
        await message.answer("❌ Заявка не найдена")
```

### Error Handling Middleware
```python
# middlewares/request_service_error_handler.py
from aiogram import BaseMiddleware
from aiogram.types import Update
import logging

logger = logging.getLogger(__name__)

class RequestServiceErrorMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        try:
            return await handler(event, data)
        except httpx.TimeoutException:
            if hasattr(event, 'answer'):
                await event.answer("❌ Превышено время ожидания. Попробуйте еще раз.")
            logger.error("Request Service timeout")
        except httpx.HTTPStatusError as e:
            if hasattr(event, 'answer'):
                await event.answer("❌ Ошибка сервиса. Попробуйте позже.")
            logger.error(f"Request Service HTTP error: {e.response.status_code}")
        except Exception as e:
            if hasattr(event, 'answer'):
                await event.answer("❌ Произошла ошибка. Попробуйте позже.")
            logger.error(f"Unexpected error: {e}")
```

## Configuration Updates

### Environment Variables
```bash
# .env for bot service
REQUEST_SERVICE_URL=http://localhost:8002
INTERNAL_API_TOKEN=your-secret-token
REQUEST_SERVICE_TIMEOUT=30

# Migration settings
USE_REQUEST_SERVICE=true
ENABLE_FALLBACK=true
MIGRATION_MODE=dual
```

### Settings Module
```python
# config/settings.py
import os
from pydantic import BaseSettings

class Settings(BaseSettings):
    # Existing settings...

    # Request Service integration
    REQUEST_SERVICE_URL: str = os.getenv("REQUEST_SERVICE_URL", "http://localhost:8002")
    INTERNAL_API_TOKEN: str = os.getenv("INTERNAL_API_TOKEN", "")
    REQUEST_SERVICE_TIMEOUT: int = int(os.getenv("REQUEST_SERVICE_TIMEOUT", "30"))

    # Migration settings
    USE_REQUEST_SERVICE: bool = os.getenv("USE_REQUEST_SERVICE", "false").lower() == "true"
    ENABLE_FALLBACK: bool = os.getenv("ENABLE_FALLBACK", "true").lower() == "true"
    MIGRATION_MODE: str = os.getenv("MIGRATION_MODE", "dual")

settings = Settings()
```

## Testing

### Integration Tests
```python
# tests/test_request_service_integration.py
import pytest
import httpx
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_create_request_handler():
    # Mock Request Service response
    mock_response = {
        "success": True,
        "request_number": "250927-001",
        "status": "новая",
        "message": "Заявка создана"
    }

    with patch('httpx.AsyncClient.post') as mock_post:
        mock_post.return_value.json.return_value = mock_response
        mock_post.return_value.raise_for_status.return_value = None

        # Test handler logic
        # ... test implementation
```

### Load Testing
```python
# tests/load_test_bot_integration.py
import asyncio
import httpx
import time

async def create_test_request():
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8002/api/v1/bot/requests/create",
            json={
                "user_id": "test_user",
                "title": "Load test request",
                "description": "Testing load",
                "address": "Test address",
                "category": "тест"
            },
            headers={"Authorization": "Bearer test-token"}
        )
        return response.status_code == 201

async def load_test():
    tasks = [create_test_request() for _ in range(100)]
    start_time = time.time()
    results = await asyncio.gather(*tasks)
    end_time = time.time()

    success_rate = sum(results) / len(results) * 100
    duration = end_time - start_time

    print(f"Success rate: {success_rate}%")
    print(f"Duration: {duration}s")
    print(f"RPS: {len(results) / duration}")

if __name__ == "__main__":
    asyncio.run(load_test())
```

## Migration Checklist

- [ ] Deploy Request Service with dual-write enabled
- [ ] Update bot environment variables
- [ ] Install httpx dependency in bot service
- [ ] Update request creation handlers
- [ ] Update status change handlers
- [ ] Update comment handlers
- [ ] Update assignment handlers
- [ ] Update list/search handlers
- [ ] Add error handling middleware
- [ ] Create request service client utility
- [ ] Update configuration management
- [ ] Write integration tests
- [ ] Perform load testing
- [ ] Monitor logs and metrics
- [ ] Validate data consistency
- [ ] Switch to microservice-only mode
- [ ] Remove monolith dependencies
- [ ] Clean up dual-write code

---

**Last Updated:** 27 September 2025
**Version:** 1.0
**Status:** Ready for Implementation