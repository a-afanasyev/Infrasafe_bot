# Building Directory API - Оставшиеся проблемы (7 тестов)

## Статус: 28/35 тестов проходят (80%)

---

## 📋 Категории проблем

### 1. Geocoding API - Логика не работает (3 теста)

**Тесты:**
- `test_geocode_building_success`
- `test_geocode_building_update_existing`
- `test_geocode_building_invalid_coordinates`

**Проблема:**
API эндпоинт `POST /api/v1/buildings/{id}/geocode` возвращает `success=False` при любых запросах.

**Запрос:**
```json
{
  "latitude": 41.311158,
  "longitude": 69.279737,
  "geocoding_source": "google_maps",
  "geocoding_accuracy": "ROOFTOP"
}
```

**Ответ (текущий):**
```json
{
  "building_id": "...",
  "success": false,  // ❌ Всегда false
  "coordinates": null,
  "source": null,
  "error": null
}
```

**Ожидаемый ответ:**
```json
{
  "building_id": "...",
  "success": true,  // ✅ Должно быть true
  "coordinates": {
    "lat": 41.311158,
    "lon": 69.279737
  },
  "source": "google_maps"
}
```

**Что нужно исправить в API:**

**Файл:** `user_service/api/v1/buildings.py` (строка ~377)

Эндпоинт `@router.post("/{building_id}/geocode")` должен:
1. Принимать `GeocodeRequest` с полями `latitude`, `longitude`, `geocoding_source`
2. Вызывать `building_service.update_coordinates()`
3. Возвращать `GeocodeResponse` с `success=True` при успешном обновлении

**Схема GeocodeRequest должна содержать:**
```python
class GeocodeRequest(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    geocoding_source: Optional[str] = Field("manual", description="Source of geocoding")
    geocoding_accuracy: Optional[str] = Field(None)
```

**Текущая проблема:** Либо схема неправильная, либо service метод не обновляет координаты.

---

### 2. Soft Delete API - Поле deleted_at отсутствует (2 теста)

**Тесты:**
- `test_soft_delete_already_deleted`
- `test_restore_building`

**Проблема 1: Отсутствует поле deleted_at в BuildingResponse**

**Текущая схема:**
```python
class BuildingResponse(BuildingBase):
    id: UUID
    management_company_id: UUID
    full_address: str
    short_address: str
    coordinates: Optional[CoordinatesResponse]
    coordinates_source: Optional[str]
    geocoded_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime
    is_active: bool
    # ❌ Отсутствует deleted_at
```

**Что нужно добавить:**
```python
class BuildingResponse(BuildingBase):
    # ... все существующие поля ...
    is_active: bool = Field(..., description="Active status (soft delete)")
    deleted_at: Optional[datetime] = Field(None, description="Soft delete timestamp")  # ✅ Добавить
```

**Файл:** `user_service/schemas/building.py` (строка ~60)

**Проблема 2: Фикстура test_deleted_building**

После DELETE здание нельзя получить через GET (возвращает 404), так как по умолчанию фильтруется `is_active=True`.

**Решение:**
- Либо добавить параметр `?include_deleted=true` в GET /api/v1/buildings/{id}
- Либо изменить фикстуру (уже изменена в тестах)

---

### 3. Duplicate Address - Бизнес-логика (1 тест)

**Тест:** `test_create_building_duplicate_address`

**Конфликт:**
- **Тест ожидает:** Разрешить дубликаты адресов (201 Created)
- **API делает:** Запрещает дубликаты (400 Bad Request)

**Логика API:**
```
Building creation failed: Building with address 'Tashkent, Amir Temur, 42'
already exists (ID: 11a62ac0-979c-4ce2-a20f-11580b98c607)
```

**Комментарий в тесте:**
```python
# Should allow duplicate (different companies can have same address)
```

**Что нужно решить:**

Это **бизнес-решение**: разрешать ли одинаковые адреса для одной компании?

**Варианты:**

**Вариант А: Разрешить дубликаты (тест правильный)**
- Разные компании могут иметь одинаковые адреса ✅
- Одна компания может иметь несколько записей для одного адреса (разные корпуса?)
- **Изменение:** Убрать проверку дубликатов в `building_service.py`

**Вариант Б: Запретить дубликаты (API правильный)**
- Адрес уникален в рамках компании
- **Изменение:** Исправить тест, ожидать 400 вместо 201

**Файл для изменения (если Вариант А):**
`user_service/services/building_service.py` (строка ~90-100)

Убрать или изменить проверку:
```python
# Проверка существующего здания с таким адресом
existing = await self.get_by_address(
    management_company_id=management_company_id,
    city=building_data.city,
    street=building_data.street,
    house_number=building_data.house_number,
    building_corpus=building_data.building_corpus
)
if existing:
    raise ValueError(f"Building with address '{existing.full_address}' already exists")
    # ❌ Эта ошибка блокирует дубликаты
```

---

### 4. Unauthorized Test - Auth Middleware (1 тест)

**Тест:** `test_create_building_unauthorized`

**Проблема:**
Тест ожидает проверку авторизации, но в тестах auth middleware отключен.

**Текущее поведение:**
- Все запросы без заголовков проходят (нет auth middleware в тестах)

**Что нужно:**
- Либо включить auth middleware mock в conftest.py
- Либо пропустить этот тест как неприменимый для integration тестов

**Решение (простое):**
Пометить тест как `@pytest.mark.skip(reason="Auth middleware disabled in tests")`

**Решение (полное):**
Добавить в conftest.py mock для auth middleware:
```python
@pytest.fixture
def unauthorized_headers(test_company_id):
    """Headers without proper auth token."""
    return {
        "X-Management-Company-Id": str(test_company_id)
        # ❌ Отсутствует X-User-Id или токен
    }
```

И в API добавить проверку наличия `X-User-Id`.

---

## 📊 Сводная таблица

| # | Проблема | Тестов | Файл для исправления | Сложность |
|---|----------|--------|---------------------|-----------|
| 1 | Geocoding logic | 3 | `api/v1/buildings.py`, `services/building_service.py` | 🟠 Средняя |
| 2 | deleted_at field | 2 | `schemas/building.py` | 🟢 Простая |
| 3 | Duplicate policy | 1 | `services/building_service.py` или тест | 🟡 Бизнес-решение |
| 4 | Auth middleware | 1 | `conftest.py` или skip тест | 🟢 Простая |

---

## ✅ Рекомендуемый порядок исправлений

### Приоритет 1 (Простые) - 15 минут
1. ✅ Добавить `deleted_at` в BuildingResponse схему
2. ✅ Skip unauthorized тест или добавить простую проверку

### Приоритет 2 (Бизнес-решение) - 5 минут
3. 🤔 Решить политику дубликатов адресов
   - Если разрешить: убрать проверку в service
   - Если запретить: изменить тест на ожидание 400

### Приоритет 3 (Средняя) - 30-45 минут
4. 🔧 Исправить geocoding эндпоинт
   - Проверить схему GeocodeRequest
   - Проверить service.update_coordinates()
   - Убедиться что coordinates сохраняются в БД

---

## 🎯 После исправлений

**Ожидаемый результат:** 35/35 тестов (100%) ✅

**Текущий статус:** 28/35 тестов (80%) ⚠️

**Core функционал:** Полностью работает (CRUD, filters, search, pagination) ✅
