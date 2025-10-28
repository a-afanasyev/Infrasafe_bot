# 📊 ПЛАН ИНТЕГРАЦИИ API С GOOGLE SHEETS ДЛЯ УПРАВЛЕНИЯ СМЕНАМИ И МОНИТОРИНГА ЗАЯВОК

**Дата создания:** 17 октября 2025
**Версия:** 1.0
**Автор:** Claude Code Analysis
**Статус:** Планирование

---

## 🎯 ЦЕЛЬ ПРОЕКТА

Создать **двустороннюю интеграцию** между UK Management Bot и Google Sheets для:

1. **Редактирования смен** через Google Sheets (менеджеры могут планировать смены в табличном формате)
2. **Мониторинга заявок** в реальном времени (просмотр статусов, исполнителей, прогресса без входа в бота)
3. **Аналитики и отчетности** (дашборды, графики, сводные таблицы)

### Бизнес-ценность

- ⏱️ **Экономия времени**: Редактирование смен в таблице быстрее, чем через бота
- 📊 **Визуализация**: Менеджеры видят расписание на неделю/месяц одним взглядом
- 📈 **Аналитика**: Встроенные инструменты Google Sheets для графиков и отчетов
- 👥 **Совместная работа**: Несколько менеджеров могут работать с таблицей одновременно
- 📱 **Мобильность**: Доступ к данным с любого устройства через Google Sheets приложение

---

## 📋 ЧАСТЬ 1: НАСТРОЙКА В GOOGLE CLOUD PLATFORM

### 1.1 Создание проекта и включение API

**Шаг 1: Создать проект**
1. Перейти на https://console.cloud.google.com/
2. Нажать "Select a project" → "New Project"
3. Название проекта: `uk-management-bot-integration`
4. Organization: оставить по умолчанию
5. Нажать "Create"

**Шаг 2: Включить Google Sheets API**
1. В меню перейти в "APIs & Services" → "Library"
2. Найти "Google Sheets API"
3. Нажать "Enable"

**Шаг 3: Включить Google Drive API**
1. В том же Library найти "Google Drive API"
2. Нажать "Enable"
3. *(Необходимо для управления доступом к таблицам)*

**Шаг 4: Настроить квоты** *(Опционально, для production)*
1. Перейти в "APIs & Services" → "Quotas"
2. Проверить лимиты:
   - Read requests: **300 запросов/минуту** на проект
   - Write requests: **300 запросов/минуту** на проект
   - Per user: **60 запросов/минуту**
3. Если нужно больше - запросить увеличение квот

### 1.2 Создание Service Account

**Что это:** Service Account - это специальный аккаунт Google для автоматизации (бот будет работать от его имени).

**Шаг 1: Создать Service Account**
1. Перейти в "IAM & Admin" → "Service Accounts"
2. Нажать "Create Service Account"
3. Заполнить:
   - **Service account name:** `uk-bot-sheets-integration`
   - **Service account ID:** `uk-bot-sheets` (автогенерируется)
   - **Description:** `Service account for UK Management Bot to access Google Sheets`
4. Нажать "Create and Continue"

**Шаг 2: Назначить роли** *(Опционально)*
1. В разделе "Grant this service account access to project"
2. Роль: оставить пустым (доступ будем давать на уровне конкретных таблиц)
3. Нажать "Continue" → "Done"

**Шаг 3: Создать ключ**
1. Найти созданный Service Account в списке
2. Нажать на него
3. Перейти на вкладку "Keys"
4. Нажать "Add Key" → "Create new key"
5. Выбрать формат: **JSON**
6. Нажать "Create"
7. Файл `uk-bot-sheets-[ID].json` автоматически скачается

**Шаг 4: Сохранить ключ безопасно**
```bash
# На сервере создать папку для credentials
mkdir -p /path/to/UK/google-credentials

# Переместить скачанный файл
mv ~/Downloads/uk-bot-sheets-*.json /path/to/UK/google-credentials/google-service-account.json

# Установить правильные права доступа
chmod 600 /path/to/UK/google-credentials/google-service-account.json

# Добавить в .gitignore
echo "google-credentials/" >> .gitignore
```

**Шаг 5: Сохранить email Service Account**
1. Открыть файл `google-service-account.json`
2. Найти поле `"client_email"`
3. Скопировать значение (например: `uk-bot-sheets@uk-management-bot-integration.iam.gserviceaccount.com`)
4. **Этот email нужен для шаринга таблиц!**

### 1.3 Создание OAuth2 Credentials *(Опционально, для будущего)*

Этот шаг можно пропустить на первом этапе. OAuth2 нужен только если планируется доступ к личным Google таблицам пользователей.

**Когда понадобится:**
- Если менеджеры хотят использовать свои личные таблицы
- Если нужен доступ к Google Drive пользователей

**Пока используем:** Service Account (достаточно для корпоративных таблиц).

---

## 📋 ЧАСТЬ 2: СОЗДАНИЕ GOOGLE SHEETS ТАБЛИЦ

### 2.1 Таблица "Управление сменами"

**Шаг 1: Создать таблицу**
1. Открыть https://sheets.google.com
2. Нажать "+" → "Blank spreadsheet"
3. Переименовать: **"UK Management - Управление сменами"**

**Шаг 2: Создать структуру листов**

#### **Лист 1: "Планирование смен"**

Структура колонок:

| Колонка | Название | Тип данных | Описание |
|---------|----------|------------|----------|
| A | ID смены | Число | Уникальный ID (read-only) |
| B | Дата | Дата | Дата смены |
| C | Время начала | Время | Начало смены (09:00) |
| D | Время окончания | Время | Окончание смены (17:00) |
| E | Специализация | Список | electric, plumbing, security, cleaning, universal |
| F | ID исполнителя | Число | ID из базы данных |
| G | ФИО исполнителя | Текст | Имя исполнителя (автозаполнение) |
| H | Статус | Список | planned, active, completed, cancelled |
| I | Тип смены | Список | regular, emergency, overtime, maintenance |
| J | Зона покрытия | Текст | Географическая зона |
| K | Макс. заявок | Число | Максимальное количество заявок |
| L | Текущих заявок | Число | Текущая нагрузка (read-only) |
| M | Примечания | Текст | Комментарии менеджера |
| N | Последнее обновление | Дата+Время | Timestamp последнего изменения (read-only) |

**Шаг 3: Добавить заголовки**
```
A1: ID смены
B1: Дата
C1: Время начала
D1: Время окончания
E1: Специализация
F1: ID исполнителя
G1: ФИО исполнителя
H1: Статус
I1: Тип смены
J1: Зона покрытия
K1: Макс. заявок
L1: Текущих заявок
M1: Примечания
N1: Последнее обновление
```

**Шаг 4: Форматирование**
```javascript
// Выполнить в Apps Script (Tools → Script editor)
function formatShiftsSheet() {
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName('Планирование смен');

  // Заморозить заголовки
  sheet.setFrozenRows(1);

  // Форматирование заголовков
  const headerRange = sheet.getRange('A1:N1');
  headerRange.setBackground('#4285F4');
  headerRange.setFontColor('#FFFFFF');
  headerRange.setFontWeight('bold');

  // Форматирование столбцов
  sheet.getRange('A2:A1000').setNumberFormat('0'); // ID - целое число
  sheet.getRange('B2:B1000').setNumberFormat('dd.mm.yyyy'); // Дата
  sheet.getRange('C2:C1000').setNumberFormat('hh:mm'); // Время
  sheet.getRange('D2:D1000').setNumberFormat('hh:mm'); // Время
  sheet.getRange('N2:N1000').setNumberFormat('dd.mm.yyyy hh:mm:ss'); // Timestamp

  // Защитить read-only колонки
  const protectedRanges = [
    sheet.getRange('A2:A1000'), // ID
    sheet.getRange('G2:G1000'), // ФИО (автозаполнение)
    sheet.getRange('L2:L1000'), // Текущих заявок
    sheet.getRange('N2:N1000')  // Timestamp
  ];

  protectedRanges.forEach(range => {
    const protection = range.protect();
    protection.setDescription('Автоматически обновляется системой');
    protection.setWarningOnly(true);
  });
}
```

#### **Лист 2: "Исполнители"**

Структура колонок:

| Колонка | Название | Тип данных | Описание |
|---------|----------|------------|----------|
| A | ID | Число | User ID из базы данных |
| B | Telegram ID | Число | Telegram ID пользователя |
| C | ФИО | Текст | Полное имя |
| D | Специализации | Текст | Через запятую: electric, plumbing |
| E | Рейтинг | Число | Рейтинг исполнителя (1.0-5.0) |
| F | Статус | Список | approved, pending, blocked |
| G | Телефон | Текст | Контактный телефон |
| H | Email | Текст | Email адрес |

#### **Лист 3: "Справочники"**

Этот лист содержит данные для выпадающих списков (Data Validation).

**Таблица "Специализации":**
```
A1: Код
B1: Название (RU)
C1: Название (EN)

A2: electric
B2: Электрик
C2: Electrician

A3: plumbing
B3: Сантехник
C3: Plumber

A4: security
B4: Охранник
C4: Security

A5: cleaning
B5: Уборщик
C5: Cleaner

A6: universal
B6: Универсал
C6: Universal
```

**Таблица "Статусы смен":**
```
D1: Код
E1: Название

D2: planned
E2: Запланирована

D3: active
E3: Активная

D4: completed
E4: Завершена

D5: cancelled
E5: Отменена
```

**Таблица "Типы смен":**
```
F1: Код
G1: Название

F2: regular
G2: Обычная

F3: emergency
G3: Экстренная

F4: overtime
G4: Сверхурочная

F5: maintenance
G5: Техническое обслуживание
```

**Шаг 5: Настроить Data Validation**
```javascript
function setupDataValidation() {
  const shiftsSheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName('Планирование смен');
  const refsSheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName('Справочники');

  // Специализации (колонка E)
  const specializationRule = SpreadsheetApp.newDataValidation()
    .requireValueInRange(refsSheet.getRange('A2:A6'), true)
    .setAllowInvalid(false)
    .setHelpText('Выберите специализацию из справочника')
    .build();
  shiftsSheet.getRange('E2:E1000').setDataValidation(specializationRule);

  // Статусы (колонка H)
  const statusRule = SpreadsheetApp.newDataValidation()
    .requireValueInRange(refsSheet.getRange('D2:D5'), true)
    .setAllowInvalid(false)
    .setHelpText('Выберите статус смены')
    .build();
  shiftsSheet.getRange('H2:H1000').setDataValidation(statusRule);

  // Типы смен (колонка I)
  const typeRule = SpreadsheetApp.newDataValidation()
    .requireValueInRange(refsSheet.getRange('F2:F5'), true)
    .setAllowInvalid(false)
    .setHelpText('Выберите тип смены')
    .build();
  shiftsSheet.getRange('I2:I1000').setDataValidation(typeRule);
}
```

