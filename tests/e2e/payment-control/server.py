"""Loopback-only E2E fixture: real UK routers + payment service, disposable data.

Authentication is replaced only in this test host. Never deployed or imported by runtime.
"""
import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
os.environ.update(DEBUG="true", BOT_TOKEN="e2e:dummy", JWT_SECRET="e2e-dummy-secret", INVITE_SECRET="e2e-dummy-secret",
                  ADMIN_PASSWORD="e2e-dummy-password-123456", DATABASE_URL="postgresql://e2e:e2e@127.0.0.1:59999/e2e",
                  USE_REDIS_RATE_LIMIT="false", INFRASAFE_WEBHOOK_ENABLED="false", UK_WEBHOOK_ENABLED="false",
                  REDIS_URL="redis://127.0.0.1:59998/0", PAYMENT_SERVICE_TOKEN="e2e-token-123456789012345678901234567890",
                  PAYMENT_SERVICE_URL="http://127.0.0.1:18085/service/v1")

import uvicorn  # noqa: E402
from fastapi import FastAPI, WebSocket, WebSocketDisconnect  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker  # noqa: E402
from payment_control.app import create_app  # noqa: E402
from uk_management_bot.api.addresses.router import router as addresses  # noqa: E402
from uk_management_bot.api.payment_control.router import router as payments  # noqa: E402
from uk_management_bot.api.dependencies import get_db, get_current_user  # noqa: E402
from uk_management_bot.api.rate_limit import limiter  # noqa: E402
from uk_management_bot.database.session import Base  # noqa: E402
from uk_management_bot.database.models import User, Yard, Building, Apartment  # noqa: E402
from uk_management_bot.services.addresses import core  # noqa: E402


if __name__ == "__main__":
    with TemporaryDirectory(prefix="uk-payment-e2e-") as directory:
        db_file = Path(directory) / "uk.db"
        engine = create_engine(f"sqlite:///{db_file}")
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            user = User(id=1, telegram_id=999, roles='["manager"]', active_role="manager", status="approved", first_name="E2E")
            db.add(user)
            db.add(Yard(id=1, name="Тестовый двор", is_active=True))
            db.flush()
            db.add(Building(id=1, yard_id=1, address="Тестовая улица 1", is_active=True, entrance_count=1, floor_count=1))
            db.flush()
            db.add(Apartment(id=1, building_id=1, apartment_number="1", account_number="001", is_active=True))
            db.commit()
        engine.dispose()
        async_engine = create_async_engine(f"sqlite+aiosqlite:///{db_file}")
        sessions = async_sessionmaker(async_engine, expire_on_commit=False)

        async def get_session():
            async with sessions() as session:
                yield session

        async def get_user():
            async with sessions() as session:
                return await session.get(User, 1)

        async def no_realtime(*args, **kwargs):
            pass

        core.publish_realtime_after_commit = no_realtime
        app = FastAPI()
        app.state.limiter = limiter
        app.add_middleware(CORSMiddleware, allow_origins=["http://127.0.0.1:5179"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
        app.dependency_overrides[get_db] = get_session
        app.dependency_overrides[get_current_user] = get_user
        app.include_router(addresses, prefix="/api/v2/addresses")
        app.include_router(payments, prefix="/api/v2/payment-control")
        app.mount("/service", create_app(f"sqlite:///{Path(directory) / 'payments.db'}", initialize=True))

        @app.get("/api/v2/profile")
        def profile():
            return {"id": 1, "roles": ["manager"], "first_name": "E2E", "has_password": True}

        @app.post("/api/v2/auth/refresh")
        def refresh_test_identity():
            return {"ok": True}

        @app.get("/api/v2/public/board-config")
        def board_config():
            return {"display_timezone": "Asia/Tashkent"}

        @app.get("/health")
        def health():
            return {"status": "ok"}

        @app.websocket("/ws/v2/{channel}")
        async def quiet_socket(websocket: WebSocket, channel: str):
            await websocket.accept()
            try:
                while True:
                    await websocket.receive_text()
            except WebSocketDisconnect:
                pass

        uvicorn.run(app, host="127.0.0.1", port=18085, access_log=False)
