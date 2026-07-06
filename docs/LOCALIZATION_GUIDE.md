# Руководство по локализации в проекте UK Management Bot

## Обзор

В проекте реализована система локализации с поддержкой русского и узбекского языков. Основные компоненты:

- Файлы локализации: `uk_management_bot/config/locales/ru.json` и `uk_management_bot/config/locales/uz.json`
- Утилита для получения локализованных строк: `get_text()` из `utils/helpers.py`
- Безопасное получение локализованных строк: `safe_get_text()` из `utils/safe_localization.py`

## Использование локализации в коде

### Базовое использование

```python
from uk_management_bot.utils.helpers import get_text

# Простое получение текста
text = get_text("key_name", language="ru")

# С параметрами форматирования
text = get_text("welcome_message", language="ru", name="Иван", time="12:00")
```

### Безопасное использование

```python
from uk_management_bot.utils.safe_localization import safe_get_text

# Безопасное получение текста с fallback
text = safe_get_text("key_name", language="ru", default="Текст по умолчанию")

# С fallback-ключом
text = safe_get_text_with_fallback("primary_key", "fallback_key", language="ru")
```

## Стандарты именования ключей

### Структура ключей

Ключи локализации должны быть организованы по секциям:

```json
{
  "section_name": {
    "key_name": "Переведенный текст",
    "key_with_params": "Текст с параметром: {param}"
  }
}
```

### Правила именования

1. Используйте snake_case для ключей: `user_not_found`, `request_created`
2. Группируйте связанные ключи в секции:
   - `errors.*` - сообщения об ошибках
   - `buttons.*` - тексты кнопок
   - `validation.*` - сообщения валидации
   - `admin.*` - сообщения администратора
3. Для параметризованных строк используйте плейсхолдеры `{param_name}`

## Добавление новой локализации

### 1. Добавление ключей в файлы локализации

При добавлении нового текста:

1. Добавьте ключ в `ru.json`:
```json
{
  "new_section": {
    "new_key": "Новый текст на русском"
  }
}
```

2. Добавьте тот же ключ в `uz.json`:
```json
{
  "new_section": {
    "new_key": "Yangi matn o'zbek tilida"
  }
}
```

### 2. Использование в коде

```python
from uk_management_bot.utils.safe_localization import safe_get_text

# Получаем язык пользователя
lang = message.from_user.language_code or "ru"

# Используем локализованный текст
await message.answer(safe_get_text("new_section.new_key", language=lang))
```

## Лучшие практики

### 1. Всегда используйте безопасное получение текста

```python
# Плохо
await message.answer("Текст на русском")

# Хорошо
await message.answer(safe_get_text("key_name", language=lang))
```

### 2. Обрабатывайте отсутствующие ключи

```python
# Плохо
text = get_text("key_name", language=lang)
if text == "key_name":
    text = "Текст по умолчанию"

# Хорошо
text = safe_get_text("key_name", language=lang, default="Текст по умолчанию")
```

### 3. Используйте единый подход к получению языка

```python
# Плохо
lang = "ru"  # хардкодированный язык

# Хорошо
lang = message.from_user.language_code or "ru"
# или
lang = await get_user_language(user_id, db)
```

### 4. Локализуйте все пользовательские сообщения

Все сообщения, которые видит пользователь, должны быть локализованы:

- Сообщения об ошибках
- Тексты кнопок
- Подтверждения действий
- Уведомления

### 5. Используйте параметризацию для динамических данных

```python
# Плохо
await message.answer(f"Заявка #{request_id} создана")

# Хорошо
await message.answer(safe_get_text("request.created", language=lang, request_id=request_id))
```

## Проверка локализации

> ⚠️ Скрипта `check_localization.py` в репозитории сейчас **нет** (ссылка была битой — проверять вручную). Ниже — ручная проверка соответствия ключей `ru.json` и `uz.json`.

Ручная сверка ключей между локалями бота:

```bash
# Ключи верхнего уровня расходятся? (грубая проверка структуры)
python3 - <<'PY'
import json
ru = json.load(open("uk_management_bot/config/locales/ru.json"))
uz = json.load(open("uk_management_bot/config/locales/uz.json"))
print("только в ru:", set(ru) - set(uz))
print("только в uz:", set(uz) - set(ru))
PY
```

Что проверять:
- Наличие хардкодированных строк (текст, минующий `get_text`/`safe_get_text`).
- Присутствие необходимых ключей локализации.
- Соответствие набора ключей между `ru.json` и `uz.json` (и на фронте — между `locales/ru.json` и `locales/uz.json`).

## Частые проблемы

### 1. Хардкодированные строки

```python
# Проблема
await message.answer("❌ Ошибка")

# Решение
await message.answer(safe_get_text("errors.error", language=lang))
```

### 2. Отсутствующие ключи

```python
# Проблема
text = get_text("missing_key", language=lang)  # вернет "missing_key"

# Решение
text = safe_get_text("missing_key", language=lang, default="Текст по умолчанию")
```

### 3. Несоответствие между языками

Убедитесь, что все ключи из `ru.json` присутствуют в `uz.json` и наоборот.

## Добавление нового языка

Для добавления нового языка (например, английского):

1. Создайте файл `en.json` в директории `config/locales/`
2. Скопируйте структуру из `ru.json`
3. Переведите все значения
4. Обновите `SUPPORTED_LANGUAGES` в `utils/language_helpers.py`

## Интеграция с CI/CD

Автоматической проверки локализации в CI сейчас нет (скрипта `check_localization.py` в репозитории нет — см. раздел «Проверка локализации»). При необходимости добавить гейт — реализовать сверку наборов ключей `ru.json`/`uz.json` (бот и фронт) в CI-шаге и подключить в pipeline. До этого — ручная сверка перед мержем.

## Заключение

Следование этим рекомендациям обеспечит:
- Полностью локализованный интерфейс
- Легкое добавление новых языков
- Предотвращение регрессий в локализации
- Улучшенный пользовательский опыт

---

# Локализация статусов заявок (бот): `utils/status_display.py`

Значения `REQUEST_STATUS_*` — это **ключи БД (русские строки)**, они не меняются. Утилита `utils/status_display.py` маппит их на локализованные display-строки, а не хранит перевод в самих данных.

- `get_status_display(status, language="ru")` — локализованное название статуса (`status_display.py:42`). Внутри маппит `STATUS_DISPLAY_KEYS` (`:15`) на i18n-ключи `statuses.*` и зовёт `get_text`.
- `get_status_with_emoji(status, language="ru")` — статус с эмодзи (`:50`); эмодзи берётся из `STATUS_EMOJI` (`:29`), fallback — `📋`.

Правила:
- Не рендерить сырое значение статуса пользователю — всегда через `get_status_display` / `get_status_with_emoji`.
- Статус «Возвращена» (`REQUEST_STATUS_RETURNED`) — канон cutover, виден менеджеру внутри бота; наружу (API/TWA) проецируется как «Исполнено» (`status_display.py:22-24`). Не «чинить» это как рассинхрон.
- При добавлении нового статуса — добавить ключ в `STATUS_DISPLAY_KEYS`, эмодзи в `STATUS_EMOJI`, и переводы `statuses.*` в `config/locales/{ru,uz}.json`.

Фронтовый аналог маппинга статусов — `frontend/src/i18n/apiMaps.ts` (`STATUS_MAP` / `tStatus`), см. раздел про фронт ниже.

---

# Локализация адресов (бот): `utils/address_helpers.py`

Адреса хранятся в БД в том виде, в котором были созданы (зависит от языка пользователя на момент создания). Старые заявки содержат русские префиксы («Дом: », «Двор: », «кв. ») даже при отображении на узбекском — поэтому нужна локализация на лету.