### 2.2 Таблица "Мониторинг заявок"

**Шаг 1: Создать таблицу**
1. Создать новую таблицу: **"UK Management - Мониторинг заявок"**

#### **Лист 1: "Активные заявки"**

Структура колонок:

| Колонка | Название | Тип данных | Описание |
|---------|----------|------------|----------|
| A | № заявки | Текст | Формат: 251017-001 |
| B | Дата создания | Дата+Время | Timestamp создания |
| C | Статус | Текст | Новая, В работе, Выполнена и т.д. |
| D | Категория | Текст | Электрика, Сантехника и т.д. |
| E | Адрес | Текст | Полный адрес |
| F | Квартира | Текст | Номер квартиры |
| G | Описание | Текст | Описание проблемы |
| H | Срочность | Текст | Обычная, Срочная, Критическая |
| I | Заявитель | Текст | ФИО заявителя |
| J | Исполнитель | Текст | ФИО исполнителя |
| K | Тип назначения | Текст | group / individual |
| L | Специализация | Текст | Специализация для группового назначения |
| M | Дата назначения | Дата+Время | Когда назначена |
| N | Дата обновления | Дата+Время | Последнее изменение |
| O | Фото | Текст | Ссылки на фото через запятую |
| P | Комментарии | Число | Количество комментариев |
| Q | Прогресс | Процент | % выполнения (вычисляемое поле) |

**Формула для прогресса (колонка Q):**
```
=IF(C2="Новая",0%,IF(C2="В работе",25%,IF(C2="Закуп",50%,IF(C2="Выполнена",75%,IF(C2="Принято",100%,0%)))))
```

#### **Лист 2: "История заявок"**

Та же структура, но для завершенных заявок (статус "Принято" или "Отменена").

#### **Лист 3: "Аналитика"**

**Сводная таблица 1: Заявки по статусам**
```
Статус          | Количество | %
----------------|------------|----
Новая           | 5          | 20%
В работе        | 10         | 40%
Выполнена       | 8          | 32%
Принято         | 2          | 8%
```

**Сводная таблица 2: Заявки по категориям**
```
Категория       | Количество | Средний срок выполнения
----------------|------------|------------------------
Электрика       | 12         | 2.5 дня
Сантехника      | 8          | 1.8 дня
Уборка          | 15         | 0.5 дня
```

**График 1: Динамика создания заявок** (линейный график по датам)

**График 2: Распределение по категориям** (круговая диаграмма)

### 2.3 Настройка доступа к таблицам

**КРИТИЧЕСКИ ВАЖНО:** Нужно дать доступ Service Account к таблицам!

**Шаг 1: Получить email Service Account**
1. Открыть файл `google-service-account.json`
2. Найти строку с `"client_email"`
3. Скопировать email (например: `uk-bot-sheets@uk-management-bot-integration.iam.gserviceaccount.com`)

**Шаг 2: Поделиться таблицей "Управление сменами"**
1. Открыть таблицу
2. Нажать кнопку "Share" (правый верхний угол)
3. Вставить email Service Account
4. Выбрать права: **Editor** (чтобы бот мог редактировать)
5. Снять галочку "Notify people" (не нужно отправлять email боту)
6. Нажать "Share"

**Шаг 3: Поделиться таблицей "Мониторинг заявок"**
1. Повторить те же шаги
2. Права: **Editor**

**Шаг 4: Получить ID таблиц**
1. Открыть таблицу "Управление сменами"
2. Скопировать ID из URL:
   ```
   https://docs.google.com/spreadsheets/d/[ЭТО_ID_ТАБЛИЦЫ]/edit
   ```
3. Сохранить ID в переменную окружения `SHIFTS_SPREADSHEET_ID`
4. Повторить для таблицы "Мониторинг заявок" → `REQUESTS_SPREADSHEET_ID`

**Шаг 5: Настроить защиту диапазонов**
```javascript
function protectSystemColumns() {
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName('Планирование смен');

  // Защитить системные колонки от редактирования вручную
  const protectedRanges = [
    { range: 'A2:A1000', description: 'ID смены (автогенерируется)' },
    { range: 'G2:G1000', description: 'ФИО (подставляется автоматически)' },
    { range: 'L2:L1000', description: 'Текущих заявок (обновляется автоматически)' },
    { range: 'N2:N1000', description: 'Timestamp (обновляется автоматически)' }
  ];

  protectedRanges.forEach(item => {
    const protection = sheet.getRange(item.range).protect();
    protection.setDescription(item.description);
    protection.setWarningOnly(true); // Предупреждение, но не блокировка

    // Разрешить редактирование только боту (Service Account)
    const me = Session.getEffectiveUser();
    protection.removeEditors(protection.getEditors());
    if (protection.canDomainEdit()) {
      protection.setDomainEdit(false);
    }
  });
}
```

---

## 📋 ЧАСТЬ 3: РАЗРАБОТКА GOOGLE APPS SCRIPT

Google Apps Script - это JavaScript код, который работает внутри Google Sheets и обрабатывает события (изменения, триггеры).

### 3.1 Создание проекта Apps Script

**Шаг 1: Открыть редактор**
1. Открыть таблицу "Управление сменами"
2. В меню: **Extensions** → **Apps Script**
3. Откроется редактор кода

**Шаг 2: Настроить проект**
1. Переименовать проект: **"UK Bot Sheets Integration"**
2. Удалить дефолтный код из `Code.gs`

### 3.2 Основной код (Code.gs)

