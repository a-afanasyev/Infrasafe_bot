# Манифест бэклога

> Генерируется: `python3 scripts/backlog_manifest.py --write`.
> Руками не править — правки вносить в `ASSIGNMENT` в скрипте.

## Зачем

Агрегаты бэклога расходились с реальностью двумя способами: метод счёта не был зафиксирован, и часть пунктов закрывалась кодом без закрытия документом. Здесь метод счёта — код скрипта, а распределение по пакетам проверяется инвариантом: `--check` падает, если у открытого пункта нет пакета. Ровно так был потерян `PENT-F14` — группа писалась сокращением.

## Метод счёта

- **Пункт** = заголовок `##`…`####`, в теле которого есть `**Priority:**`.
  Заголовки-разделы без Priority пунктами не являются по определению.
- **Закрыт** = заголовок зачёркнут (`~~`) **или** содержит `✅`/`❌`.
  Второе условие обязательно: часть пунктов закрыта словом без зачёркивания,
  и без этого закрытое считалось бы открытым.
- **Агрегаты считаются из этой таблицы**, а не пересказом.

## Агрегаты

- пунктов всего (с Priority): **401**
- закрыто маркером: **320**
- открыто маркером: **81**

  - `actionable` — **51**
  - `decision` — **26**
  - `calendar` — **1**
  - `no-pr` — **2**
  - `doc-closed` — **1**

Из них actionable по приоритету: P2=27, P3=24.

Значения `status`:

| status | смысл |
|---|---|
| `actionable` | работа в коде/конфиге, пакет обязателен |
| `decision` | ждёт решения владельца; до решения кодовой работы нет |
| `calendar` | работа определена, ждёт календарного срока |
| `no-pr` | работа вне PR (локальные файлы, потенциально деструктивно) |
| `doc-closed` | по коду закрыт, открыт только в документе |

Значения `method` — **чем** установлен статус. `doc-<дата>` означает: взято
из code-verified записи бэклога той даты, **не** перепроверено сейчас.
`plan-2026-07-26` — перепроверено при составлении плана. `to-verify` —
статус ещё не установлен чтением кода, это первый шаг работы над пунктом.

## Таблица

