# Audit Remediation Plan — UK Management System

> _Последнее редактирование: 2026-05-21_

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Устранить критические и высокоприоритетные findings из аудита code-quality-audit-2026-04-13.md. Из 117 findings план покрывает **24 из 30 CRITICAL** и **27 из 35 HIGH** (remediation). Оставшиеся 6 CRITICAL и 8 HIGH вынесены в раздел «Accepted Risks» с обоснованием.

**Architecture:** Восемь фаз: (0) security hotfix, (1) удаление dead code, (2) repository-паттерн для DRY, (3) декомпозиция God-handlers, (4) декомпозиция God-services, (5) рефакторинг API-роутеров, (6) консолидация sync/async и исправление DI, (7) инфра и DX. Каждая фаза — самостоятельный рабочий блок с тестами.

**Tech Stack:** Python 3.11, SQLAlchemy (sync + async), aiogram 3, FastAPI, pytest, Docker Compose

**Контекст проекта:** Один разработчик, MVP для ЖК (~50 пользователей). Фокус на реальных проблемах: security, God-files, DRY, broken DI patterns.

---

## Phase 0: Security Hotfix (P0 — сегодня)

### Task 0.1: Ротация секретов и очистка .env из git

**Контекст:** .gitignore уже содержит `.env` (строка 105). Ранее секреты были в файлах `env.copy` и `env.copy.dev` (удалены из tracking в коммите `d2685b0`), но **остаются в git-истории**. SSL-сертификаты также в истории (коммит `0b27928`).

**Files:**
- Modify: `.gitignore` — добавить явные паттерны
- Purge from history: `env.copy`, `env.copy.dev`, `ssl/cert.pem`, `ssl/key.pem`

- [ ] **Step 0: Проверить текущее состояние tracking**

```bash
git ls-files | grep -E '\.env|env\.copy|\.pem|\.key'
# Если файлы отслеживаются — git rm --cached <file>
# Если нет — переходить к Step 1
```

- [ ] **Step 1: Очистить git-историю от секретов (ОБЯЗАТЕЛЬНО)**

Используем `git filter-repo` (предпочтительно) или BFG:

```bash
# Вариант A: git filter-repo
pip install git-filter-repo
git filter-repo --path env.copy --path env.copy.dev --path ssl/cert.pem --path ssl/key.pem --invert-paths --force

# Вариант B: BFG Repo Cleaner
# java -jar bfg.jar --delete-files "env.copy" --delete-files "env.copy.dev" .
# bfg --delete-files "cert.pem" --delete-files "key.pem" .

git reflog expire --expire=now --all
git gc --prune=now --aggressive
```

**ВАЖНО:** После history rewrite все SHA коммитов изменятся. Для solo-разработчика это безопасно. Потребуется `git push --force` (после подтверждения).

- [ ] **Step 2: Усилить .gitignore**

Добавить в `.gitignore`:
```gitignore
# Secrets — never track
.env
**/.env
!.env.example
!.env.*.template
!.env.*.example
ssl/*.pem
ssl/*.key
*.pem
*.key
```

- [ ] **Step 3: Создать .env.example из текущего .env**

Скопировать структуру `.env`, заменив все значения на плейсхолдеры:
```
BOT_TOKEN=your_bot_token_here
MEDIA_BOT_TOKEN=your_media_bot_token_here
ADMIN_PASSWORD=change_me_strong_password
INVITE_SECRET=generate_with_openssl_rand_base64_48
DATABASE_URL=postgresql://uk_bot:change_me@postgres:5432/uk_management
POSTGRES_USER=uk_bot
POSTGRES_PASSWORD=change_me
...
```

- [ ] **Step 4: Commit**

```bash
git add .gitignore .env.example
git commit -m "security: remove secrets from git tracking, add .env.example"
```

- [ ] **Step 5: Ротация всех скомпрометированных секретов**

Вручную (не автоматизируемо). Порядок ВАЖЕН — сначала генерируем всё, потом применяем атомарно:

**A. Генерация новых значений (локально, ничего не деплоим):**
1. Telegram: @BotFather → Revoke token для BOT_TOKEN и MEDIA_BOT_TOKEN → получить новые (ВНИМАНИЕ: бот уйдёт offline сразу после revoke)
2. Сгенерировать новый INVITE_SECRET: `openssl rand -base64 48`
3. Сгенерировать новый INFRASAFE_WEBHOOK_SECRET: `openssl rand -hex 32`
4. Сгенерировать новый SECRET_KEY для media_service: `openssl rand -hex 32`
5. Придумать новый ADMIN_PASSWORD
6. Придумать новый POSTGRES_PASSWORD

**B. Применение (атомарно, минимизируем downtime):**
7. Записать ВСЕ новые значения в `.env` на сервере
8. Сменить пароль БД: `ALTER USER uk_bot WITH PASSWORD 'new_password';`
9. Перезапустить ВСЕ контейнеры одновременно: `docker compose up -d --force-recreate`

**C. SSL-сертификаты:**
10. Если self-signed: `openssl req -x509 -newkey rsa:4096 -keyout ssl/key.pem -out ssl/cert.pem -days 365 -nodes`
11. Если CA-signed: запросить перевыпуск через CA

- [ ] **Step 6: Добавить pre-commit hook для детекции секретов**

```bash
# Добавить в .pre-commit-config.yaml:
- repo: https://github.com/Yelp/detect-secrets
  rev: v1.4.0
  hooks:
    - id: detect-secrets
      args: ['--baseline', '.secrets.baseline']

# Создать baseline:
detect-secrets scan > .secrets.baseline
```

### Task 0.2: Исправить SQL injection в скриптах

**Files:**
- Modify: `scripts/check_and_fix_db.py:86,114-118`
- Modify: `scripts/clean_old_data.py:77,113,118,182,185`

- [ ] **Step 1: Исправить check_and_fix_db.py**