```javascript
/**
 * UK Management Bot - Google Sheets Integration
 *
 * Этот скрипт обеспечивает двустороннюю синхронизацию между
 * Google Sheets и UK Management Bot через REST API.
 */

// ============================================================================
// КОНФИГУРАЦИЯ
// ============================================================================

// URL бота (будет настроен в Script Properties)
const BOT_API_URL = PropertiesService.getScriptProperties().getProperty('BOT_API_URL');
const API_KEY = PropertiesService.getScriptProperties().getProperty('API_KEY');
const WEBHOOK_SECRET = PropertiesService.getScriptProperties().getProperty('WEBHOOK_SECRET');

// Имена листов
const SHIFTS_SHEET_NAME = 'Планирование смен';
const EXECUTORS_SHEET_NAME = 'Исполнители';
const REFERENCES_SHEET_NAME = 'Справочники';

// ============================================================================
// WEB APP - ПРИЕМ ДАННЫХ ОТ БОТА
// ============================================================================

/**
 * doPost - обработчик POST запросов от бота
 * Вызывается когда бот отправляет данные в Sheets
 */
function doPost(e) {
  try {
    // Проверяем подпись запроса (безопасность!)
    if (!verifySignature(e)) {
      return createJsonResponse(401, { error: 'Invalid signature' });
    }

    // Парсим данные
    const data = JSON.parse(e.postData.contents);
    const action = data.action;

    Logger.log(`Received action: ${action}`);

    // Маршрутизация по типу действия
    switch (action) {
      case 'sync_shifts':
        return syncShifts(data.shifts);

      case 'sync_shift':
        return syncSingleShift(data.shift);

      case 'sync_requests':
        return syncRequests(data.requests);

      case 'sync_executors':
        return syncExecutors(data.executors);

      case 'ping':
        return createJsonResponse(200, { status: 'ok', message: 'pong' });

      default:
        return createJsonResponse(400, { error: 'Unknown action: ' + action });
    }

  } catch (error) {
    Logger.log('Error in doPost: ' + error.toString());
    return createJsonResponse(500, { error: error.toString() });
  }
}

/**
 * doGet - для тестирования (можно открыть в браузере)
 */
function doGet(e) {
  return ContentService.createTextOutput(
    'UK Management Bot - Sheets Integration API is running. Use POST requests.'
  );
}

// ============================================================================
// СИНХРОНИЗАЦИЯ: БОТ → SHEETS
// ============================================================================

/**
 * Полная синхронизация всех смен
 */
function syncShifts(shifts) {
  try {
    const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(SHIFTS_SHEET_NAME);

    if (!sheet) {
      throw new Error('Sheet "' + SHIFTS_SHEET_NAME + '" not found');
    }

    // Очищаем существующие данные (кроме заголовков)
    const lastRow = sheet.getLastRow();
    if (lastRow > 1) {
      sheet.getRange(2, 1, lastRow - 1, sheet.getLastColumn()).clearContent();
    }

    // Подготавливаем данные для вставки
    const rows = shifts.map(shift => formatShiftRow(shift));

    // Вставляем данные одним запросом (эффективнее)
    if (rows.length > 0) {
      sheet.getRange(2, 1, rows.length, rows[0].length).setValues(rows);
    }

    // Логируем
    Logger.log(`Synced ${shifts.length} shifts to Sheets`);

    return createJsonResponse(200, {
      success: true,
      message: `Synced ${shifts.length} shifts`,
      synced_count: shifts.length
    });

  } catch (error) {
    Logger.log('Error in syncShifts: ' + error.toString());
    return createJsonResponse(500, { error: error.toString() });
  }
}

/**
 * Синхронизация одной смены
 */
function syncSingleShift(shift) {
  try {
    const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(SHIFTS_SHEET_NAME);

    // Ищем строку со сменой по ID
    const shiftId = shift.id;
    const idColumn = sheet.getRange('A:A').getValues();
    let rowIndex = -1;

    for (let i = 1; i < idColumn.length; i++) {
      if (idColumn[i][0] === shiftId) {
        rowIndex = i + 1; // +1 потому что массив с 0, а sheet с 1
        break;
      }
    }

    const row = formatShiftRow(shift);

    if (rowIndex === -1) {
      // Смена не найдена - добавляем новую строку
      sheet.appendRow(row);
      Logger.log(`Added new shift: ${shiftId}`);
    } else {
      // Смена найдена - обновляем существующую строку
      sheet.getRange(rowIndex, 1, 1, row.length).setValues([row]);
      Logger.log(`Updated shift: ${shiftId} at row ${rowIndex}`);
    }

    return createJsonResponse(200, {
      success: true,
      message: `Shift ${shiftId} synced`,
      shift_id: shiftId
    });

  } catch (error) {
    Logger.log('Error in syncSingleShift: ' + error.toString());
    return createJsonResponse(500, { error: error.toString() });
  }
}

/**
 * Форматирование смены для вставки в лист
 */
function formatShiftRow(shift) {
  return [
    shift.id,                                    // A: ID смены
    new Date(shift.date),                        // B: Дата
    shift.start_time,                            // C: Время начала
    shift.end_time,                              // D: Время окончания
    shift.specialization,                        // E: Специализация
    shift.executor_id || '',                     // F: ID исполнителя
    shift.executor_name || '',                   // G: ФИО исполнителя
    shift.status,                                // H: Статус
    shift.shift_type || 'regular',               // I: Тип смены
    shift.coverage_area || '',                   // J: Зона покрытия
    shift.max_requests || 10,                    // K: Макс. заявок
    shift.current_requests || 0,                 // L: Текущих заявок
    shift.notes || '',                           // M: Примечания
    new Date()                                   // N: Последнее обновление
  ];
}

/**
 * Синхронизация исполнителей
 */
function syncExecutors(executors) {
  try {
    const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(EXECUTORS_SHEET_NAME);

    // Очищаем существующие данные
    const lastRow = sheet.getLastRow();
    if (lastRow > 1) {
      sheet.getRange(2, 1, lastRow - 1, sheet.getLastColumn()).clearContent();
    }

    // Подготавливаем данные
    const rows = executors.map(executor => [
      executor.id,                               // A: ID
      executor.telegram_id,                      // B: Telegram ID
      executor.full_name,                        // C: ФИО
      executor.specializations.join(', '),       // D: Специализации
      executor.rating || 0,                      // E: Рейтинг
      executor.status,                           // F: Статус
      executor.phone || '',                      // G: Телефон
      executor.email || ''                       // H: Email
    ]);

    // Вставляем данные
    if (rows.length > 0) {
      sheet.getRange(2, 1, rows.length, rows[0].length).setValues(rows);
    }

    Logger.log(`Synced ${executors.length} executors to Sheets`);

    return createJsonResponse(200, {
      success: true,
      message: `Synced ${executors.length} executors`
    });

  } catch (error) {
    Logger.log('Error in syncExecutors: ' + error.toString());
    return createJsonResponse(500, { error: error.toString() });
  }
}

// ============================================================================
// МОНИТОРИНГ ИЗМЕНЕНИЙ: SHEETS → БОТ
// ============================================================================

/**
 * onEdit - триггер, который срабатывает при редактировании ячейки
 * Автоматически отслеживает изменения и отправляет их в бот
 */
function onEdit(e) {
  try {
    const sheet = e.source.getActiveSheet();
    const range = e.range;
    const row = range.getRow();
    const col = range.getColumn();

    // Игнорируем изменения в заголовках (строка 1)
    if (row === 1) return;

    // Обрабатываем только изменения в листе "Планирование смен"
    if (sheet.getName() !== SHIFTS_SHEET_NAME) return;

    // Проверяем, что редактируется разрешенная колонка
    const editableColumns = [2, 3, 4, 5, 6, 8, 9, 10, 11, 13]; // B, C, D, E, F, H, I, J, K, M
    if (!editableColumns.includes(col)) {
      // Пользователь пытается редактировать защищенную колонку
      Logger.log(`Ignored edit in protected column ${col}`);
      return;
    }

    Logger.log(`Edit detected in ${sheet.getName()} at row ${row}, col ${col}`);

    // Получаем ID смены из колонки A
    const shiftId = sheet.getRange(row, 1).getValue();

    if (!shiftId) {
      Logger.log('No shift ID found, skipping');
      return;
    }

    // Получаем всю строку
    const rowData = sheet.getRange(row, 1, 1, 14).getValues()[0];

    // Формируем данные смены
    const shiftData = {
      id: rowData[0],
      date: formatDate(rowData[1]),
      start_time: rowData[2],
      end_time: rowData[3],
      specialization: rowData[4],
      executor_id: rowData[5],
      status: rowData[7],
      shift_type: rowData[8],
      coverage_area: rowData[9],
      max_requests: rowData[10],
      notes: rowData[12],
      updated_from_sheets: true
    };

    // Отправляем изменения в бот
    sendUpdateToBot({
      type: 'shift_update',
      shift: shiftData,
      changed_column: col,
      changed_value: e.value
    });

    // Обновляем timestamp в колонке N
    sheet.getRange(row, 14).setValue(new Date());

  } catch (error) {
    Logger.log('Error in onEdit: ' + error.toString());
    // Не показываем ошибку пользователю, чтобы не мешать работе
  }
}

/**
 * Периодическая проверка изменений (backup для onEdit)
 * Триггер: каждые 5 минут
 */
function periodicSync() {
  try {
    Logger.log('Starting periodic sync check');

    // Проверяем, были ли изменения в последние 5 минут
    const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(SHIFTS_SHEET_NAME);
    const lastRow = sheet.getLastRow();

    if (lastRow < 2) return; // Нет данных

    // Получаем timestamps из колонки N
    const timestamps = sheet.getRange(2, 14, lastRow - 1, 1).getValues();
    const now = new Date();
    const fiveMinutesAgo = new Date(now.getTime() - 5 * 60 * 1000);

    let changedCount = 0;

    // Проверяем каждую строку
    for (let i = 0; i < timestamps.length; i++) {
      const timestamp = timestamps[i][0];

      if (timestamp > fiveMinutesAgo) {
        // Эта смена изменилась недавно
        const row = i + 2; // +2 потому что массив с 0, заголовок в строке 1, данные с 2
        const rowData = sheet.getRange(row, 1, 1, 14).getValues()[0];

        // Отправляем в бот
        sendUpdateToBot({
          type: 'shift_update',
          shift: {
            id: rowData[0],
            date: formatDate(rowData[1]),
            start_time: rowData[2],
            end_time: rowData[3],
            specialization: rowData[4],
            executor_id: rowData[5],
            status: rowData[7],
            shift_type: rowData[8],
            coverage_area: rowData[9],
            max_requests: rowData[10],
            notes: rowData[12]
          }
        });

        changedCount++;
      }
    }

    Logger.log(`Periodic sync: processed ${changedCount} changes`);

  } catch (error) {
    Logger.log('Error in periodicSync: ' + error.toString());
  }
}

// ============================================================================
// ВАЛИДАЦИЯ ДАННЫХ
// ============================================================================

/**
 * Валидация смены перед отправкой в бот
 * КРИТИЧЕСКИ ВАЖНО: Проверяем, что исполнитель имеет нужную специализацию!
 */
function validateShiftData(shiftData) {
  const errors = [];

  // Проверка обязательных полей
  if (!shiftData.id) {
    errors.push('ID смены отсутствует');
  }

  if (!shiftData.date) {
    errors.push('Дата смены отсутствует');
  }

  if (!shiftData.specialization) {
    errors.push('Специализация не указана');
  }

  // Если назначен исполнитель - проверяем специализацию
  if (shiftData.executor_id) {
    const executor = getExecutorById(shiftData.executor_id);

    if (!executor) {
      errors.push(`Исполнитель с ID ${shiftData.executor_id} не найден`);
    } else {
      // Проверяем, что у исполнителя есть нужная специализация
      const executorSpecs = executor.specializations.split(', ');

      if (!executorSpecs.includes(shiftData.specialization)) {
        errors.push(
          `Исполнитель ${executor.full_name} не имеет специализации "${shiftData.specialization}". ` +
          `Доступные специализации: ${executor.specializations}`
        );
      }
    }
  }

  return {
    valid: errors.length === 0,
    errors: errors
  };
}

/**
 * Получить исполнителя по ID
 */
function getExecutorById(executorId) {
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(EXECUTORS_SHEET_NAME);
  const data = sheet.getRange(2, 1, sheet.getLastRow() - 1, 8).getValues();

  for (let i = 0; i < data.length; i++) {
    if (data[i][0] === executorId) {
      return {
        id: data[i][0],
        telegram_id: data[i][1],
        full_name: data[i][2],
        specializations: data[i][3],
        rating: data[i][4],
        status: data[i][5],
        phone: data[i][6],
        email: data[i][7]
      };
    }
  }

  return null;
}

// ============================================================================
// ОТПРАВКА ДАННЫХ В БОТ
// ============================================================================

/**
 * Отправить обновление в бот через webhook
 */
function sendUpdateToBot(data) {
  try {
    // Валидация данных (если это смена)
    if (data.type === 'shift_update' && data.shift) {
      const validation = validateShiftData(data.shift);

      if (!validation.valid) {
        Logger.log('Validation failed: ' + validation.errors.join(', '));

        // Показываем ошибку пользователю
        SpreadsheetApp.getUi().alert(
          'Ошибка валидации',
          'Невозможно обновить смену:\n\n' + validation.errors.join('\n'),
          SpreadsheetApp.getUi().ButtonSet.OK
        );

        return false;
      }
    }

    const url = BOT_API_URL + '/api/v1/webhooks/shift-update';
    const payload = JSON.stringify(data);

    // Вычисляем подпись (HMAC-SHA256)
    const signature = Utilities.computeHmacSha256Signature(payload, WEBHOOK_SECRET);
    const signatureHex = signature.map(b => ('0' + (b & 0xFF).toString(16)).slice(-2)).join('');

    // Отправляем запрос
    const options = {
      method: 'post',
      contentType: 'application/json',
      headers: {
        'X-API-Key': API_KEY,
        'X-Webhook-Signature': signatureHex
      },
      payload: payload,
      muteHttpExceptions: true
    };

    const response = UrlFetchApp.fetch(url, options);
    const responseCode = response.getResponseCode();

    if (responseCode === 200) {
      Logger.log('Successfully sent update to bot');
      return true;
    } else {
      Logger.log(`Bot API error: ${responseCode} - ${response.getContentText()}`);
      return false;
    }

  } catch (error) {
    Logger.log('Error sending update to bot: ' + error.toString());
    return false;
  }
}

// ============================================================================
// ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
// ============================================================================

/**
 * Проверка подписи запроса (безопасность)
 */
function verifySignature(e) {
  try {
    const receivedSignature = e.parameter.signature || e.postData.contents.signature;
    const payload = e.postData.contents;

    const expectedSignature = Utilities.computeHmacSha256Signature(payload, WEBHOOK_SECRET);
    const expectedHex = expectedSignature.map(b => ('0' + (b & 0xFF).toString(16)).slice(-2)).join('');

    return receivedSignature === expectedHex;
  } catch (error) {
    Logger.log('Error verifying signature: ' + error.toString());
    return false;
  }
}

/**
 * Создать JSON ответ
 */
function createJsonResponse(statusCode, data) {
  return ContentService
    .createTextOutput(JSON.stringify(data))
    .setMimeType(ContentService.MimeType.JSON);
}

/**
 * Форматировать дату для отправки в бот
 */
function formatDate(date) {
  if (!date) return null;

  if (typeof date === 'string') {
    return date;
  }

  // Форматируем Date объект в ISO строку
  return Utilities.formatDate(date, Session.getScriptTimeZone(), 'yyyy-MM-dd');
}

/**
 * Настройка Script Properties (выполнить вручную один раз)
 */
function setupScriptProperties() {
  const properties = PropertiesService.getScriptProperties();

  // ВАЖНО: Заменить значения на реальные!
  properties.setProperties({
    'BOT_API_URL': 'http://your-bot-url.com',  // URL вашего бота
    'API_KEY': 'your_secure_api_key_here',      // API ключ
    'WEBHOOK_SECRET': 'your_webhook_secret'     // Секрет для подписи
  });

  Logger.log('Script properties configured');
}
```

