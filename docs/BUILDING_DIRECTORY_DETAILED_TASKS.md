# Building Directory - Подробный план задач (Week 1)

**Создан**: 7 октября 2025
**Обновлен**: 7 октября 2025
**Статус**: 📋 ГОТОВ К ВЫПОЛНЕНИЮ
**Связанные документы**:
- [UNIFIED_BUILDING_DIRECTORY.md](./UNIFIED_BUILDING_DIRECTORY.md) - Архитектурный план
- [BUILDING_DIRECTORY_WEEKS_2_4.md](./BUILDING_DIRECTORY_WEEKS_2_4.md) - **Week 2-4 детальные задачи**

> **Примечание**: Этот документ содержит детальный план только для **Week 1**.
> Для Week 2-4 см. отдельный документ [BUILDING_DIRECTORY_WEEKS_2_4.md](./BUILDING_DIRECTORY_WEEKS_2_4.md)

---

## 📊 ОБЩАЯ СТАТИСТИКА

```yaml
Общая продолжительность: 4 недели (160 часов)
Количество задач: 47 задач
Количество человек: 6
Критические задачи (P0): 28
Высокоприоритетные (P1): 13
Средний приоритет (P2): 6

Распределение по неделям:
  Week 1 (Foundation): 12 задач, 40 часов - ЭТОТ ДОКУМЕНТ
  Week 2 (Bot Integration): 13 задач, 40 часов - См. BUILDING_DIRECTORY_WEEKS_2_4.md
  Week 3 (Services + Migration): 12 задач, 40 часов - См. BUILDING_DIRECTORY_WEEKS_2_4.md
  Week 4 (Production): 10 задач, 40 часов - См. BUILDING_DIRECTORY_WEEKS_2_4.md
```

---

## 🗓️ WEEK 1: FOUNDATION & CORE API (40 часов)

### 📅 DAY 1: Database Schema & Migrations (8 часов)

#### ✅ Task 1.1: Create Buildings Table Migration (P0)
```yaml
Длительность: 3 часа
Исполнитель: Backend Developer
Зависимости: Нет
```

**Файлы:**
- `microservices/user_service/alembic/versions/YYYY_MM_DD_HHMM_create_buildings_table.py`
- `microservices/user_service/app/models/building.py`

**Шаги реализации:**

1. **Создать миграцию** (30 мин)
```bash
cd microservices/user_service
alembic revision -m "create buildings table"
```

2. **Реализовать upgrade()** (1 час)
```python
def upgrade():
    # 1. Create buildings table
    op.create_table(
        'buildings',
        sa.Column('id', postgresql.UUID(as_uuid=True),
                 primary_key=True, default=uuid.uuid4),
        sa.Column('management_company_id', postgresql.UUID(as_uuid=True),
                 nullable=False),
        sa.Column('external_code', sa.String(50), unique=True),
        sa.Column('city', sa.String(100), nullable=False),
        sa.Column('district', sa.String(100)),
        sa.Column('street', sa.String(200), nullable=False),
        sa.Column('house_number', sa.String(20), nullable=False),
        sa.Column('postcode', sa.String(12)),
        sa.Column('latitude', sa.Numeric(10, 8)),
        sa.Column('longitude', sa.Numeric(11, 8)),
        sa.Column('geo_boundary', postgresql.JSONB),
        sa.Column('entrances', postgresql.JSONB),
        sa.Column('metadata', postgresql.JSONB),
        sa.Column('is_active', sa.Boolean(), default=True, nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True),
                 server_default=sa.text('now()')),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True),
                 server_default=sa.text('now()'), onupdate=sa.text('now()'))
    )

    # 2. Create indexes
    op.create_index('ix_buildings_mc_active', 'buildings',
                   ['management_company_id', 'is_active'])
    op.create_index('ix_buildings_external_code', 'buildings',
                   ['external_code'], unique=True, postgresql_where='external_code IS NOT NULL')
    op.create_index('ix_buildings_metadata', 'buildings',
                   ['metadata'], postgresql_using='gin')
    op.create_index('ix_buildings_city', 'buildings', ['city'])
    op.create_index('ix_buildings_street', 'buildings', ['street'])

    # 3. Create spatial index for coordinates
    op.execute("""
        CREATE INDEX ix_buildings_coordinates
        ON buildings USING gist (
            ll_to_earth(latitude::float8, longitude::float8)
        )
        WHERE latitude IS NOT NULL AND longitude IS NOT NULL
    """)
```