Строка 86 — заменить f-string на whitelist:
```python
# BEFORE (line 86):
# conn.execute(text(f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {field_name} {field_type}"))

# AFTER:
ALLOWED_FIELDS = {
    "verification_status": "VARCHAR(20) DEFAULT 'pending'",
    "verified_at": "TIMESTAMP",
    "document_type": "VARCHAR(50)",
    # ... остальные поля из tuples на строках 80-82
}
for field_name, field_type in ALLOWED_FIELDS.items():
    conn.execute(text(
        f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {field_name} {field_type}"
    ))
```

Строки 114-118 — параметризовать:
```python
# BEFORE:
# result = conn.execute(text(f"SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = '{table}')"))

# AFTER:
ALLOWED_TABLES = {"users", "requests", "shifts", "request_assignments", ...}
if table not in ALLOWED_TABLES:
    raise ValueError(f"Unknown table: {table}")
result = conn.execute(
    text("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = :tbl)"),
    {"tbl": table}
)
```

- [ ] **Step 2: Исправить clean_old_data.py**

Строки 77, 113, 118 — тот же паттерн whitelist + параметризация:
```python
ALLOWED_TABLES = {"audit_logs", "notifications", "old_sessions"}

def _safe_count(self, table_name: str) -> int:
    if table_name not in ALLOWED_TABLES:
        raise ValueError(f"Disallowed table: {table_name}")
    result = self.db.execute(
        text("SELECT COUNT(*) FROM " + table_name)  # table name from whitelist only
    )
    return result.scalar()
```

**ВАЖНО:** Проверить также строки 182 и 185 (`get_tables_with_request_references` — table names из `inspector.get_table_names()`). Применить тот же whitelist-паттерн.

- [ ] **Step 3: Commit**

```bash
git add scripts/check_and_fix_db.py scripts/clean_old_data.py
git commit -m "security: fix SQL injection in migration scripts via whitelist"
```

### Task 0.3: Исправить hardcoded secret в media_service

**Files:**
- Modify: `media_service/app/core/config.py:40`

- [ ] **Step 1: Убрать default value**

```python
# BEFORE (line 40):
# secret_key: str = "dev_secret_key_change_in_production"

# AFTER:
secret_key: str = Field(..., env="SECRET_KEY")  # Required, no default
```

- [ ] **Step 2: Обновить media_service/.env.example**

Добавить: `SECRET_KEY=generate_with_openssl_rand_hex_32`

- [ ] **Step 3: Commit**

```bash
git add media_service/app/core/config.py media_service/.env.example
git commit -m "security: remove hardcoded default secret_key in media_service"
```

---

## Phase 1: Dead Code Cleanup (P1 — 30 минут)

### Task 1.1: Удалить пустые файлы и модули

**Files:**
- Delete: `uk_management_bot/services/rating_service.py` (0 bytes, 0 imports)
- Delete: `uk_management_bot/services/sheets_service.py` (0 bytes, 0 imports)
- Delete: `uk_management_bot/dashboard/export.py` (0 bytes)
- Delete: `uk_management_bot/dashboard/filters.py` (0 bytes)
- Delete: `uk_management_bot/dashboard/maps.py` (0 bytes)
- Delete: `uk_management_bot/dashboard/__init__.py` (empty module)
- Delete: `uk_management_bot/services/base_async_service.py` (260 строк, 0 наследников)

- [ ] **Step 1: Удалить файлы**

```bash
rm uk_management_bot/services/rating_service.py
rm uk_management_bot/services/sheets_service.py
rm -r uk_management_bot/dashboard/
rm uk_management_bot/services/base_async_service.py
```

- [ ] **Step 2: Проверить что ничего не сломалось**

```bash
docker exec uk-management-bot python -c "import uk_management_bot.services"
```

- [ ] **Step 3: Commit**

```bash
git add -u
git commit -m "chore: remove empty services (rating, sheets), unused dashboard module, orphaned base_async_service"
```

### Task 1.2: Удалить артефакты (.bak, .log, утилиты)

**Files:**
- Delete: `uk_management_bot/handlers/employee_management.py.bak`
- Delete: `uk_management_bot/bot.log`, `bot_output.log`, `bot_final_fix.log`, `bot_keyboard_fix.log`, `bot_permissions_fixed.log`, `bot_fixed_v2.log`
- Delete: `merge_keys.py`, `merge_keys_final.py`, `test_user_yards.py`, `check_localization.py` (root-level утилиты)
- Modify: `.gitignore` — добавить паттерны

- [ ] **Step 1: Удалить файлы**

```bash
rm uk_management_bot/handlers/employee_management.py.bak
rm uk_management_bot/bot*.log
rm merge_keys.py merge_keys_final.py test_user_yards.py check_localization.py
```

- [ ] **Step 2: Добавить в .gitignore**

```gitignore
# Artifacts
*.bak
*.bak2
*.log
!docs/**/*.log
```

- [ ] **Step 3: Commit**

```bash
git add -u .gitignore
git commit -m "chore: remove .bak, .log artifacts and root-level utility scripts"
```

### Task 1.3: Удалить неиспользуемые sync-сервисы (только те, у кого 0 production callers)

**ВАЖНО**: `shift_service.py` и `request_service.py` (sync) АКТИВНО используются handlers и middleware. НЕ удалять.

**Files:**
- Delete: `uk_management_bot/services/workload_predictor.py` (943 строк, только тесты)

- [ ] **Step 1: Убедиться что async-версия покрывает функциональность**

Прочитать `async_workload_predictor.py` и сравнить public API с `workload_predictor.py`.

- [ ] **Step 2: Обновить тесты**

Если тесты в `tests/test_shift_planning_services.py:18` и `services/test_workload_predictor.py:6` импортируют sync-версию — переключить на async или удалить эти тесты.

