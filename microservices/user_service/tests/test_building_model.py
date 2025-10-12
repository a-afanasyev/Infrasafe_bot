"""Unit Tests for Building Model.

Task 3.1: Create Unit Tests for Building Models and Service (P0)
Week 1, Day 3 - Building Directory Implementation
"""

import pytest
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from models.building import Building


class TestBuildingModel:
    """Tests for Building SQLAlchemy model."""

    def test_building_creation_minimal(self):
        """Test creating building with minimal required fields."""
        mc_id = uuid4()
        building = Building(
            management_company_id=mc_id,
            city="Tashkent",
            street="Amir Temur",
            house_number="42"
        )

        assert building.management_company_id == mc_id
        assert building.city == "Tashkent"
        assert building.street == "Amir Temur"
        assert building.house_number == "42"
        assert building.is_active is True
        assert building.latitude is None
        assert building.longitude is None

    def test_building_creation_full(self):
        """Test creating building with all fields."""
        mc_id = uuid4()
        user_id = uuid4()

        building = Building(
            management_company_id=mc_id,
            city="Tashkent",
            street="Amir Temur",
            house_number="42",
            district="Yunusabad",
            building_corpus="A",
            postal_code="100000",
            building_type="residential",
            floors_count=9,
            entrance_count=3,
            apartments_count=72,
            year_built=2015,
            notes="Test building",
            extra_data={"color": "red", "has_elevator": True},
            created_by=user_id
        )

        assert building.district == "Yunusabad"
        assert building.building_corpus == "A"
        assert building.postal_code == "100000"
        assert building.building_type == "residential"
        assert building.floors_count == 9
        assert building.entrance_count == 3
        assert building.apartments_count == 72
        assert building.year_built == 2015
        assert building.notes == "Test building"
        assert building.extra_data == {"color": "red", "has_elevator": True}
        assert building.created_by == user_id

    def test_full_address_property(self):
        """Test full_address computed property."""
        building = Building(
            management_company_id=uuid4(),
            city="Tashkent",
            street="Amir Temur",
            house_number="42"
        )

        assert building.full_address == "Tashkent, Amir Temur, 42"

    def test_full_address_with_district(self):
        """Test full_address with district included."""
        building = Building(
            management_company_id=uuid4(),
            city="Tashkent",
            street="Amir Temur",
            house_number="42",
            district="Yunusabad"
        )

        assert building.full_address == "Tashkent, Yunusabad, Amir Temur, 42"

    def test_full_address_with_corpus(self):
        """Test full_address with building corpus."""
        building = Building(
            management_company_id=uuid4(),
            city="Tashkent",
            street="Amir Temur",
            house_number="42",
            building_corpus="A"
        )

        assert building.full_address == "Tashkent, Amir Temur, 42, корп. A"

    def test_short_address_property(self):
        """Test short_address computed property."""
        building = Building(
            management_company_id=uuid4(),
            city="Tashkent",
            street="Amir Temur",
            house_number="42"
        )

        assert building.short_address == "Amir Temur, 42"

    def test_short_address_with_corpus(self):
        """Test short_address with building corpus."""
        building = Building(
            management_company_id=uuid4(),
            city="Tashkent",
            street="Amir Temur",
            house_number="42",
            building_corpus="B"
        )

        assert building.short_address == "Amir Temur, 42, корп. B"

    def test_has_coordinates_property(self):
        """Test has_coordinates computed property."""
        building = Building(
            management_company_id=uuid4(),
            city="Tashkent",
            street="Amir Temur",
            house_number="42"
        )

        assert building.has_coordinates is False

        building.latitude = Decimal("41.311158")
        building.longitude = Decimal("69.279737")

        assert building.has_coordinates is True

    def test_coordinates_property(self):
        """Test coordinates computed property."""
        building = Building(
            management_company_id=uuid4(),
            city="Tashkent",
            street="Amir Temur",
            house_number="42"
        )

        assert building.coordinates is None

        building.latitude = Decimal("41.311158")
        building.longitude = Decimal("69.279737")

        coords = building.coordinates
        assert coords is not None
        assert coords['lat'] == pytest.approx(41.311158, rel=1e-6)
        assert coords['lon'] == pytest.approx(69.279737, rel=1e-6)

    def test_set_coordinates_method(self):
        """Test set_coordinates method."""
        building = Building(
            management_company_id=uuid4(),
            city="Tashkent",
            street="Amir Temur",
            house_number="42"
        )

        building.set_coordinates(
            latitude=41.311158,
            longitude=69.279737,
            source='google_maps'
        )

        assert building.latitude == Decimal('41.311158')
        assert building.longitude == Decimal('69.279737')
        assert building.coordinates_source == 'google_maps'
        assert building.geocoded_at is not None
        assert isinstance(building.geocoded_at, datetime)

    def test_validate_latitude_valid(self):
        """Test latitude validation accepts valid values."""
        building = Building(
            management_company_id=uuid4(),
            city="Tashkent",
            street="Amir Temur",
            house_number="42"
        )

        # Valid latitudes
        building.latitude = Decimal("-90")  # Min
        building.latitude = Decimal("0")    # Equator
        building.latitude = Decimal("90")   # Max
        building.latitude = Decimal("41.311158")  # Tashkent

    def test_validate_latitude_invalid(self):
        """Test latitude validation rejects invalid values."""
        building = Building(
            management_company_id=uuid4(),
            city="Tashkent",
            street="Amir Temur",
            house_number="42"
        )

        with pytest.raises(ValueError, match="between -90 and 90"):
            building.latitude = Decimal("91")

        with pytest.raises(ValueError, match="between -90 and 90"):
            building.latitude = Decimal("-91")

    def test_validate_longitude_valid(self):
        """Test longitude validation accepts valid values."""
        building = Building(
            management_company_id=uuid4(),
            city="Tashkent",
            street="Amir Temur",
            house_number="42"
        )

        # Valid longitudes
        building.longitude = Decimal("-180")  # Min
        building.longitude = Decimal("0")     # Prime meridian
        building.longitude = Decimal("180")   # Max
        building.longitude = Decimal("69.279737")  # Tashkent

    def test_validate_longitude_invalid(self):
        """Test longitude validation rejects invalid values."""
        building = Building(
            management_company_id=uuid4(),
            city="Tashkent",
            street="Amir Temur",
            house_number="42"
        )

        with pytest.raises(ValueError, match="between -180 and 180"):
            building.longitude = Decimal("181")

        with pytest.raises(ValueError, match="between -180 and 180"):
            building.longitude = Decimal("-181")

    def test_validate_required_address_empty(self):
        """Test required address fields cannot be empty."""
        building = Building(
            management_company_id=uuid4(),
            city="Tashkent",
            street="Amir Temur",
            house_number="42"
        )

        with pytest.raises(ValueError, match="cannot be empty"):
            building.city = ""

        with pytest.raises(ValueError, match="cannot be empty"):
            building.street = "   "

        with pytest.raises(ValueError, match="cannot be empty"):
            building.house_number = ""

    def test_validate_building_type(self):
        """Test building_type validation."""
        building = Building(
            management_company_id=uuid4(),
            city="Tashkent",
            street="Amir Temur",
            house_number="42"
        )

        # Valid types
        building.building_type = "residential"
        building.building_type = "commercial"
        building.building_type = "mixed"
        building.building_type = "industrial"
        building.building_type = "other"

        # Invalid type
        with pytest.raises(ValueError, match="must be one of"):
            building.building_type = "invalid_type"

    def test_validate_coordinates_source(self):
        """Test coordinates_source validation."""
        building = Building(
            management_company_id=uuid4(),
            city="Tashkent",
            street="Amir Temur",
            house_number="42"
        )

        # Valid sources
        building.coordinates_source = "google_maps"
        building.coordinates_source = "yandex_maps"
        building.coordinates_source = "manual"
        building.coordinates_source = "2gis"
        building.coordinates_source = "osm"

        # Invalid source
        with pytest.raises(ValueError, match="must be one of"):
            building.coordinates_source = "invalid_source"

    def test_soft_delete(self):
        """Test soft_delete method."""
        building = Building(
            management_company_id=uuid4(),
            city="Tashkent",
            street="Amir Temur",
            house_number="42"
        )

        assert building.is_active is True
        assert building.deleted_at is None

        building.soft_delete()

        assert building.is_active is False
        assert building.deleted_at is not None
        assert isinstance(building.deleted_at, datetime)

    def test_restore(self):
        """Test restore method."""
        building = Building(
            management_company_id=uuid4(),
            city="Tashkent",
            street="Amir Temur",
            house_number="42"
        )

        building.soft_delete()
        assert building.is_active is False

        building.restore()
        assert building.is_active is True
        assert building.deleted_at is None

    def test_to_dict(self):
        """Test to_dict method."""
        mc_id = uuid4()
        building = Building(
            id=uuid4(),
            management_company_id=mc_id,
            city="Tashkent",
            street="Amir Temur",
            house_number="42",
            district="Yunusabad",
            building_type="residential"
        )
        building.set_coordinates(41.311158, 69.279737, 'google_maps')

        data = building.to_dict()

        assert data['city'] == "Tashkent"
        assert data['street'] == "Amir Temur"
        assert data['house_number'] == "42"
        assert data['district'] == "Yunusabad"
        assert data['building_type'] == "residential"
        assert data['full_address'] == "Tashkent, Yunusabad, Amir Temur, 42"
        assert data['short_address'] == "Amir Temur, 42"
        assert data['coordinates'] is not None
        assert data['coordinates']['lat'] == pytest.approx(41.311158, rel=1e-6)
        assert data['coordinates']['lon'] == pytest.approx(69.279737, rel=1e-6)
        assert data['coordinates_source'] == 'google_maps'
        assert data['is_active'] is True

    def test_repr(self):
        """Test __repr__ method."""
        building_id = uuid4()
        mc_id = uuid4()

        building = Building(
            id=building_id,
            management_company_id=mc_id,
            city="Tashkent",
            street="Amir Temur",
            house_number="42"
        )

        repr_str = repr(building)
        assert "Building" in repr_str
        assert str(building_id) in repr_str
        assert "Tashkent, Amir Temur, 42" in repr_str
        assert str(mc_id) in repr_str

    def test_str(self):
        """Test __str__ method."""
        building = Building(
            management_company_id=uuid4(),
            city="Tashkent",
            street="Amir Temur",
            house_number="42",
            district="Yunusabad"
        )

        str_repr = str(building)
        assert str_repr == "Tashkent, Yunusabad, Amir Temur, 42"