3. **Реализовать downgrade()** (30 мин)
```python
def downgrade():
    op.drop_index('ix_buildings_coordinates')
    op.drop_index('ix_buildings_street')
    op.drop_index('ix_buildings_city')
    op.drop_index('ix_buildings_metadata')
    op.drop_index('ix_buildings_external_code')
    op.drop_index('ix_buildings_mc_active')
    op.drop_table('buildings')
```

4. **Тестирование** (1 час)
```bash
# Test upgrade
alembic upgrade head

# Verify table creation
psql -U uk_user -d uk_user_db -c "\d buildings"

# Test downgrade
alembic downgrade -1

# Test upgrade again
alembic upgrade head
```

**Чеклист:**
- [ ] Migration файл создан с корректным timestamp
- [ ] Все колонки с правильными типами данных
- [ ] Primary key на UUID
- [ ] Indexes созданы (5 indexes including spatial)
- [ ] GIN index для JSONB metadata
- [ ] Spatial index только для non-NULL координат
- [ ] NOT NULL constraints на обязательных полях
- [ ] Default values установлены
- [ ] Timestamps с timezone
- [ ] downgrade() полностью отменяет upgrade()
- [ ] Миграция применяется без ошибок на пустой БД
- [ ] Миграция применяется на staging с данными
- [ ] Performance: создание таблицы < 5 секунд
- [ ] Rollback восстанавливает предыдущее состояние

**Критерии приемки:**
- ✅ `alembic upgrade head` успешно
- ✅ Все индексы созданы (проверить через `\di buildings*`)
- ✅ `alembic downgrade -1` удаляет таблицу
- ✅ Spatial index работает (проверить EXPLAIN для geo queries)
- ✅ Performance: INSERT 1000 записей < 2 секунды

**Риски:**
- ⚠️ ll_to_earth() требует PostGIS extension
  - **Митигация**: Добавить проверку и установку extension в миграции
- ⚠️ Spatial index может быть медленным на больших данных
  - **Митигация**: Создавать index CONCURRENTLY

---

#### ✅ Task 1.2: Create Building Access Rights Table (P0)
```yaml
Длительность: 2 часа
Исполнитель: Backend Developer
Зависимости: Task 1.1
```

**Файлы:**
- `microservices/user_service/alembic/versions/YYYY_MM_DD_HHMM_create_building_access_rights.py`

**Шаги реализации:**

1. **Создать ENUM type** (15 мин)
```python
def upgrade():
    # 1. Create enum type for access types
    access_type_enum = postgresql.ENUM(
        'residence',  # Житель
        'manager',    # Управляющий
        'service',    # Сервисный работник
        'temporary',  # Временный доступ
        name='building_access_type',
        create_type=False
    )
    access_type_enum.create(op.get_bind(), checkfirst=True)
```

2. **Создать таблицу** (45 мин)
```python
    # 2. Create table
    op.create_table(
        'building_access_rights',
        sa.Column('id', postgresql.UUID(as_uuid=True),
                 primary_key=True, default=uuid.uuid4),
        sa.Column('user_id', postgresql.UUID(as_uuid=True),
                 sa.ForeignKey('users.id', ondelete='CASCADE'),
                 nullable=False),
        sa.Column('building_id', postgresql.UUID(as_uuid=True),
                 sa.ForeignKey('buildings.id', ondelete='CASCADE'),
                 nullable=False),
        sa.Column('access_type', access_type_enum, nullable=False),
        sa.Column('verified_at', sa.TIMESTAMP(timezone=True)),
        sa.Column('verified_by', postgresql.UUID(as_uuid=True)),
        sa.Column('expires_at', sa.TIMESTAMP(timezone=True)),
        sa.Column('metadata', postgresql.JSONB, server_default='{}'),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True),
                 server_default=sa.text('now()')),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True),
                 server_default=sa.text('now()'), onupdate=sa.text('now()'))
    )

    # 3. Create indexes
    op.create_index('ix_bar_user_building', 'building_access_rights',
                   ['user_id', 'building_id'], unique=True)
    op.create_index('ix_bar_building', 'building_access_rights',
                   ['building_id'])
    op.create_index('ix_bar_user', 'building_access_rights',
                   ['user_id'])
    op.create_index('ix_bar_access_type', 'building_access_rights',
                   ['access_type'])
    op.create_index('ix_bar_expires', 'building_access_rights',
                   ['expires_at'],
                   postgresql_where='expires_at IS NOT NULL')
```

