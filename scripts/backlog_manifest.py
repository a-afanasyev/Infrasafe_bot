#!/usr/bin/env python3
"""Манифест бэклога: единственный источник агрегатов и распределения по пакетам.

Зачем скрипт, а не таблица руками. Агрегаты в бэклоге многократно расходились с
реальностью двумя разными способами:

1. **Метод счёта не был зафиксирован.** «Сколько открыто» зависело от того, что
   считать заголовком пункта и что считать закрытым. Разные проходы давали
   разные числа, и сверить их было нечем.
2. **Пункты закрывались кодом, но не документом.** Заголовок помечен ✅, а
   зачёркивания нет; наивный «незачёркнутый = открытый» их считает открытыми.

Поэтому здесь:

* метод счёта — код этого файла (`classify`), а не соглашение в чьей-то памяти;
* распределение по пакетам — таблица `ASSIGNMENT`, и `--check` падает, если у
   открытого пункта нет пакета. Именно так теряются ID: `PENT-F14` выпал из
   плана, потому что группа писалась сокращением «F12/F13/F15/F16».

Команды:
    python3 scripts/backlog_manifest.py --check      # инвариант: 0 бесхозных ID
    python3 scripts/backlog_manifest.py --write      # перегенерировать манифест
    python3 scripts/backlog_manifest.py --aggregate  # только числа
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKLOG = ROOT / "docs/audit/2026-05-20-backlog.md"
MANIFEST = ROOT / "docs/audit/2026-05-20-backlog-manifest.md"

# Заголовок пункта: 2-4 решётки, дальше ID и тире. Заголовки-разделы (без строки
# `**Priority:**` в теле) пунктами не являются по определению — именно поэтому
# наличие Priority, а не вид заголовка, служит признаком пункта.
_HEADING = re.compile(r"^(#{2,4})\s+(.*)$")
_PRIORITY = re.compile(r"^-?\s*\*\*Priority:\*\*")
_ID = re.compile(r"^~*\s*([A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*-[A-Z0-9]+)\b")

# Маркеры закрытия ПРЯМО В ЗАГОЛОВКЕ. Зачёркивание — канон документа, но часть
# пунктов закрыта только словом «✅ CLOSED» без `~~`, и это надо учитывать, иначе
# закрытое считается открытым (исторический источник расхождения агрегатов).
_CLOSED_MARKERS = ("✅", "❌")


@dataclass(frozen=True)
class Item:
    ident: str
    line: int
    priority: str
    title: str
    state: str  # open | closed


def parse(text: str) -> list[Item]:
    items: list[Item] = []
    cur: dict | None = None

    def flush() -> None:
        if not cur or not cur["priority"]:
            return  # без Priority это раздел, а не пункт
        m = _ID.match(cur["title"])
        if not m:
            return
        items.append(
            Item(
                ident=m.group(1),
                line=cur["line"],
                priority=cur["priority"],
                title=cur["title"],
                state=classify(cur["title"]),
            )
        )

    for lineno, line in enumerate(text.split("\n"), 1):
        heading = _HEADING.match(line)
        if heading:
            flush()
            cur = {"line": lineno, "title": heading.group(2), "priority": ""}
            continue
        if cur and not cur["priority"] and _PRIORITY.match(line):
            pm = re.search(r"P\d", line)
            cur["priority"] = pm.group(0) if pm else "P?"
    flush()
    return items


def classify(title: str) -> str:
    """Открыт пункт или закрыт — по маркерам заголовка."""
    if title.lstrip().startswith("~~"):
        return "closed"
    if any(mark in title for mark in _CLOSED_MARKERS):
        return "closed"
    return "open"


# ─────────────────────────────────────────────────────────────────────────────
# Распределение открытых пунктов. Ключ — ПОЛНЫЙ ID (сокращения запрещены: ровно
# так был потерян PENT-F14).
#
# status:
#   actionable   — работа в коде/конфиге, пакет обязателен
#   decision     — ждёт решения владельца, до решения кодовой работы нет
#   doc-closed   — по коду закрыт, открыт только в документе (закрывается текстом)
#   calendar     — работа определена, но по календарю (срок депрекации)
#   no-pr        — работа вне PR (локальные файлы, потенциально деструктивно)
#   deferred     — решение принято и оно «не делать сейчас»; пункт остаётся
#                  открытым как трекер, работы от него не ждём. Отличать от
#                  `decision`: там решения ещё НЕТ.
#
# method — ЧЕМ установлен статус. Не приукрашивать: `doc-<дата>` означает, что
# статус взят из code-verified записи бэклога той даты, а не перепроверен сейчас.
# ─────────────────────────────────────────────────────────────────────────────
A = dict  # краткость таблицы

ASSIGNMENT: dict[str, dict] = {
    # Аудит Codex 2026-09-08, консолидация 2026-09-09; только метаданные задач.
    # Аудит бэклога 2026-09-09: все 27 перепроверены чтением кода на HEAD 2451dc85
    # (пометки под записями), ENG-07/CODE-06/DEP-01 скорректированы по существу.
    # SEC-01 относится к уже закрытой FIX-002 и в открытые не включается.
    # Сверка по коду 2026-09-11 (отчёт Codex docs/audit/2026-09-11-backlog-code-check.md):
    # 36/36 перепроверены, закрытых нет; method=verified-2026-09-11 только там, где
    # запись/AC уточнены или строки перепроверены на HEAD 6a04699a.
    # AUD7-COR-01/02/03 (три P1) закрыты 2026-09-11, PR #558: flush каскада, единый предикат
    # полноты validate/submit + UI, FOR UPDATE во всех путях записи + PG concurrency-тест в CI.
    # Сверка по коду 2026-09-15 (отчёт Codex docs/audit/2026-09-15-backlog-code-check.md,
    # снимок 635f97db; разбор 2026-09-17): 34/34 перепроверены, закрытие COR-01..03 подтверждено,
    # закрытых нет; четыре новые задачи по находкам СВ-01..04 (CODE-07/08, ARCH-03, DOC-01);
    # method=verified-2026-09-15 там, где запись/AC/метрика уточнены на этом снимке.
    # AUD7-COR-04 закрыт 2026-09-17 (PR #562): recompute_forward после upsert + range-lock у PUT/bulk/import.
    # AUD7-SEC-02 закрыт 2026-09-17 (PR #568).
    "AUD7-SEC-03": A(pkg="AUD7-S2", status="decision", method="verified-2026-09-15",
                       services="UK API / resource API", note="нужно решение об окне отзыва в существующем RBAC-плане; RBAC-план от 2026-09-05 в main отсутствует — сначала AUD7-DOC-01"),
    # AUD7-SEC-04 закрыт 2026-09-17 (PR #565).
    # AUD7-SEC-05 закрыт 2026-09-17 (PR #567).
    # AUD7-CODE-01 закрыт 2026-09-18 (PR #573).
    # AUD7-CODE-02 закрыт 2026-09-18 (PR #573).
    # AUD7-CODE-03 закрыт 2026-09-18 (PR #574).
    # AUD7-CODE-04 закрыт 2026-09-18 (PR #574).
    # AUD7-CODE-05 закрыт 2026-09-17 (PR #564).
    # AUD7-CODE-06 закрыт 2026-09-17 (PR #563).
    # AUD7-ARCH-01 закрыт 2026-09-18 (PR #576).
    # AUD7-ARCH-02 закрыт 2026-09-18 (PR #579).
    # AUD7-SIMP-01 закрыт 2026-09-18 (PR #579).
    # AUD7-SIMP-02 закрыт 2026-09-18 (PR #579).
    # AUD7-SIMP-03 закрыт 2026-09-18 (PR #579).
    # AUD7-ENG-01 закрыт 2026-09-17 (PR #570).
    # AUD7-ENG-02 закрыт 2026-09-17 (PR #571).
    # AUD7-ENG-03 закрыт 2026-09-17 (PR #572).
    # AUD7-ENG-04 закрыт 2026-09-17 (PR #571).
    # AUD7-ENG-05 закрыт 2026-09-18 (PR #577).
    # AUD7-ENG-06 закрыт 2026-09-18 (PR #577).
    # AUD7-ENG-07 закрыт 2026-09-18 (PR #578).
    # AUD7-ENG-08 закрыт 2026-09-17 (PR #566).
    # AUD7-DEP-01 закрыт 2026-09-17 (PR #570).
    # AUD7-CODE-07 закрыт 2026-09-17 (PR #563).
    # AUD7-ARCH-03 закрыт 2026-09-18 (PR #575).
    # AUD7-CODE-08 закрыт 2026-09-17 (PR #564).
    # AUD7-DOC-01 закрыт 2026-09-19 (PR #587).
    # ── П1 ЗАКРЫТ 2026-07-26 целиком: `AUD5-CODE-4`, `AUD5-APIFE-19`,
    # `AUD5-APIFE-18`, `AUD5-PRAC-5`, `AUD5-DEP-1`, `AUD5-PRAC-9` — все шесть
    # помечены закрытыми в бэклоге, поэтому строк здесь больше нет (`--check`
    # держит равенство ASSIGNMENT ↔ открытые пункты в обе стороны).
    # ── П2 (`PENT-F17`, `PENT-F14`) закрыт 2026-09-02: владелец edge применил запрос
    # `2026-09-02-edge-owner-request.md` на оба домена — allowlist `/uk/api/health`
    # и `security.txt` проверены нашими пробами снаружи. Строк здесь больше нет.
    # П2c (`PENT-F10`) закрыт 2026-07-27: оба хоста 600/700. `.105` доступен с
    # `ssh -o IdentitiesOnly=no` — вывод «хост заблокирован» от 26.07 был неверным.
    # П2d закрыт целиком 2026-07-26: `AUD5-PRAC-1` (канонический .env.example +
    # честный первый запуск в README), `AUD5-PRAC-7` (23 стухших дока в архив),
    # `AUD5-PRAC-8` (снапшот OpenAPI + CI-гейт).
    # ── П3
    # П3a (`AUD5-CODE-7`) закрыт 2026-07-26: ERROR+проброс вместо молчаливой
    # подмены applicant-клавиатурой; фактическая строка была :59, не :54-55.
    # П3b (`AUD3-12`) закрыт 2026-07-26 решением владельца «не мутировать до
    # попытки + снимать явно с аудитом»; atomic/savepoint не потребовались.
    # П3c (`AUD3-13`) закрыт 2026-07-26: перебор кандидатов с сохранением
    # границы severity; отчёт получил attempted_executors.
    # П3d закрыт 2026-07-26: `BUG-128` (POST зеркалит planned_*) и `WR-06`
    # (класс unbound `lang`: 4 заявленных + 16 найденных сайтов + AST-гейт).
    # ── П4: доска менеджера
    # П4 закрыт целиком 2026-07-27: AUD5-APIFE-3/7/8 (записи в бэклоге).
    # ── П5: расходящиеся копии
    # `AUD5-CODE-8` закрыт 2026-08-02: остаток П5a сведён к канонам
    # (parse_specializations / display_name / единая карточка) — все копии
    # парсинга реально расходились; «карточка ×3» = фактически ×2.
    # П5b (`AUD5-APIFE-13`) закрыт 2026-07-27: сниффер и имя разведены на канон
    # (детекция) и политику (allowlist/фолбэк) — запись в бэклоге. Два хвоста
    # заведены отдельными пунктами, оба ждут решения владельца.
    # ── П6
    # П6a (`AUD3-08`) закрыт 2026-07-27: два профиля таймаутов вместо одного,
    # шесть from_url сведены к двум — запись в бэклоге.
    # П6b (`AUD3-09`) закрыт 2026-07-27: единая фабрика Bot + три профиля
    # (сессия/рассылка/загрузка); «глобальной защиты нет» опровергнуто замером.
    # П6c (`AUD5-CODE-5`) закрыт 2026-07-27: db-фаза job'ов в рабочем потоке
    # (сессия создаётся и закрывается там же), сетевая — на своей сессии.
    # П6d (`AUD5-CODE-11`) закрыт 2026-07-27: срез страницы отдан БД; семантика
    # соседнего paginate_back_to_list сознательно НЕ унифицирована.
    # Хвост П6 закрыт 2026-07-27: `WR-05` (N+1 в рассылке claim → один JOIN) и
    # `AUD5-ARCH-7` (гонка ПОДТВЕРЖДЕНА, закрыта compare-and-set перед записью).
    # ── Программа B: sync-ORM в async-контуре — ЗАКРЫТА 2026-08-07
    # (AUD3-37 + AUD5-CODE-6: волны B1–B4 + финал F1/F2, PR #362..#368 + F2)
    # ── П7
    # П7c (`AUD5-PRAC-11`) закрыт 2026-07-27: scripts вернулись в ruff-scope.
    "AUD5-JUNK-5": A(pkg="П7", status="no-pr", method="verified-2026-09-11",
                     note="локальные venv/db/png — только пофайлово с подтверждения; 2026-09-11: uk_management_bot/venv 152 МиБ, 37 PNG 7,1 МиБ, ruvector.db 1,5 МиБ; корневой .venv 249 МБ (09-09)"),
    # П8 закрыт целиком 2026-07-27: `AUD5-CODE-12` (язык каждого админа),
    # `FS-11` (канон адреса + гейт), `AUD5-APIFE-17` (deep-link через MFA).
    # ── П8: i18n
    # ── П9
    # ── П10: security-программа
    # `AUD5-ARCH-6` закрыт 2026-09-01 (фаза 4 программы ратчетов): Settings —
    # конструктор вместо class-body (env/валидация на инстанцировании, синглтон
    # держит import-time fail-fast); pydantic-settings отклонён осознанно.
    # ── П11: тесты и покрытие
    # `AUD5-PRAC-6` закрыт 2026-08-02: twa включён в знаменатель coverage ещё
    # PR #331 (волна 5 аудита #6, floors 41/39/31/32) — маркер отставал от кода.
    # TEST-068 закрыт 2026-09-18 (PR #586).
    # `AUD3-25` закрыт 2026-09-01 (фаза 2 программы ратчетов): sqlite-сьют
    # test_aud325_scoring_sqlite.py гоняет реальные SQL-предикаты скоринга;
    # мутационная порча каждого предиката краснит (мок-сосед — нет).
    # ── Программа A: архитектура
    "AUD3-07": A(pkg="A2", status="deferred", method="verified-2026-09-15",
                 note="ратчет построен 2026-09-01: test_aud307_unconverted_ratchet, "
                      "baseline 23 файла / 232 сайта, двунаправленный; срез 2026-09-15: 62 CONVERTED; "
                      "конверсия «при касании», deferred-трекер класса"),
    # `AUD5-ARCH-1` закрыт 2026-08-19 консолидацией в `AUD3-07` (остаток обоих
    # совпадал побуквенно, прогресс с 2026-08-14 и так вёлся единым) — строка
    # удалена, `--check` падает на ID закрытого пункта.
    # `BUG-180` закрыт 2026-09-01: SameExecutor из plan_transition под FOR UPDATE,
    # бот — тот же честный текст, API — 409.
    # `BUG-181` закрыт 2026-09-01: old-notice в workflow_notifications
    # (collect_reassigned_away_sync + notify_reassigned_away_detached), API-путь шлёт.
    # `BUG-182` закрыт 2026-09-01 решением владельца «уведомлять при смене»
    # (вариант б): ключ notifications.workflow.reassigned, признак reassigned
    # через оба пути (бот _aftermath + API PATCH) по факту из outcome.
    # `BUG-185` заведён и закрыт 2026-09-01 тем же днём («заводи и чини»):
    # уведомления группе консолидированы в auto_assign_request_by_category
    # (дежурным наряд, остальным лёгкий текст, язык получателя, html.escape);
    # _notify_* и get_available_executors ретайрены из assignment_service.
    # `BUG-186` заведён и закрыт 2026-09-01: `view=own|assigned` в GET /requests
    # (сужение и только, Literal → 422), мёртвый `scope` снят; список исполнителя
    # на канонах parse_specializations + is_on_shift_now_async, tiebreak по PK.
    # `BUG-183` закрыт 2026-09-02: InfraSafe открыли префикс `residents` на edge 105
    # ещё 22.08, док отставал; пробы снаружи — residents* отвечает JSON 401/405 от
    # FastAPI на обоих доменах. Строки нет: `--check` держит равенство в обе стороны.
    # `BUG-148` закрыт 2026-09-01: путь ретайрен целиком (джобы №8/№9,
    # RequestAssignmentEngine, smart_assign_request, SmartDispatcher).
    # Найденный живой остаток близнеца BUG-174 (_notify_group_assignment
    # молчит на живом assign_to_group) — на решении владельца.
    # `BUG-149` закрыт 2026-09-01 (волна A2): GPS is not None, общий _loc_spec.
    # BUG-154 и BUG-158 закрыты 2026-08-19 ретайром одним движением с BUG-150
    # (решение владельца, вариант «а»); строки удалены — `--check` падает на ID
    # закрытого пункта.
    # `BUG-156` закрыт 2026-09-01 (волна A2): все 8 пп. + близнец guard'ов в employee_management.
    # `BUG-157` закрыт 2026-09-01 (волна A2): _get_user_language на run_db; транзитивный
    # гейт с baseline (6 известных сайтов — класс AUD3-07).
    # `BUG-155` закрыт 2026-09-01 (волна A2): пп.4,7 — clear до update_data, NULL/falsy документов.
    # `BUG-153` закрыт 2026-09-01 (волна A2): язык получателя, локали, id-микс оживил
    # кнопки заявителя, fmt_datetime.
    # `BUG-152` закрыт 2026-09-01 (волна A2): пп.2-5 — language в клавиатуры, days_ago.
    # `BUG-151` закрыт 2026-09-01 (волна A2): пп.2-8 — admin_comment на языке владельца,
    # список без is_active, пагинация по двору, свежая клавиатура профиля.
    # BUG-150 закрыт 2026-08-19 ретайром (вместе с BUG-154/BUG-158); его
    # дополнение — handle_back_to_report — оказалось дырой P1, а не мёртвым
    # кодом: вход был живой, генератора не было только у кнопки.
    # `BUG-165` закрыт 2026-09-01: пересъёмка AST-сканом → 26 сайтов закрыты
    # (2 протяжки, не 7 — create-пути уже несли lang после BUG-157); гейт
    # tests/test_bug165_language_passthrough_gate.py держит класс на нуле.
    # `BUG-164` закрыт 2026-08-31: «Заявитель» убран из клавиатуры выдачи +
    # applicant отвергается в точке записи (callback шлёт клиент, урок BUG-169).
    # `BUG-166` закрыт 2026-08-17: единая семантика ЛЮБАЯ + `universal`-джокер
    # во всех восьми точках подбора; строки здесь нет — пункт закрыт в бэклоге.
    # `BUG-167` закрыт 2026-08-31: метрика покрытия по полному канон-набору
    # (9 равнозначных), фокус читается канон-парсером, universal = 100%.
    # `BUG-168` закрыт 2026-08-31: предикат доступа на matches_required_specs,
    # group_specs нормализуются на чтении (fail-closed), паритет sync/async запинен.
    # `BUG-169` закрыт 2026-08-18: второй словарь удалён, названия берутся из
    # локалей бота (`specializations.*`); строки здесь нет — пункт закрыт в бэклоге.
    # `BUG-172` закрыт 2026-08-18: IDOR комментариев (запись + два чтения).
    # `BUG-171` закрыт 2026-08-31: general в каноне COMMENT_TYPES, валидация
    # add_comment читает канон (локальная копия списка и была причиной).
    # `BUG-175` закрыт 2026-08-19 (аудит бэклога): предписанный Fix был выполнен
    # кодом PR #468 (RoleGate на всех 4 адресных роутерах) на следующий день
    # после заведения — маркер отставал. Осознанный остаток (перепроверка роли
    # в юните записи модерации) заведён отдельным пунктом решением владельца
    # 2026-08-19 — строка ниже.
    # `BUG-177` закрыт 2026-09-01 (волна A2): AddressPermissionError в точке записи + 403.
    # `BUG-174` закрыт 2026-08-19 (волна живых дефектов): B3-раскрой, все
    # четыре прод-сайта шлют; близнец в assignment_service уходит с ретайром
    # BUG-148 — проверить оба сайта при ретайре.
    # `BUG-178` закрыт 2026-08-31: html.escape(reply_text) в _apply_reply по
    # канону BUG-174; греп остальных send_to_user-сайтов чист.
    # `BUG-173` закрыт 2026-08-19 (волна живых дефектов): валидатор-зеркало
    # Create; сырые join-сайты рендера — класс BUG-149/169, остаются там.
    "AUD5-CODE-10": A(pkg="A5", status="deferred", method="verified-2026-09-15",
                      note="ратчет построен 2026-09-01: test_aud5_code10_long_functions_ratchet, "
                           "baseline 40 файлов / 49 функций; срез 2026-09-15: 48 функций (комментарий гейта ещё 49); "
                           "раскрой «при касании» под принуждением гейта"),
    # `AUD3-15` закрыт 2026-08-02: масштаб опровергнут (6 хрупких из 79),
    # починены точечно без смены формата callback_data (пакет A6 исчерпан).
    "AUD5-ARCH-4": A(pkg="A7", status="deferred", method="gate-2026-08-09",
                     note="гейт границы стоит (test_aud5_arch4_domain_boundary_gate); "
                          "развязка (L) — только при намерении разносить сервисы"),
    # Закрыто 2026-08-02 (волна 1 разбора бэклога): `AUD3-35`+`PENT-F11`
    # (RATE_LIMIT_TRUSTED_PROXIES выставлен на обоих продах, CIDR),
    # `SEC-131` (MEDIA_BOT_TOKEN снят из .env .105, Doppler-only),
    # `BUG-136` (PR #343), `AUD5-PRAC-10` (маски уже были в .gitignore);
    # `AUD3-26` опровергнут (запиненный клок, не хрупкость); `AUD5-DEP-2`
    # отклонён (свап вешает jsdom-тесты dropdown — монолит осознанно).
    # ── Решения владельца (кодовой работы до решения нет)
    # `AUD5-DEAD-3` закрыт 2026-08-02: решение владельца 2026-07-31 (аудит #6)
    # — pull-модель ОСТАВИТЬ целиком, ничего не удалять.
    # `ARCH-116` закрыт 2026-07-30 (бот: показ + дневные бакеты через канон
    # `utils/business_time`, AST-гейт). Строка удалена — `--check` держит
    # равенство ASSIGNMENT ↔ открытые пункты в обе стороны. Найденное сверх
    # пункта заведено ниже как `ARCH-135` и `BUG-136`.
    # ARCH-135 закрыт 2026-08-05 целиком: группа (б) раскатана (теги *-2026-08-05.2
    # @ 3f0aa7e), пре-деплой аудит ночных шаблонов чист на обоих продах.
    # ARCH-137 закрыт 2026-08-05: все 4 фазы раскатаны (теги *-2026-08-05 @ 562744d);
    # хвост access-диалогов — ARCH-138 ниже.
    # ARCH-138 закрыт 2026-08-05: datetimeLocalToIso + 4 сайта, префилл/показ
    # PassDetailDialog, дефолт published_at; уезжает со следующей сборкой frontend.
    # ARCH-107 закрыт 2026-08-05: dual-key {primary,next} + kid в заголовке токена,
    # форма webhook-*_NEXT; включение механизма — со следующим деплоем api+access-api,
    # процедура ротации → uk-deploy SKILL.md.
    # `PENT-F12`, `PENT-F15`, `PENT-F16` закрыты 2026-09-02 вместе с П2: один PR
    # владельца edge на оба конфига, релоад 11:22 UTC, наши пробы снаружи зелёные.
    "PENT-F13": A(pkg="—", status="deferred", method="owner-decision-2026-09-18",
                 services="DNS/регистратор владельца (оба домена)",
                 note="решение владельца 2026-09-18: CAA на текущем DNS-провайдере не реализуем — deferred до смены провайдера (тогда CAA + DNSSEC, проверять раздельно CAA и DS); OCSP stapling неприменим для Let's Encrypt (закрыто ранее)"),
    # ── Деферралы, подтверждённые решением владельца 2026-07-27
    "ARCH-06": A(pkg="—", status="deferred", method="verified-2026-09-11",
                 note="AST-граф 2026-09-11: 0 циклов services↔utils; возвращаться вместе с развязкой границы (AUD5-ARCH-4/A7)"),
    "DB-049": A(pkg="—", status="deferred", method="verified-2026-07-27",
                note="jsonb+GIN — когда появится запрос по ролям, которому нужен индекс"),
    "SEC-115": A(pkg="—", status="deferred", method="verified-2026-09-11",
                 note="UK-часть сделана (/api/uk-buildings-metrics + x-service-token при INFRASAFE_INVENTORY_TOKEN); остаток внешний — принуждение auth на стороне InfraSafe и проверка токена на продах"),
    # ── Календарь: `PENT-F04` жил здесь до 2026-08-30 — единственный
    # calendar-пункт (снятие ?token= после срока депрекации 2026-09-01).
    # Закрыт PR #516: живых клиентов query-пути не было (0 SEC-03 warning'ов
    # в прод-логах обоих хостов за 30 дней), путь снят с отказом до accept().
    # ── Закрыто кодом, открыто документом
    # `REG-03` жил здесь до 2026-07-26: последний непокрытый периметр
    # (`media_service/requirements.txt`) закрыт PR #261, подтверждено чтением
    # `ci.yml`, пункт закрыт в бэклоге. Строка удалена, потому что `--check`
    # держит равенство ASSIGNMENT ↔ открытые пункты в обе стороны.
    # Аудит #8 (полное ревью 2026-09-19, docs/audit/2026-09-19-full-review.md): 16 пунктов.
    # AUD8-SEC-01 закрыт 2026-09-19 (PR #590).
    # AUD8-SEC-02 закрыт 2026-09-19 (PR #590).
    # AUD8-SEC-03 закрыт 2026-09-19 (PR #590).
    # AUD8-SEC-04 закрыт 2026-09-19 (PR #590).
    # AUD8-ENG-01 закрыт 2026-09-19 (PR #590).
    "AUD8-ENG-02": A(pkg="AUD8-E1", status="decision", method="verified-2026-09-19", note="BACKUPS.md: дампы plaintext; ключи/cron на хостах — решение владельца"),
    # AUD8-ENG-03 закрыт 2026-09-19 (PR #593).
    # AUD8-CODE-01 закрыт 2026-09-19 (PR #591).
    # AUD8-CODE-02 закрыт 2026-09-19 (PR #591).
    # AUD8-FE-01 закрыт 2026-09-19 (PR #592).
    # AUD8-FE-02 закрыт 2026-09-19 (PR #592).
    # AUD8-FE-03 закрыт 2026-09-19 (PR #592).
    # AUD8-FE-04 закрыт 2026-09-19 (PR #592).
    # AUD8-FE-05 закрыт 2026-09-19 (PR #592).
    # AUD8-DB-01 закрыт 2026-09-19 (PR #591).
    "AUD8-DB-02": A(pkg="AUD8-C1", status="deferred", method="verified-2026-09-19", note="OFFSET-пагинация; deferred до триггера p95>300 мс / >50k строк"),
    # Аудит #9 (полный аудит 2026-09-22, AUDIT_REPORT.md): 62 пункта; пакеты AUD9-W1…W8 = волны roadmap.
    "A9-P2-33": A(pkg="AUD9-W4", status="actionable", method="found-2026-09-23", services="bot", note="Закуп: ReplyKeyboardMarkup в edit_text — менеджер видит «Произошла ошибка» при возврате заявки из закупа"),
    "A9-P2-32": A(pkg="AUD9-W4", status="actionable", method="found-2026-09-23", services="bot", note="Бот «Мои смены → Начать/Завершить» мимо общего юнита смен: без audit, start_time переписывается"),
    # A9-P1-1 закрыт 2026-09-23 (PR #598).
    # A9-P1-2 закрыт 2026-09-23 (PR #599).
    # A9-P1-3 закрыт 2026-09-23 (PR #596).
    # A9-P2-1 закрыт 2026-09-23 (PR #600).
    "A9-P2-2": A(pkg="AUD9-W3", status="actionable", method="verified-2026-09-22", services="bot", note="Бот: пользовательский ввод без html.escape в карточках заявки, модерации квартир и сменах"),
    # A9-P2-3 закрыт 2026-09-23 (PR #600).
    "A9-P2-4": A(pkg="AUD9-W3", status="actionable", method="owner-decision-2026-09-23", services="bot", note="`/admin` + общий `ADMIN_PASSWORD` делают любой аккаунт manager'ом"),
    "A9-P2-5": A(pkg="AUD9-W2", status="actionable", method="audit9-2026-09-22", services="group-intake-bot, bot", note="Group Intake: фото сохраняется с `file_id` группового бота и не открывается из основного"),
    "A9-P2-6": A(pkg="AUD9-W4", status="actionable", method="audit9-2026-09-22", services="group-intake-bot", note="Group Intake тег-режим: при отказе лимитера сообщение с тегом пропадает молча"),
    "A9-P2-7": A(pkg="AUD9-W4", status="actionable", method="audit9-2026-09-22", services="api", note="`POST /requests`: автодиспетч и Telegram-уведомления inline при открытой транзакции"),
    "A9-P2-8": A(pkg="AUD9-W4", status="actionable", method="audit9-2026-09-22", services="api", note="API: сетевые вызовы при открытой сессии и синхронные рассылки в запросе (остатки AUD6-P2-02)"),
    "A9-P2-9": A(pkg="AUD9-W4", status="actionable", method="audit9-2026-09-22", services="api", note="API: шесть самописных Telegram-клиентов на httpx мимо общего `api_bot`"),
    "A9-P2-10": A(pkg="AUD9-W8", status="actionable", method="audit9-2026-09-22", services="bot, api", note="Доменный справочник категорий лежит в UI-слое `keyboards/requests.py`"),
    "A9-P2-11": A(pkg="AUD9-W2", status="actionable", method="audit9-2026-09-22", services="api", note="`media_files: List[str]` в create-схемах без валидации; строки уходят в `answer_photo`"),
    "A9-P2-12": A(pkg="AUD9-W5", status="actionable", method="audit9-2026-09-22", services="media-service", note="media: синхронный `db.query` в трёх async-ручках (остаток AUD7-ARCH-01)"),
    "A9-P2-13": A(pkg="AUD9-W5", status="actionable", method="audit9-2026-09-22", services="access-api, resource-api", note="access/resource: блокирующий I/O в async-эндпоинтах; `get_photo` отдаёт 500 при ошибке media"),
    "A9-P2-14": A(pkg="AUD9-W5", status="actionable", method="audit9-2026-09-22", services="access-api", note="access: загрузка кадров камеры под открытой транзакцией и row-lock; осиротевшие медиа"),
    "A9-P2-15": A(pkg="AUD9-W5", status="actionable", method="audit9-2026-09-22", services="media-service", note="media: `Bot`/`AiohttpSession` и httpx-клиент создаются на каждый запрос и не закрываются"),
    "A9-P2-16": A(pkg="AUD9-W5", status="actionable", method="audit9-2026-09-22", services="access-api, media-service", note="access: 30-дневный ретеншн фото ANPR не удаляет сами медиа"),
    "A9-P2-17": A(pkg="AUD9-W5", status="actionable", method="audit9-2026-09-22", services="resource-api, CI", note="resource: PG-тест блокировки периода никогда не выполняется в CI"),
    "A9-P2-18": A(pkg="AUD9-W2", status="actionable", method="audit9-2026-09-22", services="api, CI", note="API: row-lock-семантика проверяется только на sqlite"),
    "A9-P2-19": A(pkg="AUD9-W7", status="actionable", method="audit9-2026-09-22", services="образы bot/api/media, CI", note="Прод-образ бота с dev-зависимостями без хэшей; pytest объявлен дважды с конфликтующими версиями"),
    "A9-P2-20": A(pkg="AUD9-W7", status="actionable", method="audit9-2026-09-22", services="все сервисы, деплой", note="CD наполовину: GHCR-образы публикуются, но прод собирает образы из рабочей копии хоста"),
    "A9-P2-21": A(pkg="AUD9-W7", status="actionable", method="audit9-2026-09-22", services="media-service, CI", note="media: нет версионированных миграций и дрейф-гейта"),
    "A9-P2-22": A(pkg="AUD9-W7", status="actionable", method="owner-decision-2026-09-23", services="CI, dev", note="black/isort объявлены в pre-commit, но не соблюдаются"),
    "A9-P2-23": A(pkg="AUD9-W8", status="actionable", method="audit9-2026-09-22", services="bot", note="Чистка: backfill-модули пережили squash-baseline"),
    "A9-P2-24": A(pkg="AUD9-W8", status="actionable", method="audit9-2026-09-22", services="media-service, bot", note="Чистка: ~40% media_service — SDK и эндпоинты без потребителей"),
    "A9-P2-25": A(pkg="AUD9-W8", status="actionable", method="audit9-2026-09-22", services="scripts", note="Чистка: исторические скрипты (один падает на импорте, другой делает `create_all` в обход alembic)"),
    "A9-P2-26": A(pkg="AUD9-W8", status="deferred", method="owner-decision-2026-09-23", services="bot, БД", note="Чистка: в `access_rights` никто не пишет, а UI карточки прав её читает"),
    "A9-P2-27": A(pkg="AUD9-W8", status="actionable", method="owner-decision-2026-09-23", services="bot", note="Чистка: ~2,5 тыс. строк символов, живых только в тестах, вне перечня «задела» (#6 P2-40)"),
    "A9-P2-28": A(pkg="AUD9-W8", status="actionable", method="audit9-2026-09-22", services="bot, доки", note="Чистка: `utils/enums.py` дублирует канон статусов и не используется прод-кодом"),
    "A9-P2-29": A(pkg="AUD9-W6", status="actionable", method="audit9-2026-09-22", services="frontend", note="Фронт: logout не чистит кэш `QueryClient`"),
    "A9-P2-30": A(pkg="AUD9-W6", status="actionable", method="audit9-2026-09-22", services="frontend", note="Фронт: гонка в каскаде адреса регистрации — квартиры чужого дома"),
    "A9-P2-31": A(pkg="AUD9-W6", status="actionable", method="owner-decision-2026-09-23", services="frontend, TWA, bot", note="RU-хардкод в TWA, на экране MFA и в модуле ресурсоучёта"),
    "A9-P3-1": A(pkg="AUD9-W3", status="actionable", method="audit9-2026-09-22", services="bot", note="Инвайт-токен целиком пишется в лог в `/start join_…`"),
    "A9-P3-2": A(pkg="AUD9-W5", status="actionable", method="audit9-2026-09-22", services="access-api", note="access-api `/metrics` без токена (требует подтверждения доступности через edge)"),
    "A9-P3-3": A(pkg="AUD9-W5", status="actionable", method="audit9-2026-09-22", services="resource-api", note="resource: `commit_token` импорта бессрочный и не привязан к пользователю/тенанту/месяцу"),
    # A9-P3-4 закрыт 2026-09-23 (PR #600).
    "A9-P3-5": A(pkg="AUD9-W4", status="actionable", method="owner-decision-2026-09-23", services="group-intake-bot", note="Group Intake: сырой текст групп жителей (ПДн) уходит внешнему LLM без маскирования"),
    "A9-P3-6": A(pkg="AUD9-W4", status="actionable", method="audit9-2026-09-22", services="group-intake-bot", note="Group Intake: ответ постороннему в staff-группе, теги подстрокой, завышенная метрика"),
    "A9-P3-7": A(pkg="AUD9-W4", status="actionable", method="audit9-2026-09-22", services="group-intake-bot", note="Ретрай LLM (PR #594) без backoff и мимо лимитера; докстринги противоречат поведению"),
    "A9-P3-8": A(pkg="AUD9-W4", status="actionable", method="owner-decision-2026-09-23", services="bot", note="Планировщик смен: cron-триггеры в UTC при комментариях про местное время"),
    "A9-P3-9": A(pkg="AUD9-W4", status="actionable", method="audit9-2026-09-22", services="bot", note="Fire-and-forget `create_task` без сильной ссылки (ранее закрыт по неверной посылке)"),
    "A9-P3-10": A(pkg="AUD9-W4", status="actionable", method="audit9-2026-09-22", services="bot, access-api", note="Четыре опасных «немых» `except` из 27"),
    "A9-P3-11": A(pkg="AUD9-W8", status="actionable", method="audit9-2026-09-22", services="bot, api, access-api", note="Инверсии слоёв и два резолвера ролей с разным фолбэком"),
    "A9-P3-12": A(pkg="AUD9-W5", status="actionable", method="audit9-2026-09-22", services="access-api", note="access: `registry.py` обходит слой репозиториев; long-poll на `time.sleep` занимает поток"),
    "A9-P3-13": A(pkg="AUD9-W2", status="actionable", method="audit9-2026-09-22", services="api", note="PATCH заявки: `{rating}` → 500, правки без аудита/терминального гарда, карточка без лифта"),
    "A9-P3-14": A(pkg="AUD9-W4", status="actionable", method="audit9-2026-09-22", services="БД", note="Уникальность Group Intake обходится при `source_chat_id IS NULL`"),
    # A9-P3-15 закрыт 2026-09-23 (PR #598).
    "A9-P3-16": A(pkg="AUD9-W8", status="actionable", method="audit9-2026-09-22", services="bot", note="Чистка: ~4750 из 8293 ключей бота похожи на мёртвый автоген; сломанные плейсхолдеры в uz"),
    "A9-P3-17": A(pkg="AUD9-W8", status="actionable", method="audit9-2026-09-22", services="bot", note="Чистка: заглушки уведомлений и тесты, которые не могут упасть"),
    "A9-P3-18": A(pkg="AUD9-W8", status="actionable", method="audit9-2026-09-22", services="bot, api", note="Чистка: мелкие символы без единой ссылки; скрытая инициализация логирования"),
    "A9-P3-19": A(pkg="AUD9-W6", status="actionable", method="audit9-2026-09-22", services="frontend", note="Фронт: мелкие гонки/утечки WS, кэша, TZ и `useMemo`"),
    "A9-P3-20": A(pkg="AUD9-W6", status="actionable", method="audit9-2026-09-22", services="frontend", note="Фронт: сырой `detail` в JSX, ветвление по тексту ошибки, дубли цветов/разбора ошибок"),
    "A9-P3-21": A(pkg="AUD9-W6", status="actionable", method="audit9-2026-09-22", services="frontend", note="Фронт: god-компоненты и 44 файла с прямыми вызовами `apiClient`"),
    "A9-P3-22": A(pkg="AUD9-W6", status="actionable", method="audit9-2026-09-22", services="frontend", note="Фронт: `useTWAAuth` без тестов; `frontend/preview/` (2168 строк) вне tsc и CI"),
    "A9-P3-23": A(pkg="AUD9-W5", status="actionable", method="audit9-2026-09-22", services="media-service, access-api", note="Сателлиты: мелкие дефекты саги, гонок, Redis и дубли `_client_ip`"),
    "A9-P3-24": A(pkg="AUD9-W7", status="actionable", method="audit9-2026-09-22", services="CI", note="mypy только на боте; `[tool.mypy]` resource никогда не запускается"),
    "A9-P3-25": A(pkg="AUD9-W7", status="actionable", method="audit9-2026-09-22", services="CI", note="payment-control CI: тест-инструменты без пинов, path-фильтр"),
    "A9-P3-26": A(pkg="AUD9-W7", status="actionable", method="audit9-2026-09-22", services="compose, образы", note="postgres/redis без digest; лишнее в образах сателлитов"),
    "A9-P3-27": A(pkg="AUD9-W7", status="actionable", method="audit9-2026-09-22", services="доки", note="README и ARCHITECTURE отстают от кода; устаревшие комментарии CI"),
    "A9-P3-28": A(pkg="AUD9-W8", status="actionable", method="audit9-2026-09-22", services="репо, доки", note="Чистка: исторические отчёты в корне и ~23 тыс. строк россыпи в корне `docs/`"),
}


def render(items: list[Item]) -> str:
    open_items = [x for x in items if x.state == "open"]
    closed = len(items) - len(open_items)

    by_status: dict[str, list[Item]] = {}
    for it in open_items:
        st = ASSIGNMENT.get(it.ident, {}).get("status", "UNASSIGNED")
        by_status.setdefault(st, []).append(it)

    prio: dict[str, int] = {}
    for it in open_items:
        st = ASSIGNMENT.get(it.ident, {}).get("status")
        if st == "actionable":
            prio[it.priority] = prio.get(it.priority, 0) + 1

    out: list[str] = []
    out.append("# Манифест бэклога")
    out.append("")
    out.append("> Генерируется: `python3 scripts/backlog_manifest.py --write`.")
    out.append("> Руками не править — правки вносить в `ASSIGNMENT` в скрипте.")
    out.append("")
    out.append("## Зачем")
    out.append("")
    out.append(
        "Агрегаты бэклога расходились с реальностью двумя способами: метод счёта "
        "не был зафиксирован, и часть пунктов закрывалась кодом без закрытия "
        "документом. Здесь метод счёта — код скрипта, а распределение по пакетам "
        "проверяется инвариантом: `--check` падает, если у открытого пункта нет "
        "пакета. Ровно так был потерян `PENT-F14` — группа писалась сокращением."
    )
    out.append("")
    out.append("## Метод счёта")
    out.append("")
    out.append("- **Пункт** = заголовок `##`…`####`, в теле которого есть `**Priority:**`.")
    out.append("  Заголовки-разделы без Priority пунктами не являются по определению.")
    out.append("- **Закрыт** = заголовок зачёркнут (`~~`) **или** содержит `✅`/`❌`.")
    out.append("  Второе условие обязательно: часть пунктов закрыта словом без зачёркивания,")
    out.append("  и без этого закрытое считалось бы открытым.")
    out.append("- **Агрегаты считаются из этой таблицы**, а не пересказом.")
    out.append("")
    out.append("## Агрегаты")
    out.append("")
    out.append(f"- пунктов всего (с Priority): **{len(items)}**")
    out.append(f"- закрыто маркером: **{closed}**")
    out.append(f"- открыто маркером: **{len(open_items)}**")
    out.append("")
    for st in ("actionable", "decision", "calendar", "no-pr", "deferred", "doc-closed", "UNASSIGNED"):
        if st in by_status:
            out.append(f"  - `{st}` — **{len(by_status[st])}**")
    out.append("")
    ptxt = ", ".join(f"{k}={v}" for k, v in sorted(prio.items()))
    out.append(f"Из них actionable по приоритету: {ptxt}.")
    out.append("")
    out.append("Значения `status`:")
    out.append("")
    out.append("| status | смысл |")
    out.append("|---|---|")
    out.append("| `actionable` | работа в коде/конфиге, пакет обязателен |")
    out.append("| `decision` | ждёт решения владельца; до решения кодовой работы нет |")
    out.append("| `calendar` | работа определена, ждёт календарного срока |")
    out.append("| `no-pr` | работа вне PR (локальные файлы, потенциально деструктивно) |")
    out.append("| `deferred` | решение принято — «не делать сейчас»; трекер, работы не ждём (в отличие от `decision`, где решения ещё нет) |")
    out.append("| `doc-closed` | по коду закрыт, открыт только в документе |")
    out.append("")
    out.append("Значения `method` — **чем** установлен статус. `doc-<дата>` означает: взято")
    out.append("из code-verified записи бэклога той даты, **не** перепроверено сейчас.")
    out.append("`plan-2026-07-26` — перепроверено при составлении плана. `to-verify` —")
    out.append("статус ещё не установлен чтением кода, это первый шаг работы над пунктом.")
    out.append("")
    out.append("## Таблица")
    out.append("")
    out.append("| ID | P | status | method | Пакет | PR | Сервисы | Прод-верификация | Примечание |")
    out.append("|---|---|---|---|---|---|---|---|---|")
    for it in sorted(open_items, key=lambda x: (ASSIGNMENT.get(x.ident, {}).get("pkg", "zz"), x.ident)):
        a = ASSIGNMENT.get(it.ident, {})
        out.append(
            "| `{id}` | {p} | {st} | {m} | {pkg} | {pr} | {svc} | {prod} | {note} |".format(
                id=it.ident,
                p=it.priority,
                st=a.get("status", "**UNASSIGNED**"),
                m=a.get("method", "—"),
                pkg=a.get("pkg", "—"),
                pr=a.get("pr", "—"),
                svc=a.get("services", "—"),
                prod=a.get("prod", "—"),
                note=a.get("note", ""),
            )
        )
    out.append("")
    out.append("## Спорные пункты, разведённые явно")
    out.append("")
    out.append("_История разведения (что и когда решили); текущее состояние — в таблицах выше._")
    out.append("")
    out.append("- `REG-03` — был закрыт кодом, но открыт документом; подтверждён чтением")
    out.append("  `ci.yml` и закрыт 2026-07-26. Пример класса «код впереди документа».")
    out.append("- `AUD5-APIFE-2` — закрыт PR #263, документ поправлен PR #264.")
    out.append("- `PENT-F04` — основная часть закрыта раньше; календарный остаток")
    out.append("  (query-токен WS) снят 2026-08-30 (PR #516).")
    out.append("- `AUD3-37` — не назывался в первых версиях плана, шёл как `decision`;")
    out.append("  закрыт 2026-08-07 (Программа B, парой с `AUD5-CODE-6`).")
    out.append("- `PENT-F13`, `PENT-F14`, `PENT-F15`, `PENT-F16` — каждый отдельной строкой:")
    out.append("  сокращение группы «F12/F13/F15/F16» ранее скрыло потерю `PENT-F14`.")
    out.append("  F14/F15/F16 закрыты 2026-09-02; открыт только `PENT-F13` (CAA + DNSSEC у регистратора).")
    out.append("- `AUD5-PRAC-3` и `AUD3-38` — дубль друг друга; закрыты парой 2026-07-27.")
    out.append("")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="перегенерировать манифест")
    ap.add_argument("--check", action="store_true", help="инвариант: 0 бесхозных ID")
    ap.add_argument("--aggregate", action="store_true", help="только числа")
    args = ap.parse_args()

    items = parse(BACKLOG.read_text(encoding="utf-8"))
    open_items = [x for x in items if x.state == "open"]

    if args.aggregate or not (args.write or args.check):
        print(f"пунктов с Priority: {len(items)}")
        print(f"закрыто маркером:   {len(items) - len(open_items)}")
        print(f"открыто маркером:   {len(open_items)}")
        for st in sorted({ASSIGNMENT.get(x.ident, {}).get("status", "UNASSIGNED") for x in open_items}):
            n = sum(1 for x in open_items if ASSIGNMENT.get(x.ident, {}).get("status", "UNASSIGNED") == st)
            print(f"  {st}: {n}")

    rc = 0
    if args.check:
        ids = {x.ident for x in open_items}
        orphans = sorted(ids - ASSIGNMENT.keys())
        stale = sorted(ASSIGNMENT.keys() - ids)
        if orphans:
            print("ОТКРЫТЫЕ ПУНКТЫ БЕЗ ПАКЕТА (так теряются ID):", file=sys.stderr)
            for i in orphans:
                print(f"  {i}", file=sys.stderr)
            rc = 1
        if stale:
            print("В ASSIGNMENT есть ID, которых нет среди открытых (закрыты?):", file=sys.stderr)
            for i in stale:
                print(f"  {i}", file=sys.stderr)
            rc = 1
        # Сгенерированный файл должен совпадать с текущей генерацией, иначе в
        # репозитории лежит манифест от прошлого состояния бэклога — то же
        # расхождение документа с реальностью, только этажом выше.
        if MANIFEST.exists() and MANIFEST.read_text(encoding="utf-8") != render(items):
            print(
                "Манифест устарел относительно бэклога/ASSIGNMENT — "
                "перегенерировать: python3 scripts/backlog_manifest.py --write",
                file=sys.stderr,
            )
            rc = 1
        elif not MANIFEST.exists():
            print(f"Манифест отсутствует: {MANIFEST}", file=sys.stderr)
            rc = 1
        if rc == 0:
            print(f"OK: {len(ids)} открытых пунктов, все распределены; манифест актуален")

    if args.write:
        MANIFEST.write_text(render(items), encoding="utf-8")
        print(f"записан {MANIFEST.relative_to(ROOT)}")

    return rc


if __name__ == "__main__":
    sys.exit(main())