- [ ] **Step 3: Удалить sync-версию**

```bash
rm uk_management_bot/services/workload_predictor.py
rm uk_management_bot/services/test_workload_predictor.py
```

- [ ] **Step 4: Прогнать тесты**

```bash
docker exec uk-management-bot pytest --tb=short -q 2>&1 | tail -20
```

- [ ] **Step 5: Commit**

```bash
git add -u
git commit -m "chore: remove unused sync workload_predictor (async version is canonical)"
```

**Примечание:** `assignment_optimizer.py`, `geo_optimizer.py`, `smart_dispatcher.py` (sync) используются в try-except fallback в `assignment_service.py` и `shift_assignment_service.py`. Удалять их нужно ВМЕСТЕ с рефакторингом этих сервисов на async — это отдельная задача для Phase 4.

---

## Phase 2: Repository Pattern (P1 — 1-2 дня)

### Task 2.1: Создать UserRepository

**Контекст:** 174 вхождения `db.query(User)` в 44 файлах. Два основных паттерна: by id (65), by telegram_id (71).

**Files:**
- Create: `uk_management_bot/repositories/__init__.py`
- Create: `uk_management_bot/repositories/user_repository.py`
- Test: `tests/repositories/test_user_repository.py`

- [ ] **Step 1: Написать тест**

```python
# tests/repositories/test_user_repository.py
import pytest
from uk_management_bot.repositories.user_repository import UserRepository

class TestUserRepository:
    def test_find_by_id_returns_user(self, db_session, sample_user):
        repo = UserRepository(db_session)
        user = repo.find_by_id(sample_user.id)
        assert user is not None
        assert user.id == sample_user.id

    def test_find_by_id_returns_none_for_missing(self, db_session):
        repo = UserRepository(db_session)
        assert repo.find_by_id(99999) is None

    def test_find_by_telegram_id(self, db_session, sample_user):
        repo = UserRepository(db_session)
        user = repo.find_by_telegram_id(sample_user.telegram_id)
        assert user is not None
        assert user.telegram_id == sample_user.telegram_id

    def test_find_executors(self, db_session, executor_user):
        repo = UserRepository(db_session)
        executors = repo.find_by_active_role("executor")
        assert len(executors) >= 1
```

- [ ] **Step 2: Убедиться что тест FAIL**

```bash
docker exec uk-management-bot pytest tests/repositories/test_user_repository.py -v
```

- [ ] **Step 3: Реализовать UserRepository**

```python
# uk_management_bot/repositories/user_repository.py
from typing import Optional, List
from sqlalchemy.orm import Session
from uk_management_bot.database.models import User


class UserRepository:
    def __init__(self, db: Session):
        self.db = db

    def find_by_id(self, user_id: int) -> Optional[User]:
        return self.db.query(User).filter(User.id == user_id).first()

    def find_by_telegram_id(self, telegram_id: int) -> Optional[User]:
        return self.db.query(User).filter(User.telegram_id == telegram_id).first()

    def find_by_active_role(self, role: str) -> List[User]:
        return self.db.query(User).filter(User.active_role == role).all()
```

- [ ] **Step 4: Убедиться что тест PASS**

```bash
docker exec uk-management-bot pytest tests/repositories/test_user_repository.py -v
```

- [ ] **Step 5: Commit**

```bash
git add uk_management_bot/repositories/ tests/repositories/
git commit -m "feat: add UserRepository with find_by_id, find_by_telegram_id, find_by_active_role"
```

### Task 2.2: Создать RequestRepository

**Files:**
- Create: `uk_management_bot/repositories/request_repository.py`
- Test: `tests/repositories/test_request_repository.py`

- [ ] **Step 1: Написать тест**

```python
# tests/repositories/test_request_repository.py
class TestRequestRepository:
    def test_find_by_request_number(self, db_session, sample_request):
        repo = RequestRepository(db_session)
        req = repo.find_by_number(sample_request.request_number)
        assert req is not None
        assert req.request_number == sample_request.request_number

    def test_find_by_number_returns_none(self, db_session):
        repo = RequestRepository(db_session)
        assert repo.find_by_number("999999-999") is None

    def test_find_by_status(self, db_session, sample_request):
        repo = RequestRepository(db_session)
        requests = repo.find_by_status(sample_request.status, limit=10)
        assert len(requests) >= 1
```

- [ ] **Step 2: Убедиться FAIL → Step 3: Реализовать → Step 4: Убедиться PASS**

```python
# uk_management_bot/repositories/request_repository.py
from typing import Optional, List
from sqlalchemy.orm import Session
from uk_management_bot.database.models import Request


class RequestRepository:
    def __init__(self, db: Session):
        self.db = db

    def find_by_number(self, request_number: str) -> Optional[Request]:
        return self.db.query(Request).filter(
            Request.request_number == request_number
        ).first()

    def find_by_status(self, status: str, limit: int = 50) -> List[Request]:
        return self.db.query(Request).filter(
            Request.status == status
        ).order_by(Request.created_at.desc()).limit(limit).all()
```

- [ ] **Step 5: Commit**

```bash
git add uk_management_bot/repositories/request_repository.py tests/repositories/test_request_repository.py
git commit -m "feat: add RequestRepository with find_by_number, find_by_status"
```

### Task 2.3: Создать ShiftRepository

**Files:**
- Create: `uk_management_bot/repositories/shift_repository.py`
- Test: `tests/repositories/test_shift_repository.py`

По аналогии с Task 2.1/2.2. Методы:
- `find_by_id(shift_id) -> Optional[Shift]`
- `find_by_user_and_status(user_id, status) -> List[Shift]`
- `find_active_for_date(date) -> List[Shift]`

- [ ] **Steps 1-5: TDD цикл (RED → GREEN → Commit)**

### Task 2.4: Постепенная миграция на репозитории