### 3.3 Настройка триггеров

**Автоматические триггеры нужны для:**
- Отслеживания изменений в таблице (onEdit)
- Периодической синхронизации (каждые 5 минут)

**Шаг 1: Создать триггер onEdit**
1. В Apps Script редакторе нажать на иконку "Triggers" (часы) слева
2. Нажать "+ Add Trigger"
3. Настроить:
   - **Choose which function to run:** `onEdit`
   - **Choose which deployment should run:** `Head`
   - **Select event source:** `From spreadsheet`
   - **Select event type:** `On edit`
4. Нажать "Save"

**Шаг 2: Создать триггер периодической синхронизации**
1. Нажать "+ Add Trigger"
2. Настроить:
   - **Choose which function to run:** `periodicSync`
   - **Choose which deployment should run:** `Head`
   - **Select event source:** `Time-driven`
   - **Select type of time based trigger:** `Minutes timer`
   - **Select minute interval:** `Every 5 minutes`
3. Нажать "Save"

**Шаг 3: Дать разрешения**
1. При первом сохранении триггера появится запрос на разрешения
2. Нажать "Review Permissions"
3. Выбрать ваш Google аккаунт
4. Нажать "Advanced" → "Go to [Project name] (unsafe)"
5. Нажать "Allow"

### 3.4 Публикация Web App

Web App нужен, чтобы бот мог отправлять данные в Sheets через HTTP POST запросы.

**Шаг 1: Deploy Web App**
1. В Apps Script редакторе нажать "Deploy" → "New deployment"
2. В "Select type" выбрать **"Web app"**
3. Настроить:
   - **Description:** `v1.0 - Initial deployment`
   - **Execute as:** `Me (your@email.com)`
   - **Who has access:** `Anyone` *(нужно для доступа от бота)*
4. Нажать "Deploy"

**Шаг 2: Сохранить Web App URL**
1. Скопировать "Web app URL" (например: `https://script.google.com/macros/s/AKfycbz.../exec`)
2. Сохранить в переменные окружения бота: `GOOGLE_APPS_SCRIPT_URL`

**Шаг 3: Настроить Script Properties**
1. В Apps Script редакторе выполнить функцию `setupScriptProperties`
2. Заменить значения:
   ```javascript
   'BOT_API_URL': 'http://sheets-service:8000',  // URL вашего Sheets Service
   'API_KEY': 'your_secure_api_key_here',         // Тот же ключ, что в .env
   'WEBHOOK_SECRET': 'your_webhook_secret'        // Секрет для HMAC подписи
   ```
3. Run → `setupScriptProperties`

**Шаг 4: Тестирование**
```bash
# Отправить тестовый запрос
curl -X POST \
  'https://script.google.com/macros/s/YOUR_SCRIPT_ID/exec' \
  -H 'Content-Type: application/json' \
  -d '{"action":"ping"}'

# Ожидаемый ответ:
# {"status":"ok","message":"pong"}
```

---

## 📋 ЧАСТЬ 4: РАЗРАБОТКА FASTAPI МИКРОСЕРВИСА

Теперь создадим отдельный микросервис `sheets_integration_service`, который будет посредником между ботом и Google Sheets.

### 4.1 Структура проекта

```
sheets_integration_service/
├── app/
│   ├── __init__.py
│   ├── main.py                          # Главный файл FastAPI
│   ├── api/
│   │   └── v1/
│   │       ├── __init__.py
│   │       ├── shifts.py                # Endpoints для смен
│   │       ├── requests.py              # Endpoints для заявок
│   │       ├── sync.py                  # Синхронизация
│   │       └── webhooks.py              # Webhooks от Apps Script
│   ├── services/
│   │   ├── __init__.py
│   │   ├── google_sheets_service.py     # Работа с Google Sheets API
│   │   ├── sync_service.py              # Логика синхронизации
│   │   ├── validation_service.py        # Валидация данных
│   │   ├── conflict_resolution.py       # Разрешение конфликтов
│   │   └── cache_service.py             # Кэширование в Redis
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── shift_schemas.py
│   │   ├── request_schemas.py
│   │   └── sync_schemas.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py                    # Настройки
│   │   ├── security.py                  # Аутентификация
│   │   └── dependencies.py              # FastAPI dependencies
│   └── utils/
│       ├── __init__.py
│       └── formatters.py                # Форматирование данных
├── tests/
│   ├── __init__.py
│   ├── test_sheets_service.py
│   ├── test_sync_service.py
│   └── test_api.py
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── README.md
```

### 4.2 Файл конфигурации (app/core/config.py)

```python
"""
Настройки для Sheets Integration Service
"""

import os
from pathlib import Path
from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    """Настройки приложения"""

    # Основные настройки
    APP_NAME: str = "UK Management Bot - Sheets Integration Service"
    VERSION: str = "1.0.0"
    DEBUG: bool = os.getenv("DEBUG", "False").lower() == "true"

    # API Settings
    API_V1_PREFIX: str = "/api/v1"
    API_KEY: str = os.getenv("SHEETS_API_KEY", "change_me_in_production")
    WEBHOOK_SECRET: str = os.getenv("WEBHOOK_SECRET", "change_me_in_production")

    # Database
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql://uk_bot:password@postgres:5432/uk_management"
    )

    # Redis
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://redis:6379/0")
    CACHE_TTL: int = int(os.getenv("CACHE_TTL", "30"))  # секунды

    # Google Sheets
    GOOGLE_CREDENTIALS_FILE: Path = Path(
        os.getenv(
            "GOOGLE_CREDENTIALS_FILE",
            "/app/credentials/google-service-account.json"
        )
    )
    SHIFTS_SPREADSHEET_ID: str = os.getenv("SHIFTS_SPREADSHEET_ID", "")
    REQUESTS_SPREADSHEET_ID: str = os.getenv("REQUESTS_SPREADSHEET_ID", "")

    # Google Apps Script
    GOOGLE_APPS_SCRIPT_URL: str = os.getenv("GOOGLE_APPS_SCRIPT_URL", "")

    # Rate Limiting (для соблюдения Google API квот)
    SHEETS_API_RATE_LIMIT: int = int(os.getenv("SHEETS_API_RATE_LIMIT", "60"))  # req/min
    SHEETS_API_BURST: int = int(os.getenv("SHEETS_API_BURST", "10"))  # burst size

    # Sync Settings
    SYNC_ENABLED: bool = os.getenv("SYNC_ENABLED", "True").lower() == "true"
    SYNC_INTERVAL: int = int(os.getenv("SYNC_INTERVAL", "300"))  # секунды (5 минут)
    BATCH_SIZE: int = int(os.getenv("BATCH_SIZE", "100"))  # для batch операций

    # Conflict Resolution
    CONFLICT_STRATEGY: str = os.getenv("CONFLICT_STRATEGY", "bot_priority")  # bot_priority | sheets_priority | last_write_wins

    # Logging
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()
```

### 4.3 Сервис Google Sheets (app/services/google_sheets_service.py)

