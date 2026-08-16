"""notification_service — пакет (AUD5-ARCH-3 волна 13, block-move).

Бывший services/notification_service.py (810 строк) разнесён на модули
байт-в-байт; публичный интерфейс сохранён реэкспортами ниже.

`_shared_bot` НАМЕРЕННО не реэкспортируется: это мутабельный module-level
глобал в `shared_bot.py`, реэкспорт снапшотил бы его значение на момент
импорта. Доступ — только через `set_shared_bot`/`_get_shared_bot`.

`settings` реэкспортирован осознанно: тесты (test_bug_bot_016) патчат его
атрибуты через `patch.object(notification_service.settings, ...)` — это тот же
singleton, что читает `channel._resolve_channel_id`, патч не вакуумен.
"""
from uk_management_bot.config.settings import settings

from uk_management_bot.services.notification_service.channel import (
    _CHANNEL_ID_PLACEHOLDERS,
    _resolve_channel_id,
    send_to_channel,
    send_to_user,
)
from uk_management_bot.services.notification_service.shared_bot import (
    set_shared_bot,
    _get_shared_bot,
)
from uk_management_bot.services.notification_service.shifts import (
    notify_shift_started,
    notify_shift_ended,
    _format_duration_hm,
    build_shift_started_message,
    build_shift_ended_message,
    build_shift_assignment_message,
    async_notify_shift_started,
    async_notify_shift_ended,
    async_notify_shift_assigned,
)
from uk_management_bot.services.notification_service.documents import (
    build_document_request_message,
    async_notify_document_request,
    build_multiple_documents_request_message,
    async_notify_multiple_documents_request,
)
from uk_management_bot.services.notification_service.service import (
    NotificationService,
)
from uk_management_bot.services.notification_service.requests_roles import (
    notify_status_changed,
    _build_request_status_message_channel,
    build_role_switched_message,
    async_notify_role_switched,
    build_action_denied_message,
    async_notify_action_denied,
)
from uk_management_bot.services.notification_service.feedback import (
    deliver_feedback_to_managers,
    send_feedback_reply_to_user,
)

__all__ = [
    "settings",
    "_CHANNEL_ID_PLACEHOLDERS",
    "_resolve_channel_id",
    "send_to_channel",
    "send_to_user",
    "set_shared_bot",
    "_get_shared_bot",
    "notify_shift_started",
    "notify_shift_ended",
    "_format_duration_hm",
    "build_shift_started_message",
    "build_shift_ended_message",
    "build_shift_assignment_message",
    "async_notify_shift_started",
    "async_notify_shift_ended",
    "async_notify_shift_assigned",
    "build_document_request_message",
    "async_notify_document_request",
    "build_multiple_documents_request_message",
    "async_notify_multiple_documents_request",
    "NotificationService",
    "notify_status_changed",
    "_build_request_status_message_channel",
    "build_role_switched_message",
    "async_notify_role_switched",
    "build_action_denied_message",
    "async_notify_action_denied",
    "deliver_feedback_to_managers",
    "send_feedback_reply_to_user",
]