**ВАЖНО:** Не рефакторить все 44 файла за раз. Мигрировать по одному файлу за коммит, начиная с файлов с максимальным количеством дублей.

**Порядок миграции (по убыванию impact):**

1. `handlers/admin.py` — 31 вхождение `Request.request_number`, 2 `User.id`
2. `services/user_management_service.py` — 16 вхождений `User.id`
3. `services/notification_service.py` — 7+ вхождений `User.id`
4. `handlers/request_acceptance.py` — 4 `Request.request_number`, 4 `User.telegram_id`
5. `services/auth_service.py` — 12 `User.id`
6. Остальные файлы — по необходимости

Паттерн миграции для каждого файла:
```python
# BEFORE (handlers/admin.py:289):
request = db.query(Request).filter(Request.request_number == request_number).first()

# AFTER:
from uk_management_bot.repositories.request_repository import RequestRepository
# ... в теле функции:
request = RequestRepository(db).find_by_number(request_number)
```

- [ ] **Step 1: Мигрировать handlers/admin.py** (31 замена для Request)
- [ ] **Step 2: Прогнать тесты → Commit**
- [ ] **Step 3: Мигрировать services/user_management_service.py** (16 замен для User)
- [ ] **Step 4: Прогнать тесты → Commit**
- [ ] **Продолжать по одному файлу...**

---

## Phase 3: Декомпозиция God-Handlers (P1 — 2-3 дня)

### Task 3.0: Извлечь FSM States в отдельные модули (ПРЕДВАРИТЕЛЬНЫЙ ШАГ)

**Контекст:** God-handlers содержат определения StatesGroup внутри себя. При декомпозиции эти классы нужны в нескольких подмодулях. Извлекаем ДО разделения.

**Files:**
- Create: `uk_management_bot/states/manager.py` — `ManagerStates` из admin.py:92-96
- Create: `uk_management_bot/states/executor_requests.py` — `ExecutorRequestStates` из requests.py:2851-2866
- Modify: `uk_management_bot/handlers/admin.py` — заменить определение на import
- Modify: `uk_management_bot/handlers/requests.py` — заменить определение на import

- [ ] **Step 1: Перенести ManagerStates в states/manager.py**
- [ ] **Step 2: Перенести ExecutorRequestStates в states/executor_requests.py**
- [ ] **Step 3: Заменить определения на imports в handlers**
- [ ] **Step 4: Тесты → Commit**

```bash
git commit -m "refactor: extract ManagerStates and ExecutorRequestStates to states/ modules"
```

**Примечание:** `RequestStates` уже может быть в `states/` — проверить перед извлечением.

### Task 3.1: Разделить handlers/admin.py (2771 строк → 5 модулей)

**Контекст:** Router создаётся на строке 54. Регистрация в `main.py:308` как `admin_router`. Callback prefixes хорошо изолированы по доменам — это позволяет чисто разделить.

**Целевая структура:**

```
handlers/
├── admin/
│   ├── __init__.py          — re-export router
│   ├── router.py            — Router() + shared helpers/imports
│   ├── requests.py          — строки 103-920 (request viewing, pagination, media)
│   ├── menus.py             — строки 921-1033 (admin panels, navigation)
│   ├── invites.py           — строки 1444-1667 (invite creation flow)
│   ├── request_actions.py   — строки 1667-2515 (accept/deny/clarify/complete/purchase)
│   └── assignment.py        — строки 2515-2771 (executor assignment)
```

**Files:**
- Create: `uk_management_bot/handlers/admin/` (directory)
- Create: `uk_management_bot/handlers/admin/__init__.py`
- Create: `uk_management_bot/handlers/admin/router.py`
- Create: `uk_management_bot/handlers/admin/requests.py`
- Create: `uk_management_bot/handlers/admin/menus.py`
- Create: `uk_management_bot/handlers/admin/invites.py`
- Create: `uk_management_bot/handlers/admin/request_actions.py`
- Create: `uk_management_bot/handlers/admin/assignment.py`
- Delete: `uk_management_bot/handlers/admin.py` (after migration)
- Modify: `uk_management_bot/main.py:22` — обновить import path
- Modify: `uk_management_bot/handlers/__init__.py` — обновить export

- [ ] **Step 1: Создать admin/router.py с общими импортами**

```python
# uk_management_bot/handlers/admin/router.py
from aiogram import Router

router = Router()

# Shared imports used across admin submodules
from uk_management_bot.services.request_service import RequestService
from uk_management_bot.repositories.request_repository import RequestRepository
from uk_management_bot.repositories.user_repository import UserRepository
from uk_management_bot.utils.helpers import get_text
# ... остальные общие импорты
```

- [ ] **Step 2: Перенести функции строк 103-920 в admin/requests.py**

Функции: `auto_assign_request_by_category`, `handle_manager_view_request`, `handle_view_request_media`, `handle_manager_confirm_completed`, `handle_manager_reconfirm_completed`, `handle_manager_return_to_work`, `handle_manager_request_pagination`, `handle_manager_back_to_list`

```python
# uk_management_bot/handlers/admin/requests.py
from .router import router
# ... register handlers on the shared router
```

- [ ] **Step 3: Перенести остальные группы (menus, invites, request_actions, assignment)**

- [ ] **Step 3b: Перенести module-level константы (строки 76-90) и shared helpers в router.py**

Константы типа `ADMIN_PANEL_TEXTS`, `TEST_MIDDLEWARE_TEXTS` и helper-функции, вызываемые из нескольких подмодулей (например `auto_assign_request_by_category`), должны быть в `router.py` или отдельном `admin/helpers.py`, НЕ в подмодулях handler'ов. Это предотвращает circular imports.

- [ ] **Step 4: Создать __init__.py с re-export**

