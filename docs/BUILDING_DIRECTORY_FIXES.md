# Building Directory Plan - Critical Fixes

**Дата**: 7 октября 2025
**Статус**: 🔴 КРИТИЧЕСКИЕ ИСПРАВЛЕНИЯ
**Цель**: Устранить 3 критических gaps в детальном плане

---

## 🔴 ПРОБЛЕМА 1: Integration Service отсутствует в плане

### Описание проблемы
Архитектурный документ требует integration-service для геокодинга (UNIFIED_BUILDING_DIRECTORY.md:42, 456), но в BUILDING_DIRECTORY_WEEKS_2_4.md детальных задач для integration-service нет вообще.

### ✅ РЕШЕНИЕ: Добавить Task 9.4A в Week 3 Day 2

---

## **НОВАЯ ЗАДАЧА: Task 9.4A - Integration Service для Building Directory (P0)**

**Время**: 4 часа
**Исполнитель**: Backend Developer
**Зависимости**: Task 9.1, 9.2 (Request Service updates)
**Позиция в плане**: Week 3, Day 2 (после Task 9.3, переименовать старый Task 9.4 в 9.4B)

---

### Цель
Обновить integration-service для использования Building Directory вместо прямого геокодирования каждой заявки.

### Файлы
- `microservices/integration_service/app/clients/directory_client.py` (новый)
- `microservices/integration_service/app/services/geocoding_service.py` (update)
- `microservices/integration_service/app/services/building_service.py` (новый)
- `microservices/integration_service/tests/test_building_integration.py` (новый)

---

### Шаг 1: Directory API Client (1.5 часа)

**Создать HTTP client для Directory API**:

```python
# app/clients/directory_client.py
"""HTTP client for Building Directory API."""
from httpx import AsyncClient, HTTPError
from typing import Optional, Dict, Any
from uuid import UUID
import logging

logger = logging.getLogger(__name__)

class DirectoryClient:
    """Client for Building Directory API."""

    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.client = AsyncClient(
            base_url=self.base_url,
            timeout=10.0,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
        )

    async def get_building(self, building_id: UUID) -> Optional[Dict[str, Any]]:
        """
        Get building by ID.

        Returns:
            Building data with full_address and coordinates, or None if not found
        """
        try:
            response = await self.client.get(f"/api/v1/buildings/{building_id}")
            response.raise_for_status()
            return response.json()

        except HTTPError as e:
            if e.response.status_code == 404:
                logger.warning(f"Building {building_id} not found")
                return None
            logger.error(f"Failed to fetch building {building_id}: {e}")
            raise

    async def update_building_coordinates(
        self,
        building_id: UUID,
        latitude: float,
        longitude: float
    ) -> bool:
        """
        Update building coordinates (cache geocoded result).

        Returns:
            True if successful, False otherwise
        """
        try:
            response = await self.client.put(
                f"/api/v1/buildings/{building_id}",
                json={
                    "latitude": latitude,
                    "longitude": longitude
                }
            )
            response.raise_for_status()
            logger.info(f"Updated coordinates for building {building_id}")
            return True

        except HTTPError as e:
            logger.error(f"Failed to update building {building_id} coordinates: {e}")
            return False

    async def close(self):
        """Close HTTP client."""
        await self.client.aclose()
```

**Чеклист:**
- [ ] DirectoryClient класс создан
- [ ] get_building() метод с error handling
- [ ] update_building_coordinates() для кэширования
- [ ] Timeout 10 секунд
- [ ] Authorization header
- [ ] Logging

---

### Шаг 2: Geocoding Service Update (1.5 часа)

**Обновить GeocodingService для использования Directory**:

