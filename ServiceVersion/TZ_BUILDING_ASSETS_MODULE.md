# Техническое задание: Building Assets Module (часть Core Service)

## 1. Общее описание

### 1.1 Назначение
Building Assets Module - централизованный справочник недвижимости управляющей компании, обеспечивающий единую точку истины для всех адресов, зданий и помещений с геопривязкой.

### 1.2 Цели
- Единый справочник всех управляемых объектов
- Исключение дублирования и разночтений в адресах
- Геопривязка всех объектов для оптимизации маршрутов
- Иерархическая структура: Комплекс → Здание → Подъезд → Этаж → Квартира
- Связь жильцов, заявок и услуг с конкретными помещениями

### 1.3 Размещение
- **Сервис**: Core Service (порт 8001)
- **Причина**: Тесная интеграция с Users и Requests
- **API префикс**: `/api/v1/assets/`

## 2. Функциональные требования

### 2.1 Иерархия объектов

#### 2.1.1 Структура недвижимости
```
Complex (Жилой комплекс)
├── Building (Здание)
│   ├── Entrance (Подъезд)
│   │   ├── Floor (Этаж)
│   │   │   ├── Apartment (Квартира)
│   │   │   ├── Office (Офис)
│   │   │   └── Storage (Кладовка)
│   │   └── Common Areas (Общие зоны)
│   ├── Parking (Парковка)
│   │   └── Parking Spot (Парковочное место)
│   └── Infrastructure (Инфраструктура)
│       ├── Elevator (Лифт)
│       ├── Basement (Подвал)
│       └── Roof (Крыша)
└── Territory (Территория)
    ├── Playground (Детская площадка)
    ├── Sports Ground (Спортплощадка)
    └── Green Zone (Зеленая зона)
```

#### 2.1.2 Типы помещений
- **Residential** (Жилые)
  - Apartment (Квартира)
  - Studio (Студия)
  - Penthouse (Пентхаус)

- **Commercial** (Коммерческие)
  - Office (Офис)
  - Shop (Магазин)
  - Restaurant (Ресторан)

- **Utility** (Служебные)
  - Storage (Кладовка)
  - Technical Room (Техническое помещение)
  - Janitor Room (Комната уборщика)

- **Common** (Общие)
  - Entrance Hall (Подъезд)
  - Corridor (Коридор)
  - Stairwell (Лестничная клетка)

### 2.2 Адресная система

#### 2.2.1 Адресные компоненты
```json
{
  "country": "Россия",
  "region": "Московская область",
  "city": "Москва",
  "district": "Пресненский район",
  "street": "ул. Пресненская набережная",
  "building_number": "12",
  "building_corpus": "2",
  "building_structure": "1",
  "postal_code": "123317",

  // Внутренняя адресация
  "entrance": "3",
  "floor": "15",
  "apartment": "256",

  // Дополнительно
  "cadastral_number": "77:01:0004042:1234",
  "management_code": "МСК-ПРС-0012-02"
}
```

#### 2.2.2 Форматы адресов
- **Полный**: Россия, г. Москва, ул. Пресненская набережная, д. 12, корп. 2, кв. 256
- **Короткий**: Пресненская наб., 12-2-256
- **Внутренний**: МСК-ПРС-0012-02-256
- **Для навигации**: 55.747398, 37.537210 (с точным входом)

#### 2.2.3 Валидация и ввод адресов (Q3.1)

**Принято решение**: Ручной ввод адресов ЗАПРЕЩЕН

**Политика ввода адресов**:
- ✅ Выбор только из справочника зданий
- ❌ Ручной ввод текстом запрещен
- ❌ Создание новых адресов пользователями запрещено

**Варианты выбора для пользователя**:
1. **Своя квартира** - привязана к профилю пользователя
2. **Свой дом** - общая территория дома пользователя
3. **Доступные дворы** - территории, которые пользователь может выбрать (может быть несколько)

**Примечания**:
- Все адреса предзагружены администратором
- Пользователь выбирает из доступного списка
- Геокодирование происходит автоматически из справочника
- Нормализация не требуется (все уже нормализовано в БД)

**Добавление новых адресов**:
- Только через админ-панель
- С обязательной геопривязкой
- С указанием всех метаданных
- С проверкой на дубликаты

### 2.3 Геопривязка

#### 2.3.1 Координаты и полигоны
```json
{
  "location": {
    "type": "Point",
    "coordinates": [37.537210, 55.747398]  // [lng, lat]
  },
  "polygon": {
    "type": "Polygon",
    "coordinates": [[[...]]]  // Границы территории
  },
  "entrances": [
    {
      "number": "1",
      "coordinates": [37.537110, 55.747298],
      "is_main": true
    }
  ],
  "navigation": {
    "vehicle_access": [37.537310, 55.747498],
    "pedestrian_access": [37.537210, 55.747398],
    "service_access": [37.537010, 55.747198]
  }
}
```

#### 2.3.2 Геозоны и районы обслуживания
- Зоны ответственности исполнителей
- Районы для группировки заявок
- Маршруты обхода территории
- Ограничения доступа по зонам