```python
# uk_management_bot/handlers/admin/__init__.py
from .router import router

# ВАЖНО: Порядок импорта определяет порядок регистрации handler'ов!
# Не менять порядок без проверки приоритетов callback_data фильтров.
# Если broad-фильтр (F.data.startswith("delete_")) импортирован раньше
# specific-фильтра (F.data.startswith("delete_employee_")), он его затенит.
from . import requests          # mview_, media_, confirm_completed_, mreq_page_, mreq_back_
from . import menus             # admin panel navigation
from . import invites           # invite_role_, invite_spec_, invite_expiry_
from . import request_actions   # accept_, deny_, clarify_, complete_, purchase_, edit_materials_
from . import assignment        # assign_duty_, assign_specific_, back_to_assignment_type_
```

- [ ] **Step 5: Обновить main.py import**

```python
# main.py:22
# BEFORE: from uk_management_bot.handlers.admin import router as admin_router
# AFTER: (same import works because __init__.py re-exports router)
```

- [ ] **Step 6: Прогнать тесты**

```bash
docker exec uk-management-bot pytest --tb=short -q 2>&1 | tail -20
```

- [ ] **Step 7: Rebuild и проверить логи**

```bash
docker compose build uk-management-bot && docker compose up -d uk-management-bot
docker logs uk-management-bot --tail 20
```

- [ ] **Step 8: Commit**

```bash
git add uk_management_bot/handlers/admin/
git rm uk_management_bot/handlers/admin.py
git add uk_management_bot/main.py uk_management_bot/handlers/__init__.py
git commit -m "refactor: decompose handlers/admin.py (2771 lines) into 5 focused modules"
```

**Верификация Phase 2 → Phase 3:** После декомпозиции admin.py убедиться, что imports из `repositories/` (добавленные в Phase 2 Task 2.4) корректно распределены по подмодулям. Каждый подмодуль должен импортировать только нужные ему репозитории.

### Task 3.2: Разделить handlers/requests.py (3236 строк → 5 модулей)

**Целевая структура:**

```
handlers/
├── requests/
│   ├── __init__.py
│   ├── router.py            — Router() + shared helpers
│   ├── creation.py          — строки 80-868 (FSM creation flow)
│   ├── management.py        — строки 869-2125 (manager actions, viewing, pagination)
│   ├── my_requests.py       — строки 2126-2412 (user's own requests)
│   ├── filtering.py         — строки 2413-2631 (status/category/period/executor filters)
│   └── executor.py          — строки 2632-3236 (executor workflows: purchase, completion)
```

- [ ] **Steps 1-8: Аналогично Task 3.1**

**Паттерн тот же:** создать пакет, перенести функции группами, сохранить router, обновить импорты, тесты, commit.

### Task 3.3: Разделить handlers/shift_management.py (3677 строк → 5 модулей)

**Целевая структура:**

```
handlers/
├── shift_management/
│   ├── __init__.py
│   ├── router.py
│   ├── planning.py          — строки 87-362 (auto/manual planning)
│   ├── schedule.py          — строки 362-625 (date/week/month views)
│   ├── templates.py         — строки 625-1876 (template CRUD + specializations)
│   ├── analytics.py         — строки 1925-2448 (analytics, forecasting, weekly planning)
│   └── assignment.py        — строки 2448-3677 (AI, bulk, workload, conflicts)
```

- [ ] **Steps 1-8: Аналогично Task 3.1**

---

## Phase 4: Декомпозиция God-Services (P2 — 1-2 дня)

### Task 4.1: Разделить services/address_service.py (1359 строк, 7 доменов → 3 сервиса)

**Контекст:** SOLID-001 CRITICAL. AddressService управляет 7 несвязанными доменами: yards, buildings, apartments, user-apartments, approvals, statistics, selection workflows. 35 методов в одном классе.

**Целевая структура:**

```
services/
├── address/
│   ├── __init__.py          — re-export для обратной совместимости
│   ├── yard_service.py      — CRUD дворов, статистика дворов
│   ├── building_service.py  — CRUD зданий, подъезды, этажи
│   └── apartment_service.py — CRUD квартир, user-apartment связи, approvals, selection
```

- [ ] **Step 1: Определить группы методов по доменам**

Прочитать `address_service.py`, составить список всех 35 методов, распределить по 3 целевым сервисам.

- [ ] **Step 2: Создать yard_service.py с методами управления дворами**
- [ ] **Step 3: Создать building_service.py с методами управления зданиями**
- [ ] **Step 4: Создать apartment_service.py с остальными методами**
- [ ] **Step 5: Создать __init__.py с обратной совместимостью**

```python
# uk_management_bot/services/address/__init__.py
# Backward-compatible re-exports for gradual migration
from .yard_service import YardService
from .building_service import BuildingService
from .apartment_service import ApartmentService
```

- [ ] **Step 6: Обновить импорты в handlers (address_apartments.py, address_buildings.py, address_yards.py)**
- [ ] **Step 7: Тесты → Rebuild → Commit**

```bash
git commit -m "refactor: decompose AddressService (1359 lines, 7 domains) into 3 focused services"
```

### Task 4.2: Консолидация sync/async сервисов

**КРИТИЧЕСКИ ВАЖНО:** Перед удалением каждого sync-сервиса проверить callers.

| Sync Service | Production Callers | Действие |
|---|---|---|
| `shift_service.py` | handlers/shifts.py, middlewares/shift.py, services/request_service.py | **Оставить** — пометить legacy |
| `request_service.py` | handlers/requests.py, admin.py, request_reports.py, request_status_management.py | **Оставить** — пометить legacy |
| `smart_dispatcher.py` | shift_assignment_service.py:18, assignment_optimizer.py:687,915 | **Оставить** — зависимость от sync-сервисов |
| `assignment_optimizer.py` | assignment_service.py:32 (try-except fallback) | **Удалить** |
| `geo_optimizer.py` | assignment_service.py:33 (try-except fallback) | **Удалить** |