3. **Тестирование** (30 мин)
```sql
-- Test unique constraint
INSERT INTO building_access_rights (user_id, building_id, access_type)
VALUES ('uuid1', 'uuid2', 'residence');

-- Should fail
INSERT INTO building_access_rights (user_id, building_id, access_type)
VALUES ('uuid1', 'uuid2', 'manager');

-- Test CASCADE delete
DELETE FROM buildings WHERE id = 'uuid2';
SELECT * FROM building_access_rights WHERE building_id = 'uuid2';
-- Should return 0 rows

-- Test performance
EXPLAIN ANALYZE
SELECT * FROM building_access_rights WHERE user_id = 'uuid1';
-- Should use index ix_bar_user
```

**Чеклист:**
- [ ] ENUM type создан с 4 значениями
- [ ] Foreign keys с CASCADE delete
- [ ] Unique constraint на (user_id, building_id)
- [ ] 5 indexes created
- [ ] Partial index на expires_at
- [ ] metadata с default '{}'
- [ ] Тест unique constraint работает
- [ ] Тест CASCADE delete работает
- [ ] Query by user_id < 10ms (use EXPLAIN ANALYZE)
- [ ] Query by building_id < 10ms

**Критерии приемки:**
- ✅ Нельзя создать дубль (user+building)
- ✅ DELETE building каскадно удаляет access rights
- ✅ EXPLAIN ANALYZE показывает использование индексов
- ✅ 1000 INSERT operations < 1 секунда

**Риски:**
- ⚠️ Cascade delete может быть опасен
  - **Митигация**: Добавить soft delete для зданий

---

#### ✅ Task 1.3: Create SQLAlchemy Models (P0)
```yaml
Длительность: 3 часа
Исполнитель: Backend Developer
Зависимости: Task 1.1, Task 1.2
```

**Файлы:**
- `microservices/user_service/app/models/building.py` (новый)
- `microservices/user_service/app/models/__init__.py` (update)
- `microservices/user_service/app/models/user.py` (update для relationship)

**Шаги реализации:**

1. **Создать Building model** (1 час)

Полный код в файле `app/models/building.py`:

