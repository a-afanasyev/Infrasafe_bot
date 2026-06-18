"""ARCH-012: announcements stub extracted from `api/main.py`.

Static TWA home-page data. Replace with a real Announcement model + CRUD when
needed. Path is absolute; the router is included without a prefix.
"""
from fastapi import APIRouter

router = APIRouter()


# ── Stub: Announcements (TWA A1) ─────────────────────────
# TODO: Replace with real Announcement model + CRUD when needed
@router.get("/api/v2/announcements")
async def get_announcements():
    """Stub announcements for TWA home page. Returns static data."""
    return {
        "announcements": [
            {
                "id": 1,
                "type": "info",
                "title": "Часы работы диспетчерской",
                "body": "Пн-Пт: 08:00-20:00\nСб-Вс: 09:00-18:00\nЭкстренные вызовы — круглосуточно",
            },
            {
                "id": 2,
                "type": "contact",
                "title": "Контакты",
                "body": "Диспетчерская: +998 XX XXX XX XX\nАварийная служба: +998 XX XXX XX XX",
            },
        ],
        "emergency_phones": ["+998 XX XXX XX XX"],
        "working_hours": "08:00-20:00",
    }
