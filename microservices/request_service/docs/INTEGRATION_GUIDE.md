# 🔌 Request Service - Integration Guide

**Version**: 1.0.0  
**Last Updated**: 6 October 2025  
**Audience**: Backend разработчики, интегрирующие другие сервисы с Request Service

---

## 📋 Table of Contents

- [Quick Start](#quick-start)
- [Service Authentication](#service-authentication)
- [Integration with Auth Service](#integration-with-auth-service)
- [Integration with User Service](#integration-with-user-service)
- [Integration with Media Service](#integration-with-media-service)
- [Integration with Notification Service](#integration-with-notification-service)
- [Integration with AI Service](#integration-with-ai-service)
- [Telegram Bot Integration](#telegram-bot-integration)
- [Common Integration Patterns](#common-integration-patterns)
- [Error Handling](#error-handling)
- [Best Practices](#best-practices)

---

## 🚀 Quick Start

### Minimum Viable Integration

**Что нужно для базовой интеграции**:

1. ✅ Service token от Auth Service
2. ✅ User ID mapping (Telegram ID → User Service ID)
3. ✅ HTTP client с поддержкой async (httpx, aiohttp)

**Минимальный пример** (создание заявки):

```python
import httpx

async def create_request_example():
    # Service token (получить от Auth Service один раз)
    service_token = "your_service_token_here"
    
    # Создать заявку
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://request-service:8003/api/v1/requests",
            headers={"Authorization": f"Bearer {service_token}"},
            json={
                "title": "Протечка в ванной",
                "description": "Под раковиной течет вода",
                "category": "сантехника",
                "priority": "срочный",
                "address": "Чиланзар, дом 45",
                "applicant_user_id": 42
            }
        )
        
        if response.status_code == 201:
            data = response.json()
            print(f"Заявка создана: {data['request_number']}")
            return data
        else:
            print(f"Ошибка: {response.status_code}")
            return None
```

**Результат**:
```json
{
  "request_number": "251006-015",
  "status": "новая",
  "created_at": "2025-10-06T18:00:00Z"
}
```

---

## 🔐 Service Authentication

### Получение Service Token

**Step 1: Запросить token от Auth Service**

```python
async def get_service_token():
    """Получить service token для Request Service"""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://auth-service:8001/api/v1/internal/service-token",
            json={
                "service_name": "your-service-name",
                "permissions": ["request:read", "request:write"]
            }
        )
        
        if response.status_code == 200:
            data = response.json()
            return data["token"]
        else:
            raise Exception("Failed to get service token")
```

**Step 2: Использовать token во всех запросах**

```python
# Создать client с токеном
class RequestServiceClient:
    def __init__(self, service_token: str):
        self.base_url = "http://request-service:8003"
        self.headers = {
            "Authorization": f"Bearer {service_token}",
            "Content-Type": "application/json"
        }
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            headers=self.headers,
            timeout=30.0
        )
    
    async def create_request(self, request_data: dict):
        response = await self.client.post("/api/v1/requests", json=request_data)
        response.raise_for_status()
        return response.json()
    
    async def get_request(self, request_number: str):
        response = await self.client.get(f"/api/v1/requests/{request_number}")
        response.raise_for_status()
        return response.json()
```

---

## 🔗 Integration with Auth Service

### Валидация пользователя перед созданием заявки

```python
async def validate_and_create_request(telegram_id: int, request_data: dict):
    """
    Проверка пользователя в Auth Service перед созданием заявки
    """
    # Step 1: Проверить, что пользователь авторизован
    async with httpx.AsyncClient() as client:
        auth_response = await client.get(
            f"http://auth-service:8001/api/v1/internal/user-by-telegram/{telegram_id}",
            headers={"Authorization": f"Bearer {service_token}"}
        )
        
        if auth_response.status_code != 200:
            raise Exception("User not authenticated")
        
        user_data = auth_response.json()
        user_id = user_data["user_id"]
    
    # Step 2: Создать заявку с validated user_id
    request_data["applicant_user_id"] = user_id
    
    request_response = await request_client.create_request(request_data)
    return request_response
```

---

## 👥 Integration with User Service

### Получение информации об исполнителе

```python
async def get_executor_details_for_request(request_number: str):
    """
    Получить детали заявки с информацией об исполнителе из User Service
    """
    # Step 1: Получить заявку
    request = await request_client.get_request(request_number)
    
    if not request.get("executor_user_id"):
        return {**request, "executor": None}
    
    # Step 2: Получить данные исполнителя из User Service
    async with httpx.AsyncClient() as client:
        user_response = await client.get(
            f"http://user-service:8002/api/v1/users/{request['executor_user_id']}",
            headers={"Authorization": f"Bearer {service_token}"}
        )
        
        if user_response.status_code == 200:
            executor_data = user_response.json()
            return {
                **request,
                "executor": {
                    "id": executor_data["id"],
                    "name": f"{executor_data['first_name']} {executor_data['last_name']}",
                    "phone": executor_data["phone"],
                    "specialization": executor_data["profile"]["specialization"],
                    "rating": executor_data["profile"]["rating"]
                }
            }
    
    return {**request, "executor": None}
```

### Поиск доступных исполнителей

```python
async def find_available_executors(category: str, address: str):
    """
    Найти доступных исполнителей для заявки
    """
    # Получить suggestions от AI/Request Service
    suggestions_response = await request_client.get_suggestions("251006-001")
    
    suggested_executor_ids = [s["executor_id"] for s in suggestions_response["suggestions"]]
    
    # Получить детальную информацию от User Service
    async with httpx.AsyncClient() as client:
        executors_response = await client.post(
            "http://user-service:8002/api/v1/internal/executors/batch",
            headers={"Authorization": f"Bearer {service_token}"},
            json={"executor_ids": suggested_executor_ids}
        )
        
        return executors_response.json()["executors"]
```

---

## 📷 Integration with Media Service

### Загрузка фото к заявке

```python
async def upload_request_photo(request_number: str, photo_file: bytes, user_id: int):
    """
    Загрузить фото и привязать к заявке
    """
    # Step 1: Загрузить фото в Media Service
    async with httpx.AsyncClient() as client:
        files = {"file": ("photo.jpg", photo_file, "image/jpeg")}
        data = {
            "category": "request_photo",
            "uploaded_by": user_id,
            "request_number": request_number
        }
        
        media_response = await client.post(
            "http://media-service:8004/api/v1/media/upload",
            headers={"Authorization": f"Bearer {service_token}"},
            files=files,
            data=data
        )
        
        if media_response.status_code != 201:
            raise Exception("Media upload failed")
        
        media_data = media_response.json()
        file_id = media_data["file_id"]
    
    # Step 2: Обновить заявку с ID файла
    request = await request_client.get_request(request_number)
    media_file_ids = request.get("media_file_ids", [])
    media_file_ids.append(file_id)
    
    await request_client.update_request(request_number, {"media_file_ids": media_file_ids})
    
    return file_id
```

### Получение URL фото

```python
async def get_request_photos(request_number: str):
    """
    Получить все фото заявки с download URLs
    """
    # Step 1: Получить заявку
    request = await request_client.get_request(request_number)
    media_file_ids = request.get("media_file_ids", [])
    
    if not media_file_ids:
        return []
    
    # Step 2: Получить информацию о файлах из Media Service
    async with httpx.AsyncClient() as client:
        media_response = await client.post(
            "http://media-service:8004/api/v1/internal/files/info",
            headers={"Authorization": f"Bearer {service_token}"},
            json={"file_ids": media_file_ids}
        )
        
        if media_response.status_code == 200:
            files = media_response.json()["files"]
            return [
                {
                    "file_id": f["file_id"],
                    "filename": f["original_filename"],
                    "url": f["download_url"],
                    "thumbnail_url": f.get("thumbnail_url")
                }
                for f in files
            ]
    
    return []
```

---

## 📢 Integration with Notification Service

### Отправка уведомления при создании заявки

```python
async def create_request_with_notification(request_data: dict):
    """
    Создать заявку и отправить уведомление заявителю
    """
    # Step 1: Создать заявку
    request = await request_client.create_request(request_data)
    
    # Step 2: Отправить уведомление
    async with httpx.AsyncClient() as client:
        notification_response = await client.post(
            "http://notification-service:8005/api/v1/notifications",
            headers={"Authorization": f"Bearer {service_token}"},
            json={
                "recipient_type": "user",
                "recipient_value": request["applicant_user_id"],
                "template_key": "request_created_ru",
                "data": {
                    "request_number": request["request_number"],
                    "title": request["title"],
                    "category": request["category"],
                    "priority": request["priority"]
                },
                "priority": 2,  # normal priority
                "channel": "telegram"
            }
        )
        
        if notification_response.status_code != 200:
            # Log but don't fail - notification is non-critical
            logger.warning(f"Failed to send notification: {notification_response.text}")
    
    return request
```

### Уведомления при изменении статуса

```python
async def update_status_with_notifications(request_number: str, new_status: str, updated_by: int):
    """
    Обновить статус и уведомить всех участников
    """
    # Step 1: Получить текущую заявку
    request = await request_client.get_request(request_number)
    old_status = request["status"]
    
    # Step 2: Обновить статус
    await request_client.update_status(request_number, new_status, updated_by)
    
    # Step 3: Определить получателей уведомлений
    recipients = []
    
    if request["applicant_user_id"]:
        recipients.append({
            "user_id": request["applicant_user_id"],
            "role": "applicant"
        })
    
    if request.get("executor_user_id"):
        recipients.append({
            "user_id": request["executor_user_id"],
            "role": "executor"
        })
    
    # Step 4: Отправить уведомления
    async with httpx.AsyncClient() as client:
        for recipient in recipients:
            template_key = f"request_status_{new_status}_{recipient['role']}_ru"
            
            await client.post(
                "http://notification-service:8005/api/v1/notifications",
                headers={"Authorization": f"Bearer {service_token}"},
                json={
                    "recipient_type": "user",
                    "recipient_value": recipient["user_id"],
                    "template_key": template_key,
                    "data": {
                        "request_number": request_number,
                        "old_status": old_status,
                        "new_status": new_status,
                        "title": request["title"]
                    }
                }
            )
```

---

## 🤖 Integration with AI Service

### Автоматическое назначение с AI

```python
async def auto_assign_with_ai(request_number: str):
    """
    Использовать AI Service для автоматического назначения исполнителя
    """
    # Option 1: Использовать встроенный AI endpoint Request Service
    response = await request_client.ai_auto_assign(request_number)
    
    # Option 2: Использовать напрямую AI Service (для более тонкой настройки)
    async with httpx.AsyncClient() as client:
        # Получить заявку
        request = await request_client.get_request(request_number)
        
        # Запросить рекомендации от AI Service
        ai_response = await client.post(
            "http://ai-service:8006/api/v1/assignments/basic-assign",
            headers={"Authorization": f"Bearer {service_token}"},
            json={
                "request_number": request_number,
                "category": request["category"],
                "urgency": 4 if request["priority"] == "срочный" else 2,
                "description": request["description"],
                "address": request["address"]
            }
        )
        
        if ai_response.status_code == 200:
            ai_data = ai_response.json()
            executor_id = ai_data["executor_id"]
            
            # Назначить рекомендованного исполнителя
            assignment = await request_client.assign_request(
                request_number,
                executor_id=executor_id,
                assigned_by=0,  # system user
                assignment_type="ai_recommended"
            )
            
            return assignment
```

---

## 🤖 Telegram Bot Integration

### Complete Bot Integration Example

**Создание заявки из Telegram бота**:

```python
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

# Telegram bot setup
bot = Bot(token="YOUR_BOT_TOKEN")
dp = Dispatcher()

@dp.message(Command("create_request"))
async def handle_create_request(message: types.Message):
    """
    Обработчик команды /create_request в Telegram боте
    """
    telegram_id = message.from_user.id
    
    # Step 1: Получить user_id из User Service
    async with httpx.AsyncClient() as client:
        user_response = await client.get(
            f"http://user-service:8002/api/v1/users/by-telegram/{telegram_id}",
            headers={"Authorization": f"Bearer {service_token}"}
        )
        
        if user_response.status_code != 200:
            await message.answer("❌ Пользователь не найден. Пожалуйста, зарегистрируйтесь.")
            return
        
        user = user_response.json()
        user_id = user["id"]
    
    # Step 2: Создать заявку через Bot Integration API
    async with httpx.AsyncClient() as client:
        request_response = await client.post(
            "http://request-service:8003/api/v1/bot/requests/create",
            headers={"Authorization": f"Bearer {service_token}"},
            json={
                "user_id": str(telegram_id),
                "title": "Заявка через бота",
                "description": message.text or "Описание отсутствует",
                "category": "прочее",
                "priority": "обычный",
                "phone": user["phone"],
                "contact_name": f"{user['first_name']} {user['last_name']}"
            }
        )
        
        if request_response.status_code == 200:
            data = request_response.json()
            bot_message = data.get("bot_message", f"Заявка {data['request_number']} создана")
            await message.answer(bot_message)
        else:
            await message.answer("❌ Ошибка создания заявки")

# Запуск бота
if __name__ == "__main__":
    dp.run_polling(bot)
```

### Проверка статуса заявки через бота

```python
@dp.message(Command("my_requests"))
async def handle_my_requests(message: types.Message):
    """
    Показать все заявки пользователя
    """
    telegram_id = message.from_user.id
    
    # Поиск заявок пользователя через Bot API
    async with httpx.AsyncClient() as client:
        search_response = await client.get(
            "http://request-service:8003/api/v1/bot/search",
            headers={"Authorization": f"Bearer {service_token}"},
            params={"user_id": str(telegram_id), "limit": 10}
        )
        
        if search_response.status_code == 200:
            data = search_response.json()
            
            # Использовать предформатированное сообщение
            bot_message = data.get("bot_formatted_message")
            await message.answer(bot_message)
        else:
            await message.answer("❌ Ошибка поиска заявок")
```

---

## 🔄 Common Integration Patterns

### Pattern 1: Complete Request Creation Flow

**Полный цикл создания заявки с всеми интеграциями**:

```python
async def complete_request_creation_flow(telegram_id: int, request_details: dict):
    """
    Полный flow создания заявки:
    1. Validate user (Auth Service)
    2. Get user details (User Service)
    3. Upload photos (Media Service)
    4. Create request (Request Service)
    5. Auto-assign (AI Service)
    6. Send notifications (Notification Service)
    """
    
    # Step 1: Validate and get user
    user = await auth_service.get_user_by_telegram(telegram_id)
    if not user:
        raise Exception("User not found")
    
    # Step 2: Upload photos to Media Service
    media_file_ids = []
    if request_details.get("photos"):
        for photo in request_details["photos"]:
            file_id = await media_service.upload_file(
                file_data=photo,
                category="request_photo",
                uploaded_by=user["id"]
            )
            media_file_ids.append(file_id)
    
    # Step 3: Create request
    request = await request_service.create_request({
        "title": request_details["title"],
        "description": request_details["description"],
        "category": request_details["category"],
        "priority": request_details["priority"],
        "address": request_details["address"],
        "applicant_user_id": user["id"],
        "media_file_ids": media_file_ids
    })
    
    request_number = request["request_number"]
    
    # Step 4: Auto-assign if priority is high/urgent
    if request["priority"] in ["срочный", "аварийный"]:
        assignment = await request_service.ai_auto_assign(request_number)
        executor_id = assignment["assigned_executor"]["executor_id"]
    else:
        executor_id = None
    
    # Step 5: Send notifications
    # To applicant
    await notification_service.send_notification(
        recipient_id=user["id"],
        template_key="request_created_ru",
        data={"request_number": request_number, "title": request["title"]}
    )
    
    # To executor (if assigned)
    if executor_id:
        await notification_service.send_notification(
            recipient_id=executor_id,
            template_key="request_assigned_ru",
            data={"request_number": request_number, "title": request["title"]}
        )
    
    return {
        "request_number": request_number,
        "executor_assigned": executor_id is not None,
        "notifications_sent": 1 + (1 if executor_id else 0),
        "photos_uploaded": len(media_file_ids)
    }
```

---

### Pattern 2: Status Change with Full Workflow

```python
async def complete_request_workflow(request_number: str, executor_id: int):
    """
    Полный workflow завершения заявки
    """
    # Step 1: Change status to "в работе"
    await request_service.update_status(
        request_number,
        new_status="в работе",
        updated_by=executor_id
    )
    
    # Step 2: Executor добавляет комментарий с фото прогресса
    photo_id = await media_service.upload_file(...)
    await request_service.add_comment(
        request_number,
        comment_text="Начал работу, фото текущего состояния",
        author_user_id=executor_id,
        media_file_ids=[photo_id]
    )
    
    # Step 3: Executor добавляет материалы
    await request_service.add_materials_bulk(
        request_number,
        materials=[
            {"material_name": "Труба ПВХ 32мм", "quantity": 2, "unit_price": 25000},
            {"material_name": "Прокладки", "quantity": 5, "unit_price": 5000}
        ],
        added_by=executor_id
    )
    
    # Step 4: Change status to "выполнена"
    await request_service.update_status(
        request_number,
        new_status="выполнена",
        updated_by=executor_id
    )
    
    # Step 5: Отправить уведомление заявителю с просьбой оценить
    request = await request_service.get_request(request_number)
    await notification_service.send_notification(
        recipient_id=request["applicant_user_id"],
        template_key="request_completed_rate_us_ru",
        data={
            "request_number": request_number,
            "executor_name": await get_executor_name(executor_id)
        }
    )
```

---

### Pattern 3: Dual-Write to Legacy Monolith

```python
async def create_request_with_dual_write(request_data: dict):
    """
    Создать заявку в микросервисе и синхронизировать с монолитом
    """
    # Step 1: Create in microservice (primary)
    request = await request_service.create_request(request_data)
    request_number = request["request_number"]
    
    # Step 2: Sync to monolith (secondary)
    try:
        async with httpx.AsyncClient() as client:
            monolith_response = await client.post(
                "http://monolith:5000/api/requests/sync",
                headers={"X-Internal-Token": monolith_token},
                json={
                    "source": "microservice",
                    "request_number": request_number,
                    "request_data": request
                },
                timeout=5.0
            )
            
            if monolith_response.status_code != 200:
                # Log для мониторинга, но не fail
                logger.warning(f"Monolith sync failed for {request_number}")
    
    except Exception as e:
        # Graceful degradation - продолжаем работу без монолита
        logger.error(f"Monolith unreachable: {e}")
    
    return request
```

---

## ⚠️ Error Handling

### Retry Strategy

```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10)
)
async def create_request_with_retry(request_data: dict):
    """
    Создание заявки с автоматическими повторными попытками
    """
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://request-service:8003/api/v1/requests",
            headers={"Authorization": f"Bearer {service_token}"},
            json=request_data,
            timeout=30.0
        )
        
        # Retry на temporary errors
        if response.status_code in [500, 502, 503, 504]:
            raise Exception("Temporary error, will retry")
        
        # Don't retry на client errors
        if response.status_code >= 400:
            raise Exception(f"Client error {response.status_code}: {response.text}")
        
        return response.json()
```

### Circuit Breaker Pattern

```python
class RequestServiceClient:
    """
    Client с circuit breaker для fault tolerance
    """
    def __init__(self):
        self.failure_count = 0
        self.failure_threshold = 5
        self.circuit_open = False
        self.last_failure_time = None
        self.timeout_seconds = 60
    
    async def create_request(self, request_data: dict):
        # Check circuit breaker
        if self.circuit_open:
            if (datetime.now() - self.last_failure_time).seconds > self.timeout_seconds:
                self.circuit_open = False
                self.failure_count = 0
            else:
                raise Exception("Circuit breaker open - Request Service unavailable")
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "http://request-service:8003/api/v1/requests",
                    headers={"Authorization": f"Bearer {self.service_token}"},
                    json=request_data,
                    timeout=10.0
                )
                
                if response.status_code == 200:
                    self.failure_count = 0  # Reset на success
                    return response.json()
                else:
                    raise Exception(f"HTTP {response.status_code}")
        
        except Exception as e:
            self.failure_count += 1
            
            if self.failure_count >= self.failure_threshold:
                self.circuit_open = True
                self.last_failure_time = datetime.now()
                logger.error("Circuit breaker opened for Request Service")
            
            raise
```

---

## ✅ Best Practices

### 1. Always Use Service Tokens

```python
# ✅ ПРАВИЛЬНО: Service token
headers = {"Authorization": f"Bearer {service_token}"}

# ❌ НЕПРАВИЛЬНО: User JWT token
headers = {"Authorization": f"Bearer {user_jwt_token}"}
```

**Почему**: User tokens expire быстро (15 min), service tokens live longer

---

### 2. Handle Async Properly

```python
# ✅ ПРАВИЛЬНО: async/await
async def create_request():
    request = await request_service.create_request({...})
    return request

# ❌ НЕПРАВИЛЬНО: blocking call в async function
async def create_request_bad():
    request = requests.post(...)  # Блокирует event loop!
    return request
```

---

### 3. Cache Service Tokens

```python
# ✅ ПРАВИЛЬНО: Cache token, refresh before expiry
class ServiceClient:
    def __init__(self):
        self.token = None
        self.token_expires_at = None
    
    async def get_token(self):
        if self.token and datetime.now() < self.token_expires_at:
            return self.token
        
        # Refresh token
        self.token = await auth_service.get_service_token()
        self.token_expires_at = datetime.now() + timedelta(hours=23)
        return self.token

# ❌ НЕПРАВИЛЬНО: Запрашивать token на каждый request
async def bad_pattern():
    token = await get_new_token()  # Каждый раз!
    await make_request(token)
```

---

### 4. Graceful Degradation

```python
# ✅ ПРАВИЛЬНО: Fallback если сервис недоступен
async def create_request_safe(request_data: dict):
    try:
        # Try microservice first
        return await request_service.create_request(request_data)
    except httpx.ConnectError:
        # Fallback to monolith
        logger.warning("Request Service unavailable, using monolith")
        return await monolith.create_request(request_data)
    except Exception as e:
        # Log and re-raise
        logger.error(f"Failed to create request: {e}")
        raise
```

---

### 5. Batch Operations When Possible

```python
# ✅ ПРАВИЛЬНО: Bulk operation
materials = [
    {"material_name": "Труба", "quantity": 2, "unit_price": 25000},
    {"material_name": "Прокладки", "quantity": 5, "unit_price": 5000}
]
await request_service.add_materials_bulk(request_number, materials)

# ❌ НЕПРАВИЛЬНО: Multiple single requests
for material in materials:
    await request_service.add_material(request_number, material)  # N requests!
```

**Почему**: Bulk operations:
- Используют одну транзакцию
- Быстрее (1 round-trip vs N)
- Атомарны (all-or-nothing)

---

### 6. Include Request Context

```python
# ✅ ПРАВИЛЬНО: Передавать context для tracing
headers = {
    "Authorization": f"Bearer {service_token}",
    "X-Request-ID": request_id,
    "X-Correlation-ID": correlation_id,
    "X-Source-Service": "your-service-name"
}

# Helps with:
# - Distributed tracing
# - Debugging
# - Monitoring
```

---

### 7. Validate Before Calling

```python
# ✅ ПРАВИЛЬНО: Client-side validation
async def create_request_validated(request_data: dict):
    # Validate required fields
    if not request_data.get("title"):
        raise ValueError("Title is required")
    
    if not request_data.get("category"):
        raise ValueError("Category is required")
    
    # Validate enum values
    valid_categories = ["сантехника", "электрика", ...]
    if request_data["category"] not in valid_categories:
        raise ValueError(f"Invalid category: {request_data['category']}")
    
    # Then call service
    return await request_service.create_request(request_data)

# Saves round-trip time and provides better error messages
```

---

## 🔧 Troubleshooting

### Issue 1: "Request number generation failed"

**Симптом**:
```json
{
  "detail": "Cannot generate request number: both Redis and PostgreSQL failed",
  "status_code": 503
}
```

**Причина**: Redis и PostgreSQL недоступны одновременно

**Решение**:
1. Проверить Redis: `docker-compose exec shared-redis redis-cli ping`
2. Проверить PostgreSQL: `docker-compose exec request-db pg_isready`
3. Проверить network: `docker-compose exec request-service ping shared-redis`

---

### Issue 2: "Service token invalid"

**Симптом**:
```json
{
  "detail": "Invalid service token",
  "status_code": 401
}
```

**Причина**: Token expired или неправильный

**Решение**:
```python
# Получить новый token
new_token = await auth_service.get_service_token()

# Проверить срок действия
token_info = await auth_service.validate_token(token)
print(f"Expires at: {token_info['expires_at']}")
```

---

### Issue 3: "Cannot transition from X to Y"

**Симптом**:
```json
{
  "detail": "Cannot transition from 'выполнена' to 'в работе'",
  "status_code": 409
}
```

**Причина**: Недопустимый переход статуса

**Решение**: См. [API_REFERENCE_CORE.md](API_REFERENCE_CORE.md) для allowed transitions

---

## 📖 See Also

- [API_REFERENCE_CORE.md](API_REFERENCE_CORE.md) - Core Requests API
- [API_REFERENCE_ASSIGNMENTS.md](API_REFERENCE_ASSIGNMENTS.md) - Assignments API
- [API_REFERENCE_COMMENTS.md](API_REFERENCE_COMMENTS.md) - Comments, Ratings, Materials
- [API_REFERENCE_INTEGRATION.md](API_REFERENCE_INTEGRATION.md) - Bot, Search, Export
- [REQUEST_SERVICE_DOCUMENTATION.md](REQUEST_SERVICE_DOCUMENTATION.md) - Техническая документация


