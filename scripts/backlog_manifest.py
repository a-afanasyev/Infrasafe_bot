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
    # ── П1 ЗАКРЫТ 2026-07-26 целиком: `AUD5-CODE-4`, `AUD5-APIFE-19`,
    # `AUD5-APIFE-18`, `AUD5-PRAC-5`, `AUD5-DEP-1`, `AUD5-PRAC-9` — все шесть
    # помечены закрытыми в бэклоге, поэтому строк здесь больше нет (`--check`
    # держит равенство ASSIGNMENT ↔ открытые пункты в обе стороны).
    # ── П2
    "PENT-F17": A(pkg="П2a", status="actionable", method="plan-2026-07-26",
                  note="/uk/health отдаёт SPA index.html — мониторинг ложно зелёный"),
    "PENT-F14": A(pkg="П2b", status="actionable", method="verified-2026-07-26",
                  services="edge владельца (оба домена)",
                  note="артефакт+инструкция готовы; ждёт публикации, .105 за ssh-блокером"),
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
    "AUD5-JUNK-5": A(pkg="П7", status="no-pr", method="plan-2026-07-26",
                     note="локальные venv/db/png — только пофайлово с подтверждения"),
    # П8 закрыт целиком 2026-07-27: `AUD5-CODE-12` (язык каждого админа),
    # `FS-11` (канон адреса + гейт), `AUD5-APIFE-17` (deep-link через MFA).
    # ── П8: i18n
    # ── П9
    # ── П10: security-программа
    "AUD5-ARCH-6": A(pkg="П10", status="actionable", method="doc-2026-07-21"),
    # ── П11: тесты и покрытие
    # `AUD5-PRAC-6` закрыт 2026-08-02: twa включён в знаменатель coverage ещё
    # PR #331 (волна 5 аудита #6, floors 41/39/31/32) — маркер отставал от кода.
    "TEST-068": A(pkg="П11", status="actionable", method="verified-2026-08-02",
                  note="floors уже 41/39/31/32 (#331, twa в знаменателе); остаток — ratchet до 80%"),
    "AUD3-25": A(pkg="П11", status="actionable", method="doc-2026-07-14"),
    # ── Программа A: архитектура
    "AUD3-07": A(pkg="A2", status="actionable", method="plan-2026-07-26",
                 note="168 .query( = 159 db.query + 9 db_local.query"),
    "BUG-137": A(pkg="A2", status="actionable", method="review-2026-08-10"),
    "AUD5-ARCH-1": A(pkg="A2", status="actionable", method="plan-2026-07-26"),
    "AUD5-ARCH-3": A(pkg="A3", status="actionable", method="verified-2026-07-27",
                     note="scope: core-15 / +access_control 17 / +media 19; иначе respec"),
    "AUD3-06": A(pkg="A3", status="actionable", method="doc-2026-07-14"),
    "BUG-138": A(pkg="A3", status="actionable", method="review-2026-08-10"),
    "BUG-139": A(pkg="A3", status="actionable", method="review-2026-08-11"),
    "AUD5-ARCH-5": A(pkg="A4", status="actionable", method="doc-2026-07-21"),
    "AUD5-CODE-13": A(pkg="A4", status="actionable", method="doc-2026-07-21"),
    "AUD3-27": A(pkg="A4", status="actionable", method="plan-2026-07-26",
                 note="политика, а не точечный баг: ещё и shift_planning_service.py"),
    "AUD5-CODE-10": A(pkg="A5", status="actionable", method="doc-2026-07-21"),
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
    "PENT-F12": A(pkg="—", status="actionable", method="verified-2026-07-27",
                 services="edge владельца (profk.uz)",
                 note="чек-лист отправлен: docs/audit/2026-07-27-edge-owner-checklist.md"),
    "PENT-F13": A(pkg="—", status="actionable", method="verified-2026-07-27",
                 services="edge владельца (profk.uz)",
                 note="чек-лист отправлен: docs/audit/2026-07-27-edge-owner-checklist.md"),
    "PENT-F15": A(pkg="—", status="actionable", method="verified-2026-07-27",
                 services="edge владельца (profk.uz)",
                 note="чек-лист отправлен: docs/audit/2026-07-27-edge-owner-checklist.md"),
    "PENT-F16": A(pkg="—", status="actionable", method="verified-2026-07-27",
                 services="edge владельца (profk.uz)",
                 note="чек-лист отправлен: docs/audit/2026-07-27-edge-owner-checklist.md"),
    # ── Деферралы, подтверждённые решением владельца 2026-07-27
    "ARCH-06": A(pkg="—", status="deferred", method="verified-2026-07-27",
                 note="возвращаться вместе с развязкой границы (AUD5-ARCH-4/A7)"),
    "DB-049": A(pkg="—", status="deferred", method="verified-2026-07-27",
                note="jsonb+GIN — когда появится запрос по ролям, которому нужен индекс"),
    "SEC-115": A(pkg="—", status="deferred", method="verified-2026-07-27",
                 note="фикс на стороне InfraSafe; в повестку следующего разговора"),
    # ── Календарь
    "PENT-F04": A(pkg="—", status="calendar", method="verified-2026-08-02",
                  note="остаток — снятие ?token= после 2026-09-01; зеркало панели охраны закрыто #335"),
    # ── Закрыто кодом, открыто документом
    # `REG-03` жил здесь до 2026-07-26: последний непокрытый периметр
    # (`media_service/requirements.txt`) закрыт PR #261, подтверждено чтением
    # `ci.yml`, пункт закрыт в бэклоге. Строка удалена, потому что `--check`
    # держит равенство ASSIGNMENT ↔ открытые пункты в обе стороны.
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
    for st in ("actionable", "decision", "calendar", "no-pr", "doc-closed", "UNASSIGNED"):
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
    out.append("- `REG-03` — был закрыт кодом, но открыт документом; подтверждён чтением")
    out.append("  `ci.yml` и закрыт 2026-07-26. Пример класса «код впереди документа».")
    out.append("- `AUD5-APIFE-2` — закрыт PR #263, документ поправлен PR #264.")
    out.append("- `PENT-F04` — основная часть закрыта; остаток календарный (2026-09-01).")
    out.append("- `AUD3-37` — не назывался в первых версиях плана; здесь `decision`.")
    out.append("- `PENT-F13`, `PENT-F14`, `PENT-F15`, `PENT-F16` — каждый отдельной строкой:")
    out.append("  сокращение группы «F12/F13/F15/F16» ранее скрыло потерю `PENT-F14`.")
    out.append("- `AUD5-PRAC-3` и `AUD3-38` — дубль друг друга, закрывать парой.")
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
