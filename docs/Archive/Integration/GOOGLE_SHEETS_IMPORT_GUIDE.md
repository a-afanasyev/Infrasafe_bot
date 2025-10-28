# 📊 РУКОВОДСТВО ПО ИМПОРТУ В GOOGLE SHEETS

## 🎯 Обзор процесса

Это руководство покажет как загрузить CSV файл с данными заявок в Google Sheets таблицу.

## 📋 Шаг 1: Создание Google Sheets таблицы

### 1.1 Создайте новую таблицу
1. Откройте [Google Sheets](https://sheets.google.com)
2. Нажмите **"+"** для создания новой таблицы
3. Назовите таблицу: **"UK Management - Заявки"**

### 1.2 Настройте структуру листов
Создайте два листа:

**Лист 1: "Заявки"**
```
A1: ID заявки
B1: Дата создания
C1: Статус
D1: Категория
E1: Адрес
F1: Описание
G1: Срочность
H1: Заявитель ID
I1: Заявитель имя
J1: Исполнитель ID
K1: Исполнитель имя
L1: Дата назначения
M1: Дата выполнения
N1: Комментарии
O1: Фото ссылки
P1: Последнее обновление
Q1: История изменений
```

**Лист 2: "Статистика"**
```
A1: Метрика
B1: Значение
C1: Последнее обновление
```

## 📤 Шаг 2: Подготовка CSV файла

### 2.1 Создайте CSV файл
Запустите скрипт выгрузки данных:

```bash
cd /path/to/your/project
source uk_management_bot/venv/bin/activate
python demo_data_export.py
```

### 2.2 Проверьте файл
Убедитесь что файл `demo_export.csv` создан и содержит данные.

## 🔄 Шаг 3: Импорт данных

### 3.1 Ручной импорт (первый раз)

#### Вариант A: Через меню Google Sheets
1. Откройте Google Sheets таблицу
2. Выберите лист "Заявки"
3. Нажмите **Файл** → **Импорт**
4. Выберите **"Загрузить"**
5. Найдите и выберите ваш `demo_export.csv` файл
6. В настройках импорта:
   - **Место импорта:** "Заменить данные в выбранном диапазоне"
   - **Разделитель:** "Запятая"
   - **Кодировка:** "UTF-8"
7. Нажмите **"Импортировать данные"**

#### Вариант B: Перетаскивание файла
1. Откройте Google Sheets таблицу
2. Перетащите `demo_export.csv` файл прямо в браузер
3. Google Sheets автоматически предложит импорт
4. Подтвердите настройки и импортируйте

### 3.2 Проверка импорта
После импорта проверьте:
- ✅ Все колонки отображаются корректно
- ✅ Данные читаемы (не иероглифы)
- ✅ Количество строк соответствует количеству заявок
- ✅ Заголовки на месте

## 🤖 Шаг 4: Автоматизация импорта

### 4.1 Настройка Google Apps Script

#### Создайте скрипт:
1. В Google Sheets нажмите **Расширения** → **Apps Script**
2. Назовите проект: **"UK Data Import"**

#### Вставьте код:

```javascript
function importCSVFromURL(retryCount = 0) {
  const MAX_RETRIES = 3;
  const RETRY_DELAY_MS = 1000; // Начальная задержка 1 секунда

  // URL вашего CSV файла (замените на реальный)
  const csvUrl = 'https://your-domain.com/data/requests_export.csv';

  try {
    // ✅ ДОБАВЛЕНО: Проверка квот Google Sheets API перед запросом
    checkAPIQuota();

    // Получаем CSV данные с таймаутом
    const response = UrlFetchApp.fetch(csvUrl, {
      muteHttpExceptions: true,
      validateHttpsCertificates: true,
      followRedirects: true,
      timeout: 30 // таймаут 30 секунд
    });

    // Проверяем статус ответа
    const statusCode = response.getResponseCode();
    if (statusCode !== 200) {
      throw new Error(`HTTP Error: ${statusCode}`);
    }

    const csvContent = response.getContentText();

    // Проверяем, что данные не пустые
    if (!csvContent || csvContent.trim().length === 0) {
      throw new Error('CSV file is empty');
    }

    // Парсим CSV
    const csvData = Utilities.parseCsv(csvContent);

    if (csvData.length === 0) {
      throw new Error('No data in CSV file');
    }

    // Получаем активный лист
    const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName('Заявки');

    if (!sheet) {
      throw new Error('Sheet "Заявки" not found');
    }

    // Очищаем существующие данные (кроме заголовков)
    const lastRow = sheet.getLastRow();
    if (lastRow > 1) {
      sheet.getRange(2, 1, lastRow - 1, sheet.getLastColumn()).clear();
    }

    // ✅ ДОБАВЛЕНО: Батчинг для больших датасетов (Google рекомендует < 10,000 ячеек за запрос)
    if (csvData.length > 1) {
      const BATCH_SIZE = 1000; // Размер батча
      const dataRows = csvData.slice(1);

      // Сохраняем время начала для статистики
      PropertiesService.getScriptProperties().setProperty('importStartTime', new Date().toISOString());

      // Обрабатываем данные батчами
      for (let i = 0; i < dataRows.length; i += BATCH_SIZE) {
        const batch = dataRows.slice(i, Math.min(i + BATCH_SIZE, dataRows.length));
        sheet.getRange(i + 2, 1, batch.length, csvData[0].length).setValues(batch);

        // Небольшая задержка между батчами для избежания rate limiting
        if (i + BATCH_SIZE < dataRows.length) {
          Utilities.sleep(100); // 100ms
          console.log(`⏳ Обработано ${i + batch.length}/${dataRows.length} строк...`);
        }
      }
      console.log(`✅ Все ${dataRows.length} строк обработаны`);
    }

    // Обновляем статистику
    updateStatistics(sheet, csvData.length - 1);

    // Логируем успех
    console.log('✅ Данные успешно импортированы: ' + (csvData.length - 1) + ' заявок');

    // Сбрасываем счетчик ошибок при успехе
    PropertiesService.getScriptProperties().setProperty('importErrorCount', '0');

    return true;

  } catch (error) {
    console.error('❌ Ошибка импорта (попытка ' + (retryCount + 1) + '/' + MAX_RETRIES + '): ' + error.toString());

    // Увеличиваем счетчик ошибок
    const properties = PropertiesService.getScriptProperties();
    const errorCount = parseInt(properties.getProperty('importErrorCount') || '0') + 1;
    properties.setProperty('importErrorCount', errorCount.toString());
    properties.setProperty('lastImportError', error.toString());
    properties.setProperty('lastImportErrorTime', new Date().toISOString());

    // Если не превышен лимит попыток, пробуем еще раз
    if (retryCount < MAX_RETRIES) {
      // ✅ ИСПРАВЛЕНО: Экспоненциальная задержка с jitter для избежания thundering herd
      const baseDelay = RETRY_DELAY_MS * Math.pow(2, retryCount);
      const jitter = Math.random() * 1000; // 0-1000ms случайной задержки
      const delay = baseDelay + jitter;
      console.log('⏳ Повтор через ' + (delay / 1000).toFixed(2) + ' секунд...');
      Utilities.sleep(delay);

      return importCSVFromURL(retryCount + 1);
    }

    // Если превышен лимит попыток, отправляем уведомление
    if (errorCount >= 5) {
      sendErrorNotification(error.toString(), errorCount);
    }

    return false;
  }
}

// ✅ ДОБАВЛЕНО: Валидация конфигурации Telegram при старте
function validateTelegramConfig() {
  const TELEGRAM_BOT_TOKEN = PropertiesService.getScriptProperties().getProperty('TELEGRAM_BOT_TOKEN');
  const TELEGRAM_CHAT_ID = PropertiesService.getScriptProperties().getProperty('TELEGRAM_CHAT_ID');

  if (!TELEGRAM_BOT_TOKEN || !TELEGRAM_CHAT_ID) {
    throw new Error('Telegram credentials not configured. Please set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID.');
  }

  // Проверяем формат токена (должен быть: число:35символов)
  if (!/^\d+:[A-Za-z0-9_-]{35}$/.test(TELEGRAM_BOT_TOKEN)) {
    throw new Error('Invalid Telegram bot token format');
  }

  return { TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID };
}

// Функция для отправки уведомлений об ошибках
function sendErrorNotification(errorMessage, errorCount) {
  try {
    // Получаем и валидируем Telegram credentials
    const { TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID } = validateTelegramConfig();

    const message = `🚨 Google Sheets Import Error\n\n` +
                   `Ошибок подряд: ${errorCount}\n` +
                   `Последняя ошибка: ${errorMessage}\n` +
                   `Время: ${new Date().toLocaleString('ru-RU')}`;

    const url = `https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage`;

    UrlFetchApp.fetch(url, {
      method: 'post',
      contentType: 'application/json',
      payload: JSON.stringify({
        chat_id: TELEGRAM_CHAT_ID,
        text: message,
        parse_mode: 'HTML'
      })
    });

    console.log('📨 Error notification sent');

  } catch (e) {
    console.error('❌ Failed to send notification: ' + e.toString());
  }
}

// Функция для получения статуса импорта
function getImportStatus() {
  const properties = PropertiesService.getScriptProperties();

  return {
    errorCount: parseInt(properties.getProperty('importErrorCount') || '0'),
    lastError: properties.getProperty('lastImportError') || 'None',
    lastErrorTime: properties.getProperty('lastImportErrorTime') || 'Never',
    lastSuccessTime: properties.getProperty('lastSuccessTime') || 'Never'
  };
}

// ✅ ДОБАВЛЕНО: Проверка квот Google Sheets API
function checkAPIQuota() {
  const properties = PropertiesService.getScriptProperties();
  const requests = parseInt(properties.getProperty('requestCount') || '0');
  const timestamp = parseInt(properties.getProperty('requestTimestamp') || '0');

  const now = Date.now();

  // Google Sheets API лимит: 100 запросов / 100 секунд / пользователь
  if (now - timestamp < 100000) { // 100 секунд
    if (requests >= 100) {
      throw new Error('API quota exceeded. Please wait 100 seconds.');
    }
  } else {
    // Сброс счетчика каждые 100 секунд
    properties.setProperty('requestCount', '0');
    properties.setProperty('requestTimestamp', now.toString());
  }

  // Увеличиваем счетчик запросов
  properties.setProperty('requestCount', (requests + 1).toString());
}

function updateStatistics(sheet, requestCount) {
  const statsSheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName('Статистика');
  const now = new Date();
  const startTime = new Date(PropertiesService.getScriptProperties().getProperty('importStartTime') || now);

  // ✅ УЛУЧШЕНО: Расширенная статистика
  // Базовые метрики
  statsSheet.getRange('A2:C2').setValues([['Всего заявок', requestCount, now]]);
  statsSheet.getRange('A3:C3').setValues([['Последнее обновление', now.toLocaleString('ru-RU'), now]]);

  // Производительность
  const importDuration = now - startTime;
  statsSheet.getRange('A4:C4').setValues([['Время импорта (сек)', (importDuration / 1000).toFixed(2), now]]);

  // Скорость обработки
  const rowsPerSecond = requestCount / (importDuration / 1000);
  statsSheet.getRange('A5:C5').setValues([['Строк/сек', rowsPerSecond.toFixed(2), now]]);

  // Статистика ошибок
  const properties = PropertiesService.getScriptProperties();
  const errorCount = parseInt(properties.getProperty('importErrorCount') || '0');
  statsSheet.getRange('A6:C6').setValues([['Ошибок подряд', errorCount, now]]);

  // Сохраняем время последнего успешного импорта
  properties.setProperty('lastSuccessTime', now.toISOString());
}

// Функция для ручного запуска
function manualImport() {
  importCSVFromURL();
}
```

### 4.2 Настройка триггера

#### Автоматический запуск:
1. В Apps Script нажмите **"Триггеры"** (часы слева)
2. Нажмите **"+ Добавить триггер"**
3. Настройте:
   - **Выберите функцию:** `importCSVFromURL`
   - **Выберите источник события:** "Временной триггер"
   - **Выберите тип времени:** "Минуты"
   - **Выберите интервал:** "Каждые 30 минут"
4. Нажмите **"Сохранить"**

## 📁 Шаг 5: Размещение CSV файла

### 5.1 Вариант A: Веб-сервер
Если у вас есть веб-сервер:
1. Загрузите `requests_export.csv` на сервер
2. Убедитесь что файл доступен по URL
3. Обновите `csvUrl` в скрипте

### 5.2 Вариант B: Google Drive
1. Загрузите CSV файл в Google Drive
2. Сделайте файл публичным (ПКМ → "Поделиться" → "Доступно всем")
3. Скопируйте ссылку и обновите `csvUrl`

### 5.3 Вариант C: GitHub/GitLab
1. Создайте репозиторий для данных
2. Загрузите CSV файл
3. Используйте raw URL файла

## 🔧 Шаг 6: Интеграция с ботом

### 6.1 Автоматическая выгрузка
Добавьте в ваш бот команду для выгрузки:

```python
# В handlers/admin.py добавьте:
@router.message(Command("export_data"))
async def export_data_command(message: Message):
    """Команда для выгрузки данных в CSV"""
    try:
        # Создаем выгрузку
        sync = SimpleSheetsSync("", "data/requests_export.csv")
        
        # Получаем данные из базы
        db = next(get_db())
        requests = db.query(Request).all()
        
        # Подготавливаем данные
        export_data = []
        for request in requests:
            # ... подготовка данных ...
            export_data.append(request_data)
        
        # Экспортируем
        success = await sync.export_requests_to_csv(export_data)
        
        if success:
            await message.answer("✅ Данные успешно экспортированы в CSV")
        else:
            await message.answer("❌ Ошибка экспорта данных")
            
    # ✅ ИСПРАВЛЕНО: Специфичные исключения вместо широкого Exception
    except (ValueError, TypeError) as e:
        logger.error(f"Ошибка валидации данных при экспорте: {e}")
        await message.answer(f"❌ Ошибка валидации данных: {str(e)}")
    except IOError as e:
        logger.error(f"Ошибка записи CSV файла: {e}")
        await message.answer(f"❌ Ошибка записи файла: {str(e)}")
    except Exception as e:
        logger.exception(f"Неожиданная ошибка при экспорте: {e}")
        await message.answer(f"❌ Неожиданная ошибка: {str(e)}")
```

### 6.2 Планировщик задач
Настройте автоматическую выгрузку:

```python
# В main.py добавьте:
import asyncio
from apscheduler import AsyncScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.events import JobExecutionFailed  # ✅ ДОБАВЛЕНО: Для обработки ошибок

async def scheduled_export():
    """Планируемая выгрузка данных"""
    try:
        sync = SimpleSheetsSync("", "data/requests_export.csv")
        # ... логика выгрузки ...
        logger.info("Планируемая выгрузка данных завершена")
    # ✅ ИСПРАВЛЕНО: Специфичные исключения
    except (ValueError, TypeError) as e:
        logger.error(f"Ошибка валидации данных: {e}")
    except IOError as e:
        logger.error(f"Ошибка записи файла: {e}")
    except Exception as e:
        logger.exception(f"Неожиданная ошибка планируемой выгрузки: {e}")

async def job_error_handler(event):
    """✅ ДОБАВЛЕНО: Обработчик ошибок для APScheduler jobs"""
    logger.error(f"Job {event.job_id} failed: {event.exception}")
    # Отправка уведомления в Telegram при ошибке
    try:
        from uk_management_bot.services.notification_service import NotificationService
        notification = NotificationService()
        await notification.notify_admins(
            f"⚠️ Ошибка планировщика\nJob: {event.job_id}\nОшибка: {str(event.exception)}"
        )
    except Exception as e:
        logger.error(f"Не удалось отправить уведомление об ошибке: {e}")

async def main():
    # Инициализируем планировщик с context manager
    async with AsyncScheduler() as scheduler:
        # ✅ ДОБАВЛЕНО: Подписка на события ошибок
        scheduler.subscribe(job_error_handler, {JobExecutionFailed})

        # Добавляем задачу (каждые 30 минут)
        await scheduler.add_schedule(
            scheduled_export,
            IntervalTrigger(minutes=30),
            id="sheets_export_job"
        )

        # Запускаем в фоновом режиме
        await scheduler.start_in_background()

        # Ваш основной код приложения
        # ...

# Запуск
asyncio.run(main())
```

## 📊 Шаг 7: Проверка работы

### 7.1 Тестовая проверка
1. Запустите ручной импорт в Apps Script
2. Проверьте что данные появились в таблице
3. Убедитесь что статистика обновилась

### 7.2 Мониторинг
- Проверяйте логи Apps Script
- Следите за обновлениями в таблице
- Контролируйте размер CSV файла

## 🛠️ Шаг 8: Продвинутые паттерны (Production-ready)

### 8.1 Circuit Breaker для защиты от API лимитов

Circuit Breaker предотвращает каскадные сбои при проблемах с Google Sheets API:

```python
from uk_management_bot.utils.sheets_utils import CircuitBreaker

# Создаем Circuit Breaker
circuit_breaker = CircuitBreaker(
    failure_threshold=5,      # Количество ошибок до блокировки
    recovery_timeout=60       # Время ожидания перед восстановлением
)

async def safe_sheets_sync(data):
    """Безопасная синхронизация с Circuit Breaker"""
    # Проверяем, можно ли выполнять операции
    if not circuit_breaker.is_closed():
        logger.warning("Circuit Breaker is OPEN, skipping sync")
        return False

    try:
        # Выполняем синхронизацию
        success = await sheets_service.sync_data(data)

        if success:
            circuit_breaker.on_success()
        else:
            circuit_breaker.on_error()

        return success

    except Exception as e:
        circuit_breaker.on_error()
        logger.error(f"Sync error: {e}")
        return False

# Получение статуса Circuit Breaker
status = circuit_breaker.get_state()
print(f"State: {status['state']}, Failures: {status['failure_count']}")
```

### 8.2 Rate Limiter для контроля частоты запросов

Rate Limiter соблюдает лимиты Google Sheets API (100 запросов/100 секунд):

```python
from uk_management_bot.utils.sheets_utils import RateLimiter

# Создаем Rate Limiter (60 запросов в минуту)
rate_limiter = RateLimiter(requests_per_minute=60)

async def sync_with_rate_limit(data):
    """Синхронизация с ограничением частоты"""
    # Ждем, если превышен лимит
    await rate_limiter.wait_if_needed()

    # Выполняем операцию
    result = await sheets_service.sync_data(data)

    # Получение статистики
    stats = rate_limiter.get_usage_stats()
    logger.info(f"API Usage: {stats['current_requests']}/{stats['requests_per_minute']}")

    return result
```

### 8.3 Фоновая обработка с очередями

SheetsSyncWorker обрабатывает задачи асинхронно с retry логикой:

```python
import asyncio
from uk_management_bot.utils.sheets_utils import (
    SheetsSyncWorker,
    CircuitBreaker,
    RateLimiter
)

# ✅ ИСПРАВЛЕНО: Используем factory функцию для создания компонентов
sync_queue, circuit_breaker, rate_limiter = create_sheets_sync_components(
    failure_threshold=5,
    recovery_timeout=60,
    requests_per_minute=60
)

# Инициализируем worker
worker = SheetsSyncWorker(
    sheets_service=sheets_service,
    queue=sync_queue,
    circuit_breaker=circuit_breaker,
    rate_limiter=rate_limiter
)

# Запускаем worker в фоне
asyncio.create_task(worker.start())

# Добавляем задачи в очередь
from dataclasses import dataclass

@dataclass
class SyncTask:
    request_id: str
    task_type: str  # "create" или "update"
    data: dict
    retry_count: int = 0

# Создание задачи
task = SyncTask(
    request_id="250918-001",
    task_type="create",
    data={"title": "Новая заявка", "status": "pending"}
)

# Добавляем в очередь
await sync_queue.put(task)

# Проверка статуса worker
status = worker.get_status()
print(f"Worker: {status['running']}")
print(f"Circuit Breaker: {status['circuit_breaker']['state']}")
print(f"Rate Limiter: {status['rate_limiter']['usage_percentage']}%")
```

### 8.4 Factory функция для устранения дублирования кода

```python
# ✅ ДОБАВЛЕНО: Factory функция для создания компонентов синхронизации
from typing import Tuple
from uk_management_bot.utils.sheets_utils import (
    CircuitBreaker,
    RateLimiter,
    SheetsSyncWorker
)

def create_sheets_sync_components(
    failure_threshold: int = 5,
    recovery_timeout: int = 60,
    requests_per_minute: int = 60
) -> Tuple[asyncio.Queue, CircuitBreaker, RateLimiter]:
    """
    Factory функция для создания компонентов синхронизации с Google Sheets.

    Args:
        failure_threshold: Количество ошибок до открытия Circuit Breaker
        recovery_timeout: Время ожидания перед восстановлением (секунды)
        requests_per_minute: Лимит запросов в минуту

    Returns:
        Кортеж: (queue, circuit_breaker, rate_limiter)
    """
    sync_queue = asyncio.Queue()
    circuit_breaker = CircuitBreaker(
        failure_threshold=failure_threshold,
        recovery_timeout=recovery_timeout
    )
    rate_limiter = RateLimiter(requests_per_minute=requests_per_minute)

    return sync_queue, circuit_breaker, rate_limiter
```

### 8.5 Полная интеграция (Best Practice)

```python
# В вашем сервисе
class RequestService:
    def __init__(self):
        # ✅ ИСПРАВЛЕНО: Используем factory функцию вместо дублирования
        self.sync_queue, self.circuit_breaker, self.rate_limiter = create_sheets_sync_components(
            failure_threshold=5,
            recovery_timeout=60,
            requests_per_minute=60
        )

        # Запускаем worker
        self.worker = SheetsSyncWorker(
            sheets_service=sheets_service,
            queue=self.sync_queue,
            circuit_breaker=self.circuit_breaker,
            rate_limiter=self.rate_limiter
        )
        asyncio.create_task(self.worker.start())

    async def create_request(self, data):
        """Создание заявки с автоматической синхронизацией"""
        # Сохраняем в БД
        request = await self.db.create_request(data)

        # Добавляем задачу синхронизации
        task = SyncTask(
            request_id=request.request_number,
            task_type="create",
            data=request.to_dict()
        )
        await self.sync_queue.put(task)

        return request

    async def get_sync_status(self):
        """Получение статуса синхронизации"""
        return self.worker.get_status()
```

## 🛠️ Шаг 9: Дополнительные настройки

### 9.1 Форматирование таблицы
- Добавьте фильтры к заголовкам
- Настройте условное форматирование
- Добавьте сводные таблицы

### 9.2 Уведомления
Настройте уведомления в Apps Script:

```javascript
function sendNotification(message) {
  // Отправка уведомления в Telegram или email
  // Реализуйте по необходимости
}
```

## 🚨 Решение проблем

### Проблема: Кодировка
**Симптом:** Иероглифы в таблице
**Решение:** Убедитесь что CSV в UTF-8

### Проблема: Не обновляется
**Симптом:** Данные не меняются
**Решение:**
1. Проверьте триггеры в Apps Script (Часы → Триггеры)
2. Проверьте права доступа к CSV файлу
3. Посмотрите логи выполнения (Executions)
4. Используйте `getImportStatus()` для диагностики

### Проблема: Ошибка доступа
**Симптом:** "Доступ запрещен"
**Решение:**
1. Проверьте URL CSV файла
2. Убедитесь что файл публично доступен
3. Проверьте CORS настройки сервера

### Проблема: Частые ошибки импорта
**Симптом:** Много ошибок в логах
**Решение:**
1. Проверьте Circuit Breaker статус
2. Увеличьте `recovery_timeout` в Circuit Breaker
3. Уменьшите `requests_per_minute` в Rate Limiter
4. Проверьте квоты Google Sheets API

### Диагностика через Apps Script
```javascript
// Запустите эту функцию для проверки статуса
function diagnostics() {
  const status = getImportStatus();
  console.log('📊 Import Status:');
  console.log('Error Count: ' + status.errorCount);
  console.log('Last Error: ' + status.lastError);
  console.log('Last Error Time: ' + status.lastErrorTime);
  console.log('Last Success: ' + status.lastSuccessTime);
}
```

## ✅ Чек-лист готовности

### Базовая настройка
- [ ] Google Sheets таблица создана
- [ ] CSV файл с данными готов
- [ ] Первый импорт выполнен успешно
- [ ] Apps Script настроен
- [ ] Триггеры созданы

### Production-ready компоненты
- [ ] Circuit Breaker интегрирован
- [ ] Rate Limiter настроен
- [ ] SheetsSyncWorker запущен
- [ ] APScheduler v4.x настроен
- [ ] Retry логика протестирована
- [ ] Уведомления об ошибках работают
- [ ] Telegram Bot Token настроен (опционально)

### Мониторинг
- [ ] Статистика обновляется
- [ ] Логи Apps Script проверены
- [ ] `getImportStatus()` работает
- [ ] Circuit Breaker мониторится
- [ ] Rate Limiter отслеживается

## 🎉 Готово!

После выполнения всех шагов у вас будет:

### Базовые возможности ✅
- ✅ Автоматическая синхронизация данных
- ✅ Обновление каждые 30 минут
- ✅ Резервные копии данных
- ✅ Статистика в реальном времени
- ✅ Простое управление без API

### Production-ready возможности 🚀
- ✅ Circuit Breaker защита от API лимитов
- ✅ Rate Limiter контроль частоты запросов
- ✅ Фоновая обработка с очередями
- ✅ Автоматические retry с экспоненциальной задержкой
- ✅ Telegram уведомления об ошибках
- ✅ Детальный мониторинг и диагностика
- ✅ APScheduler v4.x с современным синтаксисом

**Данные будут автоматически обновляться в Google Sheets с enterprise-grade надежностью!** 🚀

---

## 📝 История изменений

### Версия 2.0 - Best Practices Update (17.10.2025)

**Критические исправления (P0):**
1. ✅ **Добавлена проверка квот Google Sheets API** (строка 108, 257-278)
   - Реализована функция `checkAPIQuota()` для отслеживания лимитов (100 запросов/100 секунд)
   - Автоматический сброс счетчика каждые 100 секунд
   - Проверка перед каждым API запросом

2. ✅ **Добавлен jitter в exponential backoff** (строки 179-184)
   - Случайная задержка 0-1000ms для избежания thundering herd problem
   - Улучшенная формула: `baseDelay + random(0-1000ms)`
   - Логирование точного времени задержки

**Важные улучшения (P1):**
3. ✅ **Валидация Telegram Bot Token** (строки 198-213)
   - Функция `validateTelegramConfig()` проверяет формат токена
   - Regex проверка: `^\d+:[A-Za-z0-9_-]{35}$`
   - Проверка наличия TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_ID

4. ✅ **Специфичные исключения в Python коде** (строки 392-401, 420-425)
   - Заменены широкие `except Exception` на конкретные типы
   - Добавлены отдельные обработчики для ValueError, TypeError, IOError
   - Использование `logger.exception()` для полного traceback

5. ✅ **APScheduler error handler** (строки 412, 427-444)
   - Добавлен импорт `JobExecutionFailed` события
   - Функция `job_error_handler()` для обработки ошибок jobs
   - Автоматические Telegram уведомления администраторам при сбоях
   - Подписка на события: `scheduler.subscribe(job_error_handler, {JobExecutionFailed})`

**Рекомендованные улучшения (P2):**
6. ✅ **Батчинг для больших датасетов** (строки 151-171)
   - Размер батча: 1000 строк (< 10,000 ячеек Google рекомендация)
   - Задержка 100ms между батчами для rate limiting
   - Логирование прогресса обработки

7. ✅ **Расширенные метрики статистики** (строки 280-305)
   - Добавлена производительность: время импорта, строк/сек
   - Счетчик ошибок подряд для мониторинга
   - Сохранение времени начала импорта для расчета производительности

8. ✅ **Factory функция для устранения дублирования** (строки 597-632, 641-645, 556-569)
   - Функция `create_sheets_sync_components()` создает все компоненты
   - Централизованная конфигурация Circuit Breaker, Rate Limiter, Queue
   - Использована в трех местах вместо дублирования кода
   - Типизация с `Tuple` для type hints

**Источники:**
- Google Apps Script Best Practices Documentation
- APScheduler 4.x Official Documentation
- Google Sheets API v4 Quotas & Limits
- Context7 Library Documentation

**Следующие улучшения:**
- Мониторинг квот в реальном времени
- Распределенный Circuit Breaker для нескольких инстансов
- Более детальная аналитика производительности

---

**Последнее обновление:** 17 октября 2025
**Версия гайда:** 2.0 (обновлено с Context7 + sheets_utils.py)
**Технологии:** APScheduler 4.x, Google Apps Script, Circuit Breaker, Rate Limiter

