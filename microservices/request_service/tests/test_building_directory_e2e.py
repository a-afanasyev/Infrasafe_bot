"""
Request Service - Building Directory E2E Integration Test
Validates real integration between Request Service and User Service

This test verifies:
1. BuildingDirectoryClient connects to correct URL (user-service:8002)
2. Coordinates are extracted from nested structure
3. MANAGEMENT_COMPANY_ID is used correctly
"""

import pytest
import asyncio
from uuid import uuid4, UUID

from app.clients.building_directory_client import get_building_directory_client


@pytest.mark.asyncio
async def test_building_directory_client_configuration():
    """Test that BuildingDirectoryClient is configured correctly"""
    client = get_building_directory_client()

    # Verify URL points to user-service
    assert 'user-service:8002' in client.api_url, \
        f"Expected user-service:8002, got {client.api_url}"

    # Verify MANAGEMENT_COMPANY_ID is set
    assert client.management_company_id is not None
    assert len(client.management_company_id) > 0

    print(f"✅ Client configured correctly:")
    print(f"   API URL: {client.api_url}")
    print(f"   Management Company ID: {client.management_company_id}")
    print(f"   Timeout: {client.timeout}s")


@pytest.mark.asyncio
async def test_building_directory_real_connection():
    """Test real connection to User Service Building Directory API"""
    client = get_building_directory_client()

    # Try to connect to user-service health endpoint
    import httpx

    health_url = f"{client.api_url}/health"

    try:
        async with httpx.AsyncClient(timeout=5.0) as http_client:
            response = await http_client.get(health_url)

            assert response.status_code == 200, \
                f"User Service health check failed: {response.status_code}"

            health_data = response.json()
            print(f"✅ User Service is healthy:")
            print(f"   Status: {health_data.get('status')}")
            print(f"   Service: {health_data.get('service')}")

    except httpx.ConnectError as e:
        pytest.fail(f"Cannot connect to User Service at {health_url}: {e}")
    except Exception as e:
        pytest.fail(f"Error connecting to User Service: {e}")


@pytest.mark.asyncio
async def test_building_directory_coordinates_extraction():
    """Test that coordinates are extracted from nested structure correctly"""
    client = get_building_directory_client()

    # Create a test building in User Service
    import httpx

    building_data = {
        "city": "Tashkent",
        "street": "Test Street for E2E",
        "house_number": "999",
        "building_corpus": "E2E",
        "coordinates": {
            "lat": 41.311158,
            "lon": 69.279737
        }
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as http_client:
            # Create building via User Service API
            create_url = f"{client.api_url}/api/v1/buildings"
            headers = {
                "X-Management-Company-ID": client.management_company_id
            }

            create_response = await http_client.post(
                create_url,
                json=building_data,
                headers=headers
            )

            if create_response.status_code == 201:
                building = create_response.json()
                building_id = UUID(building['id'])

                print(f"✅ Created test building: {building_id}")

                # Now test our client's get_building_data_for_request
                building_data_result = await client.get_building_data_for_request(building_id)

                if building_data_result:
                    # Verify coordinates were extracted
                    assert building_data_result.get('latitude') == 41.311158, \
                        f"Latitude mismatch: expected 41.311158, got {building_data_result.get('latitude')}"

                    assert building_data_result.get('longitude') == 69.279737, \
                        f"Longitude mismatch: expected 69.279737, got {building_data_result.get('longitude')}"

                    print(f"✅ Coordinates extracted correctly from nested structure:")
                    print(f"   Latitude: {building_data_result['latitude']}")
                    print(f"   Longitude: {building_data_result['longitude']}")
                    print(f"   Address: {building_data_result.get('building_address')}")

                    # Clean up - soft delete the test building
                    delete_url = f"{create_url}/{building_id}"
                    await http_client.delete(delete_url, headers=headers, params={"soft": "true"})
                    print(f"✅ Cleaned up test building")

                else:
                    pytest.fail(f"Failed to get building data for building {building_id}")

            elif create_response.status_code == 400:
                # Building might already exist (duplicate), try to find it
                print("⚠️  Building might already exist, skipping creation test")
                pytest.skip("Building already exists, cannot test creation")
            else:
                pytest.fail(
                    f"Failed to create test building: {create_response.status_code} - {create_response.text}"
                )

    except httpx.ConnectError as e:
        pytest.fail(f"Cannot connect to User Service: {e}")
    except Exception as e:
        pytest.fail(f"Error during E2E test: {e}")


if __name__ == "__main__":
    # Allow running this test standalone
    asyncio.run(test_building_directory_client_configuration())
    asyncio.run(test_building_directory_real_connection())
    asyncio.run(test_building_directory_coordinates_extraction())
