import pytest
from sqlalchemy import text

@pytest.mark.asyncio
async def test_harness_db_and_http(api_client, async_db):
    assert (await async_db.execute(text("SELECT 1"))).scalar() == 1   # DB session live
    assert (await api_client.get("/health")).status_code == 200        # ASGI transport live