- [ ] **Step 1: Проверить что async-версии покрывают API sync-версий**
- [ ] **Step 2: Обновить `assignment_service.py` — убрать try-except fallback на sync**
- [ ] **Step 3: Удалить `assignment_optimizer.py` (1044 строк) и `geo_optimizer.py` (675 строк)**
- [ ] **Step 4: Прогнать тесты → Commit**

### Task 4.3: Пометить sync-сервисы как legacy

Для каждого sync-сервиса, который невозможно удалить сейчас — добавить docstring с конкретикой:

```python
"""
Legacy sync service.
Async counterpart: async_shift_service.py
Active callers: handlers/shifts.py, middlewares/shift.py, services/request_service.py
Do NOT delete until all callers migrate to async sessions (requires changing main.py:207 db_middleware).
"""
```

- [ ] **Step 1: Добавить docstrings в shift_service.py, request_service.py, smart_dispatcher.py → Commit**

---

## Phase 5: Рефакторинг API-роутеров (P2 — 1-2 дня)

### Task 5.1: Извлечь SQL-логику из api/shifts/router.py (1101 строк, 92 SQL-операции)

**Контекст:** Аудит Arch CRITICAL — API-роутеры содержат прямые SQL-операции (select, filter, join) вместо делегирования сервисам. Это нарушает separation of concerns.

**Подход:** Не создавать новые сервисы — использовать уже существующие `async_shift_service.py` и репозитории. Роутер должен вызывать сервис, а не формировать запросы.

**Files:**
- Modify: `uk_management_bot/api/shifts/router.py`
- Modify: `uk_management_bot/services/async_shift_service.py` — добавить методы, покрывающие логику из роутера

- [ ] **Step 1: Извлечь повторяющиеся query-паттерны из router в async_shift_service.py**
- [ ] **Step 2: Заменить inline SQL в роутере на вызовы сервиса**
- [ ] **Step 3: Тесты → Commit**

### Task 5.2: Извлечь SQL-логику из api/addresses/router.py (1033 строк, 123 SQL-операции)

**Подход:** Аналогично Task 5.1. Использовать `address/` сервисы (после Phase 4 Task 4.1).

- [ ] **Step 1: Извлечь query-паттерны в сервисы**
- [ ] **Step 2: Заменить inline SQL в роутере на вызовы сервисов**
- [ ] **Step 3: Тесты → Commit**

---

## Phase 6: Исправление DI и Session Management (P2 — 1 день)

### Task 6.1: Убрать прямое создание AsyncSessionLocal() в сервисах

**Контекст:** Аудит Arch CRITICAL. `async_assignment_optimizer.py:885` и `async_geo_optimizer.py:788` создают `AsyncSessionLocal()` внутри себя, обходя DI. Это может исчерпать DB pool и делает тестирование невозможным без реальной БД.

**Files:**
- Modify: `uk_management_bot/services/async_assignment_optimizer.py:885`
- Modify: `uk_management_bot/services/async_geo_optimizer.py:788`

- [ ] **Step 1: Заменить self-created sessions на injected sessions**

```python
# BEFORE (async_assignment_optimizer.py:885):
# async with AsyncSessionLocal() as db:
#     optimizer = AsyncAssignmentOptimizer(db)

# AFTER — вызывающий код передаёт session:
async def optimize(self, db: AsyncSession):
    optimizer = AsyncAssignmentOptimizer(db)
```

- [ ] **Step 2: Обновить все call sites — передавать session из middleware/Depends**
- [ ] **Step 3: Тесты → Commit**

```bash
git commit -m "fix: remove direct AsyncSessionLocal() creation in services, use injected sessions"
```

### Task 6.2: Исправить redis_pubsub.py — корректный reconnect

**Контекст:** Аудит Arch CRITICAL (race condition) + замечание review (broken client не сбрасывается в fast path).

**Files:**
- Modify: `uk_management_bot/services/redis_pubsub.py:9-23`

- [ ] **Step 1: Реализовать корректный double-checked locking с reset**

```python
import asyncio

_lock = asyncio.Lock()
_redis_client = None

async def get_pubsub_redis():
    global _redis_client
    client = _redis_client
    # Fast path: client exists, check health
    if client is not None:
        try:
            await client.ping()
            return client
        except Exception:
            # Client is broken — reset and fall through to reconnect
            _redis_client = None

    # Slow path: acquire lock for initialization/reconnection
    async with _lock:
        # Re-check: another coroutine may have reconnected while we waited
        if _redis_client is not None:
            return _redis_client
        url = getattr(settings, 'REDIS_PUBSUB_URL', 'redis://redis:6379/1')
        _redis_client = aioredis.from_url(url, decode_responses=True)
        return _redis_client
```

**Ключевые отличия от предыдущей версии:**
- После неудачного `ping()` — явный `_redis_client = None` (сбрасываем сломанный клиент)
- Внутри lock проверяем `_redis_client is not None` (другая корутина могла переподключиться)
- Возвращаем из lock напрямую (не используем stale `client` из fast path)

- [ ] **Step 2: Тесты → Commit**

### Task 6.3: Исправить notification_service.py — убрать скрытый global

**Контекст:** Аудит Arch CRITICAL (global mutable `_shared_bot`). Текущая задача переименована из "глобальные синглтоны → DI" — теперь это конкретное действие, а не абстрактное пожелание.

**Files:**
- Modify: `uk_management_bot/services/notification_service.py:180-189`

**Проблема:** `_shared_bot = None` с lazy `_get_shared_bot()` — global mutable state без reconnection logic. Если Bot теряет соединение, нотификации молча перестают работать.

- [ ] **Step 1: Заменить глобальный синглтон на явное создание в __init__**

