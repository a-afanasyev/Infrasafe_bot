"""Idempotent bootstrap: default tenant (run after alembic upgrade)."""

import logging

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Tenant

logger = logging.getLogger("resource_seed")


def seed() -> None:
    with SessionLocal() as db:
        tenant = db.execute(select(Tenant).where(Tenant.code == "uk")).scalar_one_or_none()
        if tenant is None:
            db.add(Tenant(code="uk", name="Управляющая компания"))
            db.commit()
            logger.info("Default tenant created")
        else:
            logger.info("Default tenant already exists")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    seed()