```python
"""
Сервис для работы с Google Sheets API
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.core.config import settings
from app.schemas.shift_schemas import Shift

logger = logging.getLogger(__name__)

# Scopes для Google Sheets API
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive.file'
]


class GoogleSheetsService:
    """Сервис дл�� работы с Google Sheets API v4"""

    def __init__(self):
        """Инициализация сервиса с Service Account credentials"""
        try:
            # Загружаем credentials из JSON файла
            self.credentials = service_account.Credentials.from_service_account_file(
                str(settings.GOOGLE_CREDENTIALS_FILE),
                scopes=SCOPES
            )

            # Создаем клиент для Sheets API
            self.service = build('sheets', 'v4', credentials=self.credentials)

            logger.info("Google Sheets Service initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize Google Sheets Service: {e}")
            raise

    # ========== ЧТЕНИЕ ДАННЫХ ==========

    async def read_shifts_from_sheet(
        self,
        spreadsheet_id: Optional[str] = None
    ) -> List[List[Any]]:
        """
        Читает данные смен из Google Sheets

        Args:
            spreadsheet_id: ID таблицы (по умолчанию из настроек)

        Returns:
            Список строк (каждая строка - список значений)
        """
        try:
            spreadsheet_id = spreadsheet_id or settings.SHIFTS_SPREADSHEET_ID

            # Читаем данные из листа "Планирование смен", начиная со строки 2 (пропускаем заголовки)
            result = self.service.spreadsheets().values().get(
                spreadsheetId=spreadsheet_id,
                range='Планирование смен!A2:N'  # От A2 до N (все колонки)
            ).execute()

            values = result.get('values', [])

            logger.info(f"Read {len(values)} shifts from Google Sheets")

            return values

        except HttpError as e:
            logger.error(f"HTTP error reading from Sheets: {e}")
            raise
        except Exception as e:
            logger.error(f"Error reading from Sheets: {e}")
            raise

    # ========== ЗАПИСЬ ДАННЫХ ==========

    async def update_shifts(
        self,
        shifts: List[Shift],
        spreadsheet_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Обновляет смены в Google Sheets (полная перезапись)

        Args:
            shifts: Список объектов Shift
            spreadsheet_id: ID таблицы

        Returns:
            Результат операции
        """
        try:
            spreadsheet_id = spreadsheet_id or settings.SHIFTS_SPREADSHEET_ID

            # Форматируем данные для вставки
            values = [self._format_shift_row(shift) for shift in shifts]

            # Сначала очищаем существующие данные
            clear_result = self.service.spreadsheets().values().clear(
                spreadsheetId=spreadsheet_id,
                range='Планирование смен!A2:N'
            ).execute()

            # Затем вставляем новые данные
            body = {'values': values}
            update_result = self.service.spreadsheets().values().update(
                spreadsheetId=spreadsheet_id,
                range='Планирование смен!A2',
                valueInputOption='USER_ENTERED',  # Автоматически конвертирует типы
                body=body
            ).execute()

            updated_cells = update_result.get('updatedCells', 0)

            logger.info(f"Updated {len(shifts)} shifts in Google Sheets ({updated_cells} cells)")

            return {
                'success': True,
                'shifts_updated': len(shifts),
                'cells_updated': updated_cells
            }

        except HttpError as e:
            logger.error(f"HTTP error updating Sheets: {e}")
            raise
        except Exception as e:
            logger.error(f"Error updating Sheets: {e}")
            raise

    async def update_single_shift(
        self,
        shift: Shift,
        spreadsheet_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Обновляет одну смену в Google Sheets

        Args:
            shift: Объект Shift
            spreadsheet_id: ID таблицы

        Returns:
            Результат операции
        """
        try:
            spreadsheet_id = spreadsheet_id or settings.SHIFTS_SPREADSHEET_ID

            # Находим строку со сменой по ID
            row_index = await self._find_shift_row(shift.id, spreadsheet_id)

            # Форматируем данные
            row_data = self._format_shift_row(shift)

            if row_index is None:
                # Смена не найдена - добавляем в конец
                body = {'values': [row_data]}
                result = self.service.spreadsheets().values().append(
                    spreadsheetId=spreadsheet_id,
                    range='Планирование смен!A2',
                    valueInputOption='USER_ENTERED',
                    body=body
                ).execute()

                logger.info(f"Added new shift {shift.id} to Sheets")

            else:
                # Смена найдена - обновляем существующую строку
                body = {'values': [row_data]}
                result = self.service.spreadsheets().values().update(
                    spreadsheetId=spreadsheet_id,
                    range=f'Планирование смен!A{row_index}:N{row_index}',
                    valueInputOption='USER_ENTERED',
                    body=body
                ).execute()

                logger.info(f"Updated shift {shift.id} in Sheets at row {row_index}")

            return {
                'success': True,
                'shift_id': shift.id,
                'action': 'added' if row_index is None else 'updated'
            }

        except HttpError as e:
            logger.error(f"HTTP error updating single shift: {e}")
            raise
        except Exception as e:
            logger.error(f"Error updating single shift: {e}")
            raise

    # ========== BATCH ОПЕРАЦИИ ==========

    async def batch_update_shifts(
        self,
        shifts: List[Shift],
        spreadsheet_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Batch обновление смен (эффективнее для большого количества смен)

        Использует batchUpdate вместо множественных update запросов.
        Это соблюдает Google API rate limits.

        Args:
            shifts: Список объектов Shift
            spreadsheet_id: ID таблицы

        Returns:
            Результат операции
        """
        try:
            spreadsheet_id = spreadsheet_id or settings.SHIFTS_SPREADSHEET_ID

            requests = []

            for shift in shifts:
                # Находим строку для каждой смены
                row_index = await self._find_shift_row(shift.id, spreadsheet_id)

                if row_index is None:
                    # Новая смена - добавляем в конец (не используем batch для append)
                    continue

                # Форматируем данные
                row_data = self._format_shift_row(shift)

                # Создаем запрос на обновление
                requests.append({
                    'updateCells': {
                        'range': {
                            'sheetId': 0,  # Первый лист
                            'startRowIndex': row_index - 1,  # 0-indexed
                            'endRowIndex': row_index,
                            'startColumnIndex': 0,  # Колонка A
                            'endColumnIndex': 14  # Колонка N
                        },
                        'rows': [{
                            'values': [{'userEnteredValue': self._format_cell_value(v)} for v in row_data]
                        }],
                        'fields': 'userEnteredValue'
                    }
                })

            # Выполняем batch update
            if requests:
                body = {'requests': requests}
                result = self.service.spreadsheets().batchUpdate(
                    spreadsheetId=spreadsheet_id,
                    body=body
                ).execute()

                logger.info(f"Batch updated {len(requests)} shifts in Google Sheets")

                return {
                    'success': True,
                    'shifts_updated': len(requests)
                }
            else:
                return {
                    'success': True,
                    'shifts_updated': 0
                }

        except HttpError as e:
            logger.error(f"HTTP error in batch update: {e}")
            raise
        except Exception as e:
            logger.error(f"Error in batch update: {e}")
            raise

    # ========== ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ ==========

    def _format_shift_row(self, shift: Shift) -> List[Any]:
        """Форматирует смену для вставки в Google Sheets"""
        return [
            shift.id,                                    # A: ID смены
            shift.date.isoformat() if shift.date else '',  # B: Дата
            shift.start_time if shift.start_time else '',  # C: Время начала
            shift.end_time if shift.end_time else '',      # D: Время окончания
            shift.specialization if shift.specialization else '',  # E: Специализация
            shift.executor_id if shift.executor_id else '',  # F: ID исполнителя
            shift.executor_name if shift.executor_name else '',  # G: ФИО исполнителя
            shift.status if shift.status else 'planned',  # H: Статус
            shift.shift_type if shift.shift_type else 'regular',  # I: Тип смены
            shift.coverage_area if shift.coverage_area else '',  # J: Зона покрытия
            shift.max_requests if shift.max_requests else 10,  # K: Макс. заявок
            shift.current_requests if shift.current_requests else 0,  # L: Текущих заявок
            shift.notes if shift.notes else '',  # M: Примечания
            datetime.now().isoformat()  # N: Последнее обновление
        ]

    def _format_cell_value(self, value: Any) -> Dict[str, Any]:
        """Форматирует значение ячейки для batchUpdate"""
        if isinstance(value, bool):
            return {'boolValue': value}
        elif isinstance(value, (int, float)):
            return {'numberValue': value}
        elif isinstance(value, str):
            return {'stringValue': value}
        else:
            return {'stringValue': str(value)}

    async def _find_shift_row(
        self,
        shift_id: int,
        spreadsheet_id: str
    ) -> Optional[int]:
        """
        Находит номер строки со сменой по ID

        Args:
            shift_id: ID смены
            spreadsheet_id: ID таблицы

        Returns:
            Номер строки (1-indexed) или None если не найдено
        """
        try:
            # Читаем колонку A (ID смен)
            result = self.service.spreadsheets().values().get(
                spreadsheetId=spreadsheet_id,
                range='Планирование смен!A:A'
            ).execute()

            values = result.get('values', [])

            # Ищем строку с нужным ID
            for i, row in enumerate(values):
                if row and len(row) > 0:
                    try:
                        if int(row[0]) == shift_id:
                            return i + 1  # 1-indexed
                    except (ValueError, TypeError):
                        continue

            return None

        except Exception as e:
            logger.error(f"Error finding shift row: {e}")
            return None

    # ========== HEALTHCHECK ==========

    async def healthcheck(self) -> Dict[str, Any]:
        """Проверка доступности Google Sheets API"""
        try:
            # Пробуем получить метаданные таблицы смен
            result = self.service.spreadsheets().get(
                spreadsheetId=settings.SHIFTS_SPREADSHEET_ID
            ).execute()

            return {
                'status': 'ok',
                'spreadsheet_title': result.get('properties', {}).get('title'),
                'sheets_count': len(result.get('sheets', []))
            }

        except Exception as e:
            logger.error(f"Healthcheck failed: {e}")
            return {
                'status': 'error',
                'error': str(e)
            }
```

### 4.4 Сервис синхронизации (app/services/sync_service.py)