```python
"""Building and Building Access models."""
from sqlalchemy import Column, String, Numeric, Boolean, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB, TIMESTAMP, ENUM
from sqlalchemy.orm import relationship, validates
from sqlalchemy.sql import func
from typing import Optional, Dict, Any, List
import uuid
from datetime import datetime

from app.db.base_class import Base
from app.core.exceptions import ValidationError


class Building(Base):
    """Building model for centralized directory."""

    __tablename__ = "buildings"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Management company reference
    management_company_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    # External integrations
    external_code = Column(String(50), unique=True, index=True)

    # Address components (normalized)
    city = Column(String(100), nullable=False, index=True)
    district = Column(String(100))
    street = Column(String(200), nullable=False, index=True)
    house_number = Column(String(20), nullable=False)
    postcode = Column(String(12))

    # Geographic data
    latitude = Column(Numeric(10, 8))  # e.g., 41.31115100
    longitude = Column(Numeric(11, 8))  # e.g., 69.27973700
    geo_boundary = Column(JSONB)  # GeoJSON Polygon/MultiPolygon

    # Building details
    entrances = Column(JSONB, server_default='[]')  # List of entrance info
    metadata = Column(JSONB, server_default='{}')   # Flexible additional data

    # Status
    is_active = Column(Boolean, default=True, nullable=False)

    # Timestamps
    created_at = Column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    updated_at = Column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )

    # Relationships
    access_rights = relationship(
        "BuildingAccessRight",
        back_populates="building",
        cascade="all, delete-orphan",
        lazy="dynamic"  # For large datasets
    )

    # Indexes (additional to column indexes)
    __table_args__ = (
        Index('ix_buildings_mc_active', 'management_company_id', 'is_active'),
        Index('ix_buildings_metadata', 'metadata', postgresql_using='gin'),
        # Spatial index created in migration
    )

    # Properties
    @property
    def full_address(self) -> str:
        """
        Generate formatted full address string.

        Returns:
            str: Formatted address like "Ташкент, Навои, 12"
        """
        parts = [self.city]
        if self.district:
            parts.append(self.district)
        parts.extend([self.street, self.house_number])
        return ", ".join(parts)

    @property
    def coordinates(self) -> Optional[tuple[float, float]]:
        """
        Get coordinates as tuple.

        Returns:
            tuple[float, float] | None: (latitude, longitude) or None
        """
        if self.latitude is not None and self.longitude is not None:
            return (float(self.latitude), float(self.longitude))
        return None

    @property
    def has_coordinates(self) -> bool:
        """Check if building has valid coordinates."""
        return self.latitude is not None and self.longitude is not None

    @property
    def entrance_count(self) -> int:
        """Get number of entrances."""
        if isinstance(self.entrances, list):
            return len(self.entrances)
        return 0

    # Validation
    @validates('latitude')
    def validate_latitude(self, key, value):
        """Validate latitude is in valid range."""
        if value is not None:
            if not (-90 <= float(value) <= 90):
                raise ValidationError(f"Latitude must be between -90 and 90, got {value}")
        return value

    @validates('longitude')
    def validate_longitude(self, key, value):
        """Validate longitude is in valid range."""
        if value is not None:
            if not (-180 <= float(value) <= 180):
                raise ValidationError(f"Longitude must be between -180 and 180, got {value}")
        return value

    @validates('house_number')
    def validate_house_number(self, key, value):
        """Validate and normalize house number."""
        if value:
            import re
            # Allow formats: "12", "12А", "12/1", "12 корп. 1"
            if not re.match(r'^[\d]+[А-Яа-яA-Za-z\s/.-]*$', value):
                raise ValidationError(f"Invalid house number format: {value}")
            return value.strip()
        return value

    def __repr__(self):
        return f"<Building {self.id}: {self.full_address}>"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": str(self.id),
            "management_company_id": str(self.management_company_id),
            "external_code": self.external_code,
            "city": self.city,
            "district": self.district,
            "street": self.street,
            "house_number": self.house_number,
            "postcode": self.postcode,
            "latitude": float(self.latitude) if self.latitude else None,
            "longitude": float(self.longitude) if self.longitude else None,
            "geo_boundary": self.geo_boundary,
            "entrances": self.entrances,
            "metadata": self.metadata,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "full_address": self.full_address,
            "coordinates": self.coordinates,
        }


class BuildingAccessRight(Base):
    """User access rights to buildings."""

    __tablename__ = "building_access_rights"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Foreign keys
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    building_id = Column(
        UUID(as_uuid=True),
        ForeignKey('buildings.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )

    # Access type
    access_type = Column(
        ENUM('residence', 'manager', 'service', 'temporary',
             name='building_access_type'),
        nullable=False,
        index=True
    )

    # Verification
    verified_at = Column(TIMESTAMP(timezone=True))
    verified_by = Column(UUID(as_uuid=True))  # Admin who verified

    # Expiration for temporary access
    expires_at = Column(TIMESTAMP(timezone=True))

    # Additional metadata
    metadata = Column(JSONB, server_default='{}')

    # Timestamps
    created_at = Column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    updated_at = Column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )

    # Relationships
    building = relationship("Building", back_populates="access_rights")
    user = relationship("User", back_populates="building_access")

    # Constraints
    __table_args__ = (
        Index('ix_bar_user_building', 'user_id', 'building_id', unique=True),
        Index('ix_bar_expires', 'expires_at',
              postgresql_where='expires_at IS NOT NULL'),
    )

    # Properties
    @property
    def is_expired(self) -> bool:
        """Check if access has expired."""
        if self.expires_at is None:
            return False
        return datetime.utcnow() > self.expires_at

    @property
    def is_verified(self) -> bool:
        """Check if access is verified."""
        return self.verified_at is not None

    def __repr__(self):
        return f"<BuildingAccessRight {self.id}: User {self.user_id} -> Building {self.building_id} ({self.access_type})>"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "building_id": str(self.building_id),
            "access_type": self.access_type,
            "verified_at": self.verified_at.isoformat() if self.verified_at else None,
            "verified_by": str(self.verified_by) if self.verified_by else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "is_expired": self.is_expired,
            "is_verified": self.is_verified,
        }
```

2. **Update User model** (30 мин)

В `app/models/user.py`:
```python
class User(Base):
    # ... existing fields ...

    # Add relationship
    building_access = relationship(
        "BuildingAccessRight",
        back_populates="user",
        lazy="dynamic"
    )
```

3. **Update __init__.py** (15 мин)

В `app/models/__init__.py`:
```python
from app.models.user import User
from app.models.building import Building, BuildingAccessRight  # NEW

__all__ = ["User", "Building", "BuildingAccessRight"]
```

4. **Написать unit tests** (1 час 15 мин)

В `tests/unit/models/test_building.py`:

```python
import pytest
from uuid import uuid4
from app.models.building import Building, BuildingAccessRight
from app.core.exceptions import ValidationError


class TestBuildingModel:
    def test_create_building(self, db_session):
        """Test building creation."""
        building = Building(
            management_company_id=uuid4(),
            city="Ташкент",
            street="Навои",
            house_number="12",
            latitude=41.311151,
            longitude=69.279737
        )
        db_session.add(building)
        db_session.commit()

        assert building.id is not None
        assert building.full_address == "Ташкент, Навои, 12"
        assert building.coordinates == (41.311151, 69.279737)

    def test_full_address_with_district(self, db_session):
        """Test full address with district."""
        building = Building(
            management_company_id=uuid4(),
            city="Ташкент",
            district="Юнусабадский",
            street="Навои",
            house_number="12А"
        )

        assert building.full_address == "Ташкент, Юнусабадский, Навои, 12А"

    def test_invalid_latitude(self, db_session):
        """Test latitude validation."""
        with pytest.raises(ValidationError):
            building = Building(
                management_company_id=uuid4(),
                city="Ташкент",
                street="Навои",
                house_number="12",
                latitude=100  # Invalid
            )
            db_session.add(building)
            db_session.commit()

    def test_invalid_house_number(self, db_session):
        """Test house number validation."""
        with pytest.raises(ValidationError):
            building = Building(
                management_company_id=uuid4(),
                city="Ташкент",
                street="Навои",
                house_number="invalid!"  # Invalid characters
            )
            db_session.add(building)
            db_session.commit()

    def test_relationship_cascade_delete(self, db_session):
        """Test cascade delete of access rights."""
        building = Building(
            management_company_id=uuid4(),
            city="Ташкент",
            street="Навои",
            house_number="12"
        )
        db_session.add(building)
        db_session.commit()

        # Create access right
        access = BuildingAccessRight(
            user_id=uuid4(),
            building_id=building.id,
            access_type="residence"
        )
        db_session.add(access)
        db_session.commit()

        access_id = access.id

        # Delete building
        db_session.delete(building)
        db_session.commit()

        # Access right should be deleted
        assert db_session.query(BuildingAccessRight).filter_by(id=access_id).first() is None


class TestBuildingAccessRight:
    def test_create_access_right(self, db_session, sample_building, sample_user):
        """Test access right creation."""
        access = BuildingAccessRight(
            user_id=sample_user.id,
            building_id=sample_building.id,
            access_type="residence"
        )
        db_session.add(access)
        db_session.commit()

        assert access.id is not None
        assert not access.is_expired
        assert not access.is_verified

    def test_unique_constraint(self, db_session, sample_building, sample_user):
        """Test unique constraint on (user_id, building_id)."""
        access1 = BuildingAccessRight(
            user_id=sample_user.id,
            building_id=sample_building.id,
            access_type="residence"
        )
        db_session.add(access1)
        db_session.commit()

        # Try to create duplicate
        access2 = BuildingAccessRight(
            user_id=sample_user.id,
            building_id=sample_building.id,
            access_type="manager"  # Different type, same user+building
        )
        db_session.add(access2)

        with pytest.raises(Exception):  # IntegrityError
            db_session.commit()
```

**Чеклист:**
- [ ] Building model создан с всеми полями
- [ ] BuildingAccessRight model создан
- [ ] Relationships настроены (bidirectional)
- [ ] Properties реализованы (full_address, coordinates, etc.)
- [ ] Validators для latitude, longitude, house_number
- [ ] CASCADE delete в relationships
- [ ] Type hints на все методы
- [ ] Docstrings для всех публичных методов
- [ ] to_dict() методы для сериализации
- [ ] __repr__() для удобной отладки
- [ ] User model updated с relationship
- [ ] __init__.py updated
- [ ] Unit tests написаны (12+ tests)
- [ ] All tests pass
- [ ] Coverage > 90%
- [ ] Type checking проходит (mypy)

**Критерии приемки:**
- ✅ Models импортируются без ошибок
- ✅ Relationships работают в обе стороны
- ✅ Properties возвращают правильные значения
- ✅ Validators отклоняют невалидные данные
- ✅ CASCADE delete работает
- ✅ pytest покрытие > 90%
- ✅ mypy не находит ошибок типов

**Риски:**
- ⚠️ Validators могут быть медленными
  - **Митигация**: Использовать @validates только для критичных полей
- ⚠️ Lazy loading может привести к N+1
  - **Митигация**: Использовать lazy="dynamic" и joinedload где нужно

---

### 📅 DAY 2: Pydantic Schemas & Service Layer (8 часов)

#### ✅ Task 2.1: Create Pydantic Schemas (P0)
```yaml
Длительность: 4 часа
Исполнитель: Backend Developer
Зависимости: Task 1.3
```

