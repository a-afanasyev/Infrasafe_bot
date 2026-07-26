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
    "PENT-F10": A(pkg="П2c", status="actionable", method="verified-2026-07-26",
                  note="profk чист (600/700 везде); остаток — .105 за ssh-блокером"),
    # П2d закрыт целиком 2026-07-26: `AUD5-PRAC-1` (канонический .env.example +
    # честный первый запуск в README), `AUD5-PRAC-7` (23 стухших дока в архив),
    # `AUD5-PRAC-8` (снапшот OpenAPI + CI-гейт).
    # ── П3
    # П3a (`AUD5-CODE-7`) закрыт 2026-07-26: ERROR+проброс вместо молчаливой
    # подмены applicant-клавиатурой; фактическая строка была :59, не :54-55.
    "AUD3-12": A(pkg="П3b", status="actionable", method="plan-2026-07-26",
                 note="нужен выбор atomic / partial-success до кода"),
    "AUD3-13": A(pkg="П3c", status="actionable", method="doc-2026-07-14"),
    "BUG-128": A(pkg="П3d", status="actionable", method="to-verify"),
    "WR-06": A(pkg="П3d", status="actionable", method="doc-2026-07-14",
               note="4 реальных сайта из 70"),
    # ── П4: доска менеджера
    "AUD5-APIFE-7": A(pkg="П4", status="actionable", method="plan-2026-07-26"),
    "AUD5-APIFE-8": A(pkg="П4", status="actionable", method="plan-2026-07-26",
                      note="AC «активный фильтр» недостижим: useKanban() без фильтров"),
    "AUD5-APIFE-3": A(pkg="П4", status="actionable", method="plan-2026-07-26",
                      note="сначала retention-решение, иначе колонки опустеют"),
    # ── П5: расходящиеся копии
    "AUD5-CODE-8": A(pkg="П5a", status="actionable", method="doc-2026-07-21"),
    "AUD5-CODE-9": A(pkg="П5a", status="actionable", method="doc-2026-07-21"),
    "AUD3-14": A(pkg="П5a", status="actionable", method="doc-2026-07-14"),
    "AUD5-APIFE-13": A(pkg="П5b", status="actionable", method="doc-2026-07-21"),
    # ── П6
    "AUD3-08": A(pkg="П6a", status="actionable", method="plan-2026-07-26",
                 note="6 call-site: 1 publisher + 5 subscriber-фабрик, 5 каналов"),
    "AUD3-09": A(pkg="П6b", status="actionable", method="doc-2026-07-14"),
    "AUD5-CODE-5": A(pkg="П6c", status="actionable", method="doc-2026-07-21"),
    "AUD5-CODE-11": A(pkg="П6d", status="actionable", method="doc-2026-07-21"),
    "WR-05": A(pkg="П6", status="actionable", method="doc-2026-06-20"),
    "AUD5-ARCH-7": A(pkg="П6", status="actionable", method="to-verify",
                     note="гонка требует подтверждения до работы"),
    # ── Программа B: sync-ORM в async-контуре
    "AUD3-37": A(pkg="B", status="decision", method="doc-2026-07-14",
                 note="выбор: AsyncSession или sync unit-of-work в to_thread"),
    "AUD5-CODE-6": A(pkg="B", status="decision", method="doc-2026-07-21"),
    # ── П7
    "AUD5-DEAD-1": A(pkg="П7a", status="actionable", method="doc-2026-07-21"),
    "AUD5-DEAD-2": A(pkg="П7a", status="actionable", method="doc-2026-07-21"),
    "AUD5-DEAD-4": A(pkg="П7a", status="actionable", method="doc-2026-07-21"),
    "AUD5-DEAD-5": A(pkg="П7b", status="actionable", method="doc-2026-07-21"),
    "AUD5-PRAC-11": A(pkg="П7c", status="actionable", method="plan-2026-07-26",
                      note="127 E/F в scripts, много ручного разбора"),
    "AUD5-JUNK-1": A(pkg="П7d", status="actionable", method="doc-2026-07-21"),
    "REFACTOR-113": A(pkg="П7e", status="actionable", method="doc-2026-06-06"),
    "AUD5-DEAD-6": A(pkg="П7", status="doc-closed", method="plan-2026-07-26",
                     note="каталога нет в git — закрывается текстом"),
    "AUD5-JUNK-5": A(pkg="П7", status="no-pr", method="plan-2026-07-26",
                     note="локальные venv/db/png — только пофайлово с подтверждения"),
    "AUD5-PRAC-10": A(pkg="П7", status="no-pr", method="plan-2026-07-26"),
    # ── П8: i18n
    "AUD5-CODE-12": A(pkg="П8", status="actionable", method="plan-2026-07-26",
                      note="остался только user_apartment_selection.py:407"),
    "FS-11": A(pkg="П8", status="actionable", method="doc-2026-07-14"),
    "AUD5-APIFE-17": A(pkg="П8", status="actionable", method="plan-2026-07-26",
                       note="остался только LoginPage.tsx:140 (OTP)"),
    # ── П9
    "AUD5-APIFE-15": A(pkg="П9a", status="actionable", method="doc-2026-07-21"),
    "AUD5-JUNK-2": A(pkg="П9b", status="decision", method="doc-2026-07-21",
                     note="channels.json — решение владельца"),
    # ── П10: security-программа
    "PENT-F11": A(pkg="П10", status="actionable", method="doc-2026-07-14"),
    "AUD3-35": A(pkg="П10", status="actionable", method="doc-2026-07-14",
                 note="уточняет PENT-F11, не дубликат"),
    "AUD3-34": A(pkg="П10", status="actionable", method="doc-2026-07-01"),
    "AUD5-SEC-NEW-2": A(pkg="П10", status="actionable", method="doc-2026-07-21"),
    "AUD5-SEC-NEW-3": A(pkg="П10", status="actionable", method="doc-2026-07-21"),
    "AUD5-SEC-NEW-4": A(pkg="П10", status="actionable", method="to-verify"),
    "SEC-124": A(pkg="П10", status="actionable", method="doc-2026-07-21",
                 note="prod fail-fast vs dev без пароля — реализации разные"),
    "AUD3-36": A(pkg="П10", status="actionable", method="doc-2026-07-01"),
    "AUD5-ARCH-6": A(pkg="П10", status="actionable", method="doc-2026-07-21"),
    "PENT-F05": A(pkg="П10", status="actionable", method="plan-2026-07-26",
                  note="остаток: Origin до accept() + edge limit_req с burst-тестом"),
    # ── П11: тесты и покрытие
    "AUD5-PRAC-6": A(pkg="П11", status="actionable", method="plan-2026-07-26",
                     note="floors 40/38/29/30; TWA-тесты есть, floor'а нет"),
    "TEST-068": A(pkg="П11", status="actionable", method="plan-2026-07-26"),
    "AUD5-PRAC-4": A(pkg="П11", status="decision", method="doc-2026-07-21",
                     note="nightly/stage или «ручной инструмент»"),
    "AUD3-25": A(pkg="П11", status="actionable", method="doc-2026-07-14"),
    "AUD3-26": A(pkg="П11", status="actionable", method="doc-2026-07-01"),
    "AUD5-DEP-2": A(pkg="П11", status="actionable", method="doc-2026-07-21"),
    # ── Программа A: архитектура
    "AUD5-ARCH-2": A(pkg="A1", status="actionable", method="doc-2026-07-21"),
    "AUD3-07": A(pkg="A2", status="actionable", method="plan-2026-07-26",
                 note="168 .query( = 159 db.query + 9 db_local.query"),
    "AUD5-ARCH-1": A(pkg="A2", status="actionable", method="plan-2026-07-26"),
    "AUD5-ARCH-3": A(pkg="A3", status="decision", method="plan-2026-07-26",
                     note="scope: core-15 / +access_control 17 / +media 19; иначе respec"),
    "AUD3-06": A(pkg="A3", status="actionable", method="doc-2026-07-14"),
    "AUD5-ARCH-5": A(pkg="A4", status="actionable", method="doc-2026-07-21"),
    "AUD5-CODE-13": A(pkg="A4", status="actionable", method="doc-2026-07-21"),
    "AUD3-27": A(pkg="A4", status="actionable", method="plan-2026-07-26",
                 note="политика, а не точечный баг: ещё и shift_planning_service.py"),
    "AUD5-CODE-10": A(pkg="A5", status="actionable", method="doc-2026-07-21"),
    "AUD3-15": A(pkg="A6", status="actionable", method="doc-2026-07-01"),
    "AUD5-ARCH-4": A(pkg="A7", status="decision", method="doc-2026-07-21",
                     note="нужна целевая архитектура границы"),
    # ── Решения владельца (кодовой работы до решения нет)
    "AUD5-DEAD-3": A(pkg="—", status="decision", method="doc-2026-07-21"),
    "AUD5-JUNK-3": A(pkg="—", status="decision", method="doc-2026-07-21"),
    "AUD5-JUNK-4": A(pkg="—", status="decision", method="doc-2026-07-21"),
    "AUD3-32": A(pkg="—", status="decision", method="doc-2026-07-14",
                 note="дефферал устарел: публичный /announcements без auth"),
    "AUD3-33": A(pkg="—", status="decision", method="plan-2026-07-26",
                 note="сформулирован как принятый риск — подтвердить, не «чинить»"),
    "ARCH-116": A(pkg="—", status="decision", method="doc-2026-07-01"),
    "AUD5-YAGNI-1": A(pkg="—", status="decision", method="doc-2026-07-21"),
    "SEC-115": A(pkg="—", status="decision", method="doc-2026-06-12"),
    "ARCH-107": A(pkg="—", status="decision", method="doc-2026-06-12"),
    "DB-049": A(pkg="—", status="decision", method="doc-2026-06-12"),
    "ARCH-06": A(pkg="—", status="decision", method="doc-2026-06-12"),
    "AUD5-PRAC-3": A(pkg="—", status="decision", method="doc-2026-07-21",
                     note="дубль AUD3-38 — закрывать парой"),
    "AUD3-38": A(pkg="—", status="decision", method="doc-2026-07-01",
                 note="дубль AUD5-PRAC-3"),
    "PENT-F12": A(pkg="—", status="decision", method="doc-2026-07-24"),
    "PENT-F13": A(pkg="—", status="decision", method="doc-2026-07-24"),
    "PENT-F15": A(pkg="—", status="decision", method="doc-2026-07-24"),
    "PENT-F16": A(pkg="—", status="decision", method="doc-2026-07-24"),
    "FS-08": A(pkg="—", status="decision", method="doc-2026-07-14",
               note="needs-prod-data"),
    "FS-14": A(pkg="—", status="decision", method="doc-2026-06-20",
               note="needs-repro"),
    "QA22-04": A(pkg="—", status="decision", method="doc-2026-06-22"),
    # ── Календарь
    "PENT-F04": A(pkg="—", status="calendar", method="plan-2026-07-26",
                  note="остаток — снятие ?token= после 2026-09-01"),
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