```python
"""
Сервис синхронизации между БД и Google Sheets
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from sqlalchemy.orm import Session

from app.services.google_sheets_service import GoogleSheetsService
from app.services.validation_service import ValidationService
from app.services.conflict_resolution import ConflictResolutionService
from app.services.cache_service import CacheService
from app.schemas.shift_schemas import Shift
from app.core.config import settings

logger = logging.getLogger(__name__)


class SyncService:
    """Сервис двусторонней синхронизации"""

    def __init__(
        self,
        db: Session,
        sheets_service: GoogleSheetsService,
        cache_service: CacheService
    ):
        self.db = db
        self.sheets = sheets_service
        self.cache = cache_service
        self.validator = ValidationService(db)
        self.conflict_resolver = ConflictResolutionService(db, sheets_service)

    # ========== БОТ → SHEETS ==========

    async def sync_shifts_to_sheets(
        self,
        full_sync: bool = False
    ) -> Dict[str, Any]:
        """
        Синхронизация смен из БД в Google Sheets

        Args:
            full_sync: Полная синхронизация (всех смен) или только измененных

        Returns:
            Статистика синхронизации
        """
        try:
            logger.info(f"Starting sync to Sheets (full_sync={full_sync})")

            # Получаем смены из БД
            from uk_management_bot.database.models.shift import Shift as ShiftModel

            query = self.db.query(ShiftModel)

            if not full_sync:
                # Только запланированные и активные смены
                query = query.filter(
                    ShiftModel.status.in_(['planned', 'active'])
                )

            db_shifts = query.all()

            # Преобразуем в Pydantic схемы
            shifts = [self._db_shift_to_schema(shift) for shift in db_shifts]

            # Отправляем в Sheets (используем batch для эффективности)
            if len(shifts) > settings.BATCH_SIZE:
                # Разбиваем на батчи
                result = await self._sync_shifts_in_batches(shifts)
            else:
                # Отправляем все сразу
                result = await self.sheets.update_shifts(shifts)

            # Инвалидируем кэш
            await self.cache.invalidate_shifts_cache()

            logger.info(f"Successfully synced {len(shifts)} shifts to Sheets")

            return {
                'success': True,
                'synced_count': len(shifts),
                'full_sync': full_sync,
                'timestamp': datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"Error syncing to Sheets: {e}")
            return {
                'success': False,
                'error': str(e),
                'synced_count': 0
            }

    async def sync_single_shift_to_sheets(
        self,
        shift_id: int
    ) -> Dict[str, Any]:
        """Синхронизация одной смены в Sheets"""
        try:
            # Получаем смену из БД
            from uk_management_bot.database.models.shift import Shift as ShiftModel

            db_shift = self.db.query(ShiftModel).filter(
                ShiftModel.id == shift_id
            ).first()

            if not db_shift:
                return {
                    'success': False,
                    'error': f'Shift {shift_id} not found'
                }

            # Преобразуем и отправляем
            shift = self._db_shift_to_schema(db_shift)
            result = await self.sheets.update_single_shift(shift)

            # Инвалидируем кэш
            await self.cache.invalidate_shift_cache(shift_id)

            return result

        except Exception as e:
            logger.error(f"Error syncing shift {shift_id}: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    # ========== SHEETS → БОТ ==========

    async def sync_shifts_from_sheets(self) -> Dict[str, Any]:
        """
        Синхронизация смен из Google Sheets в БД

        КРИТИЧЕСКИ ВАЖНО: Включает валидацию и разрешение конфликтов!
        """
        try:
            logger.info("Starting sync from Sheets")

            # Читаем данные из Sheets (с кэшем)
            rows = await self.cache.get_cached_shifts()

            if rows is None:
                rows = await self.sheets.read_shifts_from_sheet()
                await self.cache.cache_shifts(rows)

            stats = {
                'total_rows': len(rows),
                'updated': 0,
                'errors': 0,
                'conflicts': 0,
                'skipped': 0
            }

            # Обрабатываем каждую строку
            for row in rows:
                try:
                    result = await self._process_shift_row(row)

                    if result['success']:
                        stats['updated'] += 1
                    elif result.get('conflict'):
                        stats['conflicts'] += 1
                    else:
                        stats['skipped'] += 1

                except Exception as e:
                    logger.error(f"Error processing row: {e}")
                    stats['errors'] += 1

            logger.info(f"Sync from Sheets completed: {stats}")

            return {
                'success': True,
                'stats': stats,
                'timestamp': datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"Error syncing from Sheets: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    async def _process_shift_row(
        self,
        row: List[Any]
    ) -> Dict[str, Any]:
        """Обработка одной строки из Sheets"""

        # Парсим данные строки
        if len(row) < 5:  # Минимум: ID, дата, время начала, время окончания, специализация
            return {'success': False, 'error': 'Incomplete row data'}

        shift_data = {
            'id': int(row[0]) if row[0] else None,
            'date': row[1] if len(row) > 1 else None,
            'start_time': row[2] if len(row) > 2 else None,
            'end_time': row[3] if len(row) > 3 else None,
            'specialization': row[4] if len(row) > 4 else None,
            'executor_id': int(row[5]) if len(row) > 5 and row[5] else None,
            'status': row[7] if len(row) > 7 else 'planned',
            'shift_type': row[8] if len(row) > 8 else 'regular',
            'coverage_area': row[9] if len(row) > 9 else None,
            'max_requests': int(row[10]) if len(row) > 10 and row[10] else 10,
            'notes': row[12] if len(row) > 12 else None,
        }

        # Валидация данных (включая проверку специализаций!)
        validation_result = await self.validator.validate_shift(shift_data)

        if not validation_result['valid']:
            logger.warning(f"Validation failed for shift {shift_data['id']}: {validation_result['errors']}")

            # Откатываем Sheets к валидному состоянию
            await self._revert_shift_in_sheets(shift_data['id'])

            return {
                'success': False,
                'error': 'Validation failed',
                'validation_errors': validation_result['errors']
            }

        # Получаем смену из БД
        from uk_management_bot.database.models.shift import Shift as ShiftModel

        db_shift = self.db.query(ShiftModel).filter(
            ShiftModel.id == shift_data['id']
        ).first()

        if not db_shift:
            logger.warning(f"Shift {shift_data['id']} not found in DB, skipping")
            return {'success': False, 'error': 'Shift not found in DB'}

        # Проверка конфликтов
        conflict_result = await self.conflict_resolver.resolve_conflict(
            db_shift,
            shift_data
        )

        if conflict_result['has_conflict']:
            logger.warning(f"Conflict detected for shift {shift_data['id']}")

            # Применяем стратегию разрешения конфликта
            if conflict_result['resolution'] == 'bot_wins':
                # Откатываем Sheets к состоянию БД
                await self.sync_single_shift_to_sheets(db_shift.id)
                return {'success': False, 'conflict': True, 'resolution': 'bot_wins'}

            elif conflict_result['resolution'] == 'sheets_wins':
                # Обновляем БД из Sheets
                self._apply_changes_to_db(db_shift, shift_data)
                self.db.commit()
                return {'success': True, 'conflict': True, 'resolution': 'sheets_wins'}

        # Нет конфликта - просто обновляем БД
        self._apply_changes_to_db(db_shift, shift_data)
        self.db.commit()

        return {'success': True}

    # ========== ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ ==========

    def _db_shift_to_schema(self, db_shift) -> Shift:
        """Преобразует модель БД в Pydantic схему"""
        return Shift(
            id=db_shift.id,
            date=db_shift.start_time.date() if db_shift.start_time else None,
            start_time=db_shift.start_time.strftime('%H:%M') if db_shift.start_time else None,
            end_time=db_shift.end_time.strftime('%H:%M') if db_shift.end_time else None,
            specialization=db_shift.specialization_focus[0] if db_shift.specialization_focus else None,
            executor_id=db_shift.user_id,
            executor_name=f"{db_shift.user.first_name} {db_shift.user.last_name}" if db_shift.user else None,
            status=db_shift.status,
            shift_type=db_shift.shift_type,
            coverage_area=db_shift.geographic_zone,
            max_requests=db_shift.max_requests,
            current_requests=db_shift.current_request_count,
            notes=db_shift.notes
        )

    def _apply_changes_to_db(self, db_shift, changes: Dict[str, Any]):
        """Применяет изменения к модели БД"""

        # Обновляем только измененные поля
        if 'executor_id' in changes and changes['executor_id'] != db_shift.user_id:
            db_shift.user_id = changes['executor_id']

        if 'status' in changes and changes['status'] != db_shift.status:
            db_shift.status = changes['status']

        if 'notes' in changes and changes['notes'] != db_shift.notes:
            db_shift.notes = changes['notes']

        # Обновляем timestamp
        db_shift.updated_at = datetime.now()

    async def _revert_shift_in_sheets(self, shift_id: int):
        """Откатывает смену в Sheets к валидному состоянию из БД"""
        await self.sync_single_shift_to_sheets(shift_id)

    async def _sync_shifts_in_batches(
        self,
        shifts: List[Shift]
    ) -> Dict[str, Any]:
        """Синхронизация смен батчами для соблюдения rate limits"""

        total_synced = 0
        batch_size = settings.BATCH_SIZE

        for i in range(0, len(shifts), batch_size):
            batch = shifts[i:i + batch_size]

            result = await self.sheets.batch_update_shifts(batch)

            if result['success']:
                total_synced += result['shifts_updated']

            # Небольшая пауза между батчами (rate limiting)
            import asyncio
            await asyncio.sleep(1)

        return {
            'success': True,
            'shifts_updated': total_synced
        }
```

---

## 📋 ЧАСТЬ 5: ИНТЕГРАЦИЯ С СУЩЕСТВУЮЩИМ КОДОМ

### 5.1 Обновление `uk_management_bot/config/settings.py`

Добавить в конец файла:

```python
# Google Sheets Integration Service
SHEETS_SERVICE_ENABLED = os.getenv("SHEETS_SERVICE_ENABLED", "False").lower() == "true"
SHEETS_SERVICE_URL = os.getenv("SHEETS_SERVICE_URL", "http://sheets-service:8000")
SHEETS_SERVICE_API_KEY = os.getenv("SHEETS_SERVICE_API_KEY")

# Google Spreadsheet IDs
SHIFTS_SPREADSHEET_ID = os.getenv("SHIFTS_SPREADSHEET_ID", "")
REQUESTS_SPREADSHEET_ID = os.getenv("REQUESTS_SPREADSHEET_ID", "")

# Google Apps Script Web App URL
GOOGLE_APPS_SCRIPT_URL = os.getenv("GOOGLE_APPS_SCRIPT_URL", "")
```

### 5.2 Создание клиента для Sheets Service

Создать файл: `uk_management_bot/integrations/sheets_client.py`

```python
"""
Клиент для взаимодействия с Sheets Integration Service
"""

import logging
import httpx
from typing import Dict, Any, Optional

from uk_management_bot.config.settings import Settings

logger = logging.getLogger(__name__)
settings = Settings()


class SheetsServiceClient:
    """Клиент для Sheets Integration Service"""

    def __init__(self):
        self.base_url = settings.SHEETS_SERVICE_URL
        self.api_key = settings.SHEETS_SERVICE_API_KEY
        self.enabled = settings.SHEETS_SERVICE_ENABLED

        if self.enabled and not self.api_key:
            logger.warning("Sheets Service enabled but API key not configured")
            self.enabled = False

    async def sync_shift(self, shift) -> Dict[str, Any]:
        """Синхронизировать одну смену в Sheets"""

        if not self.enabled:
            return {'success': False, 'error': 'Service not enabled'}

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{self.base_url}/api/v1/sync/shift/{shift.id}",
                    json={
                        'id': shift.id,
                        'date': shift.start_time.date().isoformat() if shift.start_time else None,
                        'start_time': shift.start_time.strftime('%H:%M') if shift.start_time else None,
                        'end_time': shift.end_time.strftime('%H:%M') if shift.end_time else None,
                        'specialization': shift.specialization_focus[0] if shift.specialization_focus else None,
                        'executor_id': shift.user_id,
                        'status': shift.status,
                        'shift_type': shift.shift_type,
                        'coverage_area': shift.geographic_zone,
                        'max_requests': shift.max_requests,
                        'current_requests': shift.current_request_count,
                        'notes': shift.notes
                    },
                    headers={'X-API-Key': self.api_key}
                )

                if response.status_code == 200:
                    logger.info(f"Successfully synced shift {shift.id} to Sheets")
                    return response.json()
                else:
                    logger.error(f"Failed to sync shift: {response.status_code} - {response.text}")
                    return {'success': False, 'error': response.text}

        except httpx.TimeoutException:
            logger.error(f"Timeout syncing shift {shift.id}")
            return {'success': False, 'error': 'Timeout'}
        except Exception as e:
            logger.error(f"Error syncing shift {shift.id}: {e}")
            return {'success': False, 'error': str(e)}

    async def sync_all_shifts(self) -> Dict[str, Any]:
        """Полная синхронизация всех смен"""

        if not self.enabled:
            return {'success': False, 'error': 'Service not enabled'}

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.base_url}/api/v1/sync/shifts",
                    headers={'X-API-Key': self.api_key}
                )

                if response.status_code == 200:
                    result = response.json()
                    logger.info(f"Successfully synced all shifts: {result}")
                    return result
                else:
                    logger.error(f"Failed to sync shifts: {response.text}")
                    return {'success': False, 'error': response.text}

        except Exception as e:
            logger.error(f"Error syncing all shifts: {e}")
            return {'success': False, 'error': str(e)}

    async def healthcheck(self) -> bool:
        """Проверка доступности Sheets Service"""

        if not self.enabled:
            return False

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(
                    f"{self.base_url}/health",
                    headers={'X-API-Key': self.api_key}
                )

                return response.status_code == 200

        except Exception as e:
            logger.error(f"Sheets Service healthcheck failed: {e}")
            return False


# Глобальный экземпляр клиента
sheets_client = SheetsServiceClient()
```

### 5.3 Добавление хуков в существующие сервисы

**В файле `uk_management_bot/services/shift_service.py`:**

```python
# В начале файла добавить импорт
from uk_management_bot.integrations.sheets_client import sheets_client

# В метод start_shift() добавить после успешного старта смены:
async def start_shift(self, telegram_id: int, notes: Optional[str] = None):
    # ... существующий код ...

    if result['success']:
        shift = result['shift']

        # Синхронизируем с Google Sheets
        try:
            await sheets_client.sync_shift(shift)
        except Exception as e:
            logger.error(f"Failed to sync shift to Sheets: {e}")
            # Не прерываем выполнение - смена уже создана

    return result

# Аналогично в методы: end_shift(), update_shift(), assign_executor()
```

