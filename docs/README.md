# 📚 UK Management Bot - Документация

> _Последнее редактирование: 2026-07-06_

**Дата обновления**: 21.10.2025  
**Версия**: 2.0.0 (Phase 2B Production)

> 🧭 **Актуальность доков проверена 2026-07-06** — см. **[DOCUMENTATION_STATUS.md](DOCUMENTATION_STATUS.md)**
> (матрица «есть/актуально» по всем подсистемам; какие доки 🟢/🔴/⚫). Новое:
> **[MATERIALS_MODULE.md](MATERIALS_MODULE.md)** (модуль «Склад материалов»). Многие файлы
> ниже помечены как исторические — ориентируйтесь на статус-отчёт.

---

## 🗺️ Карта документации (актуально, 2026-07-06)

Канонический комплект. Файлы вне этих разделов — легаси/исторические (см. статус-отчёт).

**Продукт**
- [product/OVERVIEW.md](product/OVERVIEW.md) — продуктовое описание (роли, каналы, домены, границы)

**Технические документы** (`tech/`)
- [tech/ARCHITECTURE.md](tech/ARCHITECTURE.md) — архитектура, контейнеры, потоки данных, auth
- [tech/DATA_MODEL.md](tech/DATA_MODEL.md) — модель данных, ERD (+ [DATABASE_SCHEMA_ACTUAL.md](DATABASE_SCHEMA_ACTUAL.md))
- [tech/API_REFERENCE.md](tech/API_REFERENCE.md) — `/api/v2/*`, RBAC-матрица, web-auth
- [tech/REQUESTS.md](tech/REQUESTS.md) — домен «Заявки» (статусы, назначение, приёмка)
- [tech/SHIFTS_AND_ASSIGNMENT.md](tech/SHIFTS_AND_ASSIGNMENT.md) — смены + движок назначения (5 классов)
- [tech/ROLES_AND_ACCESS.md](tech/ROLES_AND_ACCESS.md) — роли (RBAC), матрица доступа, `admin` vs `system_admin`
- [MATERIALS_MODULE.md](MATERIALS_MODULE.md) — модуль «Склад материалов» (FIFO)
- [access-control/TECHNICAL_SPEC.md](access-control/TECHNICAL_SPEC.md) — контроль доступа (ANPR/пропуска)

**Инструкции по ролям** (`guides/`)
- [guides/USER_GUIDE_APPLICANT.md](guides/USER_GUIDE_APPLICANT.md) — житель
- [guides/USER_GUIDE_EXECUTOR.md](guides/USER_GUIDE_EXECUTOR.md) — исполнитель
- [guides/USER_GUIDE_MANAGER.md](guides/USER_GUIDE_MANAGER.md) — менеджер
- [guides/USER_GUIDE_INSPECTOR.md](guides/USER_GUIDE_INSPECTOR.md) — обходчик
- [guides/ADMIN_GUIDE.md](guides/ADMIN_GUIDE.md) — system_admin

**Эксплуатация и разработка**
- [ops/RUNBOOK.md](ops/RUNBOOK.md) — деплой, откат, порты, свежие грабли
- [DEVELOPMENT.md](DEVELOPMENT.md) — dev-окружение бота+фронта, «как добавить страницу»
- [LOCALIZATION_GUIDE.md](LOCALIZATION_GUIDE.md) — локализация (бот + фронт i18next)

**Статус документации:** [DOCUMENTATION_STATUS.md](DOCUMENTATION_STATUS.md)

---

## 🎯 Быстрый старт

- **[README.md](README.md)** - Главное описание проекта
- **[QUICK_START.md](QUICK_START.md)** - Быстрый запуск бота
- **[DEVELOPMENT.md](DEVELOPMENT.md)** - Руководство по разработке

---

## 🏗️ Архитектура и проектирование

- **[ARCHITECTURE_DIAGRAMS.md](ARCHITECTURE_DIAGRAMS.md)** - Диаграммы архитектуры
- **[design_claude.md](design_claude.md)** - Дизайн-документация
- **[project.md](project.md)** - Описание проекта

---

## 🔧 Конфигурация и развертывание

### Docker
- **[DOCKER_SETUP.md](DOCKER_SETUP.md)** - Настройка Docker окружения

---

## 💾 База данных

- **[DATABASE_README.md](DATABASE_README.md)** - Общая документация по БД
- **[DATABASE_SCHEMA_ACTUAL.md](DATABASE_SCHEMA_ACTUAL.md)** - Актуальная схема БД

---

## 🔐 Безопасность

- **[SECURITY_AUDIT_FINAL.md](SECURITY_AUDIT_FINAL.md)** - Финальный аудит безопасности
- **[SECURITY_STATUS.md](SECURITY_STATUS.md)** - Статус безопасности
- **[CONTEXT7_COMPLIANCE_REPORT.md](CONTEXT7_COMPLIANCE_REPORT.md)** - Compliance отчет

---

## 📖 Пользовательские руководства

### Система назначения заявок
- **[USER_GUIDE_REQUEST_ASSIGNMENT.md](USER_GUIDE_REQUEST_ASSIGNMENT.md)** - Пользовательское руководство
- **[TECHNICAL_GUIDE_REQUEST_ASSIGNMENT.md](TECHNICAL_GUIDE_REQUEST_ASSIGNMENT.md)** - Техническое руководство
- **[REQUEST_ASSIGNMENT_SYSTEM.md](REQUEST_ASSIGNMENT_SYSTEM.md)** - Описание системы

### Работа с заявками
- **[requests.md](requests.md)** - Документация по заявкам

### Система смен
- **[shifts.md](shifts.md)** - Документация по сменам
- **[SHIFT_SYSTEM_ANALYSIS.md](SHIFT_SYSTEM_ANALYSIS.md)** - Анализ системы смен

### Медиа
- **[photo.md](photo.md)** - Работа с фотографиями

---

## 🧪 Тестирование

- **[MANUAL_TESTING_GUIDE.md](MANUAL_TESTING_GUIDE.md)** - Руководство по ручному тестированию

---

## 🎓 Справочники

- **[FAQ.md](FAQ.md)** - Часто задаваемые вопросы
- **[TROUBLESHOOTING.md](TROUBLESHOOTING.md)** - Решение проблем

---

## 📊 Статус и отчеты

- **[PROJECT_COMPLETION_REPORT.md](PROJECT_COMPLETION_REPORT.md)** - Итоговый отчет проекта
- **[Claude_audit.md](Claude_audit.md)** - Аудит проекта

---

## 📁 Архив

Устаревшие документы перемещены в архив:

- **Migration/** - Отчеты по миграциям
- **Phase_Reports/** - Отчеты по фазам разработки
- **Database/** - Устаревшие документы по БД
- **Issues/** - Документы по исправлению багов
- **Old_Docs/** - Устаревшие документы

---

## 🔄 История изменений

### 21.10.2025 - Реорганизация документации
- ✅ Перемещены актуальные документы в `docs/`
- ✅ Архивированы устаревшие документы в `docs/Archive/`
- ✅ Создан индекс документации
- ✅ Организована структура по категориям

---

## 📞 Поддержка

Для вопросов и предложений:
- Создайте issue в репозитории
- Свяжитесь с командой разработки