- `localize_address(address, language)` (`address_helpers.py:34`) — заменяет русские адресные префиксы на локализованные для UZ. Для `language == "ru"` возвращает адрес как есть (short-circuit, `:43-48`). Суффиксы «кв.»/«д.» берутся из i18n (`address.apartment_short` / `address.building_short`), а не хардкодятся (`:53-54`).
- `localize_address_error(err, language="ru")` (`address_helpers.py:15`) — локализует код ошибки address-сервиса: если `address_errors.<code>` найден в локали — отдаёт перевод, иначе возвращает `err` как есть (готовое сообщение-fallback).

Правила:
- Отображая адрес пользователю в UZ-контексте — прогонять через `localize_address(address, lang)`.
- Ошибки address-сервиса локализовать через `localize_address_error`, не рендерить сырой код.
- Корневое решение (TODO в коде, `:6-9`) — переход на структурированные адреса (`apartment_id → Apartment → Building → Yard`) с формированием отображения на лету; до него действует префиксная замена.

---

# Локализация фронтенда (дашборд / TWA): i18next

Фронтенд использует **i18next** + **react-i18next**. Языки — **RU и UZ**; языка **`en` нет** (импортируются только `ru`/`uz`, `frontend/src/i18n/index.ts:4-5`). Fallback — `ru`.

## Структура

- `frontend/src/i18n/index.ts` — инициализация i18next: ресурсы `ru`/`uz`, `fallbackLng: 'ru'`, определение языка. В контексте Telegram WebApp язык берётся из `Telegram.WebApp` (uz → `uz`, любой другой → `ru`), иначе — `LanguageDetector` (localStorage → navigator), кэш в localStorage (`index.ts:8-42`).
- `frontend/src/i18n/locales/ru.json`, `uz.json` — сами переводы (ключи должны совпадать в обеих локалях).
- `frontend/src/i18n/apiMaps.ts` — типизированный маппинг **русских/бэкендных API-значений → i18n-ключи**. Русские строки живут только здесь; компоненты зовут `tStatus()`, `tUrgency()`, `tCategory()` и т.д., а не хардкодят строки.
- `frontend/src/i18n/formatters.ts` — форматирование дат (`formatDate`) и чисел (`formatNumber`) по текущей локали i18next, с fallback на `ru`.

## Использование в компонентах

```tsx
import { useTranslation } from 'react-i18next'
import { tStatus } from '@/i18n/apiMaps'

function StatusBadge({ apiStatus }: { apiStatus: string }) {
  const { t } = useTranslation()
  return <span>{tStatus(apiStatus, t)}</span>  // 'Новая' → t('status.new')
}
```

- Обычные UI-строки — через `t('some.key')`.
- Значения, приходящие от API (статусы, срочность, категории, специализации, типы смен, роли, приоритеты, аналитические статусы/события, approval-статусы) — через соответствующий `t*`-хелпер из `apiMaps.ts`. Неизвестное значение хелпер вернёт как есть и выведет `console.warn` — сигнал добавить маппинг.
- Даты/числа — через `formatDate` / `formatNumber` из `formatters.ts`, не через ручной `toLocaleString`.

## Правила фронта

- Любой новый пользовательский текст — ключ в **обоих** `locales/ru.json` и `locales/uz.json` (иначе UZ покажет fallback-строку RU).
- Новое API-значение (например, новый статус) — добавить в соответствующий `*_MAP` в `apiMaps.ts` **и** ключ перевода в обе локали.
- Русские строки API держать только в `apiMaps.ts` — не растаскивать по компонентам.
- Пункты навигации дашборда — ключи `nav.*` (см. `docs/DEVELOPMENT.md`, чек-лист добавления страницы).

## Соответствие бот ↔ фронт

Статусы заявок маппятся в двух местах независимо: бот — `utils/status_display.py` (`STATUS_DISPLAY_KEYS`), фронт — `apiMaps.ts` (`STATUS_MAP`). При изменении набора статусов обновлять оба, плюс переводы в локалях бота (`config/locales/{ru,uz}.json`) и фронта (`i18n/locales/{ru,uz}.json`).