**Файлы:**
- `microservices/user_service/app/schemas/building.py` (новый)
- `microservices/user_service/app/schemas/__init__.py` (update)

**Шаги реализации** (см. полный код в базовом плане)

**Чеклист:**
- [ ] BuildingBase schema
- [ ] BuildingCreate schema
- [ ] BuildingUpdate schema (все поля optional)
- [ ] BuildingResponse schema
- [ ] BuildingListItem (lightweight)
- [ ] BuildingAccessRight schemas (Base, Create, Update, Response)
- [ ] Validators для всех критичных полей
- [ ] Type hints и Field constraints
- [ ] Enum для access_type
- [ ] Nested schemas (EntranceSchema, CoordinatesSchema)
- [ ] from_attributes = True для ORM compatibility
- [ ] Unit tests для validation (20+ tests)
- [ ] Coverage > 85%

**Критерии приемки:**
- ✅ Валидация отклоняет невалидные данные
- ✅ GeoJSON validation работает
- ✅ House number regex покрывает все форматы
- ✅ Serialization/deserialization без ошибок
- ✅ pytest coverage > 85%

---

#### ✅ Task 2.2: Create Building Service Layer (P0)
```yaml
Длительность: 4 часа
Исполнитель: Backend Developer
Зависимости: Task 2.1
```

**Файлы:**
- `microservices/user_service/app/services/building_service.py` (новый)
- `microservices/user_service/app/services/__init__.py` (update)

**Реализация:**

См. полный код BuildingService в базовом плане. Ключевые методы:

```python
class BuildingService:
    async def create_building(...) -> Building
    async def get_building(...) -> Building
    async def list_buildings(...) -> tuple[List[Building], int]
    async def update_building(...) -> Building
    async def delete_building(...) -> None
    async def grant_access(...) -> BuildingAccessRight
    async def revoke_access(...) -> None
    async def get_user_buildings(...) -> List[Building]
    async def search_buildings_by_address(...) -> List[Building]
```

**Чеклист:**
- [ ] CRUD operations (Create, Read, Update, Delete)
- [ ] Tenant isolation (management_company_id filtering)
- [ ] Duplicate check при создании
- [ ] Search functionality (street, house_number, district)
- [ ] Pagination support (limit, offset)
- [ ] Access rights management (grant, revoke, list)
- [ ] Soft delete vs hard delete
- [ ] Error handling (NotFoundError, ValidationError)
- [ ] Async/await корректно
- [ ] Database transactions
- [ ] Query optimization (eager loading где нужно)
- [ ] Unit tests coverage > 85%
- [ ] Integration tests

**Критерии приемки:**
- ✅ Все CRUD operations работают
- ✅ Поиск находит здания по всем полям
- ✅ Pagination возвращает правильное количество + total
- ✅ Tenant isolation предотвращает доступ к чужим зданиям
- ✅ Query performance < 50ms для simple queries
- ✅ pytest coverage > 85%

---

### 📅 DAY 3-4: REST API & Caching (16 часов)

#### ✅ Task 3.1: Create REST API Endpoints (P0)
```yaml
Длительность: 6 часов
Исполнитель: Backend Developer
Зависимости: Task 2.2
```

**Файлы:**
- `microservices/user_service/app/api/v1/buildings.py` (новый)
- `microservices/user_service/app/api/v1/__init__.py` (update)
- `microservices/user_service/app/main.py` (update router)

**Endpoints:**

```yaml
Buildings:
  POST   /api/v1/buildings/                    # Create building (admin)
  GET    /api/v1/buildings/                    # List buildings (paginated)
  GET    /api/v1/buildings/{id}                # Get building details
  PUT    /api/v1/buildings/{id}                # Update building (admin)
  DELETE /api/v1/buildings/{id}                # Delete building (admin)
  POST   /api/v1/buildings/{id}/sync-geocode   # Trigger geocoding (admin)

Access Rights:
  GET    /api/v1/buildings/{id}/access         # List access rights (admin)
  POST   /api/v1/buildings/{id}/access         # Grant access (admin)
  DELETE /api/v1/buildings/{id}/access/{user_id}  # Revoke access (admin)

User Buildings:
  GET    /api/v1/users/me/buildings            # Get my buildings
  GET    /api/v1/users/{id}/buildings          # Get user buildings (admin)
```

**Чеклист:**
- [ ] 10 endpoints реализованы
- [ ] OpenAPI/Swagger documentation
- [ ] Request/response validation (Pydantic)
- [ ] Authorization checks (admin vs user)
- [ ] Pagination query params
- [ ] Search/filter query params
- [ ] Error handling (422, 404, 403, 500)
- [ ] HTTP status codes правильные
- [ ] Response models соответствуют schemas
- [ ] Integration tests (30+ tests)
- [ ] Coverage > 90%

