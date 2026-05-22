"""Raw entity-data builders for address events.

These build the RAW `data` dict that goes into the EventBus. They are NOT
webhook envelopes — `queue_webhook` wraps building.* events itself via
webhook_sender.build_building_payload. The building data keys here
(id/address/yard_name/latitude/longitude) MUST match what that envelope
builder reads (webhook_sender.py). Extra keys are harmless: the envelope
builder picks what it needs, Redis subscribers receive the full dict.
"""
from uk_management_bot.database.models import Yard, Building, Apartment


def build_building_event_data(building: Building, yard_name: str) -> dict:
    return {
        "id": building.id,
        "address": building.address,
        "yard_name": yard_name,
        "latitude": building.gps_latitude,
        "longitude": building.gps_longitude,
        "yard_id": building.yard_id,
        "entrance_count": building.entrance_count,
        "floor_count": building.floor_count,
        "is_active": building.is_active,
    }


def build_yard_event_data(yard: Yard) -> dict:
    return {
        "id": yard.id,
        "name": yard.name,
        "description": yard.description,
        "latitude": yard.gps_latitude,
        "longitude": yard.gps_longitude,
        "is_active": yard.is_active,
    }


def build_apartment_event_data(apartment: Apartment) -> dict:
    return {
        "id": apartment.id,
        "building_id": apartment.building_id,
        "apartment_number": apartment.apartment_number,
        "entrance": apartment.entrance,
        "floor": apartment.floor,
        "rooms_count": apartment.rooms_count,
        "area": apartment.area,
        "is_active": apartment.is_active,
    }
