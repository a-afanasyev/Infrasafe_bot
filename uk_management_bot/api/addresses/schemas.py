from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


# --- Yard ---
class YardOut(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    gps_latitude: Optional[float] = None
    gps_longitude: Optional[float] = None
    is_active: bool
    created_at: Optional[datetime] = None
    buildings_count: int = 0
    model_config = {"from_attributes": True}


class YardCreate(BaseModel):
    name: str = Field(..., min_length=3, max_length=200)
    description: Optional[str] = None
    gps_latitude: Optional[float] = Field(None, ge=-90, le=90)
    gps_longitude: Optional[float] = Field(None, ge=-180, le=180)


class YardUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=3, max_length=200)
    description: Optional[str] = None
    gps_latitude: Optional[float] = Field(None, ge=-90, le=90)
    gps_longitude: Optional[float] = Field(None, ge=-180, le=180)
    is_active: Optional[bool] = None


# --- Building ---
class BuildingOut(BaseModel):
    id: int
    address: str
    yard_id: int
    yard_name: Optional[str] = None
    entrance_count: int
    floor_count: int
    description: Optional[str] = None
    gps_latitude: Optional[float] = None
    gps_longitude: Optional[float] = None
    is_active: bool
    created_at: Optional[datetime] = None
    apartments_count: int = 0
    model_config = {"from_attributes": True}


class BuildingCreate(BaseModel):
    address: str = Field(..., min_length=5, max_length=300)
    yard_id: int
    entrance_count: int = Field(1, ge=1, le=50)
    floor_count: int = Field(1, ge=1, le=100)
    description: Optional[str] = None
    gps_latitude: Optional[float] = Field(None, ge=-90, le=90)
    gps_longitude: Optional[float] = Field(None, ge=-180, le=180)


class BuildingUpdate(BaseModel):
    address: Optional[str] = Field(None, min_length=5, max_length=300)
    yard_id: Optional[int] = None
    entrance_count: Optional[int] = Field(None, ge=1, le=50)
    floor_count: Optional[int] = Field(None, ge=1, le=100)
    description: Optional[str] = None
    gps_latitude: Optional[float] = Field(None, ge=-90, le=90)
    gps_longitude: Optional[float] = Field(None, ge=-180, le=180)
    is_active: Optional[bool] = None


# --- Apartment ---
class ApartmentOut(BaseModel):
    id: int
    building_id: int
    apartment_number: str
    building_address: Optional[str] = None
    yard_name: Optional[str] = None
    entrance: Optional[int] = None
    floor: Optional[int] = None
    rooms_count: Optional[int] = None
    area: Optional[float] = None
    description: Optional[str] = None
    is_active: bool
    created_at: Optional[datetime] = None
    residents_count: int = 0
    model_config = {"from_attributes": True}


class ApartmentCreate(BaseModel):
    building_id: int
    apartment_number: str = Field(..., min_length=1, max_length=20)
    entrance: Optional[int] = Field(None, ge=1, le=50)
    floor: Optional[int] = Field(None, ge=1, le=100)
    rooms_count: Optional[int] = Field(None, ge=1, le=20)
    area: Optional[float] = Field(None, gt=0, le=1000)
    description: Optional[str] = None


class ApartmentUpdate(BaseModel):
    apartment_number: Optional[str] = Field(None, min_length=1, max_length=20)
    entrance: Optional[int] = Field(None, ge=1, le=50)
    floor: Optional[int] = Field(None, ge=1, le=100)
    rooms_count: Optional[int] = Field(None, ge=1, le=20)
    area: Optional[float] = Field(None, gt=0, le=1000)
    description: Optional[str] = None
    is_active: Optional[bool] = None


class ResidentOut(BaseModel):
    id: int                          # UserApartment.id
    user_id: int
    user_name: Optional[str] = None  # User.first_name + last_name
    user_phone: Optional[str] = None  # User.phone
    username: Optional[str] = None   # User.username
    is_owner: bool
    is_primary: bool
    status: str                      # pending/approved/rejected
    requested_at: Optional[datetime] = None
    reviewed_at: Optional[datetime] = None
    model_config = {"from_attributes": True}


class ApartmentDetailOut(BaseModel):
    id: int
    building_id: int
    apartment_number: str
    building_address: Optional[str] = None
    yard_name: Optional[str] = None
    entrance: Optional[int] = None
    floor: Optional[int] = None
    rooms_count: Optional[int] = None
    area: Optional[float] = None
    description: Optional[str] = None
    is_active: bool
    created_at: Optional[datetime] = None
    residents: list[ResidentOut] = []
    model_config = {"from_attributes": True}


class BulkCreateApartments(BaseModel):
    building_id: int
    apartment_numbers: List[str] = Field(..., min_length=1, max_length=500)


class BulkCreateResult(BaseModel):
    created: int
    skipped: int
    errors: List[str]


# --- Moderation ---
class ModerationItemOut(BaseModel):
    id: int
    user_id: int
    user_name: Optional[str] = None
    user_phone: Optional[str] = None
    apartment_id: int
    apartment_number: str
    building_address: Optional[str] = None
    yard_name: Optional[str] = None
    status: str
    is_owner: bool
    is_primary: bool
    requested_at: Optional[datetime] = None
    model_config = {"from_attributes": True}


class ModerationAction(BaseModel):
    comment: Optional[str] = None


# --- Stats ---
class AddressStatsOut(BaseModel):
    yards_total: int
    yards_active: int
    buildings_total: int
    buildings_active: int
    apartments_total: int
    apartments_active: int
    residents_approved: int
    residents_pending: int
