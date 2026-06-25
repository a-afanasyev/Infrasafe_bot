# Конвенции тестов (бот)

> NICE-114. Единые правила, чтобы новые тесты не расходились по стилю
> (исторически FIX-001/003/005/006 написаны в 4 разных стилях).

## Где лежат тесты

- **Unit/handlers/services бота** → `uk_management_bot/tests/` (и подпапки
  `services/`, `utils/`, `keyboards/`, `handlers/`, `registration/`). Запуск:
  `docker exec uk-management-bot pytest -q`.
- **API + интеграция/SSOT-гейты** → корневые `tests/api/`, `tests/services/`
  (свои sqlite-conftest'ы, отдельный прогон). Запуск:
  `docker exec uk-management-bot pytest -q tests/api tests/services`.
- Оба набора — в CI (`.github/workflows/ci.yml`).

### Landmine раскладки

- **Не делать `tests/`/`tests/api` пакетами** — НЕ добавлять `__init__.py`.
  Коллекция работает через `--import-mode=importlib` (см. `pyproject.toml`),
  который импортирует тесты по пути файла и терпит одинаковые basename
  в разных папках. `__init__.py` сломает это.
- При переносе/добавлении тестов проверять, что
  `pytest --collect-only -q` не уменьшает счёт.

## Async

- Глобально включён `asyncio_mode = "auto"` — `async def test_*` работают
  без декоратора. **Не** писать DIY-обёртки `_run(coro)` и не дублировать
  `@pytest.mark.asyncio` — полагаться на auto-mode.

## Маркеры

Зарегистрированы в `pyproject.toml`:

- `@pytest.mark.unit` — быстрый герметичный тест (без БД/сети/внешнего I/O).
- `@pytest.mark.integration` — тест, затрагивающий БД или внешние сервисы.

Прогон по категории: `pytest -m unit` / `pytest -m integration`.

## Мокинг

Предпочитать `unittest.mock.patch` / `patch.object` (явный target-путь).
`monkeypatch` — для подмены env/атрибутов модулей, где он лаконичнее.
Не смешивать оба стиля в одном файле без причины.

## Прочее

- `from __future__ import annotations` — добавлять в новые тест-модули
  (консистентность с conftest'ами).
- Conftest'ы `tests/keyboards/` и `tests/handlers/` ставят hermetic-stub
  `uk_management_bot.database.session` в `sys.modules` (он leak'ается по
  процессу) — новые символы в `database/session.py` дублировать в этих
  stub'ах, иначе full-suite-прогон падает (а отдельный файл — нет).