| ID | P | status | method | Пакет | PR | Сервисы | Прод-верификация | Примечание |
|---|---|---|---|---|---|---|---|---|
| `AUD5-ARCH-2` | P2 | actionable | doc-2026-07-21 | A1 | — | — | — |  |
| `AUD3-07` | P2 | actionable | plan-2026-07-26 | A2 | — | — | — | 168 .query( = 159 db.query + 9 db_local.query |
| `AUD5-ARCH-1` | P2 | actionable | plan-2026-07-26 | A2 | — | — | — |  |
| `AUD3-06` | P2 | actionable | doc-2026-07-14 | A3 | — | — | — |  |
| `AUD5-ARCH-3` | P2 | decision | plan-2026-07-26 | A3 | — | — | — | scope: core-15 / +access_control 17 / +media 19; иначе respec |
| `AUD3-27` | P3 | actionable | plan-2026-07-26 | A4 | — | — | — | политика, а не точечный баг: ещё и shift_planning_service.py |
| `AUD5-ARCH-5` | P2 | actionable | doc-2026-07-21 | A4 | — | — | — |  |
| `AUD5-CODE-13` | P3 | actionable | doc-2026-07-21 | A4 | — | — | — |  |
| `AUD5-CODE-10` | P3 | actionable | doc-2026-07-21 | A5 | — | — | — |  |
| `AUD3-15` | P2 | actionable | doc-2026-07-01 | A6 | — | — | — |  |
| `AUD5-ARCH-4` | P2 | decision | doc-2026-07-21 | A7 | — | — | — | нужна целевая архитектура границы |
| `AUD3-37` | P3 | decision | doc-2026-07-14 | B | — | — | — | выбор: AsyncSession или sync unit-of-work в to_thread |
| `AUD5-CODE-6` | P2 | decision | doc-2026-07-21 | B | — | — | — |  |
| `AUD3-34` | P3 | actionable | doc-2026-07-01 | П10 | — | — | — |  |
| `AUD3-35` | P3 | actionable | doc-2026-07-14 | П10 | — | — | — | уточняет PENT-F11, не дубликат |
| `AUD3-36` | P3 | actionable | doc-2026-07-01 | П10 | — | — | — |  |
| `AUD5-ARCH-6` | P3 | actionable | doc-2026-07-21 | П10 | — | — | — |  |
| `AUD5-SEC-NEW-2` | P3 | actionable | doc-2026-07-21 | П10 | — | — | — |  |
| `AUD5-SEC-NEW-3` | P3 | actionable | doc-2026-07-21 | П10 | — | — | — |  |
| `AUD5-SEC-NEW-4` | P3 | actionable | to-verify | П10 | — | — | — |  |
| `PENT-F05` | P2 | actionable | plan-2026-07-26 | П10 | — | — | — | остаток: Origin до accept() + edge limit_req с burst-тестом |
| `PENT-F11` | P3 | actionable | doc-2026-07-14 | П10 | — | — | — |  |
| `SEC-124` | P3 | actionable | doc-2026-07-21 | П10 | — | — | — | prod fail-fast vs dev без пароля — реализации разные |
| `SEC-131` | P3 | actionable | verified-2026-07-27 | П10 | — | media-service (.105) | — | MEDIA_BOT_TOKEN в .env на .105 — второй источник истины, :?-гард не срабатывает |
| `AUD3-25` | P3 | actionable | doc-2026-07-14 | П11 | — | — | — |  |
| `AUD3-26` | P3 | actionable | doc-2026-07-01 | П11 | — | — | — |  |
| `AUD5-DEP-2` | P3 | actionable | doc-2026-07-21 | П11 | — | — | — |  |
| `AUD5-PRAC-4` | P3 | decision | doc-2026-07-21 | П11 | — | — | — | nightly/stage или «ручной инструмент» |
| `AUD5-PRAC-6` | P3 | actionable | plan-2026-07-26 | П11 | — | — | — | floors 40/38/29/30; TWA-тесты есть, floor'а нет |
| `TEST-068` | P2 | actionable | plan-2026-07-26 | П11 | — | — | — |  |
| `PENT-F17` | P3 | actionable | plan-2026-07-26 | П2a | — | — | — | /uk/health отдаёт SPA index.html — мониторинг ложно зелёный |
| `PENT-F14` | P3 | actionable | verified-2026-07-26 | П2b | — | edge владельца (оба домена) | — | артефакт+инструкция готовы; ждёт публикации, .105 за ssh-блокером |
| `AUD5-APIFE-3` | P2 | actionable | plan-2026-07-26 | П4 | — | — | — | сначала retention-решение, иначе колонки опустеют |
| `AUD5-APIFE-7` | P2 | actionable | plan-2026-07-26 | П4 | — | — | — |  |
| `AUD5-APIFE-8` | P2 | actionable | plan-2026-07-26 | П4 | — | — | — | AC «активный фильтр» недостижим: useKanban() без фильтров |
| `AUD3-14` | P2 | actionable | doc-2026-07-14 | П5a | — | — | — |  |
| `AUD5-CODE-8` | P2 | actionable | doc-2026-07-21 | П5a | — | — | — |  |
| `AUD5-CODE-9` | P2 | actionable | doc-2026-07-21 | П5a | — | — | — |  |
| `AUD5-APIFE-13` | P2 | actionable | doc-2026-07-21 | П5b | — | — | — |  |
| `AUD5-ARCH-7` | P3 | actionable | to-verify | П6 | — | — | — | гонка требует подтверждения до работы |
| `WR-05` | P3 | actionable | doc-2026-06-20 | П6 | — | — | — |  |
| `AUD3-08` | P2 | actionable | plan-2026-07-26 | П6a | — | — | — | 6 call-site: 1 publisher + 5 subscriber-фабрик, 5 каналов |
| `AUD3-09` | P2 | actionable | doc-2026-07-14 | П6b | — | — | — |  |
| `AUD5-CODE-5` | P2 | actionable | doc-2026-07-21 | П6c | — | — | — |  |
| `AUD5-CODE-11` | P2 | actionable | doc-2026-07-21 | П6d | — | — | — |  |
| `AUD5-DEAD-6` | P3 | doc-closed | plan-2026-07-26 | П7 | — | — | — | каталога нет в git — закрывается текстом |
| `AUD5-JUNK-5` | P3 | no-pr | plan-2026-07-26 | П7 | — | — | — | локальные venv/db/png — только пофайлово с подтверждения |
| `AUD5-PRAC-10` | P3 | no-pr | plan-2026-07-26 | П7 | — | — | — |  |
| `AUD5-DEAD-1` | P2 | actionable | doc-2026-07-21 | П7a | — | — | — |  |
| `AUD5-DEAD-2` | P2 | actionable | doc-2026-07-21 | П7a | — | — | — |  |
| `AUD5-DEAD-4` | P2 | actionable | doc-2026-07-21 | П7a | — | — | — |  |
| `AUD5-DEAD-5` | P2 | actionable | doc-2026-07-21 | П7b | — | — | — |  |
| `AUD5-PRAC-11` | P2 | actionable | plan-2026-07-26 | П7c | — | — | — | 127 E/F в scripts, много ручного разбора |
| `AUD5-JUNK-1` | P3 | actionable | doc-2026-07-21 | П7d | — | — | — |  |
| `REFACTOR-113` | P3 | actionable | doc-2026-06-06 | П7e | — | — | — |  |
| `AUD5-APIFE-17` | P2 | actionable | plan-2026-07-26 | П8 | — | — | — | остался только LoginPage.tsx:140 (OTP) |
| `AUD5-CODE-12` | P2 | actionable | plan-2026-07-26 | П8 | — | — | — | остался только user_apartment_selection.py:407 |
| `FS-11` | P3 | actionable | doc-2026-07-14 | П8 | — | — | — |  |
| `AUD5-APIFE-15` | P2 | actionable | doc-2026-07-21 | П9a | — | — | — |  |
| `AUD5-JUNK-2` | P3 | decision | doc-2026-07-21 | П9b | — | — | — | channels.json — решение владельца |
| `ARCH-06` | P2 | decision | doc-2026-06-12 | — | — | — | — |  |
| `ARCH-107` | P2 | decision | doc-2026-06-12 | — | — | — | — |  |
| `ARCH-116` | P3 | decision | doc-2026-07-01 | — | — | — | — |  |
| `AUD3-32` | P3 | decision | doc-2026-07-14 | — | — | — | — | дефферал устарел: публичный /announcements без auth |
| `AUD3-33` | P3 | decision | plan-2026-07-26 | — | — | — | — | сформулирован как принятый риск — подтвердить, не «чинить» |
| `AUD3-38` | P3 | decision | doc-2026-07-01 | — | — | — | — | дубль AUD5-PRAC-3 |
| `AUD5-DEAD-3` | P2 | decision | doc-2026-07-21 | — | — | — | — |  |
| `AUD5-JUNK-3` | P3 | decision | doc-2026-07-21 | — | — | — | — |  |
| `AUD5-JUNK-4` | P3 | decision | doc-2026-07-21 | — | — | — | — |  |
| `AUD5-PRAC-3` | P2 | decision | doc-2026-07-21 | — | — | — | — | дубль AUD3-38 — закрывать парой |
| `AUD5-YAGNI-1` | P2 | decision | doc-2026-07-21 | — | — | — | — |  |
| `DB-049` | P2 | decision | doc-2026-06-12 | — | — | — | — |  |
| `FS-08` | P3 | decision | doc-2026-07-14 | — | — | — | — | needs-prod-data |
| `FS-14` | P3 | decision | doc-2026-06-20 | — | — | — | — | needs-repro |
| `PENT-F04` | P2 | calendar | plan-2026-07-26 | — | — | — | — | остаток — снятие ?token= после 2026-09-01 |
| `PENT-F12` | P3 | decision | doc-2026-07-24 | — | — | — | — |  |
| `PENT-F13` | P3 | decision | doc-2026-07-24 | — | — | — | — |  |
| `PENT-F15` | P3 | decision | doc-2026-07-24 | — | — | — | — |  |
| `PENT-F16` | P3 | decision | doc-2026-07-24 | — | — | — | — |  |
| `QA22-04` | P3 | decision | doc-2026-06-22 | — | — | — | — |  |
| `SEC-115` | P3 | decision | doc-2026-06-12 | — | — | — | — |  |

## Спорные пункты, разведённые явно

- `REG-03` — был закрыт кодом, но открыт документом; подтверждён чтением
  `ci.yml` и закрыт 2026-07-26. Пример класса «код впереди документа».
- `AUD5-APIFE-2` — закрыт PR #263, документ поправлен PR #264.
- `PENT-F04` — основная часть закрыта; остаток календарный (2026-09-01).
- `AUD3-37` — не назывался в первых версиях плана; здесь `decision`.
- `PENT-F13`, `PENT-F14`, `PENT-F15`, `PENT-F16` — каждый отдельной строкой:
  сокращение группы «F12/F13/F15/F16» ранее скрыло потерю `PENT-F14`.
- `AUD5-PRAC-3` и `AUD3-38` — дубль друг друга, закрывать парой.