### 2.4 Метаданные объектов

#### 2.4.1 Building Metadata
```json
{
  "construction_year": 2019,
  "floors_count": 25,
  "entrances_count": 4,
  "apartments_count": 320,
  "elevators_count": 8,
  "total_area": 45000,  // м²
  "living_area": 32000,  // м²
  "land_area": 5000,     // м²
  "building_type": "residential_multistory",
  "building_series": "П-44Т",
  "wall_material": "panel",
  "heating_type": "central",
  "gas_type": "central",
  "water_type": "central_hot_cold",
  "sewerage_type": "central",
  "management_start_date": "2019-01-01",
  "warranty_end_date": "2024-01-01"
}
```

#### 2.4.2 Apartment Metadata
```json
{
  "rooms_count": 3,
  "total_area": 75.5,      // м²
  "living_area": 45.2,     // м²
  "kitchen_area": 12.3,    // м²
  "ceiling_height": 2.7,   // м
  "balconies_count": 1,
  "bathrooms_count": 2,
  "layout_type": "standard",
  "renovation_type": "designer",
  "view_type": "yard",
  "ownership_type": "private",
  "residents_count": 3,
  "pets_allowed": true,
  "parking_spots": ["B2-145", "B2-146"]
}
```

#### 2.4.3 Доступ пользователей к объектам

**Связь пользователь ↔ недвижимость**:
```json
{
  "user_id": "uuid",
  "primary_apartment_id": "uuid",      // Основная квартира
  "accessible_buildings": ["uuid"],    // Доступные дома
  "accessible_territories": ["uuid"],  // Доступные дворы/территории
  "access_type": "owner|tenant|employee",
  "verified": true,
  "assigned_at": "timestamp"
}
```

**Правила доступа**:
- Пользователь может создавать заявки только для доступных объектов
- Житель видит только свои объекты
- Сотрудник видит объекты в зоне ответственности
- Менеджер видит все объекты организации
- Админ видит всё

### 2.5 Связи с другими сущностями

#### 2.5.1 User-Asset Relations
```
User (Resident/Owner)
  ├── Primary Residence (основное жилье)
  ├── Additional Properties (доп. собственность)
  ├── Parking Spots (парковочные места)
  └── Storage Units (кладовки)
```

#### 2.5.2 Request-Asset Relations
```
Request
  ├── Location (где выполнить)
  ├── Access Points (как попасть)
  └── Affected Assets (затронутые объекты)
```

#### 2.5.3 Service-Asset Relations
```
Service Contract
  ├── Covered Buildings
  ├── Service Areas
  └── Excluded Zones
```

## 3. API Specifications

### 3.1 RESTful API Endpoints

#### Complex Management
```
GET    /api/v1/assets/complexes
GET    /api/v1/assets/complexes/{id}
POST   /api/v1/assets/complexes
PUT    /api/v1/assets/complexes/{id}
DELETE /api/v1/assets/complexes/{id}
```

#### Building Management
```
GET    /api/v1/assets/buildings
GET    /api/v1/assets/buildings/{id}
POST   /api/v1/assets/buildings
PUT    /api/v1/assets/buildings/{id}
DELETE /api/v1/assets/buildings/{id}
GET    /api/v1/assets/buildings/{id}/entrances
GET    /api/v1/assets/buildings/{id}/apartments
GET    /api/v1/assets/buildings/{id}/infrastructure
```

#### Apartment Management
```
GET    /api/v1/assets/apartments
GET    /api/v1/assets/apartments/{id}
POST   /api/v1/assets/apartments
PUT    /api/v1/assets/apartments/{id}
DELETE /api/v1/assets/apartments/{id}
GET    /api/v1/assets/apartments/{id}/residents
POST   /api/v1/assets/apartments/{id}/residents
```

#### Геопоиск
```
GET    /api/v1/assets/search/nearby?lat={lat}&lng={lng}&radius={radius}
GET    /api/v1/assets/search/polygon
POST   /api/v1/assets/search/route
GET    /api/v1/assets/zones
GET    /api/v1/assets/zones/{id}/assets
```

#### Адресный поиск
```
GET    /api/v1/assets/search?q={query}
POST   /api/v1/assets/geocode
POST   /api/v1/assets/reverse-geocode
GET    /api/v1/assets/validate-address
```

## 4. База данных

### 4.1 Основные таблицы

#### Complexes Table
```sql
CREATE TABLE complexes (
    id UUID PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    code VARCHAR(50) UNIQUE,
    address JSONB,
    location GEOGRAPHY(POINT, 4326),
    polygon GEOGRAPHY(POLYGON, 4326),
    metadata JSONB,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);

CREATE INDEX idx_complexes_location ON complexes USING GIST (location);
CREATE INDEX idx_complexes_polygon ON complexes USING GIST (polygon);
```

