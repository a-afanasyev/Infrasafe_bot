# Архив: документы, перенесённые 2026-07-26 (AUD5-PRAC-7)

**Ничего здесь не обновлять и ни на что здесь не опираться.** Это исторические
снимки; они противоречат текущему коду и оставлены только чтобы не терять
контекст решений.

## Почему перенесены

`AUD5-PRAC-7`: индекс `docs/DOCUMENTATION_STATUS.md` сам помечал эти файлы
🔴 («сильно устарело / вводит в заблуждение») и ⚫ («исторический архив»), но
лежали они в корне `docs/` вперемешку с актуальными. Пометка в индексе не
защищает: человек (и агент) открывает файл по имени, а не через матрицу статусов.
Физическое разделение — единственное, что реально работает.

## Что и почему устарело

| Файл | Было | Чем противоречит коду |
|---|---|---|
| `REQUEST_ASSIGNMENT_SYSTEM.md` | 🔴 | удалённые сервисы/хендлеры, «несуществующая» alembic-миграция, устаревший статусный контур |
| `TECHNICAL_GUIDE_REQUEST_ASSIGNMENT.md` | 🔴 | `models/assignment.py` → реально `database/models/request_assignment.py`; класс `Assignment` → `RequestAssignment`; роли без inspector/system_admin |
| `requests.md` | 🔴 | `AssignmentOptimizer`/`GeoOptimizer` удалены (ARC-04); жив только SmartDispatcher |
| `DATABASE_SCHEMA_ACTUAL.md` | 🔴 | 23 таблицы по состоянию 2025-10: нет `access_control` и materials; документирует удалённое поле `users.role` |
| `DATABASE_README.md` | 🔴 | «27 таблиц», «Alembic — Week 3» (alembic давно боевой; история сжата в baseline 001+002, PRC-05) |
| `TROUBLESHOOTING.md` | 🔴 | контейнеры `*-dev` и таблица `assignments` не существуют; `cp env.example .env` — файла нет с 2026-07-26 |
| `QUICK_START.md`, `DEVELOPMENT.md` | 🔴/🟡 | pre-Docker `python main.py`, SQLite-легаси, `production.env.example` (удалён) |
| `SECURITY_AUDIT_FINAL.md`, `SECURITY_STATUS.md` | 🔴 | «0 critical / PRODUCTION READY» от 15.10.2025 — прямо противоречит найденному позже MFA-bypass (`SEC-01`) |
| `ux-audit-report.md`, `modernization-architecture-plan.md` | ⚫ | до-модернизационный AS-IS; описанное уже реализовано |
| `SHIFT_SYSTEM_ANALYSIS.md`, `TASK_16_*`, `TASK_17_*`, `AUTH_P1/P2/P3_COMPLETED.md` | ⚫ | отчёты о завершённых задачах |
| `РАЗДЕЛ_1..6_*.md` | ⚫ | отчёты по разделам, все помечены «✅ ЗАВЕРШЕНА» |

`РАЗДЕЛ_2_СИСТЕМА_ЗАЯВКОВ.md` — тот самый дубль с опечаткой в имени
(«ЗАЯВКОВ» вместо «ЗАЯВОК») из формулировки пункта. Он **не** копия: это
отдельный 40-строчный фрагмент про раздел 2.5 «Просмотр заявок — Архивация»,
которого в правильно названном файле нет. Поэтому он перенесён, а не удалён —
удаление потеряло бы содержимое.

## Куда смотреть вместо этого

| Тема | Актуальный источник |
|---|---|
| Быстрый старт, миграции, тесты | [`README.md`](../../../README.md) |
| Процедуры деплоя, роли БД, Doppler | `.claude/skills/uk-deploy/SKILL.md` |
| Схема БД | `alembic/versions/` (baseline 001 + 002 и далее) — единственный источник истины |
| Задачи и статусы | [`docs/audit/2026-05-20-backlog.md`](../../audit/2026-05-20-backlog.md) + генерируемый манифест рядом |
| Индекс документации | [`docs/README.md`](../../README.md), матрица статусов — [`docs/DOCUMENTATION_STATUS.md`](../../DOCUMENTATION_STATUS.md) |
