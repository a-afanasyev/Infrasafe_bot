import pytest
from uk_management_bot.api.registration.catalog import list_apartments, is_apartment_selectable


@pytest.mark.asyncio
async def test_list_apartments_returns_active_rows(async_db, seed_apartment):
    # seed_apartment suffixes yard_name with a uuid (Yard.name is UNIQUE),
    # so match on the prefix rather than exact equality.
    await seed_apartment(number="12", yard_name="Двор-1", address="ул. Ленина 1")
    rows = await list_apartments(async_db)
    assert any(
        a.apartment_number == "12" and a.yard_name.startswith("Двор-1")
        for a in rows
    )


@pytest.mark.asyncio
async def test_is_apartment_selectable_true_for_active(async_db, seed_apartment):
    apt = await seed_apartment(number="34")
    assert await is_apartment_selectable(async_db, apt.id) is True


@pytest.mark.asyncio
async def test_is_apartment_selectable_false_for_missing(async_db):
    assert await is_apartment_selectable(async_db, 999999) is False