```python
# BEFORE:
# _shared_bot = None
# def _get_shared_bot():
#     global _shared_bot
#     if _shared_bot is None:
#         _shared_bot = Bot(token=settings.BOT_TOKEN)
#     return _shared_bot

# AFTER — Bot создаётся при инициализации NotificationService:
class NotificationService:
    def __init__(self, db: Session, bot: Bot = None):
        self.db = db
        self.bot = bot or Bot(token=settings.BOT_TOKEN)
```

- [ ] **Step 2: Обновить call sites — передавать bot instance из dp.bot**
- [ ] **Step 3: Удалить `_shared_bot` global и `_get_shared_bot()` → Commit**

```bash
git commit -m "fix: replace global _shared_bot with injected Bot instance in NotificationService"
```

---

## Phase 7: Инфра и DX (P2-P3)

### Task 7.1: Консолидация Docker Compose (6 → 2 файла)

**Целевая структура:**
- `docker-compose.yml` — base (все сервисы, dev defaults)
- `docker-compose.prod.yml` — production overrides (logging, restart, resource limits)

**Files:**
- Modify: `docker-compose.yml` — base
- Create: `docker-compose.prod.yml` — overrides
- Delete: `docker-compose.dev.yml`, `docker-compose.production.yml`, `docker-compose.unified.yml`, `docker-compose.prod.unified.yml`

- [ ] **Step 1: Создать base + prod override**
- [ ] **Step 2: Проверить `docker compose up` и `docker compose -f docker-compose.yml -f docker-compose.prod.yml up`**
- [ ] **Step 3: Удалить лишние файлы → Commit**

### Task 7.2: Добавить missing DB indexes

**Files:**
- Create: `alembic/versions/xxx_add_missing_indexes.py`

```python
def upgrade():
    op.create_index("ix_request_assignments_request_number", "request_assignments", ["request_number"])
    op.create_index("ix_request_assignments_status", "request_assignments", ["status"])
    op.create_index("ix_user_apartments_apartment_id", "user_apartments", ["apartment_id"])
    op.create_index("ix_user_apartments_user_id", "user_apartments", ["user_id"])
```

- [ ] **Step 1: Создать миграцию → Step 2: Применить → Step 3: Commit**

### Task 7.3: Fix N+1 в admin.py

**Files:**
- Modify: `uk_management_bot/handlers/admin/requests.py` (после Phase 3, бывш. admin.py:240-247)

```python
# BEFORE (N+1):
for executor in matching_executors:
    active_shift = db.query(Shift).filter(...).first()

# AFTER (batch):
executor_ids = [e.id for e in matching_executors]
active_shifts = {s.user_id: s for s in db.query(Shift).filter(
    Shift.user_id.in_(executor_ids), Shift.status == "active"
).all()}
for executor in matching_executors:
    active_shift = active_shifts.get(executor.id)
```

- [ ] **Step 1: Реализовать → Step 2: Тесты → Step 3: Commit**

### Task 7.4: Root README

**Files:**
- Create: `README.md`

- [ ] **Step 1: Написать README**

Содержание:
- Что это (1 абзац)
- Quick Start (`cp .env.example .env && docker compose up`)
- Архитектура (ссылка на CLAUDE.md)
- Тесты (`docker exec uk-management-bot pytest`)

- [ ] **Step 2: Commit**

---

## Чек-лист валидации после каждой фазы

- [ ] `docker compose build` — успешно
- [ ] `docker compose up -d` — все контейнеры healthy
- [ ] `docker exec uk-management-bot pytest --tb=short -q` — тесты зелёные
- [ ] `docker logs uk-management-bot --tail 20` — нет ошибок
- [ ] `cd frontend && npm run build` — фронт собирается

---

## Accepted Risks — сознательно НЕ исправляем

Findings из аудита, которые формально классифицированы как CRITICAL или HIGH, но после анализа контекста проекта приняты как допустимые. Каждый пункт содержит обоснование и условие пересмотра.

### AR-001: SOLID-004 — Hardcoded status transition matrix (CRITICAL в аудите)

**Finding:** `services/request_service.py:299-325` — захардкоженная матрица переходов статусов, `request_service.py:327-377` — role-based access через if/elif.

**Решение:** Принять текущую реализацию.

**Обоснование:** 3 роли, 8 статусов, 1 разработчик. Strategy pattern или state machine добавят 3-5 классов и ~200 строк абстракций ради гибкости, которая не потребуется. Текущий dict literal читаем и легко модифицируем. Время на рефакторинг не окупится.

**Условие пересмотра:** Если количество статусов превысит 15, или появится второй тип сущности с аналогичными переходами, или добавится 4+ ролей — вернуться к State Machine паттерну.

### AR-002: SOLID-009/010 — DIP, конкретные зависимости в __init__ (CRITICAL в аудите)

**Finding:** `shift_planning_service.py:26-33` и `shift_assignment_service.py:67-71` создают конкретные сервисы через `new` в `__init__`.

**Решение:** Принять текущую реализацию.

**Обоснование:** В Python нет стандартного DI-контейнера. Добавление Protocol/ABC интерфейсов для каждого сервиса при одной реализации — boilerplate без практической выгоды. Тестирование возможно через monkey-patching/mock.patch. Фреймворк dependency-injector или python-inject добавит новую зависимость без пропорциональной выгоды для MVP.

**Условие пересмотра:** Если появится вторая реализация любого сервиса (например, mock-сервис для staging), или при переходе к микросервисной архитектуре.

### AR-003: SOLID-014/015 — ISP, разделение RequestService/NotificationService (MEDIUM в аудите)

**Finding:** RequestService имеет 16+ методов, клиенты используют подмножества.

**Решение:** Принять текущую реализацию.

**Обоснование:** Все 16 методов работают с одним доменом (Request CRUD + status transitions). Разделение на 4 класса (Creation, Query, Status, Analytics) создаст 4 файла с cross-references и shared state (db session). При текущем масштабе один файл проще поддерживать.

