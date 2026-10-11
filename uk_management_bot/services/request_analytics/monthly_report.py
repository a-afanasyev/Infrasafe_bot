"""Ежемесячный автоотчёт менеджерам: CSV принятых заявок + сводка в подписи.

1-го числа в 09:00 по Ташкенту (джоба в `utils/shift_scheduler.py`) каждому
активному менеджеру уходит файл за прошлый календарный месяц — тот же CSV, что
выгружает дашборд (`build_completed_csv`). Best-effort: ошибки логируются,
джоба не падает. Повтор за тот же месяц (рестарт бота, вторая реплика)
отсекает ключ Redis; без Redis — fail-open (лучше дубль, чем тишина).
"""
from __future__ import annotations

import html
import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

from uk_management_bot.utils.business_time import business_today
from uk_management_bot.utils.helpers import get_text

from .csv_export import build_completed_csv, export_filename
from .executors import ExecutorSummary, executor_summaries
from .period import mean

logger = logging.getLogger(__name__)

REPORT_KEY = "report:monthly:{month}"
REPORT_TTL_SECONDS = 40 * 24 * 3600
TOP_EXECUTORS = 3


def previous_month(today: date) -> tuple[date, date]:
    last = today.replace(day=1) - timedelta(days=1)
    return last.replace(day=1), last


@dataclass(frozen=True)
class ReportSummary:
    accepted: int
    executed: int
    returned: int
    avg_work_hours: Optional[float]
    top: list[tuple[str, int]]


def summarize(rows: list[ExecutorSummary]) -> ReportSummary:
    ranked = [r for r in rows if r.accepted and r.user_id is not None]
    return ReportSummary(
        accepted=sum(r.accepted for r in rows),
        executed=sum(r.executed for r in rows),
        returned=sum(r.returned for r in rows),
        avg_work_hours=mean(r.avg_work_hours for r in ranked),
        top=[(r.name or "—", r.accepted) for r in ranked[:TOP_EXECUTORS]],
    )


def caption(summary: ReportSummary, first: date, lang: str) -> str:
    """Подпись к файлу (HTML: имена экранируются)."""
    lines = [
        get_text("analytics_report.title", language=lang,
                 month=f"{first.month:02d}.{first.year}"),
        get_text("analytics_report.accepted", language=lang, count=summary.accepted),
        get_text("analytics_report.executed", language=lang, count=summary.executed),
        get_text("analytics_report.returned", language=lang, count=summary.returned),
    ]
    if summary.avg_work_hours is not None:
        lines.append(get_text("analytics_report.avg_work", language=lang,
                              hours=str(summary.avg_work_hours).replace(".", ",")))
    if summary.top:
        lines.append(get_text("analytics_report.top", language=lang))
        lines += [f"{i}. {html.escape(name)} — {count}"
                  for i, (name, count) in enumerate(summary.top, start=1)]
    return "\n".join(lines)


async def _claim_month(first: date) -> bool:
    """True — за этот месяц ещё не слали (и пометить). Без Redis — True."""
    try:
        from uk_management_bot.services.redis_pubsub import get_pubsub_redis

        redis = await get_pubsub_redis()
        key = REPORT_KEY.format(month=f"{first.year:04d}-{first.month:02d}")
        return bool(await redis.set(key, "1", nx=True, ex=REPORT_TTL_SECONDS))
    except Exception as exc:  # noqa: BLE001 — fail-open, см. докстринг модуля
        logger.warning("monthly_report: Redis недоступен для дедупа: %s", type(exc).__name__)
        return True


async def send_monthly_report(
    bot, *, today: Optional[date] = None, session_factory=None, force: bool = False,
) -> int:
    """Разослать отчёт за прошлый месяц; → сколько менеджеров получили файл."""
    from aiogram.types import BufferedInputFile

    from uk_management_bot.services.auto_manager.config import load_config
    from uk_management_bot.services.feedback_service import manager_recipients_async

    if session_factory is None:
        from uk_management_bot.database.session import AsyncSessionLocal

        session_factory = AsyncSessionLocal
    if session_factory is None:
        logger.error("monthly_report: async-сессия БД не настроена — отчёт не собран")
        return 0

    first, last = previous_month(today or business_today())
    if not force and not await _claim_month(first):
        logger.info("monthly_report: отчёт за %s уже отправлен", first.isoformat()[:7])
        return 0

    async with session_factory() as db:
        sla_hours = (await load_config(db))["sla_hours"]
        payload, count = await build_completed_csv(db, first, last, sla_hours)
        summary = summarize(await executor_summaries(db, first, last, sla_hours))
        recipients = await manager_recipients_async(db)

    data = payload.encode("utf-8")
    filename = export_filename("completed_requests", first, last)
    sent = 0
    for telegram_id, lang in recipients:
        try:
            await bot.send_document(
                telegram_id, BufferedInputFile(data, filename=filename),
                caption=caption(summary, first, lang),
            )
            sent += 1
        except Exception as exc:  # noqa: BLE001 — best-effort, текст Bot API не логируем
            logger.warning("monthly_report: не доставлено tg=%s: %s",
                           telegram_id, type(exc).__name__)
    logger.info("monthly_report: %s строк за %s, доставлено %s/%s менеджерам",
                count, first.isoformat()[:7], sent, len(recipients))
    return sent