**Критерии приемки:**
- ✅ Swagger UI доступен на /docs
- ✅ Все endpoints возвращают правильные коды
- ✅ Валидация работает (тесты на invalid data)
- ✅ Authorization предотвращает неавторизованный доступ
- ✅ API response time < 100ms (p95)

---

#### ✅ Task 3.2: Redis Caching Implementation (P1)
```yaml
Длительность: 4 часа
Исполнитель: Backend Developer
Зависимости: Task 3.1
```

**Файлы:**
- `microservices/user_service/app/services/cache_service.py` (новый)
- `microservices/user_service/app/core/cache.py` (update)
- `microservices/user_service/app/core/deps.py` (add get_cache)

**Реализация:**

```python
class BuildingCacheService:
    def __init__(self, redis: Redis):
        self.redis = redis
        self.ttl_list = 300  # 5 minutes
        self.ttl_detail = 3600  # 1 hour

    async def get_buildings_list(mc_id: UUID) -> Optional[List[dict]]
    async def set_buildings_list(mc_id: UUID, buildings: List) -> None
    async def get_building_detail(building_id: UUID) -> Optional[dict]
    async def set_building_detail(building_id: UUID, building: dict) -> None
    async def invalidate_building(building_id, mc_id) -> None
    async def invalidate_company(mc_id) -> None
```

**Cache Keys Strategy:**
```
buildings:{mc_id}                    # List cache
building:{id}                         # Detail cache
building:search:{mc_id}:{hash}       # Search results cache
```

**Invalidation Strategy:**
- CREATE building → invalidate `buildings:{mc_id}`
- UPDATE building → invalidate `building:{id}` + `buildings:{mc_id}`
- DELETE building → invalidate `building:{id}` + `buildings:{mc_id}`
- Access grant/revoke → invalidate `building:{id}`

**Чеклист:**
- [ ] Redis connection pool настроен
- [ ] TTL для разных типов (list=5min, detail=1hour)
- [ ] Cache key naming convention
- [ ] Get/Set methods для lists и details
- [ ] Invalidation methods
- [ ] Pub/Sub для distributed invalidation
- [ ] Error handling (fallback to DB on Redis failure)
- [ ] Cache hit/miss metrics (Prometheus)
- [ ] Unit tests > 80%
- [ ] Integration tests

**Критерии приемки:**
- ✅ Cache hit rate > 90% для списков
- ✅ Invalidation работает < 10ms
- ✅ Graceful degradation при Redis down
- ✅ Response time < 10ms для cache hits
- ✅ Metrics exported to Prometheus

---

#### ✅ Task 3.3: Event Publishing (P1)
```yaml
Длительность: 3 часа
Исполнитель: Backend Developer
Зависимости: Task 3.1
```

**События:**
```yaml
building.created:
  payload:
    building_id: UUID
    management_company_id: UUID
    user_id: UUID  # who created
    timestamp: datetime

building.updated:
  payload:
    building_id: UUID
    management_company_id: UUID
    changes: dict  # what changed
    user_id: UUID
    timestamp: datetime

building.deleted:
  payload:
    building_id: UUID
    management_company_id: UUID
    user_id: UUID
    timestamp: datetime

building.access_granted:
  payload:
    building_id: UUID
    user_id: UUID
    access_type: str
    granted_by: UUID
    timestamp: datetime

building.access_revoked:
  payload:
    building_id: UUID
    user_id: UUID
    revoked_by: UUID
    timestamp: datetime
```

**Чеклист:**
- [ ] Event schemas (Pydantic)
- [ ] EventPublisher class
- [ ] Redis Pub/Sub integration
- [ ] Redis Streams для replay
- [ ] Event publishing в BuildingService
- [ ] Event validation
- [ ] Error handling
- [ ] Metrics (events published count)
- [ ] Integration tests
- [ ] Monitoring alerts

**Критерии приемки:**
- ✅ Events публикуются < 5ms после операции
- ✅ Event delivery rate > 99.9%
- ✅ Stream retention 10k events
- ✅ Subscribers получают события

---

#### ✅ Task 3.4: Integration Tests (P0)
```yaml
Длительность: 3 часа
Исполнитель: QA Engineer
Зависимости: Task 3.1, 3.2, 3.3
```

**Test Cases (35+ tests):**