**Условие пересмотра:** Если RequestService превысит 1500 строк, или если разные команды будут работать над разными аспектами заявок.

### AR-004: main.py:208 — sync session в async-контексте (HIGH в аудите)

**Finding:** Bot middleware создаёт `SessionLocal()` (sync) в async handler context, потенциально блокируя event loop.

**Решение:** Принять текущую реализацию.

**Обоснование:** Миграция на async sessions требует изменения ВСЕХ 20+ handler-модулей и всех sync-сервисов (shift_service, request_service, auth_service и др.). Это перезапись ~30% кодовой базы. При 50 concurrent users sync queries на PostgreSQL занимают <10ms и не создают measurable блокировки event loop. Практических жалоб на производительность нет.

**Условие пересмотра:** Если нагрузка превысит 200 concurrent users, или если мониторинг покажет event loop blocking >100ms на DB queries, или если начнётся разработка новых handler-модулей (писать сразу на async).

### AR-005: DRY-009 — Keyboard building boilerplate (MEDIUM в аудите)

**Finding:** 63+ одинаковых конструкций KeyboardButton + get_text().

**Решение:** Принять текущую реализацию.

**Обоснование:** Каждая клавиатура уникальна по составу кнопок. Абстракция `create_keyboard_row(text_key, language)` сэкономит ~2 строки на клавиатуру (~120 строк total) ценой дополнительного indirection. При текущей структуре (keyboards/ уже хорошо покрыты тестами на 80%) выигрыш минимален.

### AR-006: Frontend тесты, перенос test_* в /tests/, ADR документация

**Решение:** Отложить. Не являются risks — это improvements.

**Обоснование:** Frontend тесты — отдельный план. Перенос 83 test_* — cosmetic. ADR — полезно при масштабировании команды.

---

## Scope Coverage Matrix

Маппинг findings аудита на remediation tasks и accepted risks.

### CRITICAL findings (30 total)

| Finding | Status | Location in plan |
|---------|--------|-----------------|
| SEC-001..007 (.env secrets) | **REMEDIATION** | Phase 0, Task 0.1 |
| Arch: handlers/shift_management.py God-file | **REMEDIATION** | Phase 3, Task 3.3 |
| Arch: handlers/requests.py God-file | **REMEDIATION** | Phase 3, Task 3.2 |
| Arch: handlers/admin.py God-file | **REMEDIATION** | Phase 3, Task 3.1 |
| KISS: sync/async дупликация (6 пар) | **REMEDIATION** (partial) | Phase 4, Task 4.2-4.3 |
| Arch: redis_pubsub.py race condition | **REMEDIATION** | Phase 6, Task 6.2 |
| SOLID-001: address_service.py SRP | **REMEDIATION** | Phase 4, Task 4.1 |
| SOLID-004: status transition matrix | **ACCEPTED** | AR-001 |
| SOLID-005: role-based access hardcode | **ACCEPTED** | AR-001 (same scope) |
| DRY-001/002: db.query(User) 30+ раз | **REMEDIATION** | Phase 2, Tasks 2.1-2.4 |
| Testing: 0% frontend | **ACCEPTED** | AR-006 |
| KISS-001..005: функции >150 строк | **REMEDIATION** (implicit) | Phase 3 decomposition |
| KISS-040..043: sync/async pairs | **REMEDIATION** (partial) | Phase 4, Task 4.2 |
| Arch: AsyncSessionLocal() bypass DI | **REMEDIATION** | Phase 6, Task 6.1 |
| Arch: global _shared_bot | **REMEDIATION** | Phase 6, Task 6.3 |
| Arch: API routers с SQL | **REMEDIATION** | Phase 5, Tasks 5.1-5.2 |
| SEC-008/009: SQL injection | **REMEDIATION** | Phase 0, Task 0.2 |
| SOLID-009/010: DIP | **ACCEPTED** | AR-002 |
| SOLID-002: admin.py 8+ domains | **REMEDIATION** | Phase 3, Task 3.1 |
| YAGNI-008/009: empty files | **REMEDIATION** | Phase 1, Task 1.1 |

### HIGH findings (35 total) — top items

| Finding | Status | Location in plan |
|---------|--------|-----------------|
| SEC-008..011 | **REMEDIATION** | Phase 0, Tasks 0.2-0.3 |
| DRY-003..005 | **REMEDIATION** | Phase 2, Phase 7 Task 7.1 |
| KISS-006..010 | **REMEDIATION** (implicit) | Phase 3 decomposition |
| SOLID-006..008 (if/elif chains) | **ACCEPTED** | AR-001 (same rationale as SOLID-004) |
| SOLID-011/012 (DIP in services) | **ACCEPTED** | AR-002 |
| PERF-001 (N+1 admin.py) | **REMEDIATION** | Phase 7, Task 7.3 |
| PERF-003 (missing indexes) | **REMEDIATION** | Phase 7, Task 7.2 |
| YAGNI-001..006 (unused imports) | **REMEDIATION** (implicit) | Phase 1 + Phase 3 |
| AR-004: sync session in async | **ACCEPTED** | AR-004 |
| Docs: no root README, no ADR | **REMEDIATION** / **ACCEPTED** | Phase 7 Task 7.4 / AR-006 |

---

## Оценка трудозатрат

| Phase | Задачи | Оценка |
|-------|--------|--------|
| Phase 0 | Security hotfix | 2-3 часа |
| Phase 1 | Dead code cleanup | 30-60 мин |
| Phase 2 | Repository pattern | 1-2 дня |
| Phase 3 | Handler decomposition | 2-3 дня |
| Phase 4 | Service decomposition + sync/async | 1-2 дня |
| Phase 5 | API router refactoring | 1-2 дня |
| Phase 6 | DI и session management fixes | 1 день |
| Phase 7 | Infra & DX | 1-2 дня |
| **Total** | | **~10-15 рабочих дней** |
