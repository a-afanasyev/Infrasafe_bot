"""DB-level integrity: constraints must hold even if service code is bypassed."""

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models import Meter, Reading, ReportingPeriod, ResourceObject, Tenant


@pytest.fixture()
def tenant(db):
    return db.execute(select(Tenant)).scalars().first()


def _meter(tenant, obj, number, status="active"):
    return Meter(
        tenant_id=tenant.id,
        meter_number=number,
        meter_number_normalized=number.upper(),
        name="t",
        resource_type="electricity",
        unit="kWh",
        description="t",
        install_location="t",
        status=status,
        primary_object_id=obj.id,
    )


@pytest.fixture()
def obj(db, tenant):
    row = ResourceObject(tenant_id=tenant.id, name="constraint-obj")
    db.add(row)
    db.commit()
    return row


def test_unique_active_meter_number(db, tenant, obj):
    db.add(_meter(tenant, obj, "DBC-001"))
    db.commit()
    db.add(_meter(tenant, obj, "DBC-001"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    # archived duplicate is allowed (partial index)
    db.add(_meter(tenant, obj, "DBC-001", status="archived"))
    db.commit()


def test_unique_reading_per_meter_period(db, tenant, obj):
    meter = _meter(tenant, obj, "DBC-002")
    period = ReportingPeriod(tenant_id=tenant.id, month="2031-01")
    db.add_all([meter, period])
    db.commit()
    db.add(Reading(tenant_id=tenant.id, meter_id=meter.id, reporting_period_id=period.id))
    db.commit()
    db.add(Reading(tenant_id=tenant.id, meter_id=meter.id, reporting_period_id=period.id))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_unique_period_month(db, tenant):
    db.add(ReportingPeriod(tenant_id=tenant.id, month="2031-02"))
    db.commit()
    db.add(ReportingPeriod(tenant_id=tenant.id, month="2031-02"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_meter_requires_primary_object(db, tenant):
    meter = Meter(
        tenant_id=tenant.id,
        meter_number="DBC-003",
        meter_number_normalized="DBC-003",
        name="t",
        resource_type="electricity",
        unit="kWh",
        description="t",
        install_location="t",
        status="active",
        primary_object_id=None,
    )
    db.add(meter)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
