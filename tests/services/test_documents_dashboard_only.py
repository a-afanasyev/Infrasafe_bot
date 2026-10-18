"""Документы жителя смотрят только в дашборде.

Пересылка файла в Telegram создаёт копию в чате менеджера, которую уничтожение
ключа уже не сделает нечитаемой. Бот показывает список документов и ссылку на
карточку жителя в дашборде; ни один хендлер не отправляет файлы документов.
"""
from pathlib import Path

from uk_management_bot.database.models.user_verification import DocumentType, UserDocument

HANDLERS = Path(__file__).resolve().parents[2] / "uk_management_bot" / "handlers"


def test_document_list_links_to_dashboard_without_download_buttons(el_db, el_seed, monkeypatch):
    from uk_management_bot.config.settings import settings
    from uk_management_bot.handlers.user_management.actions import _load_user_documents_view

    monkeypatch.setattr(settings, "FRONTEND_URL", "https://profk.uz")
    el_db.add(el_seed.user(5))
    el_db.flush()
    el_db.add(UserDocument(user_id=5, document_type=DocumentType.PASSPORT, media_id=1,
                           encryption_key=b"k" * 32, document_uuid="00000000-0000-4000-8000-000000000001"))
    el_db.commit()

    verdict, view = _load_user_documents_view(el_db, 5, "ru")

    assert verdict == "ok"
    buttons = [b for row in view.keyboard.inline_keyboard for b in row]
    assert any(b.url == "https://profk.uz/uk/dashboard/residents/5" for b in buttons)
    assert not any((b.callback_data or "").startswith("download_document_") for b in buttons)


def test_no_handler_sends_document_files():
    offenders = [
        str(path.relative_to(HANDLERS)) for path in HANDLERS.rglob("*.py")
        if 'startswith("download_document_")' in path.read_text(encoding="utf-8")
    ]
    assert offenders == []
