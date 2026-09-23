# Архив: документы из корня `docs/`, перенесённые 2026-09-23 (A9-P3-28)

**Ничего здесь не обновлять и ни на что здесь не опираться.** Это исторические
отчёты и устаревшие справочники (в основном 2025 года). Они оставлены только
чтобы не терять контекст решений; ссылки внутри них относительные на момент
написания и могут не работать.

Прецедент и правило — [../2026-07-26-stale-docs/README.md](../2026-07-26-stale-docs/README.md):
документ, противоречащий коду, либо правится, либо уезжает в архив.

## Что перенесено и куда смотреть вместо этого

| Файл | Что это | Актуальный источник |
|---|---|---|
| `PROJECT_FINAL_REPORT.md`, `PROJECT_COMPLETION_REPORT.md`, `PROJECT_ARCHIVE_REPORT.md`, `PROJECT_REQUEST_REPORT.md` | итоговые отчёты фаз 2025 года | [`docs/audit/2026-05-20-backlog.md`](../../audit/2026-05-20-backlog.md) |
| `FINAL_REORGANIZATION_REPORT.md`, `DOCUMENTATION_REORGANIZATION.md`, `GIT_COMMIT_FILES.txt`, `UNIFIED_FILES_SUMMARY.txt` | отчёты о прошлых реорганизациях репо/доков | [`docs/README.md`](../../README.md) |
| `ARCHIVE_EMPLOYEE_MANAGEMENT_IMPROVEMENTS.md` | отчёт сессии 2025-08 | `docs/guides/USER_GUIDE_MANAGER.md` |
| `design_claude.md` | архитектурное видение 2025-09 | [`docs/tech/ARCHITECTURE.md`](../../tech/ARCHITECTURE.md) |
| `ARCHITECTURE_DIAGRAMS.md` | диаграммы 2025-09 (микросервисный план) | [`docs/tech/ARCHITECTURE_DIAGRAMS.md`](../../tech/ARCHITECTURE_DIAGRAMS.md) |
| `project.md` | снимок структуры каталогов бота | корневой [`README.md`](../../../README.md) «Структура» |
| `TASK_15_ADDRESS_DIRECTORY.md` | отчёт о задаче «справочник адресов» (2025-10) | [`docs/tech/DATA_MODEL.md`](../../tech/DATA_MODEL.md) |
| `USER_GUIDE_REQUEST_ASSIGNMENT.md` | пользовательское руководство по назначению (2025-09; роли без приёмки/возврата) | `docs/guides/` |
| `FAQ.md` | FAQ 2025-09 | [`docs/user-guide/08-faq.md`](../../user-guide/08-faq.md) |
| `MANUAL_TESTING_GUIDE.md` | ручное тестирование 2025-10 (окружение `docker-compose.dev.yml` как «прод») | корневой `README.md` «Тесты», `make test-ci` |
| `photo.md` | спецификация MediaService на Telegram-каналах (2025-09) | `media_service/README.md`, `docs/tech/ARCHITECTURE.md` §3.2 |
| `shifts.md` | продуктовый обзор смен (сам помечал себя «не истина») | [`docs/tech/SHIFTS_AND_ASSIGNMENT.md`](../../tech/SHIFTS_AND_ASSIGNMENT.md), `docs/guides/SHIFTS.md` |

Аудиторские и security-отчёты той же волны перенесены не сюда, а в
[`docs/audit/`](../../audit/): `security-audit-2026-05-29.md`,
`secret-rotation-checklist-2026-05-29.md`, `security-hardening-plan.md`,
`request_lifecycle_audit.md`, `i18n-coverage-2026-03-23.md`, `Claude_audit.md`,
`CONTEXT7_COMPLIANCE_REPORT.md`, пентест profk из корня репо
(`codex_audit.md` → `2026-07-11-profk-pentest-codex.md`) и бывший корневой
каталог `audit/` → `2026-03-system-analysis/`.
