## VAN‑обзор: UK Management Bot

### Среда выполнения (Host)
- OS: darwin 24.5.0
- Shell: /bin/zsh
- Рабочая директория: `/Users/andreyafanasyev/Library/Mobile Documents/com~apple~CloudDocs/Code/UK`
- Виртуальное окружение: venv (локальная разработка)

### Контейнеры на хосте (для справки, проект их не использует)
- infrasafe-frontend-1 — Up (healthy)
- infrasafe-app-1 — Up (healthy)
- infrasafe-postgres-1 (PostgreSQL/PostGIS) — Up (healthy) — не изменяем и не удаляем
- infrasafe-prometheus-1, infrasafe-grafana-1, infrasafe-node-exporter-1 — Up

Проект UK Management Bot запускается локально без Docker. При любых обновлениях контейнеры не трогаем; БД‑контейнер хранит рабочие данные.

---

### Стек и входные точки
- Python 3.11+, Aiogram 3.x, SQLAlchemy, SQLite (по умолчанию для dev)
- Точка входа: `uk_management_bot/main.py`
- Конфиг: `uk_management_bot/config/settings.py` (в т.ч. абсолютный `DATABASE_URL`, локали, роли/статусы)

### Структура (сокращённо)
- `handlers/`: `base.py`, `auth.py`, `requests.py`, `shifts.py`, `admin.py`
- `keyboards/`: базовые/заявки/смены (Reply/Inline)
- `services/`: `auth_service.py`, `request_service.py`, `shift_service.py`, `notification_service.py`
- `middlewares/`: `auth.py`, `role_mode` (в составе `auth.py`), `shift.py`, `localization.py`, `logging.py`
- `database/models/`: `user.py`, `request.py`, `shift.py`, `rating.py`, `audit.py`
- `utils/`: `helpers.py`, `validators.py`, `address_helpers.py`, `constants.py`
- `config/locales/`: `ru.json`, `uz.json`
- Тесты: `test_*.py` в корне

### Модель данных (ORM)
- `User`: `roles` (JSON‑строка), `active_role`, историческое `role`, `status`, `language`, адреса (`home/apartment/yard`), `specialization`
- `Request`: категории/срочность/адрес/описание, `status`, `media_files` (JSON), `executor_id`, `notes`, `completed_at`; связь `ratings`
- `Shift`: `user_id`, `start_time/end_time`, `status`, `notes`
- `Rating`, `AuditLog` (JSON `details`)

### Ключевые потоки
- Роли/режимы: `auth_middleware` + `role_mode_middleware` формируют `data['user']`, `data['roles']`, `data['active_role']`
- Заявки (FSM): категории → адрес → описание → срочность → медиа → подтверждение → сохранение; просмотр/фильтры/пагинация; изменения статусов с RBAC и аудитом
- Смены: `ShiftService` (start/end/force_end), `shift_context_middleware` добавляет `data['shift_context'] = { is_active, shift }`
- Уведомления: стандартизированные тексты, async‑рассылка для заявок и смен
- Локализация: безопасные загрузка и фолбэк через `utils/helpers.get_text` (RU/UZ)

### Тестирование
- Запуск: `pytest -q`
- Покрытие: ключевые сервисы, middleware, локализация, FSM‑потоки заявок и смен
- Текущее состояние: зелёный прогон (см. `activeContext.md` / `tasks.md`)

### Уровень сложности (ACM)
- Level 3 (Feature): полноценные доменные потоки (RBAC, заявки, смены, уведомления, локализация, тесты)

---

### Активный фокус
- Режим: PLAN / Эпик AUTH (P1)
- Ближайшие задачи (P1):
  - AUTH‑1: Политика статусов — базовые ограничения (middleware + ранние проверки)
  - AUTH‑2: Локализация статусов и блокировок (RU/UZ)
  - AUTH‑3: Онбординг заявителя (телефон + базовый адрес)
  - AUTH‑10: Профиль — отображение статуса/ролей/телефона и адресов

### Риски и долги
- Безопасность: в README упомянута временная выдача админа по дефолтному паролю (`12345`) — нужно запретить по умолчанию и требовать env‑переменную
- Rate‑limit на переключение роли реализован в памяти процесса — ок для dev; для прод требуется вынос в Redis (флаг/конфиг)

### Next steps (приоритет)
1) AUTH P1 (см. выше): ограничения/локализация/онбординг/профиль
2) Устранить дефолтный админ‑пароль: только через env, обновить README и проверки
3) Поддержать опциональный Redis для rate‑limit (конфиг) без изменения публичного API

---

### Готовность и запуск (локально)
- Установить зависимости: `pip install -r requirements.txt && pip install -r uk_management_bot/requirements.txt`
- Настроить окружение (пример): `BOT_TOKEN`, `ADMIN_USER_IDS`, `LOG_LEVEL`
- Запуск: `python -m uk_management_bot.main`


