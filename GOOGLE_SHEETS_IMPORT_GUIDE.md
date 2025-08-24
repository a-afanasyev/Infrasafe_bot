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
function importCSVFromURL() {
  // URL вашего CSV файла (замените на реальный)
  const csvUrl = 'https://your-domain.com/data/requests_export.csv';
  
  try {
    // Получаем CSV данные
    const response = UrlFetchApp.fetch(csvUrl);
    const csvContent = response.getContentText();
    
    // Парсим CSV
    const csvData = Utilities.parseCsv(csvContent);
    
    // Получаем активный лист
    const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName('Заявки');
    
    // Очищаем существующие данные (кроме заголовков)
    const lastRow = sheet.getLastRow();
    if (lastRow > 1) {
      sheet.getRange(2, 1, lastRow - 1, sheet.getLastColumn()).clear();
    }
    
    // Вставляем новые данные
    if (csvData.length > 1) { // Если есть данные кроме заголовков
      sheet.getRange(2, 1, csvData.length - 1, csvData[0].length).setValues(csvData.slice(1));
    }
    
    // Обновляем статистику
    updateStatistics(sheet, csvData.length - 1);
    
    console.log('Данные успешно импортированы: ' + (csvData.length - 1) + ' заявок');
    
  } catch (error) {
    console.error('Ошибка импорта: ' + error.toString());
  }
}

function updateStatistics(sheet, requestCount) {
  const statsSheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName('Статистика');
  
  // Обновляем статистику
  statsSheet.getRange('A2').setValue('Всего заявок');
  statsSheet.getRange('B2').setValue(requestCount);
  statsSheet.getRange('C2').setValue(new Date());
  
  statsSheet.getRange('A3').setValue('Последнее обновление');
  statsSheet.getRange('B3').setValue(new Date().toLocaleString('ru-RU'));
  statsSheet.getRange('C3').setValue(new Date());
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
            
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")
```

### 6.2 Планировщик задач
Настройте автоматическую выгрузку:

```python
# В main.py добавьте:
import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# Создаем планировщик
scheduler = AsyncIOScheduler()

async def scheduled_export():
    """Планируемая выгрузка данных"""
    try:
        sync = SimpleSheetsSync("", "data/requests_export.csv")
        # ... логика выгрузки ...
        logger.info("Планируемая выгрузка данных завершена")
    except Exception as e:
        logger.error(f"Ошибка планируемой выгрузки: {e}")

# Добавляем задачу (каждые 30 минут)
scheduler.add_job(scheduled_export, 'interval', minutes=30)
scheduler.start()
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

## 🛠️ Шаг 8: Дополнительные настройки

### 8.1 Форматирование таблицы
- Добавьте фильтры к заголовкам
- Настройте условное форматирование
- Добавьте сводные таблицы

### 8.2 Уведомления
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
**Решение:** Проверьте триггеры и права доступа

### Проблема: Ошибка доступа
**Симптом:** "Доступ запрещен"
**Решение:** Проверьте настройки доступа к файлу

## ✅ Чек-лист готовности

- [ ] Google Sheets таблица создана
- [ ] CSV файл с данными готов
- [ ] Первый импорт выполнен успешно
- [ ] Apps Script настроен
- [ ] Триггеры созданы
- [ ] Автоматическая выгрузка работает
- [ ] Статистика обновляется
- [ ] Уведомления настроены

## 🎉 Готово!

После выполнения всех шагов у вас будет:
- ✅ Автоматическая синхронизация данных
- ✅ Обновление каждые 30 минут
- ✅ Резервные копии данных
- ✅ Статистика в реальном времени
- ✅ Простое управление без API

**Данные будут автоматически обновляться в Google Sheets!** 🚀