1. **CRUD Tests** (10 tests)
   - Create building success
   - Create duplicate fails
   - Get building by ID
   - List buildings with pagination
   - Update building
   - Delete building (soft/hard)

2. **Search Tests** (5 tests)
   - Search by street
   - Search by house number
   - Search by city
   - Search no results
   - Search with pagination

3. **Authorization Tests** (8 tests)
   - Unauthorized access blocked
   - Admin can create
   - User cannot create
   - User can read own buildings
   - User cannot read other company buildings
   - Admin can manage access rights

4. **Cache Tests** (6 tests)
   - Cache miss → DB query
   - Cache hit → no DB query
   - Invalidation on create
   - Invalidation on update
   - Invalidation on delete
   - Cache TTL expiration

5. **Event Tests** (6 tests)
   - Event published on create
   - Event published on update
   - Event published on delete
   - Event payload correct
   - Subscribers receive events

**Чеклист:**
- [ ] 35+ test cases
- [ ] Positive scenarios
- [ ] Negative scenarios
- [ ] Edge cases
- [ ] Performance tests
- [ ] All tests pass
- [ ] Coverage > 90%
- [ ] Tests run < 30 seconds
- [ ] No flaky tests

**Критерии приемки:**
- ✅ pytest success 100%
- ✅ Coverage report > 90%
- ✅ Performance baseline established
- ✅ CI/CD integration ready

---

### 📅 DAY 5: API Documentation & Week 1 Review (8 часов)

#### ✅ Task 4.1: OpenAPI Documentation (P1)
```yaml
Длительность: 3 часа
Исполнитель: Backend Developer
Зависимости: Task 3.1
```

**Deliverables:**
- Swagger UI на `/docs`
- ReDoc на `/redoc`
- OpenAPI JSON на `/openapi.json`
- API Reference документация (Markdown)

**Чеклист:**
- [ ] Все endpoints documented
- [ ] Request/response examples
- [ ] Error response examples
- [ ] Authentication описана
- [ ] Query parameters documented
- [ ] Tags и descriptions
- [ ] Markdown API reference

---

#### ✅ Task 4.2: Week 1 Review & Testing (P0)
```yaml
Длительность: 5 часов
Исполнитель: Team
Зависимости: All Week 1 tasks
```

**Чеклист:**
- [ ] All migrations applied
- [ ] All tests passing
- [ ] API functional
- [ ] Cache working
- [ ] Events publishing
- [ ] Documentation complete
- [ ] Code review done
- [ ] Performance benchmarks met
- [ ] Security review passed
- [ ] Ready for Week 2

**Week 1 Acceptance Criteria:**
- ✅ Database schema created
- ✅ Core API working (10 endpoints)
- ✅ Unit tests > 85% coverage
- ✅ Integration tests > 90% coverage
- ✅ API docs complete
- ✅ Caching working (>90% hit rate)
- ✅ Events publishing
- ✅ Performance: API response < 100ms (p95)

---

## 🗓️ WEEK 2: BOT INTEGRATION (40 часов)

*Детальные задачи для Week 2 будут аналогично структурированы с FSM states, keyboards, handlers, и тестами.*

---

## 🗓️ WEEK 3: SERVICES INTEGRATION & MIGRATION (40 часов)

*Интеграция с request-service, analytics-service, и миграция данных.*

---

## 🗓️ WEEK 4: PRODUCTION READINESS (40 часов)

*Performance tuning, security audit, documentation, training, deployment.*

---

## 📊 TRACKING & METRICS

### Daily Metrics
```yaml
Development Velocity:
  - Tasks completed per day
  - Story points burned
  - Code commits count
  - Pull requests merged

Quality Metrics:
  - Test coverage %
  - Bugs found/fixed ratio
  - Code review feedback
  - Technical debt items

Performance Metrics:
  - API response time (p50, p95, p99)
  - Database query performance
  - Cache hit rate
  - Error rate
```

### Weekly Review Checklist
```yaml
Week 1:
  - [ ] Database migrations complete
  - [ ] Core API functional
  - [ ] Tests passing (>85% coverage)
  - [ ] Documentation up to date

Week 2:
  - [ ] Bot integration complete
  - [ ] User verification working
  - [ ] E2E tests passing

Week 3:
  - [ ] All services integrated
  - [ ] Data migration complete
  - [ ] Analytics updated

Week 4:
  - [ ] Production deployment ready
  - [ ] Performance benchmarks met
  - [ ] Security audit passed
  - [ ] Team trained
```

---

**Документ готов к использованию для детального планирования спринта.**
