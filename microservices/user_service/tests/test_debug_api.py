"""Debug API test - converted to proper test."""
import pytest
from uuid import uuid4
from fastapi import status


@pytest.mark.asyncio
async def test_create_building_debug(test_client, test_company_id, auth_headers):
    """Test building creation with detailed debug output."""
    building_data = {
        "management_company_id": str(test_company_id),
        "city": "Tashkent",
        "street": "Amir Temur",
        "house_number": "42"
    }

    print(f"\n=== Request Data ===")
    print(f"Headers: {auth_headers}")
    print(f"Body: {building_data}")

    response = await test_client.post(
        "/api/v1/buildings",
        json=building_data,
        headers=auth_headers
    )

    print(f"\n=== Response ===")
    print(f"Status: {response.status_code}")
    print(f"Body: {response.json()}")

    # Now properly assert success
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["city"] == "Tashkent"
    assert data["street"] == "Amir Temur"
    assert data["house_number"] == "42"
