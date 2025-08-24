# 📊 ПРОСТАЯ ИНТЕГРАЦИЯ С GOOGLE SHEETS (БЕЗ API)

## 🎯 **ОБЗОР**

Этот подход позволяет интегрировать UK Management Bot с Google Sheets **без использования API** через простой CSV экспорт/импорт.

### **✅ ПРЕИМУЩЕСТВА:**
- 🚀 **Простая настройка** - не требует API ключей
- 🔧 **Быстрый старт** - работает сразу
- 📁 **Локальный контроль** - данные в CSV файлах
- 🔄 **Автоматическая синхронизация** - real-time обновления
- 💾 **Резервные копии** - автоматическое создание backup

### **⚠️ ОГРАНИЧЕНИЯ:**
- 📊 **Не real-time** - обновления через CSV файлы
- 🔒 **Публичный доступ** - таблица должна быть доступна по ссылке
- 📈 **Ручной импорт** - нужно импортировать CSV в Google Sheets

---

## 🛠️ **НАСТРОЙКА GOOGLE SHEETS**

### **Шаг 1: Создание Google Sheets таблицы**

1. Перейдите на [Google Sheets](https://sheets.google.com)
2. Создайте новую таблицу
3. Назовите её "UK Management - Заявки"

### **Шаг 2: Настройка структуры таблицы**

Создайте лист "Заявки" со следующими заголовками:

| A | B | C | D | E | F | G | H | I | J | K | L | M | N | O | P | Q |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **ID заявки** | **Дата создания** | **Статус** | **Категория** | **Адрес** | **Описание** | **Срочность** | **Заявитель ID** | **Заявитель имя** | **Исполнитель ID** | **Исполнитель имя** | **Дата назначения** | **Дата выполнения** | **Комментарии** | **Фото ссылки** | **Последнее обновление** | **История изменений** |

### **Шаг 3: Настройка публичного доступа**

1. Нажмите кнопку **"Share"** (в правом верхнем углу)
2. Выберите **"Change to anyone with the link"**
3. Установите права доступа:
   - **Viewer** - для просмотра
   - **Editor** - для редактирования (если нужно)
4. Скопируйте ссылку на таблицу

### **Шаг 4: Создание листа "Статистика"**

Создайте второй лист "Статистика":


| A | B | C | D |
|---|---|---|---|
| **Метрика** | **Значение** | **Дата** | **Время** |

---

## ⚙️ **НАСТРОЙКА ПРОЕКТА**

### **Шаг 1: Обновление переменных окружения**

Добавьте в файл `.env`:

```env
# Simple Google Sheets Integration (без API)
SIMPLE_SHEETS_URL=https://docs.google.com/spreadsheets/d/YOUR_SPREADSHEET_ID/edit
SIMPLE_SHEETS_CSV_PATH=data/requests_export.csv
SIMPLE_SHEETS_SYNC_ENABLED=true
```

### **Шаг 2: Создание директории для данных**

```bash
mkdir -p data
```

### **Шаг 3: Настройка прав доступа**

```bash
chmod 755 data
chmod 644 data/requests_export.csv
```

---

## 🔄 **ПРОЦЕСС СИНХРОНИЗАЦИИ**

### **Автоматическая синхронизация:**

1. **Создание заявки** → Автоматически добавляется в CSV
2. **Обновление статуса** → Автоматически обновляется в CSV
3. **Добавление комментариев** → Автоматически обновляется в CSV

### **Ручной импорт в Google Sheets:**

1. Откройте Google Sheets таблицу
2. Перейдите в **File** → **Import**
3. Выберите **"Upload"** → загрузите CSV файл
4. Выберите **"Replace current sheet"**
5. Нажмите **"Import data"**

### **Автоматизация импорта:**

Можно настроить автоматический импорт через:
- **Google Apps Script** - скрипт для автоматического импорта
- **Zapier** - интеграция для автоматической синхронизации
- **IFTTT** - автоматизация через webhooks

---

## 📋 **ИСПОЛЬЗОВАНИЕ**

### **Интеграция с RequestService:**

```python
# В файле uk_management_bot/services/request_service.py
from integrations.simple_sheets_sync import simple_sheets_sync

# При создании заявки
async def create_request_with_sync(self, ...):
    request = await self.create_request(...)
    
    # Синхронизация с CSV
    await simple_sheets_sync.add_request_to_csv(request.to_dict())
    
    return request

# При обновлении заявки
async def update_request_with_sync(self, ...):
    request = await self.update_request_status(...)
    
    # Синхронизация изменений
    changes = {"status": new_status, "comments": notes}
    await simple_sheets_sync.update_request_in_csv(request.id, changes)
    
    return request
```

### **Полный экспорт данных:**

```python
# Экспорт всех заявок
all_requests = await request_service.get_all_requests()
await simple_sheets_sync.export_requests_to_csv(all_requests)
```

### **Получение статистики:**

```python
# Статистика синхронизации
stats = await simple_sheets_sync.get_statistics()
print(f"Всего заявок: {stats['total_requests']}")
print(f"Размер файла: {stats['file_size']} байт")
```

---

## 🔧 **НАСТРОЙКА АВТОМАТИЧЕСКОГО ИМПОРТА**

### **Google Apps Script (рекомендуется):**

1. Откройте Google Sheets
2. Перейдите в **Extensions** → **Apps Script**
3. Создайте скрипт:

```javascript
function importCSVFromURL() {
  // URL к вашему CSV файлу (если размещен на веб-сервере)
  var csvUrl = "https://your-domain.com/data/requests_export.csv";
  
  try {
    var response = UrlFetchApp.fetch(csvUrl);
    var csvContent = response.getContentText();
    
    // Парсим CSV
    var csvData = Utilities.parseCsv(csvContent);
    
    // Получаем активный лист
    var sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName("Заявки");
    
    // Очищаем существующие данные (кроме заголовков)
    sheet.getRange(2, 1, sheet.getLastRow(), sheet.getLastColumn()).clear();
    
    // Добавляем новые данные
    if (csvData.length > 1) { // Если есть данные кроме заголовков
      sheet.getRange(2, 1, csvData.length - 1, csvData[0].length).setValues(csvData.slice(1));
    }
    
    Logger.log("CSV импортирован успешно");
  } catch (error) {
    Logger.log("Ошибка импорта: " + error.toString());
  }
}

// Функция для автоматического запуска каждые 5 минут
function createTrigger() {
  ScriptApp.newTrigger('importCSVFromURL')
    .timeBased()
    .everyMinutes(5)
    .create();
}
```

4. Сохраните скрипт
5. Запустите функцию `createTrigger()` один раз для настройки автоматического импорта

---

## 📊 **МОНИТОРИНГ И ОТЛАДКА**

### **Проверка статуса синхронизации:**

```python
status = await simple_sheets_sync.get_sync_status()
print(f"Синхронизация включена: {status['enabled']}")
print(f"CSV файл существует: {status['csv_file_exists']}")
print(f"Размер файла: {status['csv_file_size']} байт")
```

### **Создание резервной копии:**

```python
backup_path = await simple_sheets_sync.create_backup()
print(f"Резервная копия создана: {backup_path}")
```

### **Логирование:**

Все операции логируются с помощью `structlog`:

```python
# Примеры логов
logger.info("Request added to CSV successfully", request_id=123)
logger.warning("CSV file not found", file_path="data/requests.csv")
logger.error("Failed to update request in CSV", error="Permission denied")
```

---

## 🚀 **ПРОИЗВОДСТВЕННАЯ НАСТРОЙКА**

### **Для production окружения:**

1. **Безопасное хранение CSV:**
```bash
# Создайте защищенную директорию
sudo mkdir -p /var/uk-bot/data
sudo chown uk-bot:uk-bot /var/uk-bot/data
sudo chmod 750 /var/uk-bot/data
```

2. **Обновите переменные окружения:**
```env
SIMPLE_SHEETS_CSV_PATH=/var/uk-bot/data/requests_export.csv
```

3. **Настройте автоматические backup:**
```bash
# Добавьте в crontab
0 2 * * * /usr/bin/cp /var/uk-bot/data/requests_export.csv /var/uk-bot/backups/requests_$(date +\%Y\%m\%d).csv
```

4. **Мониторинг:**
```bash
# Проверка размера файла
ls -lh /var/uk-bot/data/requests_export.csv

# Проверка последнего обновления
stat /var/uk-bot/data/requests_export.csv
```

---

## ✅ **ТЕСТИРОВАНИЕ**

Запустите тесты для проверки функциональности:

```bash
python test_simple_sheets_sync.py
```

Ожидаемый результат:
```
🎉 Все тесты прошли успешно!
✅ Simple Google Sheets Sync готов к использованию
```

---

## 📞 **ПОДДЕРЖКА**

### **Частые проблемы:**

1. **CSV файл не создается:**
   - Проверьте права доступа к директории
   - Убедитесь, что путь указан правильно

2. **Данные не импортируются в Google Sheets:**
   - Проверьте формат CSV файла
   - Убедитесь, что кодировка UTF-8

3. **Автоматический импорт не работает:**
   - Проверьте настройки Google Apps Script
   - Убедитесь, что триггер создан правильно

### **Полезные команды:**

```bash
# Проверка CSV файла
head -5 data/requests_export.csv

# Подсчет строк
wc -l data/requests_export.csv

# Проверка кодировки
file data/requests_export.csv
```

---

**🎯 Simple Google Sheets Integration готов к использованию!**