**В файле `uk_management_bot/services/shift_assignment_service.py`:**

```python
# После назначения исполнителя на смену:
async def _assign_single_shift(self, shift, available_executors):
    # ... существующий код назначения ...

    # Синхронизируем обновленную смену
    try:
        await sheets_client.sync_shift(shift)
    except Exception as e:
        logger.error(f"Failed to sync shift to Sheets: {e}")

    return result
```

### 5.4 Команда для ручной синхронизации

Добавить в `uk_management_bot/handlers/admin.py`:

```python
@router.message(Command("sync_sheets"))
@require_role(['admin', 'manager'])
async def sync_shifts_to_sheets(message: Message):
    """Команда для ручной синхронизации смен с Google Sheets"""

    await message.answer("🔄 Начинаю синхронизацию с Google Sheets...")

    try:
        result = await sheets_client.sync_all_shifts()

        if result['success']:
            await message.answer(
                f"✅ Синхронизация завершена!\n\n"
                f"Синхронизировано смен: {result.get('synced_count', 0)}\n"
                f"Время: {result.get('timestamp', 'N/A')}"
            )
        else:
            await message.answer(
                f"❌ Ошибка синхронизации:\n{result.get('error', 'Unknown error')}"
            )

    except Exception as e:
        logger.error(f"Error in sync command: {e}")
        await message.answer(f"❌ Произошла ошибка: {str(e)}")
```

---

## 📋 ЧАСТЬ 6: DOCKER И DEPLOYMENT

### 6.1 Dockerfile для Sheets Service

Создать файл: `sheets_integration_service/Dockerfile`

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Установка зависимостей системы
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Копируем requirements
COPY requirements.txt .

# Устанавливаем Python зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код приложения
COPY app/ ./app/

# Создаем папку для credentials
RUN mkdir -p /app/credentials

# Expose порт
EXPOSE 8000

# Запуск приложения
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
```

### 6.2 Requirements для Sheets Service

Создать файл: `sheets_integration_service/requirements.txt`

```txt
# FastAPI
fastapi==0.104.1
uvicorn[standard]==0.24.0
pydantic==2.5.0
pydantic-settings==2.1.0

# Google APIs
google-api-python-client==2.108.0
google-auth==2.25.2
google-auth-oauthlib==1.2.0
google-auth-httplib2==0.2.0

# Database
sqlalchemy==2.0.23
psycopg2-binary==2.9.9
alembic==1.13.0

# Redis
redis==5.0.1

# HTTP Client
httpx==0.25.2

# Utilities
python-dotenv==1.0.0
python-multipart==0.0.6
```

### 6.3 Обновление docker-compose.dev.yml

Добавить в `docker-compose.dev.yml`:

```yaml
services:
  # ... существующие сервисы ...

  sheets-service:
    build:
      context: ./sheets_integration_service
      dockerfile: Dockerfile
    container_name: uk-sheets-service
    ports:
      - "8003:8000"
    environment:
      # Database
      - DATABASE_URL=postgresql://uk_bot:${POSTGRES_PASSWORD}@postgres:5432/uk_management

      # Redis
      - REDIS_URL=redis://redis:6379/0

      # Google Credentials
      - GOOGLE_CREDENTIALS_FILE=/app/credentials/google-service-account.json
      - SHIFTS_SPREADSHEET_ID=${SHIFTS_SPREADSHEET_ID}
      - REQUESTS_SPREADSHEET_ID=${REQUESTS_SPREADSHEET_ID}

      # Google Apps Script
      - GOOGLE_APPS_SCRIPT_URL=${GOOGLE_APPS_SCRIPT_URL}

      # API Security
      - SHEETS_API_KEY=${SHEETS_API_KEY}
      - WEBHOOK_SECRET=${WEBHOOK_SECRET}

      # Sync Settings
      - SYNC_ENABLED=true
      - SYNC_INTERVAL=300
      - BATCH_SIZE=100

      # Logging
      - LOG_LEVEL=INFO
      - DEBUG=true

    volumes:
      - ./google-credentials:/app/credentials:ro
      - ./sheets_integration_service/app:/app/app

    depends_on:
      - postgres
      - redis

    networks:
      - uk-network

    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s

    restart: unless-stopped
```

### 6.4 Обновление .env файла

Добавить в `.env`:

```env
# ============================================
# GOOGLE SHEETS INTEGRATION
# ============================================

# Sheets Service
SHEETS_SERVICE_ENABLED=true
SHEETS_SERVICE_URL=http://sheets-service:8000
SHEETS_API_KEY=your_secure_api_key_change_me_in_production

# Google Spreadsheet IDs (получить из URL таблиц)
SHIFTS_SPREADSHEET_ID=your_shifts_spreadsheet_id_here
REQUESTS_SPREADSHEET_ID=your_requests_spreadsheet_id_here

# Google Apps Script Web App URL (получить после deployment)
GOOGLE_APPS_SCRIPT_URL=https://script.google.com/macros/s/YOUR_SCRIPT_ID/exec

# Webhook Security
WEBHOOK_SECRET=your_webhook_secret_change_me_in_production

# Google Service Account
GOOGLE_CREDENTIALS_FILE=./google-credentials/google-service-account.json

# Sync Settings
SYNC_INTERVAL=300
BATCH_SIZE=100
CACHE_TTL=30

# Rate Limiting (Google API квоты)
SHEETS_API_RATE_LIMIT=60
SHEETS_API_BURST=10

# Conflict Resolution Strategy
# Варианты: bot_priority | sheets_priority | last_write_wins
CONFLICT_STRATEGY=bot_priority
```

### 6.5 Запуск системы

```bash
# 1. Создать папку для credentials
mkdir -p google-credentials

# 2. Скопировать Google Service Account JSON
cp ~/Downloads/uk-bot-sheets-*.json google-credentials/google-service-account.json

# 3. Установить правильные права
chmod 600 google-credentials/google-service-account.json

# 4. Заполнить .env файл (вставить реальные ID таблиц, API ключи)

# 5. Запустить все сервисы
docker-compose -f docker-compose.dev.yml up --build

# 6. Проверить логи Sheets Service
docker-compose -f docker-compose.dev.yml logs -f sheets-service

# 7. Проверить healthcheck
curl http://localhost:8003/health

# 8. Выполнить первую синхронизацию
curl -X POST http://localhost:8003/api/v1/sync/shifts \
  -H "X-API-Key: your_api_key_here"
```

---

## 📋 ЧАСТЬ 7: БЕЗОПАСНОСТЬ И МОНИТОРИНГ

### 7.1 Чек-лист безопасности

**Google Cloud:**
- ✅ Service Account с минимальными правами (только Sheets API)
- ✅ Credentials файл не в git (добавлен в .gitignore)
- ✅ Файл credentials доступен только для чтения (chmod 600)

**API:**
- ✅ API ключи для аутентификации между сервисами
- ✅ HMAC-SHA256 подпись для webhooks
- ✅ Rate limiting (соблюдение Google квот)
- ✅ Валидация всех входящих данных

**Docker:**
- ✅ Credentials монтируются как read-only volume
- ✅ Сервисы в отдельной Docker network
- ✅ Environment variables для секретов

### 7.2 Мониторинг и алерты

**Метрики для отслеживания:**
- Количество успешных/неуспешных синхронизаций
- Время выполнения синхронизации
- Количество конфликтов данных
- Использование Google API квот
- Ошибки валидации

**Логирование:**
```python
# В каждом сервисе логировать критические операции
logger.info(f"Sync started: {timestamp}")
logger.error(f"Sync failed: {error}")
logger.warning(f"Conflict detected: {details}")
```

**Healthcheck endpoints:**
```python
# sheets-service/app/main.py
@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "sheets-integration-service",
        "version": settings.VERSION,
        "google_sheets_api": await sheets_service.healthcheck(),
        "database": database_health(),
        "redis": redis_health()
    }
```

### 7.3 Обработка ошибок

**Стратегия retry:**
- Exponential backoff для Google API запросов
- Circuit Breaker для предотвращения каскадных сбоев
- Очередь отложенных синхронизаций (в Redis)

**Пример в коде:**
```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=60)
)
async def sync_with_retry(self, shift):
    """Синхронизация с автоматическими повторными попытками"""
    return await self.sheets.update_single_shift(shift)
```

---

## 📋 ЧАСТЬ 8: ТЕСТИРОВАНИЕ

### 8.1 Unit тесты

Создать файл: `sheets_integration_service/tests/test_sheets_service.py`

```python
import pytest
from unittest.mock import Mock, patch
from app.services.google_sheets_service import GoogleSheetsService
from app.schemas.shift_schemas import Shift

@pytest.fixture
def mock_credentials():
    with patch('google.oauth2.service_account.Credentials.from_service_account_file') as mock:
        yield mock

@pytest.fixture
def sheets_service(mock_credentials):
    return GoogleSheetsService()

@pytest.mark.asyncio
async def test_update_shifts(sheets_service):
    """Тест обновления смен в Sheets"""

    shifts = [
        Shift(
            id=1,
            date="2025-10-17",
            start_time="09:00",
            end_time="17:00",
            specialization="electric",
            executor_id=2,
            status="planned"
        )
    ]

    with patch.object(sheets_service.service.spreadsheets().values(), 'update') as mock_update:
        mock_update.return_value.execute.return_value = {'updatedCells': 14}

        result = await sheets_service.update_shifts(shifts)

        assert result['success'] == True
        assert result['shifts_updated'] == 1
        mock_update.assert_called_once()

@pytest.mark.asyncio
async def test_read_shifts(sheets_service):
    """Тест чтения смен из Sheets"""

    mock_data = [
        [1, "2025-10-17", "09:00", "17:00", "electric", 2, "Иван Петров", "planned", "regular", "", 10, 0, "", "2025-10-17 10:00:00"]
    ]

    with patch.object(sheets_service.service.spreadsheets().values(), 'get') as mock_get:
        mock_get.return_value.execute.return_value = {'values': mock_data}

        result = await sheets_service.read_shifts_from_sheet()

        assert len(result) == 1
        assert result[0][0] == 1
        mock_get.assert_called_once()
```

### 8.2 Integration тесты

```python
@pytest.mark.integration
@pytest.mark.asyncio
async def test_full_sync_cycle():
    """Тест полного цикла синхронизации: БД → Sheets → БД"""

    # 1. Создаем смену в БД
    shift = create_test_shift()

    # 2. Синхронизируем в Sheets
    result = await sync_service.sync_shifts_to_sheets()
    assert result['success'] == True

    # 3. Читаем из Sheets
    rows = await sheets_service.read_shifts_from_sheet()
    assert len(rows) > 0

    # 4. Модифицируем в Sheets (имитируем редактирование менеджером)
    # ... изменяем данные ...

    # 5. Синхронизируем обратно в БД
    result = await sync_service.sync_shifts_from_sheets()
    assert result['success'] == True

    # 6. Проверяем, что изменения применились
    updated_shift = db.query(Shift).filter(Shift.id == shift.id).first()
    assert updated_shift.status == "modified_status"