```python
# app/services/geocoding_service.py
"""Geocoding service with Building Directory integration."""
from typing import Optional, Tuple
from uuid import UUID
import logging

from app.clients.directory_client import DirectoryClient
from app.clients.google_maps_client import GoogleMapsClient
from app.core.exceptions import GeocodingError

logger = logging.getLogger(__name__)

class GeocodingService:
    """
    Geocoding service with Directory-first strategy.

    Strategy:
    1. Check Building Directory for cached coordinates
    2. If not cached, geocode via Google Maps API
    3. Cache result in Building Directory for future use
    """

    def __init__(
        self,
        directory_client: DirectoryClient,
        google_maps_client: GoogleMapsClient
    ):
        self.directory = directory_client
        self.google_maps = google_maps_client

    async def geocode_building(
        self,
        building_id: UUID
    ) -> Tuple[float, float]:
        """
        Geocode building by ID.

        Uses cached coordinates from Directory if available,
        otherwise geocodes via Google Maps and caches result.

        Args:
            building_id: Building UUID from Directory

        Returns:
            (latitude, longitude) tuple

        Raises:
            GeocodingError: If geocoding fails
        """
        # 1. Fetch building from Directory
        building = await self.directory.get_building(building_id)

        if not building:
            raise GeocodingError(f"Building {building_id} not found in Directory")

        # 2. Check for cached coordinates
        if building.get("coordinates"):
            lat, lon = building["coordinates"]
            logger.info(
                f"Using cached coordinates for building {building_id}: "
                f"{lat}, {lon}"
            )
            return (lat, lon)

        # 3. No cached coordinates - geocode via Google Maps
        address = building.get("full_address")
        if not address:
            raise GeocodingError(
                f"Building {building_id} has no address to geocode"
            )

        logger.info(f"Geocoding building {building_id} address: {address}")

        try:
            coordinates = await self.google_maps.geocode_address(address)

        except Exception as e:
            logger.error(f"Google Maps geocoding failed for {address}: {e}")
            raise GeocodingError(f"Failed to geocode address: {address}") from e

        # 4. Cache geocoded coordinates in Directory
        lat, lon = coordinates
        cache_success = await self.directory.update_building_coordinates(
            building_id, lat, lon
        )

        if cache_success:
            logger.info(
                f"Cached coordinates for building {building_id}: {lat}, {lon}"
            )
        else:
            logger.warning(
                f"Failed to cache coordinates for building {building_id}"
            )

        return coordinates

    async def geocode_address(
        self,
        address: str
    ) -> Tuple[float, float]:
        """
        Geocode free-form address (fallback for legacy data).

        This method bypasses Directory and goes directly to Google Maps.
        Use only for migration or legacy requests without building_id.

        Args:
            address: Free-form address string

        Returns:
            (latitude, longitude) tuple

        Raises:
            GeocodingError: If geocoding fails
        """
        logger.warning(
            f"Geocoding free-form address (bypass Directory): {address}"
        )

        try:
            return await self.google_maps.geocode_address(address)

        except Exception as e:
            logger.error(f"Failed to geocode address {address}: {e}")
            raise GeocodingError(f"Failed to geocode address: {address}") from e
```

**Чеклист:**
- [ ] GeocodingService обновлен
- [ ] geocode_building() - Directory-first strategy
- [ ] Check cached coordinates
- [ ] Fallback to Google Maps
- [ ] Cache results in Directory
- [ ] geocode_address() для legacy data
- [ ] Error handling на всех уровнях
- [ ] Logging для debugging

---

### Шаг 3: Building Service (30 мин)

**Создать Building Service для других операций**:

```python
# app/services/building_service.py
"""Building operations for integration service."""
from typing import Optional, Dict, Any
from uuid import UUID
import logging

from app.clients.directory_client import DirectoryClient
from app.core.exceptions import BuildingNotFoundError

logger = logging.getLogger(__name__)

class BuildingService:
    """Service for building-related operations."""

    def __init__(self, directory_client: DirectoryClient):
        self.directory = directory_client

    async def get_building_details(
        self,
        building_id: UUID
    ) -> Dict[str, Any]:
        """
        Get building details for integrations.

        Returns:
            {
                "id": "uuid",
                "full_address": "Ташкент, Навои, 12",
                "coordinates": (41.311151, 69.279737),
                "city": "Ташкент",
                "district": "Юнусабадский"
            }

        Raises:
            BuildingNotFoundError: If building not found
        """
        building = await self.directory.get_building(building_id)

        if not building:
            raise BuildingNotFoundError(f"Building {building_id} not found")

        return {
            "id": str(building["id"]),
            "full_address": building.get("full_address"),
            "coordinates": building.get("coordinates"),
            "city": building.get("city"),
            "district": building.get("district"),
            "is_active": building.get("is_active", True)
        }

    async def validate_building(self, building_id: UUID) -> bool:
        """
        Validate building exists and is active.

        Returns:
            True if valid, False otherwise
        """
        try:
            building = await self.directory.get_building(building_id)
            return building is not None and building.get("is_active", False)

        except Exception as e:
            logger.error(f"Building validation failed for {building_id}: {e}")
            return False
```

---

### Шаг 4: Integration Tests (30 мин)

