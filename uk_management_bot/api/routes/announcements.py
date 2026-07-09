"""TWA home-page «Информация» — читает board_config (путь Б).

Ранее была статическая заглушка. Теперь эндпоинт отдаёт контент из
редактируемого board_config (контакты, новости, часы работы), так что менеджер
правит его в «Редакторе витрины» без деплоя, отдельно на каждый инстанс.

Контракт ответа сохранён (`{announcements, working_hours, emergency_phones}`),
чтобы фронт HomePage почти не менялся. Локализация — `?lang=ru|uz`.
"""
from fastapi import APIRouter, Depends, Request

from uk_management_bot.api.board_config.schemas import LocalizedText
from uk_management_bot.api.board_config.service import format_working_hours, load_board_config
from uk_management_bot.api.dependencies import get_db
from uk_management_bot.api.rate_limit import limiter

router = APIRouter()


# ⚠️ имя `get_announcements` импортируется напрямую в api/main.py — не переименовывать.
@router.get("/api/v2/announcements")
@limiter.limit("120/minute")
async def get_announcements(request: Request, db=Depends(get_db), lang: str = "ru"):
    """Контент главной TWA из board_config. Без аутентификации (публичный)."""
    lang = "uz" if lang.startswith("uz") else "ru"

    # Пустой/пробельный UZ допустим схемой → fallback на RU (как табло,
    # ResidentBoardPage). strip и в RU-ветке — чтобы карточка из одних пробелов
    # отсеивалась одинаково.
    def loc(t: LocalizedText) -> str:
        return (t.uz.strip() or t.ru.strip()) if lang == "uz" else t.ru.strip()

    cfg = await load_board_config(db)

    announcements: list[dict] = []

    # Новости: сортируем сырые cfg.announcements (важные вперёд, свежие выше,
    # пустые даты вниз) ДО маппинга, затем отбрасываем пустые title/text.
    ordered_news = sorted(
        cfg.announcements,
        key=lambda a: (a.important, a.published_at or ""),
        reverse=True,
    )
    for a in ordered_news:
        title = loc(a.title)
        body = loc(a.text)
        if not title or not body:
            continue
        announcements.append({"id": a.id, "type": "info", "title": title, "body": body})

    # Контакты — последней карточкой. Лейбл с fallback (dispatch_label может быть
    # пустым), body собираем из непустых строк, чтобы не было «: +998» / пустых.
    phone = cfg.contacts.dispatch_phone.strip()
    label = loc(cfg.contacts.dispatch_label) or ("Диспетчерская" if lang == "ru" else "Dispetcherlik")
    emergency = loc(cfg.contacts.emergency)
    parts: list[str] = []
    if phone:
        parts.append(f"{label}: {phone}")
    if emergency:
        parts.append(emergency)
    if parts:
        announcements.append({
            "id": "contacts",
            "type": "contact",
            "title": "Контакты" if lang == "ru" else "Aloqa",
            "body": "\n".join(parts),
        })

    return {
        "announcements": announcements,
        "working_hours": format_working_hours(cfg.working_hours, lang),
        "emergency_phones": [phone] if phone else [],
    }
