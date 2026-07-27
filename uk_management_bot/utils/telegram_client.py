"""Единая точка создания ``Bot`` и профили таймаутов обращений к Telegram.

**Замер, а не предположение** (2026-07-27, aiogram 3.30 против TCP-сервера,
который принимает соединение и не отвечает): дефолтная сессия сдаётся за
**60.2 с**. То есть формулировка «нет и глобальной защиты» (AUD3-09) неверна —
защита есть, но её порог 60 с, и этого достаточно, чтобы:

* рассылка менеджерам (`send_manager_notification`, `deliver_feedback_to_managers`)
  шла ПОСЛЕДОВАТЕЛЬНО по получателям → N × 60 с; вызов
  `deliver_feedback_to_managers` живёт прямо внутри HTTP-обработчика
  (`api/feedback/router.py`), то есть житель ждёт всю рассылку;
* плановые job'ы шедулера стояли на одном недоступном получателе.

Профили разные, потому что операции разные (тот же вывод, что в AUD3-08 про
Redis: единый таймаут «на всё» либо слишком длинный, либо рвёт легитимно
долгую операцию):

``SESSION_TIMEOUT``
    Общий предел на ЛЮБОЙ вызов API — страховка для десятков `send_message`
    в хендлерах, которым отдельный таймаут не нужен.
``SEND_TIMEOUT``
    Короткий текстовый round-trip. Ставится явно там, где вызов стоит в цикле
    по получателям: там важен не предел одного вызова, а сумма.
``UPLOAD_TIMEOUT``
    Отправка байтов медиа. Легитимно дольше текста — ограничивать её
    `SEND_TIMEOUT` значило бы рвать нормальную загрузку фото.

Long-polling не страдает: aiogram сам считает `request_timeout` как
``session.timeout + polling_timeout`` (`Dispatcher._listen_updates`), то есть
любой ПОЛОЖИТЕЛЬНЫЙ ``SESSION_TIMEOUT`` оставляет длинному опросу запас. Ноль
недопустим — при нём aiogram не передаёт `request_timeout` вовсе.
"""
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode

SESSION_TIMEOUT = 15.0
SEND_TIMEOUT = 10.0
UPLOAD_TIMEOUT = 60.0


def build_bot(token: str, *, html: bool = True) -> Bot:
    """Единственный конструктор ``Bot`` в проекте (гейт в тестах следит).

    ``html`` вынесен параметром сознательно: диспетчерский бот и бот API
    работают с ``parse_mode=HTML``, а ленивый fallback в
    ``notification_service._get_shared_bot`` исторически — без него, и его
    получатели шлют СЫРОЙ текст (``send_to_user``). Молча включить HTML там
    нельзя: сообщение с ``<`` или ``&`` начнёт падать или отображаться криво.
    Здесь расхождение хотя бы видно в одном месте, а не разъезжается по трём
    конструкторам.
    """
    if SESSION_TIMEOUT <= 0:
        raise ValueError("SESSION_TIMEOUT должен быть > 0 — иначе предела нет")
    return Bot(
        token=token,
        session=AiohttpSession(timeout=SESSION_TIMEOUT),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML) if html else None,
    )