```python
# tests/test_building_integration.py
"""Integration tests for Building Directory integration."""
import pytest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from app.services.geocoding_service import GeocodingService
from app.clients.directory_client import DirectoryClient

@pytest.mark.asyncio
class TestBuildingDirectoryIntegration:

    async def test_geocode_building_with_cached_coords(
        self,
        mock_directory_client
    ):
        """Test geocoding with cached coordinates."""
        building_id = uuid4()

        # Mock Directory response with cached coordinates
        mock_directory_client.get_building.return_value = {
            "id": str(building_id),
            "full_address": "Ташкент, Навои, 12",
            "coordinates": (41.311151, 69.279737)
        }

        service = GeocodingService(
            mock_directory_client,
            AsyncMock()  # Google Maps not called
        )

        coords = await service.geocode_building(building_id)

        assert coords == (41.311151, 69.279737)
        mock_directory_client.get_building.assert_called_once_with(building_id)

    async def test_geocode_building_without_cache(
        self,
        mock_directory_client,
        mock_google_maps_client
    ):
        """Test geocoding without cached coordinates."""
        building_id = uuid4()

        # Mock Directory response without coordinates
        mock_directory_client.get_building.return_value = {
            "id": str(building_id),
            "full_address": "Ташкент, Навои, 12",
            "coordinates": None
        }

        # Mock Google Maps response
        mock_google_maps_client.geocode_address.return_value = (41.311151, 69.279737)

        service = GeocodingService(
            mock_directory_client,
            mock_google_maps_client
        )

        coords = await service.geocode_building(building_id)

        assert coords == (41.311151, 69.279737)

        # Verify Google Maps was called
        mock_google_maps_client.geocode_address.assert_called_once_with(
            "Ташкент, Навои, 12"
        )

        # Verify coordinates were cached
        mock_directory_client.update_building_coordinates.assert_called_once_with(
            building_id, 41.311151, 69.279737
        )

    async def test_geocode_building_not_found(
        self,
        mock_directory_client
    ):
        """Test geocoding with invalid building_id."""
        building_id = uuid4()

        mock_directory_client.get_building.return_value = None

        service = GeocodingService(mock_directory_client, AsyncMock())

        with pytest.raises(GeocodingError, match="not found in Directory"):
            await service.geocode_building(building_id)
```

---

### Шаг 5: Configuration Update (30 мин)

**Обновить конфигурацию**:

```python
# app/core/config.py
from pydantic import BaseSettings

class Settings(BaseSettings):
    # ... existing settings ...

    # NEW: Building Directory API
    DIRECTORY_API_URL: str
    DIRECTORY_API_KEY: str

    class Config:
        env_file = ".env"

settings = Settings()
```

**Environment variables**:
```bash
# .env
DIRECTORY_API_URL=http://user-service:8000
DIRECTORY_API_KEY=your-api-key-here
```

---

### Критерии приемки

**Функциональность:**
- ✅ DirectoryClient успешно подключается к Directory API
- ✅ GeocodingService использует кэшированные координаты
- ✅ Fallback to Google Maps работает
- ✅ Координаты кэшируются в Directory после геокодинга
- ✅ BuildingService валидирует здания

**Тестирование:**
- ✅ Unit tests для DirectoryClient (5+ tests)
- ✅ Unit tests для GeocodingService (10+ tests)
- ✅ Integration tests (5+ tests)
- ✅ Mock Google Maps API
- ✅ Mock Directory API
- ✅ Coverage > 85%

**Performance:**
- ✅ Cached coordinates: response < 10ms
- ✅ Non-cached: response < 500ms (Google Maps)
- ✅ No redundant Google Maps calls

**Documentation:**
- ✅ Docstrings для всех публичных методов
- ✅ Configuration guide updated
- ✅ Integration test examples

---

## 🔴 ПРОБЛЕМА 2: Противоречие в именовании поля address

### Описание проблемы
- **Архитектурный документ** (UNIFIED_BUILDING_DIRECTORY.md:415): "**address используется как пользовательский ввод для уточнений**"
- **Детальный план** (BUILDING_DIRECTORY_WEEKS_2_4.md:115-152): Переименовать `address` → `address_details`

**Конфликт**: План противоречит архитектуре.

### ✅ РЕШЕНИЕ: Сохранить поле `address` БЕЗ переименования

**Обоснование**:
1. Архитектурный документ - источник истины (source of truth)
2. Переименование - breaking change для API и БД
3. Имя `address` семантически корректно для "уточнений адреса"
4. Обратная совместимость сохраняется

---

### Исправления в Task 9.1

**БЫЛО (НЕВЕРНО)**:
```python
# Rename address → address_details
op.alter_column('requests', 'address',
    new_column_name='address_details')
```

**СТАЛО (ПРАВИЛЬНО)**:
```python
# NOTE: address колонка ОСТАЕТСЯ БЕЗ ИЗМЕНЕНИЙ
# Согласно архитектурному плану (UNIFIED_BUILDING_DIRECTORY.md:415):
# "address используется как пользовательский ввод для уточнений"
# Это поле для apartment/entrance/floor и т.д.
```