```

### 8.3 E2E тесты

```python
@pytest.mark.e2e
@pytest.mark.asyncio
async def test_specialization_validation():
    """
    E2E тест: Проверка валидации специализаций

    Сценарий:
    1. Создаем смену "электрик" в боте
    2. Синхронизируем в Sheets
    3. В Sheets пытаемся назначить исполнителя без специализации "электрик"
    4. Синхронизация должна откатить изменение
    """

    # 1. Создаем смену
    shift = Shift(
        date="2025-10-17",
        specialization="electric",
        status="planned"
    )
    db.add(shift)
    db.commit()

    # 2. Синхронизируем в Sheets
    await sheets_client.sync_shift(shift)

    # 3. Симулируем редактирование в Sheets (неправильный исполнитель)
    invalid_executor_id = get_executor_without_specialization("electric")

    # Обновляем в Sheets
    await modify_shift_in_sheets(shift.id, executor_id=invalid_executor_id)

    # 4. Триггер Apps Script отправляет webhook в бот
    webhook_data = {
        'type': 'shift_update',
        'shift': {
            'id': shift.id,
            'executor_id': invalid_executor_id
        }
    }

    # 5. Бот обрабатывает webhook и валидирует
    response = await process_webhook(webhook_data)

    # 6. Проверяем результат
    assert response['validation_failed'] == True
    assert 'специализации' in response['error'].lower()

    # 7. Проверяем, что Sheets откатился к валидному состоянию
    sheet_data = await sheets_service.read_shifts_from_sheet()
    shift_row = find_shift_in_data(sheet_data, shift.id)
    assert shift_row[5] != invalid_executor_id  # executor_id не изменился
```

---

## 🎯 ПЛАН РЕАЛИЗАЦИИ (Timeline)

### **Фаза 1: Базовая настройка (2-3 дня)**

**День 1: Google Cloud Setup**
- [ ] Создать Google Cloud Project
- [ ] Включить APIs (Sheets + Drive)
- [ ] Создать Service Account
- [ ] Скачать credentials JSON
- [ ] Создать таблицы в Google Sheets
- [ ] Поделиться таблицами с Service Account
- [ ] Получить IDs таблиц

**День 2: Google Apps Script**
- [ ] Создать проект Apps Script
- [ ] Написать код синхронизации (Code.gs)
- [ ] Настроить триггеры (onEdit, periodicSync)
- [ ] Опубликовать Web App
- [ ] Протестировать doPost endpoint
- [ ] Настроить Script Properties

**День 3: Docker и Environment**
- [ ] Создать структуру `sheets_integration_service/`
- [ ] Написать Dockerfile
- [ ] Обновить docker-compose.dev.yml
- [ ] Настроить .env переменные
- [ ] Настроить volume для credentials
- [ ] Протестировать запуск контейнера

### **Фаза 2: Backend разработка (4-5 дней)**

**День 4: Core Services**
- [ ] Написать GoogleSheetsService
- [ ] Написать ValidationService (с проверкой специализаций!)
- [ ] Написать CacheService
- [ ] Протестировать чтение/запись в Sheets

**День 5: Sync Logic**
- [ ] Написать SyncService (БД → Sheets)
- [ ] Написать SyncService (Sheets → БД)
- [ ] Реализовать ConflictResolutionService
- [ ] Добавить batch операции

**День 6-7: API Endpoints**
- [ ] Написать endpoints для синхронизации
- [ ] Написать webhooks обработчики
- [ ] Добавить аутентификацию (API ключи)
- [ ] Добавить signature verification
- [ ] Написать healthcheck endpoint

**День 8: Integration с ботом**
- [ ] Создать SheetsServiceClient
- [ ] Добавить хуки в ShiftService
- [ ] Добавить хуки в ShiftAssignmentService
- [ ] Добавить команду /sync_sheets
- [ ] Обновить settings.py

### **Фаза 3: Тестирование (3-4 дня)**

**День 9-10: Unit & Integration тесты**
- [ ] Написать unit тесты для GoogleSheetsService
- [ ] Написать unit тесты для SyncService
- [ ] Написать integration тесты
- [ ] Написать тесты для conflict resolution

**День 11: E2E тесты**
- [ ] Тест: создание смены в боте → появление в Sheets
- [ ] Тест: редактирование в Sheets → обновление в боте
- [ ] Тест: валидация специализаций работает
- [ ] Тест: конфликты разрешаются корректно

**День 12: Stress testing**
- [ ] Тест производительности (1000+ смен)
- [ ] Тест rate limiting
- [ ] Тест обработки ошибок
- [ ] Тест retry механизмов

### **Фаза 4: Production Deployment (2-3 дня)**

**День 13: Подготовка к production**
- [ ] Настроить production .env
- [ ] Сгенерировать secure API ключи
- [ ] Настроить логирование (уровни, форматы)
- [ ] Настроить мониторинг
- [ ] Создать документацию

**День 14: Deployment**
- [ ] Deploy на production сервер
- [ ] Проверить connectivity
- [ ] Выполнить первую синхронизацию
- [ ] Настроить backup (credentials, data)

**День 15: Мониторинг и оптимизация**
- [ ] Настроить алерты
- [ ] Мониторить Google API quotas
- [ ] Оптимизировать batch размеры
- [ ] Настроить автоматические backups

---

## ✅ ЧЕКЛИСТ ГОТОВНОСТИ

### Google Cloud Platform
- [ ] Проект создан и настроен
- [ ] Google Sheets API включен
- [ ] Google Drive API включен
- [ ] Service Account создан
- [ ] Credentials JSON скачан и сохранен безопасно
- [ ] Email Service Account скопирован

### Google Sheets
- [ ] Таблица "Управление сменами" создана
- [ ] Таблица "Мониторинг заявок" создана
- [ ] Структура листов настроена
- [ ] Data Validation добавлена
- [ ] Таблицы поделены с Service Account
- [ ] IDs таблиц сохранены

### Google Apps Script
- [ ] Проект Apps Script создан
- [ ] Код Code.gs написан
- [ ] Триггеры настроены (onEdit, periodicSync)
- [ ] Web App опубликован
- [ ] Script Properties настроены
- [ ] Тестовый POST запрос успешен

### Backend Service
- [ ] Структура проекта создана
- [ ] GoogleSheetsService реализован
- [ ] SyncService реализован
- [ ] ValidationService с проверкой специализаций
- [ ] ConflictResolutionService реализован
- [ ] API endpoints реализованы
- [ ] Webhooks реализованы
- [ ] Security (API keys, signatures) настроены

### Integration с ботом
- [ ] settings.py обновлен
- [ ] SheetsServiceClient создан
- [ ] Хуки в ShiftService добавлены
- [ ] Хуки в ShiftAssignmentService добавлены
- [ ] Команда /sync_sheets добавлена

### Docker & Deployment
- [ ] Dockerfile создан
- [ ] docker-compose.yml обновлен
- [ ] .env настроен (все переменные заполнены)
- [ ] Credentials volume настроен
- [ ] Healthcheck работает
- [ ] Сервис запускается без ошибок

### Тестирование
- [ ] Unit тесты написаны и проходят
- [ ] Integration тесты написаны и проходят
- [ ] E2E тесты написаны и проходят
- [ ] Валидация специализаций протестирована
- [ ] Stress testing выполнен

### Production Ready
- [ ] Secure API ключи сгенерированы
- [ ] Production credentials настроены
- [ ] Логирование настроено
- [ ] Мониторинг настроен
- [ ] Backup стратегия определена
- [ ] Документация написана

---

## 📊 ОЖИДАЕМЫЕ РЕЗУЛЬТАТЫ

После завершения интеграции получим:

### Функциональность
✅ **Двусторонняя синхронизация** Bot ↔️ Google Sheets
✅ **Редактирование смен** в удобной таблице
✅ **Real-time обновления** (через onEdit trigger)
✅ **Валидация данных** (включая специализации)
✅ **Разрешение конфликтов** (автоматическое)
✅ **Batch операции** (для больших объемов данных)
✅ **Rate limiting** (соблюдение Google квот)

### Безопасность
✅ **Service Account** с минимальными правами
✅ **API ключи** для аутентификации
✅ **HMAC подписи** для webhooks
✅ **Валидация всех данных** перед применением
✅ **Credentials** не в git, read-only mount

### Производительность
✅ **Кэширование** в Redis (30s TTL)
✅ **Batch updates** вместо отдельных запросов
✅ **Асинхронные операции**
✅ **Circuit Breaker** для защиты от сбоев
✅ **Retry механизм** с exponential backoff

### Мониторинг
✅ **Healthcheck endpoints**
✅ **Детальное логирование** всех операций
✅ **Метрики синхронизации**
✅ **Алерты при ошибках**

---

## 🔗 ПОЛЕЗНЫЕ ССЫЛКИ

### Документация Google
- [Google Sheets API v4](https://developers.google.com/sheets/api)
- [Google Apps Script](https://developers.google.com/apps-script)
- [Service Account Authentication](https://cloud.google.com/iam/docs/service-accounts)
- [API Quotas and Limits](https://developers.google.com/sheets/api/limits)

### Библиотеки Python
- [google-api-python-client](https://github.com/googleapis/google-api-python-client)
- [FastAPI](https://fastapi.tiangolo.com/)
- [SQLAlchemy](https://docs.sqlalchemy.org/)
- [Redis Python](https://redis-py.readthedocs.io/)

### Best Practices
- [Google Sheets API Best Practices](https://developers.google.com/sheets/api/guides/concepts)
- [Rate Limiting Strategies](https://cloud.google.com/apis/design/design_patterns)
- [Conflict Resolution Patterns](https://martinfowler.com/articles/patterns-of-distributed-systems/conflicting-writes.html)

---

## 📞 ПОДДЕРЖКА И ВОПРОСЫ

При возникновении проблем:

1. **Проверить логи:**
   ```bash
   docker-compose -f docker-compose.dev.yml logs -f sheets-service
   ```

2. **Проверить healthcheck:**
   ```bash
   curl http://localhost:8003/health
   ```

3. **Проверить Google Apps Script logs:**
   - В Apps Script редакторе: Executions → View executions

4. **Проверить Google API quotas:**
   - Google Cloud Console → APIs & Services → Quotas

---

**Конец документа**

*Версия: 1.0*
*Дата: 17 октября 2025*
*Автор: Claude Code Analysis*