#### Buildings Table
```sql
CREATE TABLE buildings (
    id UUID PRIMARY KEY,
    complex_id UUID REFERENCES complexes(id),
    building_number VARCHAR(20),
    building_corpus VARCHAR(10),
    address JSONB NOT NULL,
    location GEOGRAPHY(POINT, 4326) NOT NULL,
    polygon GEOGRAPHY(POLYGON, 4326),
    floors_count INTEGER,
    entrances JSONB,  -- Array of entrance locations
    metadata JSONB,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);

CREATE INDEX idx_buildings_complex ON buildings(complex_id);
CREATE INDEX idx_buildings_location ON buildings USING GIST (location);
```

#### Apartments Table
```sql
CREATE TABLE apartments (
    id UUID PRIMARY KEY,
    building_id UUID REFERENCES buildings(id),
    entrance_number VARCHAR(10),
    floor_number INTEGER,
    apartment_number VARCHAR(20),
    internal_code VARCHAR(50) UNIQUE,
    location GEOGRAPHY(POINT, 4326),
    apartment_type VARCHAR(50),
    metadata JSONB,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);

CREATE INDEX idx_apartments_building ON apartments(building_id);
CREATE UNIQUE INDEX idx_apartments_unique ON apartments(building_id, apartment_number);
```

#### Asset_Users Table (связь жильцов с квартирами)
```sql
CREATE TABLE asset_users (
    id UUID PRIMARY KEY,
    asset_id UUID NOT NULL,
    asset_type VARCHAR(50), -- 'apartment', 'parking', 'storage'
    user_id UUID REFERENCES users(id),
    relation_type VARCHAR(50), -- 'owner', 'resident', 'tenant'
    is_primary BOOLEAN DEFAULT false,
    start_date DATE,
    end_date DATE,
    created_at TIMESTAMP
);

CREATE INDEX idx_asset_users_asset ON asset_users(asset_id, asset_type);
CREATE INDEX idx_asset_users_user ON asset_users(user_id);
```

### 4.2 Индексы для геопоиска
```sql
-- Поиск ближайших зданий
CREATE INDEX idx_buildings_location_gist ON buildings USING GIST (location);

-- Поиск объектов в полигоне
CREATE INDEX idx_buildings_polygon_gist ON buildings USING GIST (polygon);

-- Полнотекстовый поиск по адресу
CREATE INDEX idx_buildings_address_gin ON buildings USING GIN (address);

-- Составной индекс для фильтрации
CREATE INDEX idx_buildings_complex_type ON buildings(complex_id, metadata->>'building_type');
```

## 5. Интеграции

### 5.1 С другими модулями Core Service

#### Users Module
```python
# При создании пользователя
user = create_user(data)
if user.role == 'resident':
    assign_user_to_apartment(user.id, apartment_id)
```

#### Requests Module
```python
# При создании заявки
request = create_request(data)
request.asset_id = apartment_id
request.location = get_asset_location(apartment_id)
```

### 5.2 С другими сервисами

#### Operations Service
```python
# Оптимизация маршрутов по геоданным
buildings = get_buildings_in_zone(zone_id)
optimized_route = calculate_optimal_route(buildings)
```

#### Integration Hub
```python
# Синхронизация с внешним Building Directory
external_data = fetch_building_directory()
sync_building_data(external_data)
```

## 6. Валидация и нормализация

### 6.1 Адресная валидация
- Проверка формата адреса
- Нормализация написания (ул./улица, д./дом)
- Проверка почтового индекса
- Валидация кадастрового номера

### 6.2 Геовалидация
- Проверка попадания координат в границы города
- Валидация полигонов (замкнутость, пересечения)
- Проверка расстояний между объектами

### 6.3 Дедупликация
- Поиск дубликатов по адресу
- Слияние дублирующихся записей
- Проверка уникальности внутренних кодов

## 7. Производительность

### 7.1 Требования
- Поиск по координатам: < 50ms
- Полнотекстовый поиск: < 100ms
- Загрузка иерархии здания: < 200ms
- Bulk import: 1000 записей/сек

### 7.2 Кеширование
- Список зданий: 5 минут
- Геоданные: 1 час
- Адресные справочники: 24 часа
- Иерархия объектов: 10 минут

## 8. Миграция данных

### 8.1 Import из существующих систем
- Excel/CSV файлы с адресами
- Выгрузки из 1С
- Данные из госреестров
- API внешних справочников

### 8.2 Очистка и обогащение
- Геокодирование адресов без координат
- Добавление кадастровых номеров
- Обогащение метаданными
- Связывание с существующими пользователями

## 9. Безопасность

### 9.1 Контроль доступа
- Публичная информация о зданиях
- Приватная информация о квартирах
- Персональные данные жильцов
- Служебная информация

### 9.2 Аудит
- Логирование всех изменений
- История владения/проживания
- Отслеживание доступа к данным

## 10. Roadmap

### Phase 1 (MVP)
- Базовый справочник зданий
- Простая иерархия
- Геокодирование
- Связь с заявками

### Phase 2
- Полная иерархия объектов
- Геозоны и маршруты
- Интеграция с ГИС
- Мобильное приложение

### Phase 3
- 3D-модели зданий
- BIM интеграция
- IoT датчики
- Digital Twin