**Model**:
```python
class Request(Base):
    building_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    building_address = Column(String(500))  # Denormalized from Directory
    address = Column(String(500))  # User input for apartment/entrance (БЕЗ ИЗМЕНЕНИЙ)
```

---

### Исправления в Task 9.2 (API Schema)

**БЫЛО (НЕВЕРНО)**:
```python
class RequestCreate(BaseModel):
    building_id: UUID4
    address_details: Optional[str] = None
```

**СТАЛО (ПРАВИЛЬНО)**:
```python
class RequestCreate(BaseModel):
    building_id: UUID4
    address: Optional[str] = None  # User details (apartment, entrance, etc.)
```

---

### Исправления в Bot Integration (Week 2)

**Task 7.1** - обновить RequestServiceClient:
```python
# БЫЛО (НЕВЕРНО)
await request_service_client.create_request(
    user_id=user_id,
    building_id=building_id,
    category=category,
    description=description,
    address_details=address_details  # НЕВЕРНО
)

# СТАЛО (ПРАВИЛЬНО)
await request_service_client.create_request(
    user_id=user_id,
    building_id=building_id,
    category=category,
    description=description,
    address=address  # ПРАВИЛЬНО - согласно архитектуре
)
```

---

## 🔴 ПРОБЛЕМА 3: Migration script использует несуществующее поле

### Описание проблемы
Task 9.3 (строка 210-224) - скрипт миграции обращается к `request.address`, но если в Task 9.1 это поле переименовали в `address_details`, скрипт упадет с ошибкой.

### ✅ РЕШЕНИЕ: Исправлено автоматически

После исправления Проблемы 2 (поле `address` остается без изменений), скрипт миграции будет работать корректно:

```python
# scripts/migrate_building_ids.py
for request in requests_without_building_id:
    # request.address существует и не переименовывался
    building = matcher.match_address(
        request.address,  # ✅ КОРРЕКТНО - поле существует
        buildings_cache,
        threshold=0.8
    )

    if building:
        request.building_id = building.id
        request.building_address = building.full_address
        # request.address остается с пользовательским вводом
```

**Дополнительная безопасность** - добавить fallback:
```python
# Безопасный доступ к полю
address_to_match = getattr(request, 'address', None) or \
                   getattr(request, 'address_details', None)

if not address_to_match:
    logger.warning(f"Request {request.request_number} has no address to match")
    stats["no_address"] += 1
    continue

building = matcher.match_address(address_to_match, buildings_cache)
```

---

## 📋 ИТОГОВЫЙ ЧЕКЛИСТ ИСПРАВЛЕНИЙ

### ✅ Исправление 1: Integration Service
- [ ] Добавить Task 9.4A в Week 3 Day 2
- [ ] Переименовать Task 9.4 → Task 9.4B (Geocoding становится подзадачей)
- [ ] Создать DirectoryClient
- [ ] Обновить GeocodingService
- [ ] Создать BuildingService
- [ ] Написать integration tests
- [ ] Обновить конфигурацию

### ✅ Исправление 2: Именование поля address
- [ ] Task 9.1: Убрать переименование address → address_details
- [ ] Task 9.1: Добавить NOTE о сохранении поля address
- [ ] Task 9.2: Изменить address_details → address в schema
- [ ] Task 7.1 (Week 2): Изменить address_details → address в bot
- [ ] Обновить все примеры кода с address_details → address

### ✅ Исправление 3: Migration script
- [ ] Task 9.3: Добавить fallback для безопасного доступа к полю
- [ ] Task 9.3: Добавить обработку requests без address
- [ ] Task 9.3: Обновить статистику (добавить no_address counter)

---

## 🚀 СЛЕДУЮЩИЕ ШАГИ

1. **Применить исправления** к BUILDING_DIRECTORY_WEEKS_2_4.md:
   - Вставить Task 9.4A после Task 9.3
   - Исправить Task 9.1 (убрать переименование)
   - Исправить Task 9.2 (изменить schema)
   - Исправить Task 9.3 (добавить fallback)
   - Исправить Task 7.1 в Week 2

2. **Обновить зависимости** в плане:
   - Task 9.4B зависит от Task 9.4A
   - Task 9.5 (tests) зависит от Task 9.4A

3. **Проверить consistency** между документами:
   - UNIFIED_BUILDING_DIRECTORY.md (архитектура)
   - BUILDING_DIRECTORY_WEEKS_2_4.md (детальный план)
   - BUILDING_DIRECTORY_DETAILED_TASKS.md (Week 1)

---

**Все исправления критичны для успешной реализации!**
