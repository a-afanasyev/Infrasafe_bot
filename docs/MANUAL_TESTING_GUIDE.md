# Manual Testing Guide - UK Management Bot

> _Последнее редактирование: 2025-10-29_

**Version**: 1.0
**Last Updated**: 20 October 2025
**Bot**: @infrasafebot
**Environment**: Production (docker-compose.dev.yml)

---

## 📋 Table of Contents

1. [Введение](#введение)
2. [Подготовка к тестированию](#подготовка-к-тестированию)
3. [Роли пользователей](#роли-пользователей)
4. [User Stories и Test Scenarios](#user-stories-и-test-scenarios)
5. [Критические пути тестирования](#критические-пути-тестирования)
6. [Чеклист функциональности](#чеклист-функциональности)
7. [Тестовые данные](#тестовые-данные)
8. [Known Issues](#known-issues)
9. [Reporting Bugs](#reporting-bugs)

---

## Введение

### Цель документа

Этот документ предоставляет comprehensive руководство для ручного тестирования UK Management Bot. Он включает:
- Все user stories с acceptance criteria
- Подробные test scenarios
- Чек-листы для каждого модуля
- Критические пути (happy path & edge cases)
- Тестовые данные

### Scope тестирования

**Покрываемые модули** (29 handlers, 481+ endpoints):
- ✅ Аутентификация и онбординг
- ✅ Управление заявками (CRUD + статусы)
- ✅ Система смен (планирование, назначения, передачи)
- ✅ Управление пользователями (верификация, сотрудники)
- ✅ Адресная система (дворы, дома, квартиры)
- ✅ Админ-панель (настройки, статистика)
- ✅ Отчеты и комментарии
- ✅ AI-системы (auto-assignment, workload prediction)

---

## Подготовка к тестированию

### Требования

#### 1. Доступы
- [ ] Telegram аккаунт
- [ ] Доступ к боту @infrasafebot
- [ ] 3+ тестовых аккаунта с разными ролями
- [ ] Доступ к базе данных (для проверки данных)

#### 2. Тестовое окружение
- [ ] Docker запущен: `docker-compose -f docker-compose.dev.yml ps`
- [ ] Все сервисы healthy
- [ ] База данных доступна
- [ ] Redis работает

#### 3. Инструменты
- [ ] Telegram на телефоне + desktop
- [ ] Скриншоты для баг-репортов
- [ ] Notepad для записи багов
- [ ] Секундомер (для тестирования производительности)

---

### Проверка готовности системы

```bash
# 1. Проверка Docker сервисов
docker-compose -f docker-compose.dev.yml ps
# Ожидается: все сервисы Up (healthy)

# 2. Проверка логов бота
docker-compose -f docker-compose.dev.yml logs --tail=50 app | grep "Бот успешно запущен"
# Ожидается: "✅ Бот успешно запущен и готов к работе"

# 3. Проверка базы данных
docker-compose -f docker-compose.dev.yml exec postgres psql -U uk_bot uk_management -c "SELECT COUNT(*) FROM users;"
# Ожидается: количество пользователей

# 4. Проверка планировщика
docker-compose -f docker-compose.dev.yml logs app | grep "Планировщик смен запущен"
# Ожидается: "Планировщик: 9 задач активно"
```

**Если хотя бы одна проверка не прошла** - обратитесь к DevOps перед началом тестирования.

---

## Роли пользователей

### Описание ролей

#### 1. Applicant (Заявитель) 👤
**Права**:
- Создание заявок
- Просмотр своих заявок
- Добавление комментариев
- Просмотр статуса

**Ограничения**:
- Не видит других заявок
- Не может назначать исполнителей
- Не может изменять статусы (кроме "Уточнение")

**Тестовый аккаунт**: См. раздел "Тестовые данные"

---

#### 2. Executor (Исполнитель) 🔧
**Права**:
- Просмотр назначенных заявок
- Принятие/отклонение заявок
- Изменение статусов (В работе, Выполнена, Не выполнена)
- Добавление отчетов и фото
- Управление своими сменами
- Передача смен

**Ограничения**:
- Видит только свои заявки
- Не может создавать смены
- Не может назначать других

**Тестовый аккаунт**: См. раздел "Тестовые данные"

---

#### 3. Manager (Менеджер) 👔
**Права**:
- Все права Executor
- Просмотр всех заявок
- Назначение исполнителей
- Изменение любых статусов
- Создание и управление сменами
- Квартальное планирование
- Просмотр статистики
- Управление адресной системой

**Ограничения**:
- Не может изменять системные настройки
- Не может управлять пользователями (кроме верификации)

**Тестовый аккаунт**: См. раздел "Тестовые данные"

---

#### 4. Admin (Администратор) 👑
**Права**:
- Все права Manager
- Управление пользователями
- Системные настройки
- Доступ к логам
- Управление сотрудниками
- Изменение ролей
- Полный доступ к базе данных

**Ограничения**: Нет

**Тестовый аккаунт**: Супер-админ из init_admin.py

---

## Подготовка тестовых данных

### ⚠️ ВАЖНО: Обязательная последовательность подготовки

Перед началом тестирования **НЕОБХОДИМО** выполнить подготовку данных в строгой последовательности. Регистрация пользователей (US-001) и большинство других сценариев требуют наличия адресной иерархии и базовых данных.

**Последовательность подготовки**:
1. ✅ Создание адресной иерархии (дворы → дома → квартиры)
2. ✅ Создание тестовых пользователей с назначением квартир
3. ✅ Верификация исполнителей
4. ✅ Создание тестовых смен
5. ✅ Генерация исторических данных (для статистики и AI)

---

### 1. Создание адресной иерархии

#### Шаг 1.1: Создание дворов

**Метод 1: Через SQL (быстрый способ)**

```sql
-- Создание двух дворов с координатами
INSERT INTO yards (name, latitude, longitude, description, created_at)
VALUES
  ('Двор 1 (Северный)', 41.299496, 69.240073, 'Северный жилой комплекс', NOW()),
  ('Двор 2 (Южный)', 41.311151, 69.279737, 'Южный жилой комплекс', NOW());

-- Проверка создания
SELECT id, name, latitude, longitude FROM yards;
-- Ожидается: 2 двора с id=1 и id=2
```

**Метод 2: Через бота (ручной способ)**

1. Войти как Manager или Admin
2. Открыть меню → "⚙️ Админ-панель"
3. Нажать "🏘️ Управление адресами"
4. Выбрать "Дворы"
5. Нажать "➕ Добавить двор"
6. Ввести название: `Двор 1 (Северный)`
7. Ввести координаты (или пропустить): `41.299496, 69.240073`
8. Ввести описание: `Северный жилой комплекс`
9. **Результат**: ✅ "Двор успешно добавлен"
10. Повторить для "Двор 2 (Южный)" с координатами `41.311151, 69.279737`

**Проверка**:
```bash
# Проверка через БД
docker-compose -f docker-compose.dev.yml exec postgres psql -U uk_bot uk_management -c "SELECT id, name FROM yards;"

# Ожидается:
#  id |        name
# ----+--------------------
#   1 | Двор 1 (Северный)
#   2 | Двор 2 (Южный)
```

---

#### Шаг 1.2: Создание домов внутри дворов

**Метод 1: Через SQL (быстрый способ)**

```sql
-- Создание 3 домов: 2 в Дворе 1, 1 в Дворе 2
INSERT INTO buildings (yard_id, number, floors, entrances, apartments_count, created_at)
VALUES
  (1, '1', 5, 2, 40, NOW()),  -- Дом 1 в Дворе 1
  (1, '2', 9, 3, 72, NOW()),  -- Дом 2 в Дворе 1
  (2, '1', 4, 1, 20, NOW());  -- Дом 1 в Дворе 2

-- Проверка создания
SELECT b.id, y.name AS yard_name, b.number, b.floors, b.entrances, b.apartments_count
FROM buildings b
JOIN yards y ON b.yard_id = y.id
ORDER BY y.id, b.number;

-- Ожидается: 3 дома с правильными yard_id
```

**Метод 2: Через бота (ручной способ)**

1. Войти как Manager/Admin
2. "⚙️ Админ-панель" → "🏘️ Управление адресами"
3. Выбрать "Дома"
4. Нажать "➕ Добавить дом"
5. Выбрать двор: "Двор 1 (Северный)"
6. Ввести номер дома: `1`
7. Ввести количество этажей: `5`
8. Ввести количество подъездов: `2`
9. Ввести количество квартир: `40`
10. **Результат**: ✅ "Дом успешно добавлен"
11. Повторить для:
    - Дом 2 в Дворе 1: этажей=9, подъездов=3, квартир=72
    - Дом 1 в Дворе 2: этажей=4, подъездов=1, квартир=20

**Проверка связей**:
```sql
-- Проверка иерархии двор → дома
SELECT
  y.name AS yard,
  COUNT(b.id) AS buildings_count,
  STRING_AGG(b.number, ', ' ORDER BY b.number) AS building_numbers
FROM yards y
LEFT JOIN buildings b ON y.id = b.yard_id
GROUP BY y.id, y.name
ORDER BY y.id;

-- Ожидается:
--        yard        | buildings_count | building_numbers
-- -------------------+-----------------+------------------
--  Двор 1 (Северный) |               2 | 1, 2
--  Двор 2 (Южный)    |               1 | 1
```

---

#### Шаг 1.3: Создание квартир

**Метод 1: Через SQL (массовое создание - рекомендуется)**

```sql
-- Функция для массового создания квартир
CREATE OR REPLACE FUNCTION create_apartments_for_building(
  p_building_id INT,
  p_start_number INT,
  p_count INT
) RETURNS VOID AS $$
DECLARE
  i INT;
BEGIN
  FOR i IN 0..(p_count - 1) LOOP
    INSERT INTO apartments (building_id, number, floor, entrance, created_at)
    VALUES (
      p_building_id,
      (p_start_number + i)::TEXT,
      ((i / 4) + 1),  -- 4 квартиры на этаж
      ((i / 20) + 1), -- 20 квартир на подъезд
      NOW()
    );
  END LOOP;
END;
$$ LANGUAGE plpgsql;

-- Создание квартир для всех домов
SELECT create_apartments_for_building(1, 1, 40);   -- Дом 1, Двор 1: квартиры 1-40
SELECT create_apartments_for_building(2, 41, 72);  -- Дом 2, Двор 1: квартиры 41-112
SELECT create_apartments_for_building(3, 1, 20);   -- Дом 1, Двор 2: квартиры 1-20

-- Проверка создания
SELECT
  b.id AS building_id,
  y.name AS yard,
  b.number AS building,
  COUNT(a.id) AS apartments_count
FROM apartments a
JOIN buildings b ON a.building_id = b.id
JOIN yards y ON b.yard_id = y.id
GROUP BY b.id, y.name, b.number
ORDER BY y.id, b.number;

-- Ожидается:
--  building_id |        yard        | building | apartments_count
-- -------------+--------------------+----------+------------------
--            1 | Двор 1 (Северный)  |        1 |               40
--            2 | Двор 1 (Северный)  |        2 |               72
--            3 | Двор 2 (Южный)     |        1 |               20
```

**Метод 2: Через бота (ручное создание отдельных квартир)**

1. Войти как Manager/Admin
2. "⚙️ Админ-панель" → "🏘️ Управление адресами"
3. Выбрать "Квартиры"
4. Нажать "➕ Добавить квартиру"
5. Выбрать двор: "Двор 1 (Северный)"
6. Выбрать дом: "Дом 1"
7. Ввести номер квартиры: `10`
8. Ввести этаж: `3`
9. Ввести подъезд: `1`
10. **Результат**: ✅ "Квартира успешно добавлена"

**Метод 3: Через бота (пакетное создание)**

1. "⚙️ Админ-панель" → "🏘️ Управление адресами" → "Квартиры"
2. Нажать "📦 Массовое создание"
3. Выбрать дом
4. Ввести диапазон: `1-40`
5. Указать подъездов: `2` (автоматически распределит)
6. Указать этажей: `5`
7. **Результат**: ✅ "Создано 40 квартир"

**Проверка полной иерархии**:
```sql
-- Полная иерархия с подсчетом квартир
SELECT
  y.id AS yard_id,
  y.name AS yard_name,
  b.id AS building_id,
  b.number AS building_number,
  COUNT(a.id) AS apartments_count,
  MIN(a.number::INT) AS first_apt,
  MAX(a.number::INT) AS last_apt
FROM yards y
LEFT JOIN buildings b ON y.id = b.yard_id
LEFT JOIN apartments a ON b.id = a.building_id
GROUP BY y.id, y.name, b.id, b.number
ORDER BY y.id, b.number;
```

---

#### Шаг 1.4: Верификация адресной структуры

**Финальная проверка целостности**:

```sql
-- Проверка 1: Все дома привязаны к дворам
SELECT
  'Дома без двора' AS check_type,
  COUNT(*) AS issues_count
FROM buildings
WHERE yard_id IS NULL;
-- Ожидается: 0

-- Проверка 2: Все квартиры привязаны к домам
SELECT
  'Квартиры без дома' AS check_type,
  COUNT(*) AS issues_count
FROM apartments
WHERE building_id IS NULL;
-- Ожидается: 0

-- Проверка 3: Сводная статистика
SELECT
  (SELECT COUNT(*) FROM yards) AS total_yards,
  (SELECT COUNT(*) FROM buildings) AS total_buildings,
  (SELECT COUNT(*) FROM apartments) AS total_apartments;
-- Ожидается: 2 двора, 3 дома, 132 квартиры

-- Проверка 4: Тестовая навигация (как в боте)
SELECT
  CONCAT(y.name, ' → Дом ', b.number, ' → Кв. ', a.number) AS full_address
FROM apartments a
JOIN buildings b ON a.building_id = b.id
JOIN yards y ON b.yard_id = y.id
WHERE a.id IN (10, 50, 100)
ORDER BY a.id;
-- Должны увидеть 3 полных адреса
```

**Тест через бота**:
1. Начать новую регистрацию: `/start` (с нового аккаунта)
2. Выбрать язык
3. На шаге выбора квартиры должен появиться список:
   ```
   🏘️ Выберите ваш двор:
   - Двор 1 (Северный)
   - Двор 2 (Южный)
   ```
4. После выбора двора → список домов
5. После выбора дома → список квартир
6. **Результат**: Полная иерархия работает

---

### 2. Создание тестовых пользователей

#### Шаг 2.1: Создание 5 тестовых аккаунтов

**SQL скрипт (выполнить в БД)**:

```sql
-- Тестовый Applicant 1 (Двор 1, Дом 1, Кв. 10)
INSERT INTO users (telegram_id, username, first_name, last_name, role, language, apartment_id, created_at, updated_at)
VALUES (
  111111111,
  'test_applicant1',
  'Тест',
  'Заявитель',
  'applicant',
  'ru',
  (SELECT id FROM apartments WHERE building_id = 1 AND number = '10' LIMIT 1),
  NOW(),
  NOW()
);

-- Тестовый Applicant 2 (Двор 2, Дом 1, Кв. 5)
INSERT INTO users (telegram_id, username, first_name, last_name, role, language, apartment_id, created_at, updated_at)
VALUES (
  111111112,
  'test_applicant2',
  'Второй',
  'Заявитель',
  'applicant',
  'uz',  -- Узбекский язык для тестирования локализации
  (SELECT id FROM apartments WHERE building_id = 3 AND number = '5' LIMIT 1),
  NOW(),
  NOW()
);

-- Тестовый Executor 1 (Сантехник)
INSERT INTO users (telegram_id, username, first_name, last_name, role, language, specialization, rating, is_verified, created_at, updated_at)
VALUES (
  222222221,
  'test_executor_plumber',
  'Иван',
  'Сантехников',
  'executor',
  'ru',
  'Сантехника',
  4.5,
  true,
  NOW(),
  NOW()
);

-- Тестовый Executor 2 (Электрик)
INSERT INTO users (telegram_id, username, first_name, last_name, role, language, specialization, rating, is_verified, created_at, updated_at)
VALUES (
  222222222,
  'test_executor_electrician',
  'Петр',
  'Электриков',
  'executor',
  'ru',
  'Электрика',
  4.8,
  true,
  NOW(),
  NOW()
);

-- Тестовый Executor 3 (Универсальный, не верифицирован)
INSERT INTO users (telegram_id, username, first_name, last_name, role, language, specialization, rating, is_verified, created_at, updated_at)
VALUES (
  222222223,
  'test_executor_universal',
  'Сергей',
  'Универсалов',
  'executor',
  'ru',
  'Другое',
  3.8,
  false,  -- Не верифицирован для тестирования
  NOW(),
  NOW()
);

-- Тестовый Manager
INSERT INTO users (telegram_id, username, first_name, last_name, role, language, created_at, updated_at)
VALUES (
  333333331,
  'test_manager',
  'Мария',
  'Менеджерова',
  'manager',
  'ru',
  NOW(),
  NOW()
);

-- Проверка создания
SELECT
  id,
  telegram_id,
  username,
  CONCAT(first_name, ' ', last_name) AS full_name,
  role,
  language,
  apartment_id,
  specialization,
  rating,
  is_verified
FROM users
WHERE username LIKE 'test_%'
ORDER BY role, id;
```

**Ожидаемый результат**:
```
 id  | telegram_id | username                  | full_name           | role      | language | apartment_id | specialization | rating | is_verified
-----+-------------+---------------------------+---------------------+-----------+----------+--------------+----------------+--------+-------------
  1  | 111111111   | test_applicant1           | Тест Заявитель      | applicant | ru       |           10 |                |        |
  2  | 111111112   | test_applicant2           | Второй Заявитель    | applicant | uz       |            5 |                |        |
  3  | 222222221   | test_executor_plumber     | Иван Сантехников    | executor  | ru       |              | Сантехника     | 4.5    | t
  4  | 222222222   | test_executor_electrician | Петр Электриков     | executor  | ru       |              | Электрика      | 4.8    | t
  5  | 222222223   | test_executor_universal   | Сергей Универсалов  | executor  | ru       |              | Другое         | 3.8    | f
  6  | 333333331   | test_manager              | Мария Менеджерова   | manager   | ru       |              |                |        |
```

---

#### Шаг 2.2: Назначение квартир пользователям (если еще не назначены)

```sql
-- Обновить apartment_id для тестовых пользователей
UPDATE users
SET apartment_id = (SELECT id FROM apartments WHERE building_id = 1 AND number = '10' LIMIT 1)
WHERE username = 'test_applicant1';

UPDATE users
SET apartment_id = (SELECT id FROM apartments WHERE building_id = 3 AND number = '5' LIMIT 1)
WHERE username = 'test_applicant2';

-- Проверка назначений
SELECT
  u.username,
  u.role,
  CONCAT(y.name, ' → Дом ', b.number, ' → Кв. ', a.number) AS full_address
FROM users u
LEFT JOIN apartments a ON u.apartment_id = a.id
LEFT JOIN buildings b ON a.building_id = b.id
LEFT JOIN yards y ON b.yard_id = y.id
WHERE u.username LIKE 'test_applicant%';

-- Ожидается:
-- username         | role      | full_address
-- -----------------+-----------+---------------------------------------
-- test_applicant1  | applicant | Двор 1 (Северный) → Дом 1 → Кв. 10
-- test_applicant2  | applicant | Двор 2 (Южный) → Дом 1 → Кв. 5
```

---

#### Шаг 2.3: Верификация исполнителей (через бота или SQL)

**Метод 1: Через SQL (быстрый)**
```sql
-- Верифицировать всех тестовых исполнителей
UPDATE users
SET is_verified = true, updated_at = NOW()
WHERE role = 'executor' AND username LIKE 'test_executor%';

-- Кроме одного (для тестирования неверифицированного)
UPDATE users
SET is_verified = false
WHERE username = 'test_executor_universal';
```

**Метод 2: Через бота**
1. Войти как Admin
2. "⚙️ Админ-панель" → "👥 Управление пользователями"
3. Найти "Иван Сантехников"
4. Нажать "✅ Верифицировать"
5. Повторить для остальных исполнителей (кроме Сергея Универсалова)

---

### 3. Создание тестовых смен

#### Шаг 3.1: Создание смен на следующие 7 дней

```sql
-- Функция для создания тестовых смен
DO $$
DECLARE
  executor1_id INT;
  executor2_id INT;
  shift_date DATE;
  i INT;
BEGIN
  -- Получить ID исполнителей
  SELECT id INTO executor1_id FROM users WHERE username = 'test_executor_plumber';
  SELECT id INTO executor2_id FROM users WHERE username = 'test_executor_electrician';

  -- Создать смены на 7 дней
  FOR i IN 0..6 LOOP
    shift_date := CURRENT_DATE + i;

    -- Утренняя смена для Сантехника (08:00-17:00)
    INSERT INTO shifts (
      executor_id,
      specialization,
      start_time,
      end_time,
      status,
      created_at
    ) VALUES (
      executor1_id,
      'Сантехника',
      shift_date + INTERVAL '8 hours',
      shift_date + INTERVAL '17 hours',
      'Запланирована',
      NOW()
    );

    -- Вечерняя смена для Электрика (14:00-21:00)
    INSERT INTO shifts (
      executor_id,
      specialization,
      start_time,
      end_time,
      status,
      created_at
    ) VALUES (
      executor2_id,
      'Электрика',
      shift_date + INTERVAL '14 hours',
      shift_date + INTERVAL '21 hours',
      'Запланирована',
      NOW()
    );
  END LOOP;
END $$;

-- Проверка созданных смен
SELECT
  s.id,
  CONCAT(u.first_name, ' ', u.last_name) AS executor_name,
  s.specialization,
  TO_CHAR(s.start_time, 'DD.MM.YYYY HH24:MI') AS start_time,
  TO_CHAR(s.end_time, 'HH24:MI') AS end_time,
  s.status
FROM shifts s
JOIN users u ON s.executor_id = u.id
WHERE u.username LIKE 'test_executor%'
ORDER BY s.start_time;

-- Ожидается: 14 смен (2 смены × 7 дней)
```

---

### 4. Генерация исторических данных

#### ⚠️ Важно для US-010 (Статистика) и AI Auto-Assignment

Для корректного тестирования модуля статистики и AI-назначений необходимы исторические данные за 90+ дней.

#### Шаг 4.1: Массовое создание исторических заявок

```sql
-- Функция для генерации случайных заявок
CREATE OR REPLACE FUNCTION generate_historical_requests(
  days_back INT,
  requests_per_day INT
) RETURNS VOID AS $$
DECLARE
  applicant_id INT;
  executor1_id INT;
  executor2_id INT;
  apartment_ids INT[];
  current_date DATE;
  day_offset INT;
  req_count INT;
  random_apartment INT;
  random_executor INT;
  random_category TEXT;
  random_urgency TEXT;
  request_num TEXT;
BEGIN
  -- Получить ID тестовых пользователей
  SELECT id INTO applicant_id FROM users WHERE username = 'test_applicant1';
  SELECT id INTO executor1_id FROM users WHERE username = 'test_executor_plumber';
  SELECT id INTO executor2_id FROM users WHERE username = 'test_executor_electrician';

  -- Получить список квартир
  SELECT ARRAY_AGG(id) INTO apartment_ids FROM apartments LIMIT 50;

  -- Генерация заявок за указанный период
  FOR day_offset IN 0..days_back LOOP
    current_date := CURRENT_DATE - day_offset;

    FOR req_count IN 1..requests_per_day LOOP
      -- Случайный выбор параметров
      random_apartment := apartment_ids[1 + floor(random() * array_length(apartment_ids, 1))::INT];
      random_executor := CASE WHEN random() > 0.5 THEN executor1_id ELSE executor2_id END;
      random_category := (ARRAY['Сантехника', 'Электрика', 'Уборка'])[1 + floor(random() * 3)::INT];
      random_urgency := (ARRAY['Обычная', 'Срочно', 'Плановая'])[1 + floor(random() * 3)::INT];

      -- Формирование номера заявки
      request_num := TO_CHAR(current_date, 'YYMMDD') || '-' || LPAD(req_count::TEXT, 3, '0');

      -- Создание заявки
      INSERT INTO requests (
        request_number,
        applicant_id,
        apartment_id,
        category,
        subcategory,
        description,
        urgency,
        status,
        assigned_to,
        created_at,
        updated_at
      ) VALUES (
        request_num,
        applicant_id,
        random_apartment,
        random_category,
        'Тестовая подкатегория',
        'Автоматически сгенерированная тестовая заявка №' || req_count,
        random_urgency,
        'Выполнена',  -- Все исторические заявки завершены
        random_executor,
        current_date + (INTERVAL '1 hour' * floor(random() * 16 + 6)),  -- 06:00-22:00
        current_date + (INTERVAL '1 hour' * floor(random() * 8 + 16))   -- Завершена позже
      );
    END LOOP;
  END LOOP;

  RAISE NOTICE 'Создано % заявок за % дней', (days_back + 1) * requests_per_day, days_back + 1;
END;
$$ LANGUAGE plpgsql;

-- Генерация исторических данных за 90 дней (5 заявок/день = 450 заявок)
SELECT generate_historical_requests(90, 5);

-- Проверка созданных данных
SELECT
  DATE_TRUNC('month', created_at) AS month,
  COUNT(*) AS requests_count,
  COUNT(DISTINCT category) AS categories,
  COUNT(DISTINCT assigned_to) AS executors
FROM requests
WHERE created_at >= CURRENT_DATE - INTERVAL '90 days'
GROUP BY DATE_TRUNC('month', created_at)
ORDER BY month;

-- Статистика по категориям
SELECT
  category,
  COUNT(*) AS total,
  COUNT(*) FILTER (WHERE urgency = 'Срочно') AS urgent,
  ROUND(AVG(EXTRACT(EPOCH FROM (updated_at - created_at)) / 3600), 2) AS avg_completion_hours
FROM requests
WHERE created_at >= CURRENT_DATE - INTERVAL '90 days'
GROUP BY category
ORDER BY total DESC;
```

---

#### Шаг 4.2: Генерация рейтингов для исполнителей

```sql
-- Создание исторических оценок (ratings) для заявок
DO $$
DECLARE
  req RECORD;
  random_rating INT;
BEGIN
  FOR req IN
    SELECT id, assigned_to
    FROM requests
    WHERE status = 'Выполнена'
      AND created_at >= CURRENT_DATE - INTERVAL '90 days'
      AND assigned_to IS NOT NULL
    LIMIT 200  -- Оцениваем 200 случайных заявок
  LOOP
    random_rating := 3 + floor(random() * 3)::INT;  -- Оценка 3-5

    -- Сохранение рейтинга (зависит от структуры вашей таблицы ratings)
    -- Если есть отдельная таблица ratings:
    -- INSERT INTO ratings (request_id, executor_id, rating, created_at)
    -- VALUES (req.id, req.assigned_to, random_rating, NOW());

    -- Или обновление в таблице requests:
    UPDATE requests
    SET rating = random_rating
    WHERE id = req.id;
  END LOOP;
END $$;

-- Пересчет среднего рейтинга для исполнителей
UPDATE users u
SET rating = (
  SELECT ROUND(AVG(r.rating)::NUMERIC, 2)
  FROM requests r
  WHERE r.assigned_to = u.id AND r.rating IS NOT NULL
)
WHERE role = 'executor';

-- Проверка рейтингов
SELECT
  CONCAT(u.first_name, ' ', u.last_name) AS executor_name,
  u.specialization,
  u.rating AS avg_rating,
  COUNT(r.id) AS completed_requests,
  COUNT(r.rating) AS rated_requests
FROM users u
LEFT JOIN requests r ON r.assigned_to = u.id AND r.status = 'Выполнена'
WHERE u.role = 'executor' AND u.username LIKE 'test_executor%'
GROUP BY u.id, u.first_name, u.last_name, u.specialization, u.rating;
```

---

#### Шаг 4.3: Создание данных для проверки AI весов

**AI Auto-Assignment использует следующие веса**:
- Специализация: 35%
- География: 25%
- Нагрузка: 20%
- Рейтинг: 15%
- Срочность: 5%

**Генерация сценариев для проверки весов**:

```sql
-- Сценарий 1: Проверка веса специализации (35%)
-- Создаем заявку категории "Сантехника" и проверяем, что исполнитель-сантехник получает высокий score

INSERT INTO requests (
  request_number,
  applicant_id,
  apartment_id,
  category,
  subcategory,
  description,
  urgency,
  status,
  created_at
) VALUES (
  TO_CHAR(NOW(), 'YYMMDD') || '-901',
  (SELECT id FROM users WHERE username = 'test_applicant1'),
  (SELECT id FROM apartments WHERE building_id = 1 AND number = '10'),
  'Сантехника',
  'Течь из крана',
  'TEST: Проверка веса специализации - должен назначиться Иван Сантехников',
  'Обычная',
  'Новая',
  NOW()
);

-- Сценарий 2: Проверка веса географии (25%)
-- Создаем заявку в Дворе 1 и заявку в Дворе 2, проверяем учет расстояния

INSERT INTO requests (
  request_number,
  applicant_id,
  apartment_id,
  category,
  subcategory,
  description,
  urgency,
  status,
  created_at
) VALUES (
  TO_CHAR(NOW(), 'YYMMDD') || '-902',
  (SELECT id FROM users WHERE username = 'test_applicant1'),
  (SELECT id FROM apartments WHERE building_id = 1 AND number = '15'),  -- Двор 1
  'Электрика',
  'Розетка',
  'TEST: Проверка веса географии - Двор 1',
  'Обычная',
  'Новая',
  NOW()
);

INSERT INTO requests (
  request_number,
  applicant_id,
  apartment_id,
  category,
  subcategory,
  description,
  urgency,
  status,
  created_at
) VALUES (
  TO_CHAR(NOW(), 'YYMMDD') || '-903',
  (SELECT id FROM users WHERE username = 'test_applicant2'),
  (SELECT id FROM apartments WHERE building_id = 3 AND number = '8'),  -- Двор 2
  'Электрика',
  'Розетка',
  'TEST: Проверка веса географии - Двор 2 (дальше)',
  'Обычная',
  'Новая',
  NOW()
);

-- Сценарий 3: Проверка веса нагрузки (20%)
-- Назначаем много заявок одному исполнителю, проверяем что новая уйдет другому

DO $$
DECLARE
  executor1_id INT;
  applicant_id INT;
  apartment_id INT;
BEGIN
  SELECT id INTO executor1_id FROM users WHERE username = 'test_executor_plumber';
  SELECT id INTO applicant_id FROM users WHERE username = 'test_applicant1';
  SELECT id INTO apartment_id FROM apartments WHERE building_id = 1 AND number = '20';

  -- Создаем 10 активных заявок для одного исполнителя
  FOR i IN 1..10 LOOP
    INSERT INTO requests (
      request_number,
      applicant_id,
      apartment_id,
      category,
      subcategory,
      description,
      urgency,
      status,
      assigned_to,
      created_at
    ) VALUES (
      TO_CHAR(NOW(), 'YYMMDD') || '-9' || LPAD((10 + i)::TEXT, 2, '0'),
      applicant_id,
      apartment_id,
      'Сантехника',
      'Загрузка',
      'TEST: Создание нагрузки - заявка ' || i,
      'Обычная',
      'Назначена',  -- Активная заявка
      executor1_id,
      NOW()
    );
  END LOOP;

  -- Создаем новую заявку - должна уйти другому (менее загруженному)
  INSERT INTO requests (
    request_number,
    applicant_id,
    apartment_id,
    category,
    subcategory,
    description,
    urgency,
    status,
    created_at
  ) VALUES (
    TO_CHAR(NOW(), 'YYMMDD') || '-930',
    applicant_id,
    apartment_id,
    'Сантехника',
    'Разное',
    'TEST: Проверка веса нагрузки - должна уйти НЕ к Ивану',
    'Обычная',
    'Новая',
    NOW()
  );
END $$;

-- Сценарий 4: Проверка веса рейтинга (15%)
-- Проверяем, что при равных условиях выбирается исполнитель с более высоким рейтингом

-- Проверка текущих рейтингов
SELECT username, CONCAT(first_name, ' ', last_name) AS name, specialization, rating
FROM users
WHERE role = 'executor' AND username LIKE 'test_executor%'
ORDER BY rating DESC;

-- Сценарий 5: Проверка веса срочности (5%)
INSERT INTO requests (
  request_number,
  applicant_id,
  apartment_id,
  category,
  subcategory,
  description,
  urgency,
  status,
  created_at
) VALUES (
  TO_CHAR(NOW(), 'YYMMDD') || '-950',
  (SELECT id FROM users WHERE username = 'test_applicant1'),
  (SELECT id FROM apartments WHERE building_id = 1 AND number = '25'),
  'Электрика',
  'Авария',
  'TEST: Проверка срочности - срочная заявка должна обрабатываться быстрее',
  'Срочно',
  'Новая',
  NOW()
);
```

**Проверка AI назначения**:

```sql
-- Посмотреть результаты AI назначения (после запуска auto-assignment через бота)
SELECT
  r.request_number,
  r.description,
  r.category,
  r.urgency,
  CONCAT(u.first_name, ' ', u.last_name) AS assigned_executor,
  u.specialization,
  u.rating
FROM requests r
LEFT JOIN users u ON r.assigned_to = u.id
WHERE r.request_number LIKE TO_CHAR(NOW(), 'YYMMDD') || '-9%'
ORDER BY r.request_number;
```

---

#### Шаг 4.4: Тестирование fallback логики AI

**Сценарий: Нет доступных исполнителей**

```sql
-- Отключить всех исполнителей (симуляция "нет на смене")
UPDATE shifts
SET status = 'Отменена'
WHERE executor_id IN (
  SELECT id FROM users WHERE username LIKE 'test_executor%'
)
AND DATE(start_time) = CURRENT_DATE;

-- Создать заявку без доступных исполнителей
INSERT INTO requests (
  request_number,
  applicant_id,
  apartment_id,
  category,
  subcategory,
  description,
  urgency,
  status,
  created_at
) VALUES (
  TO_CHAR(NOW(), 'YYMMDD') || '-999',
  (SELECT id FROM users WHERE username = 'test_applicant1'),
  (SELECT id FROM apartments WHERE building_id = 1 AND number = '30'),
  'Сантехника',
  'Fallback Test',
  'TEST: Проверка fallback - нет доступных исполнителей',
  'Обычная',
  'Новая',
  NOW()
);

-- Ожидаемое поведение:
-- 1. AI не находит подходящих исполнителей
-- 2. Заявка остается в статусе "Новая"
-- 3. Менеджер получает уведомление о необходимости ручного назначения
-- 4. Логи содержат: "No suitable executors found for request ..."

-- Восстановление смен после теста
UPDATE shifts
SET status = 'Запланирована'
WHERE executor_id IN (
  SELECT id FROM users WHERE username LIKE 'test_executor%'
)
AND DATE(start_time) = CURRENT_DATE;
```

---

### 5. Проверка готовности данных

#### Финальная верификация всех данных

```bash
# Выполнить финальную проверку через Docker
docker-compose -f docker-compose.dev.yml exec postgres psql -U uk_bot uk_management << 'EOF'

-- ========================================
-- ФИНАЛЬНАЯ ПРОВЕРКА ГОТОВНОСТИ ДАННЫХ
-- ========================================

\echo '=== 1. Адресная иерархия ==='
SELECT
  (SELECT COUNT(*) FROM yards) AS yards,
  (SELECT COUNT(*) FROM buildings) AS buildings,
  (SELECT COUNT(*) FROM apartments) AS apartments;

\echo '\n=== 2. Тестовые пользователи ==='
SELECT
  role,
  COUNT(*) AS count
FROM users
WHERE username LIKE 'test_%'
GROUP BY role
ORDER BY role;

\echo '\n=== 3. Смены на следующие 7 дней ==='
SELECT
  DATE(start_time) AS shift_date,
  COUNT(*) AS shifts_count
FROM shifts
WHERE start_time BETWEEN NOW() AND NOW() + INTERVAL '7 days'
GROUP BY DATE(start_time)
ORDER BY shift_date;

\echo '\n=== 4. Исторические заявки ==='
SELECT
  COUNT(*) AS total_requests,
  COUNT(*) FILTER (WHERE status = 'Выполнена') AS completed,
  COUNT(*) FILTER (WHERE created_at >= CURRENT_DATE - INTERVAL '90 days') AS last_90_days
FROM requests;

\echo '\n=== 5. Рейтинги исполнителей ==='
SELECT
  username,
  rating,
  is_verified
FROM users
WHERE role = 'executor' AND username LIKE 'test_executor%';

\echo '\n✅ Проверка завершена'
EOF
```

**Ожидаемые результаты**:

```
=== 1. Адресная иерархия ===
 yards | buildings | apartments
-------+-----------+------------
     2 |         3 |        132

=== 2. Тестовые пользователи ===
   role    | count
-----------+-------
 applicant |     2
 executor  |     3
 manager   |     1

=== 3. Смены на следующие 7 дней ===
 shift_date | shifts_count
------------+--------------
 2025-10-21 |            2
 2025-10-22 |            2
 2025-10-23 |            2
 2025-10-24 |            2
 2025-10-25 |            2
 2025-10-26 |            2
 2025-10-27 |            2

=== 4. Исторические заявки ===
 total_requests | completed | last_90_days
----------------+-----------+--------------
            450 |       450 |          450

=== 5. Рейтинги исполнителей ===
        username         | rating | is_verified
-------------------------+--------+-------------
 test_executor_plumber     |   4.5 | t
 test_executor_electrician |   4.8 | t
 test_executor_universal   |   3.8 | f

✅ Проверка завершена
```

---

### 6. Быстрый старт (для нового окружения)

Если вам нужно подготовить данные с нуля, выполните следующие команды последовательно:

```bash
# 1. Подключитесь к базе данных
docker-compose -f docker-compose.dev.yml exec postgres psql -U uk_bot uk_management

# 2. Скопируйте и выполните ВСЕ SQL скрипты из разделов выше в следующем порядке:
#    - Шаг 1.1: Создание дворов
#    - Шаг 1.2: Создание домов
#    - Шаг 1.3: Создание квартир (с функцией create_apartments_for_building)
#    - Шаг 1.4: Верификация структуры
#    - Шаг 2.1: Создание тестовых пользователей
#    - Шаг 2.2: Назначение квартир
#    - Шаг 2.3: Верификация исполнителей
#    - Шаг 3.1: Создание смен
#    - Шаг 4.1: Генерация исторических заявок (функция generate_historical_requests)
#    - Шаг 4.2: Генерация рейтингов
#    - Шаг 4.3: Тестовые сценарии для AI (опционально, можно выполнить перед тестами)

# 3. Запустите финальную проверку готовности
# (скрипт из раздела 5)

# Время выполнения: ~10 минут
```

**Альтернативный способ (из файла)**:

Вы можете создать файл `prepare_test_data.sql` со всеми скриптами и выполнить его одной командой:

```bash
# Создать файл со всеми SQL скриптами
cat > prepare_test_data.sql << 'EOF'
-- [Вставьте сюда все SQL скрипты из разделов 1-4]
EOF

# Выполнить файл
docker-compose -f docker-compose.dev.yml exec -T postgres psql -U uk_bot uk_management < prepare_test_data.sql
```

---

### 7. Очистка тестовых данных

После завершения тестирования:

```sql
-- ВНИМАНИЕ: Эти команды удалят ВСЕ тестовые данные необратимо!

-- Удалить тестовые заявки
DELETE FROM requests WHERE applicant_id IN (
  SELECT id FROM users WHERE username LIKE 'test_%'
);

-- Удалить тестовые смены
DELETE FROM shifts WHERE executor_id IN (
  SELECT id FROM users WHERE username LIKE 'test_%'
);

-- Удалить тестовых пользователей
DELETE FROM users WHERE username LIKE 'test_%';

-- Удалить адресную структуру (опционально)
-- DELETE FROM apartments WHERE building_id IN (SELECT id FROM buildings);
-- DELETE FROM buildings WHERE yard_id IN (SELECT id FROM yards);
-- DELETE FROM yards;

-- Сброс sequences (опционально)
-- ALTER SEQUENCE requests_id_seq RESTART WITH 1;
-- ALTER SEQUENCE users_id_seq RESTART WITH 1;
```

---

## User Stories и Test Scenarios

### US-001: Регистрация нового пользователя

**Как**: Новый пользователь
**Я хочу**: Зарегистрироваться в системе
**Чтобы**: Иметь возможность создавать заявки

#### Acceptance Criteria
- ✅ Пользователь может начать диалог с ботом через /start
- ✅ Бот запрашивает язык (RU/UZ)
- ✅ Пользователь выбирает квартиру из списка
- ✅ Бот сохраняет профиль в БД
- ✅ Пользователь видит главное меню

#### Test Scenario 1: Happy Path - Успешная регистрация

**Preconditions**:
- Новый Telegram аккаунт (не зарегистрирован в боте)
- Бот запущен и отвечает

**Steps**:
1. Открыть Telegram
2. Найти бот @infrasafebot
3. Нажать "Start" или отправить `/start`
4. **Ожидаемый результат**: Бот приветствует и предлагает выбрать язык
5. Выбрать "🇷🇺 Русский"
6. **Ожидаемый результат**: Бот запрашивает выбор квартиры
7. Выбрать квартиру из списка (например, "Двор 1, Дом 1, Кв. 10")
8. **Ожидаемый результат**:
   - Сообщение "✅ Квартира успешно выбрана"
   - Появляется главное меню с кнопками
9. Проверить главное меню
10. **Ожидаемый результат**: Кнопки "📝 Мои заявки", "➕ Создать заявку", "👤 Профиль"

**Expected Duration**: 30-60 секунд

**Postconditions**:
- Пользователь сохранен в БД с ролью "applicant"
- Выбранная квартира привязана к пользователю
- Язык сохранен в настройках

**Проверка в БД**:
```sql
SELECT id, username, role, language, apartment_id
FROM users
WHERE telegram_id = <your_telegram_id>;
-- Должна вернуть одну запись с role='applicant'
```

---

#### Test Scenario 2: Edge Case - Регистрация без выбора квартиры

**Preconditions**: Новый аккаунт

**Steps**:
1. Начать `/start`
2. Выбрать язык
3. Нажать "↩️ Назад" или "Отменить"
4. **Ожидаемый результат**: Бот предлагает выбрать квартиру повторно
5. Попробовать перейти к главному меню
6. **Ожидаемый результат**: Бот не позволяет, требует выбор квартиры

**Expected Behavior**: Обязательный выбор квартиры для регистрации

---

#### Test Scenario 3: Edge Case - Повторный /start

**Preconditions**: Уже зарегистрированный пользователь

**Steps**:
1. Отправить `/start` повторно
2. **Ожидаемый результат**: Бот показывает главное меню без повторной регистрации
3. Проверить, что квартира не сбросилась

**Expected Behavior**: Повторная регистрация не требуется

---

### US-002: Создание заявки

**Как**: Заявитель (Applicant)
**Я хочу**: Создать заявку на обслуживание
**Чтобы**: Решить проблему в квартире

#### Acceptance Criteria
- ✅ Заявитель может создать заявку через кнопку "➕ Создать заявку"
- ✅ Система запрашивает категорию (Сантехника, Электрика, и т.д.)
- ✅ Система запрашивает описание
- ✅ Система позволяет добавить фото/видео
- ✅ Система присваивает уникальный номер (YYMMDD-NNN)
- ✅ Заявка сохраняется в БД со статусом "Новая"
- ✅ Заявитель получает подтверждение с номером

#### Test Scenario 1: Happy Path - Создание заявки с фото

**Preconditions**:
- Пользователь зарегистрирован с ролью "applicant"
- Квартира выбрана

**Steps**:
1. В главном меню нажать "➕ Создать заявку"
2. **Ожидаемый результат**: Бот показывает категории (Сантехника, Электрика, и т.д.)
3. Выбрать "💧 Сантехника"
4. **Ожидаемый результат**: Бот запрашивает подкатегорию
5. Выбрать "Течь из крана"
6. **Ожидаемый результат**: Бот запрашивает описание
7. Написать описание: "Капает кран на кухне, требуется замена прокладки"
8. **Ожидаемый результат**: Бот запрашивает срочность
9. Выбрать "🔴 Срочно"
10. **Ожидаемый результат**: Бот предлагает прикрепить фото
11. Отправить 1 фото крана
12. **Ожидаемый результат**: Бот загружает фото
13. Нажать "Готово" или "Отправить заявку"
14. **Ожидаемый результат**:
    - Сообщение "✅ Заявка создана"
    - Номер заявки (например, "251020-001")
    - Кнопка "Посмотреть заявку"

**Expected Duration**: 1-2 минуты

**Postconditions**:
- Заявка создана в БД
- Статус = "Новая"
- Номер формата YYMMDD-NNN
- Фото загружено в Media Service

**Проверка в БД**:
```sql
SELECT request_number, status, category, urgency, description, media_files
FROM requests
WHERE user_id = <applicant_user_id>
ORDER BY created_at DESC
LIMIT 1;
-- Должна вернуть созданную заявку
```

---

#### Test Scenario 2: Happy Path - Создание заявки без фото

**Steps**: Аналогично сценарию 1, но пропустить шаг с фото

**Expected Result**: Заявка создается без media_files

---

#### Test Scenario 3: Edge Case - Создание с 5+ фото

**Steps**:
1-10. Как в сценарии 1
11. Попытаться отправить 6 фотографий подряд
12. **Ожидаемый результат**: Бот принимает максимум 5 фото, показывает предупреждение

**Acceptance**: Лимит 5 фото на заявку

---

#### Test Scenario 4: Edge Case - Очень длинное описание (1000+ символов)

**Steps**:
1-6. Как в сценарии 1
7. Написать описание длиной 1500 символов
8. **Ожидаемый результат**: Бот обрезает до 1000 символов или показывает ошибку

**Validation**: Проверить лимит описания

---

#### Test Scenario 5: Negative - Создание без описания

**Steps**:
1-6. Как в сценарии 1
7. Отправить пустое сообщение или пробелы
8. **Ожидаемый результат**: Бот показывает ошибку "Описание обязательно"

---

### US-003: Просмотр своих заявок

**Как**: Заявитель
**Я хочу**: Видеть список своих заявок
**Чтобы**: Отслеживать их статус

#### Acceptance Criteria
- ✅ Пользователь видит список только своих заявок
- ✅ Заявки отсортированы по дате (новые сверху)
- ✅ Показываются: номер, статус, дата, категория
- ✅ Можно открыть детали заявки

#### Test Scenario 1: Happy Path - Просмотр списка

**Preconditions**: Пользователь создал 3+ заявки

**Steps**:
1. В главном меню нажать "📝 Мои заявки"
2. **Ожидаемый результат**: Список заявок с кнопками
3. Проверить, что показываются:
   - Номер заявки (251020-001)
   - Статус (🟢 Новая, 🔵 В работе, и т.д.)
   - Дата создания
4. Проверить сортировку (новые сверху)
5. Нажать на одну заявку
6. **Ожидаемый результат**: Детали заявки (описание, фото, статус, комментарии)

**Validation**: Заявки других пользователей НЕ видны

---

#### Test Scenario 2: Edge Case - Нет заявок

**Preconditions**: Новый пользователь без заявок

**Steps**:
1. Нажать "📝 Мои заявки"
2. **Ожидаемый результат**: Сообщение "У вас пока нет заявок" + кнопка "Создать заявку"

---

### US-004: Назначение исполнителя (Manager)

**Как**: Менеджер
**Я хочу**: Назначить исполнителя на заявку
**Чтобы**: Обеспечить выполнение работы

#### Acceptance Criteria
- ✅ Менеджер видит все новые заявки
- ✅ Может выбрать заявку и назначить исполнителя
- ✅ Система показывает доступных исполнителей
- ✅ Система учитывает специализацию и нагрузку
- ✅ Исполнитель получает уведомление
- ✅ Статус меняется на "Назначена"

#### Test Scenario 1: Happy Path - Ручное назначение

**Preconditions**:
- Пользователь с ролью "manager"
- Есть заявка со статусом "Новая"
- Есть хотя бы 1 исполнитель с подходящей специализацией

**Steps**:
1. В меню менеджера нажать "📋 Все заявки"
2. **Ожидаемый результат**: Список всех заявок (не только своих)
3. Выбрать заявку со статусом "🟢 Новая"
4. Нажать "Назначить исполнителя"
5. **Ожидаемый результат**: Список исполнителей с информацией:
   - Имя
   - Специализация
   - Текущая нагрузка
   - Рейтинг (если есть)
6. Выбрать исполнителя "Иван Сантехник"
7. **Ожидаемый результат**:
   - Сообщение "✅ Исполнитель назначен"
   - Статус заявки изменен на "Назначена"
   - Исполнитель получил уведомление в Telegram

**Expected Duration**: 30-60 секунд

**Postconditions**:
- executor_id заполнен в БД
- Статус = "Назначена"
- Notification отправлено

**Проверка уведомления исполнителю**:
- Открыть Telegram исполнителя
- Проверить наличие сообщения: "🔔 Вам назначена новая заявка [номер]"

---

#### Test Scenario 2: Happy Path - AI Auto-Assignment

**Preconditions**: Заявка со статусом "Новая"

**Steps**:
1. В карточке заявки нажать "🤖 Автоназначение"
2. **Ожидаемый результат**: Бот показывает "⏳ Подбираю оптимального исполнителя..."
3. Дождаться результата (3-5 секунд)
4. **Ожидаемый результат**:
   - "✅ Назначен: [Имя исполнителя]"
   - Информация о факторах выбора (специализация 90%, нагрузка 50%, и т.д.)
   - Статус = "Назначена"

**Validation**: AI выбирает исполнителя с учетом:
- Специализации (35% вес)
- Географии (25% вес)
- Нагрузки (20% вес)
- Рейтинга (15% вес)
- Срочности (5% вес)

---

#### Test Scenario 3: Edge Case - Нет доступных исполнителей

**Preconditions**: Все исполнители заняты или не подходят по специализации

**Steps**:
1-4. Как в сценарии 1
5. **Ожидаемый результат**: "⚠️ Нет доступных исполнителей"
6. Система предлагает:
   - Изменить срочность
   - Добавить в очередь
   - Создать смену

---

### US-005: Принятие заявки (Executor)

**Как**: Исполнитель
**Я хочу**: Принять назначенную мне заявку
**Чтобы**: Начать работу

#### Acceptance Criteria
- ✅ Исполнитель видит назначенные ему заявки
- ✅ Может принять или отклонить
- ✅ При принятии статус меняется на "В работе"
- ✅ При отклонении заявка возвращается в пул

#### Test Scenario 1: Happy Path - Принятие заявки

**Preconditions**:
- Пользователь с ролью "executor"
- Ему назначена заявка со статусом "Назначена"

**Steps**:
1. Открыть бот (исполнитель получил уведомление)
2. **Ожидаемый результат**: Уведомление "🔔 Вам назначена новая заявка"
3. Нажать на уведомление или перейти в "📋 Мои заявки"
4. **Ожидаемый результат**: Список заявок со статусом "Назначена"
5. Открыть заявку
6. **Ожидаемый результат**: Детали + кнопки "✅ Принять" и "❌ Отклонить"
7. Нажать "✅ Принять"
8. **Ожидаемый результат**:
   - Сообщение "✅ Заявка принята в работу"
   - Статус изменен на "🔵 В работе"
   - Заявитель получил уведомление

**Postconditions**:
- Статус = "В работе"
- Дата accepted_at заполнена

---

#### Test Scenario 2: Happy Path - Отклонение заявки

**Steps**:
1-6. Как в сценарии 1
7. Нажать "❌ Отклонить"
8. **Ожидаемый результат**: Бот запрашивает причину
9. Написать "Не подходит специализация"
10. **Ожидаемый результат**:
    - Сообщение "Заявка отклонена"
    - Статус вернулся в "Новая"
    - executor_id = null
    - Менеджер получил уведомление

**Postconditions**: Заявка доступна для переназначения

---

### US-006: Завершение заявки (Executor)

**Как**: Исполнитель
**Я хочу**: Завершить выполненную заявку
**Чтобы**: Зафиксировать результат

#### Acceptance Criteria
- ✅ Исполнитель может завершить заявку "В работе"
- ✅ Система запрашивает отчет о выполнении
- ✅ Можно прикрепить фото результата
- ✅ Статус меняется на "Выполнена"
- ✅ Заявитель получает уведомление

#### Test Scenario 1: Happy Path - Успешное завершение

**Preconditions**:
- Заявка со статусом "В работе"
- Исполнитель = текущий пользователь

**Steps**:
1. Открыть заявку "В работе"
2. Нажать "✅ Завершить"
3. **Ожидаемый результат**: Бот запрашивает отчет
4. Написать отчет: "Заменена прокладка в кране. Течь устранена."
5. **Ожидаемый результат**: Бот предлагает прикрепить фото
6. Отправить 2 фото (до и после)
7. Нажать "Готово"
8. **Ожидаемый результат**:
   - "✅ Заявка выполнена"
   - Статус = "Выполнена"
   - Заявитель получил уведомление

**Expected Duration**: 1-2 минуты

**Postconditions**:
- Статус = "Выполнена"
- completion_report заполнен
- completion_media содержит фото
- completed_at = текущая дата

---

#### Test Scenario 2: Edge Case - Завершение без фото

**Steps**: Как в сценарии 1, но пропустить фото

**Expected Result**: Заявка завершается без фото (опциональное поле)

---

#### Test Scenario 3: Negative - Завершение чужой заявки

**Preconditions**: Исполнитель пытается завершить заявку другого исполнителя

**Steps**:
1. Попытаться открыть чужую заявку
2. **Ожидаемый результат**: "⛔ Доступ запрещен" или заявка не видна

---

### US-007: Создание смены (Manager)

**Как**: Менеджер
**Я хочу**: Создать смену для исполнителя
**Чтобы**: Спланировать график работы

#### Acceptance Criteria
- ✅ Менеджер может создать смену через календарь
- ✅ Указать исполнителя, дату, время начала/конца
- ✅ Выбрать специализацию
- ✅ Смена не пересекается с другими сменами исполнителя
- ✅ Исполнитель получает уведомление

#### Test Scenario 1: Happy Path - Создание смены

**Preconditions**: Пользователь с ролью "manager"

**Steps**:
1. В меню менеджера нажать "📅 Управление сменами"
2. Нажать "➕ Создать смену"
3. **Ожидаемый результат**: Календарь для выбора даты
4. Выбрать дату (например, завтра)
5. **Ожидаемый результат**: Запрос времени начала
6. Выбрать время: 08:00
7. **Ожидаемый результат**: Запрос времени окончания
8. Выбрать время: 17:00
9. **Ожидаемый результат**: Список исполнителей
10. Выбрать исполнителя "Иван Сантехник"
11. **Ожидаемый результат**: Список специализаций
12. Выбрать "Сантехника"
13. **Ожидаемый результат**:
    - "✅ Смена создана"
    - Детали смены (дата, время, исполнитель)
    - Исполнитель получил уведомление

**Expected Duration**: 1 минута

**Postconditions**:
- Смена создана в БД
- Статус = "Запланирована"
- Уведомление отправлено

**Проверка в БД**:
```sql
SELECT id, executor_id, start_time, end_time, status, specialization
FROM shifts
WHERE executor_id = <executor_id>
AND DATE(start_time) = 'YYYY-MM-DD'
ORDER BY created_at DESC
LIMIT 1;
```

---

#### Test Scenario 2: Edge Case - Пересечение смен

**Preconditions**: У исполнителя уже есть смена 08:00-17:00

**Steps**:
1-10. Как в сценарии 1
6. Выбрать время 10:00 (пересекается)
7. Выбрать время 15:00
8-10. Продолжить создание
11. **Ожидаемый результат**:
    - "⚠️ Конфликт смен"
    - "Исполнитель уже занят с 08:00 до 17:00"
    - Предложение выбрать другое время

**Validation**: Система не позволяет создать пересекающиеся смены

---

#### Test Scenario 3: Edge Case - Смена в прошлом

**Steps**:
1-4. Как в сценарии 1
4. Выбрать вчерашнюю дату
5. **Ожидаемый результат**: "⚠️ Нельзя создать смену в прошлом"

---

### US-008: Передача смены (Executor)

**Как**: Исполнитель
**Я хочу**: Передать свою смену другому исполнителю
**Чтобы**: Не пропустить смену из-за форс-мажора

#### Acceptance Criteria
- ✅ Исполнитель видит свои будущие смены
- ✅ Может инициировать передачу
- ✅ Выбирает нового исполнителя
- ✅ Новый исполнитель получает запрос
- ✅ Может принять или отклонить
- ✅ При принятии смена переназначается

#### Test Scenario 1: Happy Path - Успешная передача

**Preconditions**:
- Исполнитель 1 (Иван) имеет смену завтра
- Исполнитель 2 (Петр) свободен

**Steps (от имени Ивана)**:
1. Открыть "🔄 Мои смены"
2. Выбрать смену завтра
3. Нажать "Передать смену"
4. **Ожидаемый результат**: Список доступных исполнителей
5. Выбрать "Петр Сантехник"
6. Написать причину: "Болею, не смогу выйти"
7. **Ожидаемый результат**:
   - "✅ Запрос на передачу отправлен"
   - Статус смены = "Ожидает передачи"
   - Петр получил уведомление

**Steps (от имени Петра)**:
8. Открыть уведомление "🔔 Запрос на принятие смены"
9. Просмотреть детали (дата, время, причина)
10. Нажать "✅ Принять"
11. **Ожидаемый результат**:
    - "✅ Смена принята"
    - executor_id изменен на Петра
    - Иван получил подтверждение
    - Менеджер получил уведомление

**Postconditions**:
- Смена переназначена на Петра
- Статус = "Запланирована"
- История передачи записана

---

#### Test Scenario 2: Happy Path - Отклонение передачи

**Steps**:
1-9. Как в сценарии 1
10. Нажать "❌ Отклонить"
11. Написать причину: "Уже занят"
12. **Ожидаемый результат**:
    - Смена остается за Иваном
    - Иван получил уведомление об отклонении
    - Может попробовать передать другому

---

### US-009: Квартальное планирование (Manager)

**Как**: Менеджер
**Я хочу**: Спланировать смены на квартал
**Чтобы**: Обеспечить покрытие всех дней

#### Acceptance Criteria
- ✅ Менеджер выбирает квартал (Q1, Q2, Q3, Q4)
- ✅ Система показывает шаблоны смен
- ✅ Можно создать смены по шаблону
- ✅ Система учитывает праздники
- ✅ Автоматическое распределение по дням

#### Test Scenario 1: Happy Path - Планирование на квартал

**Preconditions**: Менеджер, есть 3+ исполнителя

**Steps**:
1. В меню нажать "📊 Квартальное планирование"
2. Выбрать "Q4 2025 (Октябрь-Декабрь)"
3. **Ожидаемый результат**: Календарь квартала
4. Нажать "Создать по шаблону"
5. **Ожидаемый результат**: Список шаблонов:
   - Пн-Пт 08:00-17:00
   - Сб-Вс 09:00-15:00
   - 24/7 с ротацией
6. Выбрать "Пн-Пт 08:00-17:00"
7. Выбрать исполнителей (Иван, Петр, Сергей)
8. Нажать "Создать смены"
9. **Ожидаемый результат**:
   - "⏳ Создание смен... 10%... 50%... 100%"
   - "✅ Создано 65 смен"
   - Все смены распределены равномерно

**Expected Duration**: 30-60 секунд (в зависимости от количества дней)

**Postconditions**: 65 смен созданы в БД для Q4

---

### US-010: Просмотр статистики (Manager/Admin)

**Как**: Менеджер
**Я хочу**: Видеть статистику по заявкам
**Чтобы**: Анализировать работу

#### Acceptance Criteria
- ✅ Показываются метрики за период
- ✅ Количество заявок по статусам
- ✅ Среднее время выполнения
- ✅ Загрузка исполнителей
- ✅ Можно экспортировать в Excel

#### Test Scenario 1: Happy Path - Просмотр статистики за месяц

**Preconditions**: Менеджер, есть исторические данные

**Steps**:
1. В меню нажать "📊 Статистика"
2. Выбрать период "Последний месяц"
3. **Ожидаемый результат**: Дашборд с метриками:
   - 📝 Всего заявок: 150
   - ✅ Выполнено: 120 (80%)
   - 🔵 В работе: 20 (13%)
   - 🟢 Новые: 10 (7%)
   - ⏱️ Среднее время: 3.5 дня
4. Пролистать вниз
5. **Ожидаемый результат**: Графики и таблицы:
   - График заявок по дням
   - Топ-5 категорий
   - Рейтинг исполнителей
6. Нажать "📥 Экспорт в Excel"
7. **Ожидаемый результат**: Файл скачивается

**Validation**: Данные соответствуют БД

---

### US-011: Управление адресами (Manager)

**Как**: Менеджер
**Я хочу**: Управлять дворами, домами и квартирами
**Чтобы**: Актуализировать адресную систему

#### Acceptance Criteria
- ✅ Можно добавлять/редактировать дворы
- ✅ Можно добавлять/редактировать дома
- ✅ Можно добавлять/редактировать квартиры
- ✅ Изменения видны пользователям
- ✅ Удаление с проверкой связей

#### Test Scenario 1: Happy Path - Добавление нового двора

**Preconditions**: Войти как Manager или Admin

**Steps**:
1. В админ-меню нажать "⚙️ Админ-панель"
2. Нажать "🏘️ Управление адресами"
3. Выбрать "Дворы"
4. Нажать "➕ Добавить двор"
5. Ввести название: "Двор 5 (Западный)"
6. Ввести координаты: `41.305123, 69.250456`
7. Ввести описание: "Западный жилой комплекс - тестовый"
8. **Ожидаемый результат**:
   - Сообщение "✅ Двор успешно добавлен"
   - Двор появился в списке дворов
9. Нажать "↩️ Назад" и снова войти в "Дворы"
10. **Ожидаемый результат**: Новый двор виден в списке

**Postconditions**:
```sql
SELECT id, name, latitude, longitude, description
FROM yards
WHERE name LIKE '%Западный%';
-- Должна вернуть 1 запись
```

**Expected Duration**: 1-2 минуты

---

#### Test Scenario 2: Happy Path - Добавление дома в существующий двор

**Preconditions**:
- Войти как Manager или Admin
- Существует двор "Двор 1 (Северный)"

**Steps**:
1. "⚙️ Админ-панель" → "🏘️ Управление адресами"
2. Выбрать "Дома"
3. Нажать "➕ Добавить дом"
4. Выбрать двор из списка: "Двор 1 (Северный)"
5. Ввести номер дома: `3`
6. Ввести количество этажей: `7`
7. Ввести количество подъездов: `2`
8. Ввести количество квартир: `56` (7 этажей × 4 кв/этаж × 2 подъезда)
9. **Ожидаемый результат**:
   - "✅ Дом успешно добавлен"
   - Дом появился в списке домов для Двора 1
10. Проверить связь с двором

**Проверка в БД**:
```sql
SELECT b.id, y.name AS yard_name, b.number, b.floors, b.entrances, b.apartments_count
FROM buildings b
JOIN yards y ON b.yard_id = y.id
WHERE b.number = '3' AND y.name LIKE '%Северный%';
-- Должна вернуть: yard_name='Двор 1 (Северный)', number='3', floors=7, entrances=2, apartments_count=56
```

**Expected Duration**: 1-2 минуты

---

#### Test Scenario 3: Happy Path - Массовое создание квартир для дома

**Preconditions**:
- Войти как Manager или Admin
- Существует дом с квартирами (например, Двор 1, Дом 1)

**Steps**:
1. "⚙️ Админ-панель" → "🏘️ Управление адресами"
2. Выбрать "Квартиры"
3. Нажать "📦 Массовое создание" (если есть такая функция)
4. Выбрать двор: "Двор 1 (Северный)"
5. Выбрать дом: "Дом 3"
6. Ввести диапазон номеров: `301-356` (56 квартир)
7. Указать подъездов: `2`
8. Указать этажей: `7`
9. **Ожидаемый результат**:
   - "✅ Создано 56 квартир"
   - Квартиры автоматически распределены по этажам и подъездам

**Проверка в БД**:
```sql
SELECT
  b.number AS building,
  COUNT(a.id) AS apartments_count,
  MIN(a.number::INT) AS first_apt,
  MAX(a.number::INT) AS last_apt,
  COUNT(DISTINCT a.floor) AS floors,
  COUNT(DISTINCT a.entrance) AS entrances
FROM apartments a
JOIN buildings b ON a.building_id = b.id
JOIN yards y ON b.yard_id = y.id
WHERE y.name LIKE '%Северный%' AND b.number = '3'
GROUP BY b.id, b.number;
-- Ожидается: apartments_count=56, first_apt=301, last_apt=356, floors=7, entrances=2
```

**Expected Duration**: 2-3 минуты

---

#### Test Scenario 4: Edge Case - Создание отдельной квартиры вручную

**Preconditions**:
- Войти как Manager или Admin
- Существует дом (Двор 1, Дом 1)

**Steps**:
1. "⚙️ Админ-панель" → "🏘️ Управление адресами"
2. Выбрать "Квартиры"
3. Нажать "➕ Добавить квартиру"
4. Выбрать двор: "Двор 1 (Северный)"
5. Выбрать дом: "Дом 1"
6. Ввести номер квартиры: `999` (нестандартный номер для тестирования)
7. Ввести этаж: `10`
8. Ввести подъезд: `9`
9. **Ожидаемый результат**:
   - "✅ Квартира успешно добавлена"
   - Квартира 999 доступна для выбора
10. Проверить, что квартира видна пользователям при регистрации

**Проверка**:
```sql
SELECT a.id, a.number, a.floor, a.entrance, b.number AS building, y.name AS yard
FROM apartments a
JOIN buildings b ON a.building_id = b.id
JOIN yards y ON b.yard_id = y.id
WHERE a.number = '999';
-- Должна вернуть 1 запись: number=999, floor=10, entrance=9
```

**Expected Duration**: 1-2 минуты

---

#### Test Scenario 5: Редактирование существующего двора

**Preconditions**:
- Войти как Manager или Admin
- Существует двор "Двор 5 (Западный)"

**Steps**:
1. "⚙️ Админ-панель" → "🏘️ Управление адресами"
2. Выбрать "Дворы"
3. Выбрать "Двор 5 (Западный)" из списка
4. Нажать "✏️ Редактировать"
5. Изменить название на: "Двор 5 (Западный - обновлен)"
6. Изменить координаты: `41.305999, 69.250999`
7. Обновить описание: "Западный жилой комплекс - после ремонта"
8. Нажать "💾 Сохранить"
9. **Ожидаемый результат**:
   - "✅ Двор успешно обновлен"
   - Изменения видны в списке
10. Проверить, что связанные дома и квартиры не пострадали

**Проверка**:
```sql
-- Проверка обновления двора
SELECT name, latitude, longitude, description
FROM yards
WHERE name LIKE '%Западный%';

-- Проверка, что дома и квартиры связаны корректно
SELECT COUNT(*) AS total_apartments
FROM apartments a
JOIN buildings b ON a.building_id = b.id
JOIN yards y ON b.yard_id = y.id
WHERE y.name LIKE '%Западный%';
-- Все квартиры должны остаться связанными
```

**Expected Duration**: 2-3 минуты

---

#### Test Scenario 6: Удаление с проверкой связей

**Preconditions**:
- Войти как Admin (только админ может удалять)
- Существует двор БЕЗ домов для безопасного удаления
- Для теста связей: двор С домами и квартирами

**Steps (безопасное удаление)**:
1. Создать новый тестовый двор: "Двор TEST - для удаления"
2. НЕ создавать в нем дома и квартиры
3. "⚙️ Админ-панель" → "🏘️ Управление адресами" → "Дворы"
4. Выбрать "Двор TEST - для удаления"
5. Нажать "🗑️ Удалить"
6. **Ожидаемый результат**:
   - Подтверждение: "Вы уверены? У этого двора нет домов."
   - После подтверждения: "✅ Двор успешно удален"

**Steps (проверка защиты связей)**:
1. Выбрать двор с домами (например, "Двор 1 (Северный)")
2. Нажать "🗑️ Удалить"
3. **Ожидаемый результат**:
   - "⚠️ Невозможно удалить двор: существует 3 связанных дома"
   - "Сначала удалите или переместите дома"
   - Операция отклонена

**Steps (каскадная проверка - дом с квартирами)**:
1. Выбрать "Дома"
2. Попытаться удалить "Дом 1" в "Дворе 1"
3. **Ожидаемый результат**:
   - "⚠️ Невозможно удалить дом: существует 40 связанных квартир"
   - "Сначала удалите или переместите квартиры"
   - Операция отклонена

**Steps (каскадная проверка - квартира с пользователями)**:
1. Выбрать "Квартиры"
2. Попытаться удалить квартиру, к которой привязан пользователь (Кв. 10)
3. **Ожидаемый результат**:
   - "⚠️ Невозможно удалить квартиру: к ней привязан 1 пользователь"
   - "Сначала переместите пользователя в другую квартиру"
   - Операция отклонена

**Проверка в БД (FK constraints)**:
```sql
-- Проверка внешних ключей
SELECT
  tc.table_name,
  tc.constraint_name,
  tc.constraint_type,
  kcu.column_name,
  ccu.table_name AS foreign_table_name,
  ccu.column_name AS foreign_column_name
FROM information_schema.table_constraints AS tc
JOIN information_schema.key_column_usage AS kcu
  ON tc.constraint_name = kcu.constraint_name
JOIN information_schema.constraint_column_usage AS ccu
  ON ccu.constraint_name = tc.constraint_name
WHERE tc.constraint_type = 'FOREIGN KEY'
  AND tc.table_name IN ('buildings', 'apartments', 'users');
-- Должны быть FK: buildings.yard_id → yards.id, apartments.building_id → buildings.id, users.apartment_id → apartments.id
```

**Expected Duration**: 5-7 минут

---

#### Test Scenario 7: Full Chain - Создание полной иерархии и выбор в профиле

**Описание**: Сквозной тест всей цепочки создания и использования адресной структуры

**Preconditions**:
- Войти как Admin
- Новый Telegram аккаунт для регистрации

**Steps**:

**Часть 1: Создание иерархии (Admin)**
1. "⚙️ Админ-панель" → "🏘️ Управление адресами"
2. Создать двор: "Двор ТЕСТ ЦЕПОЧКИ"
3. В этом дворе создать дом: Дом 99, 3 этажа, 1 подъезд, 12 квартир
4. В этом доме создать квартиры: 991-1002 (12 квартир)
5. **Ожидаемый результат**: Иерархия создана

**Проверка создания**:
```sql
SELECT
  y.name AS yard,
  b.number AS building,
  COUNT(a.id) AS apartments
FROM yards y
LEFT JOIN buildings b ON y.id = b.yard_id
LEFT JOIN apartments a ON b.id = a.building_id
WHERE y.name LIKE '%ТЕСТ ЦЕПОЧКИ%'
GROUP BY y.id, y.name, b.id, b.number;
-- Ожидается: yard='Двор ТЕСТ ЦЕПОЧКИ', building='99', apartments=12
```

**Часть 2: Выбор в регистрации (Applicant)**
6. Выйти из админа
7. Начать регистрацию с нового аккаунта: `/start`
8. Выбрать язык: Русский
9. **Ожидаемый результат**: Появился список дворов, включая "Двор ТЕСТ ЦЕПОЧКИ"
10. Выбрать "Двор ТЕСТ ЦЕПОЧКИ"
11. **Ожидаемый результат**: Появился список домов: "Дом 99"
12. Выбрать "Дом 99"
13. **Ожидаемый результат**: Появился список квартир: 991, 992, ..., 1002
14. Выбрать квартиру: 995
15. **Ожидаемый результат**:
    - "✅ Квартира успешно выбрана"
    - "Ваша квартира: Двор ТЕСТ ЦЕПОЧКИ → Дом 99 → Кв. 995"
    - Появилось главное меню

**Часть 3: Проверка в профиле**
16. Открыть "👤 Профиль"
17. **Ожидаемый результат**:
    - Отображается: "📍 Адрес: Двор ТЕСТ ЦЕПОЧКИ, Дом 99, Кв. 995"
18. Нажать "🏠 Изменить квартиру"
19. Изменить на квартиру 1000 в том же доме
20. **Ожидаемый результат**:
    - "✅ Квартира успешно изменена"
    - Профиль обновлен: "Кв. 1000"

**Часть 4: Проверка в БД**
```sql
SELECT
  u.telegram_id,
  u.username,
  u.role,
  CONCAT(y.name, ' → Дом ', b.number, ' → Кв. ', a.number) AS full_address,
  a.floor,
  a.entrance
FROM users u
JOIN apartments a ON u.apartment_id = a.id
JOIN buildings b ON a.building_id = b.id
JOIN yards y ON b.yard_id = y.id
WHERE a.number IN ('995', '1000')
ORDER BY u.created_at DESC
LIMIT 1;
-- Должна вернуть: full_address='Двор ТЕСТ ЦЕПОЧКИ → Дом 99 → Кв. 1000', floor=3, entrance=1
```

**Часть 5: Создание заявки с новым адресом**
21. Создать заявку: "➕ Создать заявку"
22. Выбрать категорию: Сантехника
23. Описание: "Тест адресной цепочки"
24. **Ожидаемый результат**:
    - Заявка создана
    - В деталях заявки адрес: "Двор ТЕСТ ЦЕПОЧКИ, Дом 99, Кв. 1000"

**Часть 6: Cleanup (Admin)**
25. Войти как Admin
26. Удалить тестовую квартиру пользователя (перед этим перенести пользователя)
27. Удалить все квартиры из дома 99
28. Удалить дом 99
29. Удалить "Двор ТЕСТ ЦЕПОЧКИ"
30. **Ожидаемый результат**: Вся тестовая иерархия удалена

**Expected Duration**: 10-15 минут

**Success Criteria**:
- ✅ Полная иерархия создается без ошибок
- ✅ Пользователь может выбрать квартиру на любом уровне вложенности
- ✅ Адрес корректно отображается во всех местах (профиль, заявки)
- ✅ Изменение квартиры работает
- ✅ FK constraints защищают от некорректного удаления
- ✅ Cleanup завершается успешно

---

#### Test Scenario 8: Negative Case - Дублирование адресов

**Preconditions**: Войти как Manager/Admin

**Steps (дублирование двора)**:
1. "⚙️ Админ-панель" → "🏘️ Управление адресами" → "Дворы"
2. Создать двор: "Двор 1 (Северный)" (уже существует)
3. **Ожидаемый результат**:
   - "⚠️ Двор с таким названием уже существует"
   - Операция отклонена

**Steps (дублирование дома в одном дворе)**:
1. Выбрать "Дома"
2. Попытаться создать "Дом 1" в "Дворе 1" (уже существует)
3. **Ожидаемый результат**:
   - "⚠️ Дом с номером '1' уже существует в этом дворе"
   - Операция отклонена

**Steps (дублирование квартиры в одном доме)**:
1. Выбрать "Квартиры"
2. Попытаться создать квартиру "10" в "Доме 1, Дворе 1" (уже существует)
3. **Ожидаемый результат**:
   - "⚠️ Квартира с номером '10' уже существует в этом доме"
   - Операция отклонена

**Проверка уникальности в БД**:
```sql
-- Unique constraints должны быть настроены
SELECT
  tc.table_name,
  tc.constraint_name,
  STRING_AGG(kcu.column_name, ', ' ORDER BY kcu.ordinal_position) AS columns
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu
  ON tc.constraint_name = kcu.constraint_name
WHERE tc.constraint_type = 'UNIQUE'
  AND tc.table_name IN ('yards', 'buildings', 'apartments')
GROUP BY tc.table_name, tc.constraint_name;
-- Ожидается:
-- yards: UNIQUE(name)
-- buildings: UNIQUE(yard_id, number)
-- apartments: UNIQUE(building_id, number)
```

**Expected Duration**: 3-5 минут

---

### US-012: Комментарии к заявке

**Как**: Любой участник заявки
**Я хочу**: Добавлять комментарии
**Чтобы**: Общаться по задаче

#### Acceptance Criteria
- ✅ Заявитель, исполнитель, менеджер видят все комментарии
- ✅ Можно добавить текст и фото
- ✅ Комментарии в хронологическом порядке
- ✅ Участники получают уведомления

#### Test Scenario 1: Happy Path - Добавление комментария

**Preconditions**: Открыта заявка "В работе"

**Steps**:
1. Открыть заявку
2. Нажать "💬 Комментарии"
3. **Ожидаемый результат**: История комментариев
4. Нажать "Добавить комментарий"
5. Написать: "Нужны дополнительные материалы"
6. **Ожидаемый результат**:
   - Комментарий добавлен
   - Остальные участники получили уведомление

---

### US-013: Управление пользователями (Admin)

**Как**: Администратор
**Я хочу**: Управлять пользователями системы
**Чтобы**: Контролировать доступ, верифицировать исполнителей и управлять ролями

#### Acceptance Criteria
- ✅ Можно просматривать список всех пользователей
- ✅ Можно искать пользователей по имени/ID
- ✅ Можно изменять роли пользователей
- ✅ Можно верифицировать исполнителей
- ✅ Можно блокировать/разблокировать пользователей
- ✅ Изменения отражаются в системе немедленно
- ✅ Можно просматривать историю активности

#### Test Scenario 1: Happy Path - Верификация исполнителя

**Preconditions**:
- Войти как Admin
- Существует неверифицированный исполнитель (test_executor_universal)

**Steps**:
1. Открыть "⚙️ Админ-панель"
2. Нажать "👥 Управление пользователями"
3. **Ожидаемый результат**: Список всех пользователей с их ролями
4. Найти "Сергей Универсалов" (username: test_executor_universal)
5. **Ожидаемый результат**:
   - Роль: Исполнитель
   - Статус: ⚠️ Не верифицирован
   - Специализация: Другое
   - Рейтинг: 3.8
6. Нажать на пользователя для детальной информации
7. Нажать "✅ Верифицировать"
8. **Ожидаемый результат**:
   - "✅ Исполнитель успешно верифицирован"
   - Статус изменился на: ✅ Верифицирован
   - Пользователь теперь может получать назначения через AI
9. Проверить, что исполнитель появился в списке для назначения заявок

**Проверка в БД**:
```sql
SELECT username, role, is_verified, specialization, rating
FROM users
WHERE username = 'test_executor_universal';
-- Должна вернуть: is_verified=true
```

**Expected Duration**: 2-3 минуты

---

#### Test Scenario 2: Happy Path - Изменение роли пользователя

**Preconditions**:
- Войти как Admin
- Существует пользователь с ролью "applicant"

**Steps**:
1. "⚙️ Админ-панель" → "👥 Управление пользователями"
2. Найти тестового заявителя (test_applicant1)
3. Открыть профиль пользователя
4. Нажать "🔄 Изменить роль"
5. **Ожидаемый результат**: Список ролей:
   - Заявитель (applicant)
   - Исполнитель (executor)
   - Менеджер (manager)
   - Администратор (admin)
6. Выбрать "Исполнитель"
7. **Ожидаемый результат**: Появилась форма для специализации
8. Выбрать специализацию: "Уборка"
9. Подтвердить изменение
10. **Ожидаемый результат**:
    - "✅ Роль успешно изменена"
    - Пользователь теперь видит меню исполнителя
    - В списке исполнителей появился новый пользователь
11. Войти под этим пользователем
12. **Ожидаемый результат**: Главное меню показывает функции исполнителя

**Проверка**:
```sql
SELECT username, role, specialization
FROM users
WHERE username = 'test_applicant1';
-- Должна вернуть: role='executor', specialization='Уборка'
```

**Rollback после теста**:
```sql
UPDATE users
SET role = 'applicant', specialization = NULL
WHERE username = 'test_applicant1';
```

**Expected Duration**: 3-5 минут

---

#### Test Scenario 3: Happy Path - Поиск пользователя

**Preconditions**: Войти как Admin

**Steps**:
1. "⚙️ Админ-панель" → "👥 Управление пользователями"
2. **Ожидаемый результат**: Список пользователей с поисковой строкой
3. Ввести в поиск: "Иван"
4. **Ожидаемый результат**:
   - Список фильтруется в реальном времени
   - Показывается: "Иван Сантехников"
5. Очистить поиск
6. Ввести: "test_executor"
7. **Ожидаемый результат**:
   - Показываются все пользователи с username, содержащим "test_executor"
   - 3 исполнителя: plumber, electrician, universal
8. Ввести telegram_id: "222222221"
9. **Ожидаемый результат**: Найден "Иван Сантехников"

**Expected Duration**: 2-3 минуты

---

#### Test Scenario 4: Edge Case - Блокировка пользователя

**Preconditions**:
- Войти как Admin
- Существует активный пользователь

**Steps**:
1. "⚙️ Админ-панель" → "👥 Управление пользователями"
2. Найти тестового пользователя
3. Нажать "🚫 Заблокировать"
4. Указать причину: "Тестирование блокировки"
5. Подтвердить
6. **Ожидаемый результат**:
   - "✅ Пользователь заблокирован"
   - Статус: 🚫 Заблокирован
7. Попытаться войти под этим пользователем
8. **Ожидаемый результат**:
   - "⚠️ Ваш аккаунт заблокирован"
   - "Причина: Тестирование блокировки"
   - "Обратитесь к администратору"
   - Никакие функции бота недоступны

**Steps (разблокировка)**:
9. Вернуться в админ-панель
10. Найти заблокированного пользователя
11. Нажать "✅ Разблокировать"
12. **Ожидаемый результат**: "✅ Пользователь разблокирован"
13. Войти под пользователем снова
14. **Ожидаемый результат**: Полный доступ восстановлен

**Проверка**:
```sql
SELECT username, is_blocked, block_reason
FROM users
WHERE username = 'test_applicant1';
-- После блокировки: is_blocked=true, block_reason='Тестирование блокировки'
-- После разблокировки: is_blocked=false, block_reason=NULL
```

**Expected Duration**: 3-5 минут

---

#### Test Scenario 5: Edge Case - Добавление специализации исполнителю

**Preconditions**:
- Войти как Admin
- Существует верифицированный исполнитель с одной специализацией

**Steps**:
1. "⚙️ Админ-панель" → "👥 Управление пользователями"
2. Найти "Иван Сантехников" (специализация: Сантехника)
3. Открыть профиль
4. Нажать "➕ Добавить специализацию"
5. Выбрать дополнительную: "Электрика"
6. **Ожидаемый результат**:
   - "✅ Специализация добавлена"
   - Теперь у исполнителя 2 специализации: Сантехника, Электрика
7. Создать заявку категории "Электрика"
8. Использовать AI автоназначение
9. **Ожидаемый результат**:
   - Иван Сантехников теперь рассматривается для электрических заявок
   - AI учитывает обе специализации при оптимизации

**Проверка**:
```sql
SELECT username, specialization, secondary_specializations
FROM users
WHERE username = 'test_executor_plumber';
-- Может быть массивом или JSON полем в зависимости от реализации
```

**Expected Duration**: 3-4 минуты

---

#### Test Scenario 6: Просмотр истории активности пользователя

**Preconditions**:
- Войти как Admin
- Существует пользователь с историей заявок/смен

**Steps**:
1. "⚙️ Админ-панель" → "👥 Управление пользователями"
2. Найти "Иван Сантехников"
3. Открыть профиль
4. Нажать "📜 История активности"
5. **Ожидаемый результат**: Список событий:
   - Дата регистрации
   - Последний вход
   - Выполненные заявки (с номерами и датами)
   - История смен
   - Изменения роли/верификации (если были)
   - Блокировки (если были)
6. Фильтр по периоду: "Последние 30 дней"
7. **Ожидаемый результат**: Показываются только события за 30 дней
8. Нажать на конкретную заявку
9. **Ожидаемый результат**: Переход к деталям заявки

**Expected Duration**: 2-3 минуты

---

#### Test Scenario 7: Экспорт списка пользователей

**Preconditions**: Войти как Admin

**Steps**:
1. "⚙️ Админ-панель" → "👥 Управление пользователей"
2. Нажать "📥 Экспорт в Excel"
3. **Ожидаемый результат**:
   - Файл `users_export_20251020.xlsx` загружен
   - Содержит колонки: ID, Username, Имя, Роль, Специализация, Рейтинг, Верифицирован, Дата регистрации
4. Открыть файл
5. **Ожидаемый результат**:
   - Все пользователи в таблице
   - Корректные данные
   - Читаемый формат

**Expected Duration**: 1-2 минуты

---

### US-014: Система уведомлений

**Как**: Пользователь системы (любая роль)
**Я хочу**: Получать уведомления о важных событиях
**Чтобы**: Быть в курсе статуса заявок, смен и системных событий

#### Acceptance Criteria
- ✅ Уведомления доставляются в Telegram в реальном времени
- ✅ Уведомления имеют правильный контекст и ссылки
- ✅ Можно настроить типы уведомлений
- ✅ Можно временно отключить уведомления
- ✅ Уведомления локализованы (RU/UZ)
- ✅ Критические уведомления нельзя отключить

#### Test Scenario 1: Happy Path - Уведомление о назначении заявки (Executor)

**Preconditions**:
- Войти как Applicant
- Есть верифицированный исполнитель с включенными уведомлениями

**Steps**:
1. **Заявитель**: Создать заявку (категория: Сантехника)
2. **Менеджер**: Назначить исполнителя "Иван Сантехников"
3. **Ожидаемый результат (исполнитель получает уведомление)**:
   ```
   🔔 Новая заявка назначена на вас!

   📋 Номер: 251020-001
   📍 Адрес: Двор 1, Дом 1, Кв. 10
   🔧 Категория: Сантехника - Течь из крана
   ⚡ Срочность: Обычная

   [Принять] [Отклонить] [Детали]
   ```
4. Проверить, что уведомление содержит:
   - Номер заявки (кликабельная ссылка)
   - Адрес
   - Описание
   - Кнопки быстрых действий
5. Нажать "Принять" прямо из уведомления
6. **Ожидаемый результат**: Заявка принята без входа в меню

**Expected Duration**: 2-3 минуты

---

#### Test Scenario 2: Happy Path - Уведомление о смене (за 1 час до начала)

**Preconditions**:
- Создана смена на завтра в 10:00 для исполнителя
- Планировщик APScheduler работает

**Steps**:
1. Дождаться времени: завтра в 09:00 (за 1 час до смены)
2. **Ожидаемый результат (исполнитель получает напоминание)**:
   ```
   ⏰ Напоминание о смене!

   🕐 Начало через 1 час: 10:00
   🕔 Окончание: 18:00
   🔧 Специализация: Сантехника

   Не забудьте начать смену вовремя!
   [Начать смену] [Передать смену]
   ```
3. Проверить время доставки: ровно за 60 минут до начала
4. Нажать "Начать смену" в 10:00
5. **Ожидаемый результат**: Смена началась, статус обновлен

**Note**: Для тестирования можно изменить время в БД:
```sql
-- Установить смену на +1 час от текущего времени
UPDATE shifts
SET start_time = NOW() + INTERVAL '1 hour'
WHERE executor_id = (SELECT id FROM users WHERE username = 'test_executor_plumber')
  AND DATE(start_time) = CURRENT_DATE;
```

**Expected Duration**: 5 минут (включая ожидание)

---

#### Test Scenario 3: Happy Path - Уведомление о статусе заявки (Applicant)

**Preconditions**:
- Заявитель создал заявку
- Заявка назначена и в работе

**Steps**:
1. **Исполнитель**: Завершить заявку
2. **Ожидаемый результат (заявитель получает уведомление)**:
   ```
   ✅ Ваша заявка выполнена!

   📋 Номер: 251020-001
   🔧 Категория: Сантехника - Течь из крана
   👷 Исполнитель: Иван Сантехников

   Пожалуйста, оцените работу исполнителя:
   ⭐⭐⭐⭐⭐ [Оценить]

   [Просмотр заявки]
   ```
3. Проверить уведомление содержит:
   - Номер заявки
   - Имя исполнителя
   - Кнопку для оценки
4. Нажать "Оценить"
5. Выбрать рейтинг: 5 звезд
6. **Ожидаемый результат**:
   - Оценка сохранена
   - Рейтинг исполнителя обновлен

**Expected Duration**: 2-3 минуты

---

#### Test Scenario 4: Happy Path - Уведомление о комментарии

**Preconditions**:
- Заявка в статусе "В работе"
- 3 участника: заявитель, исполнитель, менеджер

**Steps**:
1. **Исполнитель**: Добавить комментарий: "Нужны дополнительные материалы"
2. **Ожидаемый результат (заявитель и менеджер получают уведомление)**:
   ```
   💬 Новый комментарий к заявке 251020-001

   👷 Иван Сантехников:
   "Нужны дополнительные материалы"

   [Ответить] [Просмотр заявки]
   ```
3. **Заявитель**: Нажать "Ответить"
4. Написать ответ: "Какие именно?"
5. **Ожидаемый результат**: Исполнитель и менеджер получают уведомление о новом комментарии

**Expected Duration**: 3-4 минуты

---

#### Test Scenario 5: Happy Path - Уведомление о передаче смены

**Preconditions**:
- Два исполнителя: Иван и Петр
- У Ивана есть смена на завтра

**Steps**:
1. **Иван**: Открыть "📅 Мои смены"
2. Выбрать смену на завтра
3. Нажать "↪️ Передать смену"
4. Выбрать исполнителя: "Петр Электриков"
5. Указать причину: "Семейные обстоятельства"
6. Подтвердить передачу
7. **Ожидаемый результат (Петр получает уведомление)**:
   ```
   🔄 Вам предложена смена

   📅 Дата: 21.10.2025
   🕐 Время: 10:00 - 18:00
   🔧 Специализация: Сантехника

   От: Иван Сантехников
   Причина: Семейные обстоятельства

   [Принять] [Отклонить]
   ```
8. **Петр**: Нажать "Принять"
9. **Ожидаемый результат**:
   - Смена переназначена на Петра
   - Иван получает уведомление: "✅ Петр Электриков принял вашу смену"
   - Менеджер получает уведомление о смене исполнителя

**Expected Duration**: 4-5 минут

---

#### Test Scenario 6: Настройка уведомлений в профиле

**Preconditions**: Войти как любой пользователь

**Steps**:
1. Открыть "👤 Профиль"
2. Нажать "🔔 Настройки уведомлений"
3. **Ожидаемый результат**: Список типов уведомлений:
   - ✅ Новые заявки (для исполнителей)
   - ✅ Изменения статуса (для заявителей)
   - ✅ Напоминания о сменах (за 1 час)
   - ✅ Комментарии к заявкам
   - ✅ Передача смен
   - 🔒 Критические (нельзя отключить)
4. Отключить "Комментарии к заявкам"
5. Нажать "💾 Сохранить"
6. **Ожидаемый результат**: "✅ Настройки сохранены"
7. Создать тестовый комментарий к заявке этого пользователя
8. **Ожидаемый результат**: Уведомление НЕ доставлено
9. Вернуться и включить снова
10. **Ожидаемый результат**: Уведомления работают

**Проверка**:
```sql
SELECT username, notification_settings
FROM users
WHERE username = 'test_executor_plumber';
-- notification_settings - JSON с настройками
```

**Expected Duration**: 3-4 минуты

---

#### Test Scenario 7: Временное отключение всех уведомлений ("Не беспокоить")

**Preconditions**: Войти как исполнитель

**Steps**:
1. "👤 Профиль" → "🔔 Настройки уведомлений"
2. Включить режим "🔕 Не беспокоить"
3. Указать период: "До 18:00 сегодня"
4. Подтвердить
5. **Ожидаемый результат**:
   - "✅ Режим 'Не беспокоить' включен до 18:00"
   - Иконка 🔕 в профиле
6. Назначить заявку этому исполнителю
7. **Ожидаемый результат**: Уведомление НЕ доставлено
8. Дождаться 18:00 (или изменить время в БД)
9. **Ожидаемый результат**: Режим автоматически выключен
10. Назначить новую заявку
11. **Ожидаемый результат**: Уведомление доставлено

**Expected Duration**: 5-7 минут

---

#### Test Scenario 8: Системные уведомления администратору

**Preconditions**: Войти как Admin

**Steps**:
1. Симулировать критическую ситуацию:
   - AI не смог назначить заявку (нет подходящих исполнителей)
2. **Ожидаемый результат (админ получает уведомление)**:
   ```
   ⚠️ СИСТЕМНОЕ: Требуется внимание

   🚨 AI не смог назначить заявку 251020-005
   Причина: Нет доступных исполнителей со специализацией "Сантехника"

   [Назначить вручную] [Просмотр заявки]
   ```
3. Нажать "Назначить вручную"
4. Выбрать исполнителя
5. **Ожидаемый результат**: Заявка назначена, проблема решена

**Другие системные события для тестирования**:
- Healthcheck failure (БД недоступна)
- Планировщик остановился
- Критическая ошибка в логах
- Превышение лимита запросов

**Expected Duration**: 3-5 минут

---

#### Test Scenario 9: Multilingual - Уведомления на узбекском

**Preconditions**:
- Пользователь с языком "uz"
- Создана заявка этим пользователем

**Steps**:
1. Назначить заявку исполнителю
2. Исполнитель завершает заявку
3. **Ожидаемый результат (заявитель получает уведомление на узбекском)**:
   ```
   ✅ Sizning arizangiz bajarildi!

   📋 Raqam: 251020-001
   🔧 Kategoriya: Santexnika - ...
   👷 Ijrochi: Ivan Santexnikov

   Iltimos, ishni baholang:
   ⭐⭐⭐⭐⭐ [Baholash]
   ```
4. Проверить, что весь текст на узбекском
5. Кнопки имеют узбекские названия

**Expected Duration**: 2-3 минуты

---

### US-015: Управление профилем пользователя

**Как**: Пользователь любой роли
**Я хочу**: Управлять своим профилем
**Чтобы**: Актуализировать личные данные, настройки и видеть свою статистику

#### Acceptance Criteria
- ✅ Можно просматривать свой профиль
- ✅ Можно редактировать имя, телефон
- ✅ Можно менять язык интерфейса
- ✅ Можно менять квартиру
- ✅ Исполнитель видит свой рейтинг и статистику
- ✅ Заявитель видит свои активные заявки
- ✅ Можно настраивать уведомления

#### Test Scenario 1: Happy Path - Просмотр профиля

**Preconditions**: Войти как Applicant

**Steps**:
1. Открыть главное меню
2. Нажать "👤 Профиль"
3. **Ожидаемый результат**: Профиль с информацией:
   ```
   👤 Профиль: Тест Заявитель

   📱 Telegram: @test_applicant1
   🆔 ID: 111111111
   🏷️ Роль: Заявитель
   🌐 Язык: 🇷🇺 Русский
   📍 Адрес: Двор 1, Дом 1, Кв. 10

   📊 Моя статистика:
   📝 Создано заявок: 15
   ✅ Выполнено: 12
   ⏳ В работе: 3

   [Редактировать] [Настройки] [Мои заявки]
   ```
4. Проверить, что все данные корректны
5. Нажать "📊 Моя статистика"
6. **Ожидаемый результат**: Детальная статистика

**Expected Duration**: 1-2 минуты

---

#### Test Scenario 2: Happy Path - Редактирование имени и телефона

**Preconditions**: Войти как любой пользователь

**Steps**:
1. "👤 Профиль" → "✏️ Редактировать"
2. **Ожидаемый результат**: Форма редактирования:
   - Имя: [текущее имя]
   - Фамилия: [текущая фамилия]
   - Телефон: [текущий телефон]
3. Изменить имя: "Тест Обновлен"
4. Добавить телефон: "+998901234567"
5. Нажать "💾 Сохранить"
6. **Ожидаемый результат**:
   - "✅ Профиль успешно обновлен"
   - В профиле отображается новое имя
   - Телефон сохранен
7. Проверить, что имя обновилось в заявках
8. Создать новую заявку
9. **Ожидаемый результат**: В деталях заявки новое имя

**Проверка**:
```sql
SELECT username, first_name, last_name, phone
FROM users
WHERE username = 'test_applicant1';
-- Должна вернуть обновленные данные
```

**Expected Duration**: 2-3 минуты

---

#### Test Scenario 3: Happy Path - Смена языка интерфейса

**Preconditions**: Войти как пользователь с языком RU

**Steps**:
1. "👤 Профиль" → "🌐 Сменить язык"
2. **Ожидаемый результат**: Выбор языка:
   - 🇷🇺 Русский (текущий)
   - 🇺🇿 O'zbekcha
3. Выбрать "🇺🇿 O'zbekcha"
4. **Ожидаемый результат**:
   - "✅ Til muvaffaqiyatli o'zgartirildi"
   - Весь интерфейс переключился на узбекский
5. Открыть главное меню
6. **Ожидаемый результат**: Все кнопки на узбекском:
   - "📝 Mening arizalarim"
   - "➕ Ariza yaratish"
   - "👤 Profil"
7. Создать заявку
8. **Ожидаемый результат**: Весь процесс на узбекском
9. Вернуться в профиль и сменить язык обратно на русский
10. **Ожидаемый результат**: Интерфейс снова на русском

**Проверка**:
```sql
SELECT username, language
FROM users
WHERE username = 'test_applicant1';
```

**Expected Duration**: 3-4 минуты

---

#### Test Scenario 4: Happy Path - Смена квартиры

**Preconditions**:
- Войти как Applicant
- Существует несколько квартир для выбора

**Steps**:
1. "👤 Профиль" → "🏠 Изменить квартиру"
2. **Ожидаемый результат**: Текущая квартира:
   ```
   Ваша текущая квартира:
   📍 Двор 1, Дом 1, Кв. 10

   [Выбрать другую квартиру]
   ```
3. Нажать "Выбрать другую квартиру"
4. Выбрать двор: "Двор 2 (Южный)"
5. Выбрать дом: "Дом 1"
6. Выбрать квартиру: "Кв. 8"
7. Подтвердить изменение
8. **Ожидаемый результат**:
   - "✅ Квартира успешно изменена"
   - Профиль обновлен: "📍 Двор 2, Дом 1, Кв. 8"
9. Создать новую заявку
10. **Ожидаемый результат**:
    - Адрес заявки: "Двор 2, Дом 1, Кв. 8"
    - Старые заявки сохранили старый адрес

**Проверка**:
```sql
-- Проверка обновления пользователя
SELECT u.username, CONCAT(y.name, ', Дом ', b.number, ', Кв. ', a.number) AS new_address
FROM users u
JOIN apartments a ON u.apartment_id = a.id
JOIN buildings b ON a.building_id = b.id
JOIN yards y ON b.yard_id = y.id
WHERE u.username = 'test_applicant1';

-- Проверка, что старые заявки не изменились
SELECT request_number, apartment_id
FROM requests
WHERE applicant_id = (SELECT id FROM users WHERE username = 'test_applicant1')
ORDER BY created_at;
```

**Expected Duration**: 3-4 минуты

---

#### Test Scenario 5: Просмотр рейтинга и статистики (Executor)

**Preconditions**:
- Войти как Executor
- У исполнителя есть история выполненных заявок

**Steps**:
1. "👤 Профиль"
2. **Ожидаемый результат**: Профиль исполнителя:
   ```
   👤 Профиль: Иван Сантехников

   🔧 Специализация: Сантехника
   ⭐ Рейтинг: 4.5 / 5.0
   ✅ Верифицирован

   📊 Статистика за все время:
   ✅ Выполнено заявок: 87
   ⏱️ Среднее время выполнения: 2.5 часа
   👍 Положительных оценок: 95%
   📈 Динамика рейтинга: +0.3 за месяц

   📅 Текущая активность:
   🔄 В работе: 3 заявки
   ⏳ Назначено: 2 заявки
   📆 Смены на этой неделе: 5

   [Подробная статистика] [Мои заявки] [Мои смены]
   ```
3. Нажать "📊 Подробная статистика"
4. **Ожидаемый результат**: График с динамикой:
   - Заявки по месяцам
   - Изменение рейтинга
   - Распределение по категориям
5. Выбрать период: "Последние 3 месяца"
6. **Ожидаемый результат**: Статистика за 3 месяца

**Expected Duration**: 2-3 минуты

---

#### Test Scenario 6: Edge Case - Попытка изменить роль самостоятельно

**Preconditions**: Войти как Applicant

**Steps**:
1. "👤 Профиль" → "✏️ Редактировать"
2. Проверить форму редактирования
3. **Ожидаемый результат**:
   - Нет поля "Роль" (только админ может менять роли)
   - Нет возможности добавить специализацию
   - Нет кнопки "Верифицировать"
4. Попытаться через API изменить роль (если есть доступ)
5. **Ожидаемый результат**:
   - "⚠️ Недостаточно прав"
   - Роль не изменилась

**Expected Duration**: 2 минуты

---

### US-016: Health Check и мониторинг системы

**Как**: Администратор / DevOps / Monitoring System
**Я хочу**: Проверять состояние всех компонентов системы
**Чтобы**: Обеспечить стабильность и быстро реагировать на проблемы

#### Acceptance Criteria
- ✅ Healthcheck endpoint доступен по HTTP
- ✅ Проверка всех зависимостей (БД, Redis, Media Service)
- ✅ Время ответа < 1 секунды
- ✅ Статус планировщика и фоновых задач
- ✅ Возврат детальной информации в JSON
- ✅ Логи критических ошибок доступны

#### Test Scenario 1: Happy Path - Healthcheck endpoint отвечает

**Preconditions**: Все сервисы запущены

**Steps**:
1. Открыть терминал
2. Выполнить команду:
   ```bash
   curl -s http://localhost:8009/health | jq
   ```
3. **Ожидаемый результат**:
   ```json
   {
     "status": "healthy",
     "timestamp": "2025-10-20T15:30:45.123Z",
     "version": "2.5.0",
     "services": {
       "database": {
         "status": "healthy",
         "latency_ms": 0.58,
         "details": "PostgreSQL 15.3 connected"
       },
       "redis": {
         "status": "healthy",
         "latency_ms": 0.84,
         "details": "Redis 7.0 connected"
       },
       "media_service": {
         "status": "healthy",
         "latency_ms": 12.3,
         "details": "Media service responding"
       },
       "telegram_bot": {
         "status": "healthy",
         "details": "Polling active, 1234 updates processed"
       },
       "scheduler": {
         "status": "healthy",
         "details": "APScheduler running, 9 jobs active"
       }
     },
     "uptime_seconds": 86400
   }
   ```
4. Проверить:
   - HTTP status code: 200
   - Все сервисы "healthy"
   - Latency < 50ms для БД/Redis

**Expected Duration**: 30 секунд

---

#### Test Scenario 2: Performance - Время ответа healthcheck

**Preconditions**: Система под нормальной нагрузкой

**Steps**:
1. Выполнить 50 запросов healthcheck подряд:
   ```bash
   for i in {1..50}; do
     curl -s -w "%{time_total}\n" -o /dev/null http://localhost:8009/health
   done
   ```
2. **Ожидаемый результат**:
   - Все запросы вернули 200 OK
   - Среднее время ответа < 100ms
   - Максимальное время < 200ms
3. Рассчитать среднее:
   ```bash
   for i in {1..50}; do
     curl -s -w "%{time_total}\n" -o /dev/null http://localhost:8009/health
   done | awk '{sum+=$1; count++} END {print "Avg:", sum/count "s"}'
   ```
4. **Ожидаемый результат**: Avg: < 0.1s

**Expected Duration**: 1-2 минуты

---

#### Test Scenario 3: Edge Case - Database недоступна

**Preconditions**: Система запущена

**Steps**:
1. Остановить PostgreSQL:
   ```bash
   docker-compose -f docker-compose.dev.yml stop postgres
   ```
2. Подождать 5 секунд
3. Выполнить healthcheck:
   ```bash
   curl -s http://localhost:8009/health | jq
   ```
4. **Ожидаемый результат**:
   ```json
   {
     "status": "unhealthy",
     "timestamp": "2025-10-20T15:35:10.456Z",
     "services": {
       "database": {
         "status": "unhealthy",
         "error": "Connection refused",
         "details": "Cannot connect to PostgreSQL"
       },
       "redis": {
         "status": "healthy",
         "latency_ms": 0.92
       },
       "media_service": {
         "status": "healthy",
         "latency_ms": 10.5
       }
     }
   }
   ```
5. Проверить:
   - HTTP status code: 503 (Service Unavailable)
   - `status`: "unhealthy"
   - `database.status`: "unhealthy"
6. Запустить PostgreSQL обратно:
   ```bash
   docker-compose -f docker-compose.dev.yml start postgres
   ```
7. Подождать 10 секунд (время на подключение)
8. Выполнить healthcheck снова
9. **Ожидаемый результат**:
   - HTTP 200
   - `status`: "healthy"
   - База данных восстановлена

**Expected Duration**: 2-3 минуты

---

#### Test Scenario 4: Edge Case - Redis недоступен

**Preconditions**: Система запущена

**Steps**:
1. Остановить Redis:
   ```bash
   docker-compose -f docker-compose.dev.yml stop redis
   ```
2. Выполнить healthcheck:
   ```bash
   curl -s http://localhost:8009/health | jq
   ```
3. **Ожидаемый результат**:
   ```json
   {
     "status": "degraded",
     "services": {
       "redis": {
         "status": "unhealthy",
         "error": "Connection timeout",
         "impact": "Caching unavailable, sessions may be affected"
       }
     }
   }
   ```
4. HTTP status code: 503
5. Проверить, что бот продолжает работать (fallback без Redis)
6. Отправить `/start` боту
7. **Ожидаемый результат**: Бот отвечает (работает без кеша)
8. Запустить Redis обратно:
   ```bash
   docker-compose -f docker-compose.dev.yml start redis
   ```

**Expected Duration**: 2-3 минуты

---

#### Test Scenario 5: Проверка планировщика APScheduler

**Preconditions**: Планировщик запущен с 9 задачами

**Steps**:
1. Проверить логи планировщика:
   ```bash
   docker-compose -f docker-compose.dev.yml logs app | grep "Планировщик"
   ```
2. **Ожидаемый результат**:
   ```
   INFO: Планировщик смен запущен успешно
   INFO: Запланировано задач: 9
   INFO: Активные задачи:
     - daily_shift_reminders (trigger: cron, next_run: 2025-10-21 09:00:00)
     - weekly_statistics (trigger: cron, next_run: 2025-10-25 00:00:00)
     - ...
   ```
3. Выполнить healthcheck с детализацией:
   ```bash
   curl -s "http://localhost:8009/health?verbose=true" | jq '.services.scheduler'
   ```
4. **Ожидаемый результат**:
   ```json
   {
     "status": "healthy",
     "jobs_count": 9,
     "running_jobs": 0,
     "next_run": "2025-10-21T09:00:00Z",
     "jobs": [
       {"name": "daily_shift_reminders", "next_run": "2025-10-21T09:00:00Z"},
       {"name": "auto_shift_assignment", "next_run": "2025-10-21T08:00:00Z"},
       ...
     ]
   }
   ```

**Expected Duration**: 2 минуты

---

#### Test Scenario 6: Мониторинг критических ошибок в логах

**Preconditions**: Бот работает

**Steps**:
1. Проверить логи на наличие критических ошибок:
   ```bash
   docker-compose -f docker-compose.dev.yml logs app | grep -i "ERROR\|CRITICAL"
   ```
2. **Ожидаемый результат**: Нет критических ошибок (или только известные P3)
3. Симулировать критическую ошибку:
   ```bash
   # Создать невалидную заявку через SQL (без required полей)
   docker-compose -f docker-compose.dev.yml exec postgres psql -U uk_bot uk_management -c "
     INSERT INTO requests (request_number, applicant_id)
     VALUES ('TEST-999', 99999);
   "
   ```
4. Попытаться обработать эту заявку через бота
5. **Ожидаемый результат**:
   - Лог содержит: `ERROR: Failed to process request TEST-999`
   - Админ получает системное уведомление
6. Проверить healthcheck:
   ```bash
   curl -s "http://localhost:8009/health?check_errors=true" | jq '.recent_errors'
   ```
7. **Ожидаемый результат**:
   ```json
   {
     "recent_errors": [
       {
         "timestamp": "2025-10-20T15:45:30Z",
         "level": "ERROR",
         "message": "Failed to process request TEST-999",
         "traceback": "..."
       }
     ],
     "error_count_last_hour": 1
   }
   ```
8. Cleanup:
   ```bash
   docker-compose -f docker-compose.dev.yml exec postgres psql -U uk_bot uk_management -c "
     DELETE FROM requests WHERE request_number = 'TEST-999';
   "
   ```

**Expected Duration**: 5-7 минут

---

#### Test Scenario 7: Проверка Media Service

**Preconditions**: Media Service запущен

**Steps**:
1. Проверить доступность Media Service:
   ```bash
   curl -s http://localhost:9000/health
   ```
2. **Ожидаемый результат**:
   ```json
   {
     "status": "healthy",
     "service": "media-service",
     "storage": "minio",
     "uptime": 3600
   }
   ```
3. Загрузить тестовое фото через бота
4. Проверить, что фото сохранилось:
   ```bash
   docker-compose -f docker-compose.dev.yml exec app ls -lh /app/media/
   ```
5. **Ожидаемый результат**: Файлы с timestamp

**Expected Duration**: 2-3 минуты

---

#### Test Scenario 8: Full System Health Check

**Описание**: Комплексная проверка всей системы

**Steps**:
1. Запустить полную проверку:
   ```bash
   # 1. Проверка Docker сервисов
   docker-compose -f docker-compose.dev.yml ps

   # 2. Проверка healthcheck
   curl -s http://localhost:8009/health | jq

   # 3. Проверка БД
   docker-compose -f docker-compose.dev.yml exec postgres psql -U uk_bot uk_management -c "SELECT COUNT(*) FROM users;"

   # 4. Проверка Redis
   docker-compose -f docker-compose.dev.yml exec redis redis-cli PING

   # 5. Проверка бота
   docker-compose -f docker-compose.dev.yml logs app | grep "Бот успешно запущен"

   # 6. Проверка планировщика
   docker-compose -f docker-compose.dev.yml logs app | grep "Планировщик: 9 задач"

   # 7. Проверка ошибок
   docker-compose -f docker-compose.dev.yml logs app | grep -i "ERROR" | tail -20

   # 8. Проверка производительности
   docker stats --no-stream
   ```

2. **Ожидаемые результаты**:
   - ✅ Все 4 контейнера Up (healthy)
   - ✅ Healthcheck: 200 OK, все сервисы healthy
   - ✅ БД отвечает, пользователи существуют
   - ✅ Redis: PONG
   - ✅ Бот: "Бот успешно запущен и готов к работе"
   - ✅ Планировщик: 9 задач активно
   - ✅ Нет критических ошибок (или только P3)
   - ✅ CPU < 5%, Memory < 500MB

3. Создать скрипт автоматической проверки:
   ```bash
   cat > health_check_all.sh << 'EOF'
   #!/bin/bash
   echo "=== UK Management Bot - Full Health Check ==="
   echo ""

   echo "1. Docker Services:"
   docker-compose -f docker-compose.dev.yml ps | grep -E "Up|healthy"

   echo ""
   echo "2. HTTP Healthcheck:"
   curl -s http://localhost:8009/health | jq -r '.status'

   echo ""
   echo "3. Database:"
   docker-compose -f docker-compose.dev.yml exec -T postgres psql -U uk_bot uk_management -c "SELECT 'DB OK';" | grep "DB OK"

   echo ""
   echo "4. Redis:"
   docker-compose -f docker-compose.dev.yml exec -T redis redis-cli PING

   echo ""
   echo "5. Bot Status:"
   docker-compose -f docker-compose.dev.yml logs --tail=100 app | grep "Бот успешно запущен" | tail -1

   echo ""
   echo "6. Scheduler:"
   docker-compose -f docker-compose.dev.yml logs --tail=100 app | grep "Планировщик" | tail -1

   echo ""
   echo "7. Recent Errors:"
   ERROR_COUNT=$(docker-compose -f docker-compose.dev.yml logs --tail=1000 app | grep -i "ERROR" | wc -l)
   echo "Errors in last 1000 lines: $ERROR_COUNT"

   echo ""
   echo "=== Health Check Complete ==="
   EOF

   chmod +x health_check_all.sh
   ./health_check_all.sh
   ```

**Expected Duration**: 5-10 минут

**Success Criteria**:
- ✅ Все проверки прошли успешно
- ✅ Нет критических ошибок
- ✅ Производительность в норме
- ✅ Все сервисы отвечают < 1s

---

### US-017: Системные настройки (Admin)

**Как**: Администратор
**Я хочу**: Управлять системными настройками и глобальными фичами
**Чтобы**: Контролировать поведение бота, SLA и доступность интеграций

#### Acceptance Criteria
- ✅ Раздел "⚙️ Системные настройки" доступен только админам
- ✅ Можно включать/выключать AI автоназначение, автоуведомления, интеграции
- ✅ Можно настраивать SLA по категориям заявок
- ✅ Можно задавать рабочие часы и дни
- ✅ Все изменения логируются с указанием автора и времени
- ✅ Критические функции требуют подтверждения

#### Test Scenario 1: Happy Path - Настройка SLA по категориям

**Preconditions**:
- Войти как администратор
- Имеются данные по заявкам разных категорий

**Steps**:
1. Открыть "⚙️ Админ-панель" → "🛠 Системные настройки"
2. Перейти в вкладку "SLA и лимиты"
3. Выбрать категорию "Сантехника"
4. Установить:
   - `SLA, часы`: 4
   - `Макс. время отклика`: 1 час
   - `Авто-эскалация`: через 2 часа
5. Нажать "💾 Сохранить"
6. **Ожидаемый результат**:
   - "✅ Настройки SLA сохранены"
   - В списке отображаются новые значения
7. Создать тестовую заявку категории "Сантехника"
8. Проверить в карточке заявки новый SLA таймер

**Проверка в БД**:
```sql
SELECT category, sla_hours, response_time_minutes, escalation_hours
FROM settings_request_sla
WHERE category = 'Сантехника';
-- Ожидается: 4h SLA, 60 минут отклика, 2h эскалация
```

**Expected Duration**: 3-4 минуты

---

#### Test Scenario 2: Edge Case - Отключение AI автоназначения

**Preconditions**: AI автоназначение активно

**Steps**:
1. Открыть "⚙️ Системные настройки" → вкладка "Интеграции"
2. Отключить переключатель "🤖 AI автоназначение"
3. **Ожидаемый результат**:
   - Модальное окно подтверждения: "Отключение AI приведет к ручному назначению заявок. Продолжить?"
   - Требуется ввести причину
4. Ввести причину "Плановая профилактика"
5. Нажать "Подтвердить"
6. **Ожидаемый результат**:
   - "✅ AI автоназначение отключено"
   - Таймер обратного включения (если настроен)
   - Лог аудитора содержит запись об изменении
7. Попробовать назначить новую заявку
8. **Ожидаемый результат**: Кнопка "🤖 Автоназначение" недоступна, отображается предупреждение

**Cleanup**: Включить AI обратно, убедиться что кнопка снова активна

---

### US-018: Экспорт и отчеты (Manager/Admin)

**Как**: Менеджер или администратор
**Я хочу**: Экспортировать данные о заявках и сменах
**Чтобы**: Анализировать показатели и делиться отчетами с внешними системами

#### Acceptance Criteria
- ✅ Доступны виды экспорта: Excel, CSV, Google Sheets
- ✅ Можно фильтровать данные перед экспортом
- ✅ Экспорт сохраняет поля (номер, статус, исполнители, сроки, SLA)
- ✅ Файл содержит локализованные заголовки и формат дат
- ✅ Для больших выгрузок используется асинхронный экспорт с уведомлением
- ✅ Успешные/ошибочные экспорты логируются

#### Test Scenario 1: Happy Path - Экспорт заявок в Excel

**Preconditions**:
- Войти как менеджер
- Существует 50+ заявок за последний месяц

**Steps**:
1. Открыть "📊 Статистика" → вкладка "Экспорт"
2. Выбрать тип "Заявки"
3. Применить фильтры:
   - Период: "Последний месяц"
   - Статусы: "Выполнена", "В работе"
   - Категория: "Сантехника"
4. Выбрать формат "Excel (.xlsx)"
5. Нажать "📥 Экспорт"
6. **Ожидаемый результат**:
   - Статус "Экспорт запущен"
   - Через < 30 секунд приходит уведомление: "✅ Экспорт готов"
   - Ссылка на файл `requests_YYYYMMDD.xlsx`
7. Скачать файл и открыть
8. Проверить:
   - 50+ строк
   - Заголовки: Номер, Категория, Статус, Исполнитель, SLA, Время выполнения, Оценка
   - Формат дат `DD.MM.YYYY HH:MM`

**Проверка содержимого**:
```bash
pip install --quiet pandas openpyxl
python - <<'PY'
import pandas as pd
df = pd.read_excel("exports/requests_20251020.xlsx")
assert {"Номер", "Категория", "Статус", "Исполнитель"} <= set(df.columns)
assert (df["Категория"] == "Сантехника").all()
print("Export OK", len(df))
PY
```

**Expected Duration**: 4-5 минут

---

#### Test Scenario 2: Happy Path - Экспорт смен в Google Sheets

**Preconditions**:
- Включена интеграция с Google Sheets
- У менеджера есть доступ к Google аккаунту

**Steps**:
1. "📊 Статистика" → вкладка "Экспорт"
2. Выбрать тип "Смены"
3. Настроить фильтры:
   - Период: "Следующие 2 недели"
   - Исполнители: "Иван Сантехников", "Петр Электриков"
4. Выбрать формат "Google Sheets"
5. Указать название документа: "UK Shifts - Week 43-44"
6. Нажать "📤 Отправить в Sheets"
7. **Ожидаемый результат**:
   - "⏳ Отправка в Google Sheets..."
   - Уведомление в Telegram: "✅ Экспорт завершён. Ссылка: https://docs.google.com/..."
   - Документ содержит лист "Смены" со всеми колонками (Дата, Начало, Окончание, Исполнитель, Статус, Специализация)

**Validation**:
- Проверить форматирование дат (ISO → локальный формат)
- Убедиться, что ссылки на заявки кликабельны
- Проверить права доступа (только у менеджеров)

**Expected Duration**: 3-4 минуты

---

#### Test Scenario 3: Edge Case - Пустой результат экспорта

**Preconditions**: В базе нет заявок за указанный период

**Steps**:
1. Открыть "📊 Статистика" → "Экспорт"
2. Выбрать период "2020-01-01 — 2020-01-31"
3. Нажать "📥 Экспорт"
4. **Ожидаемый результат**:
   - Сообщение "ℹ️ По выбранным фильтрам данных нет. Экспорт не создан."
   - Файл не генерируется
   - Лог содержит запись уровня INFO

---

## Критические пути тестирования

### Critical Path 1: End-to-End заявка (Happy Path)

**Описание**: Полный жизненный цикл заявки от создания до завершения

**Участники**: Заявитель, Менеджер, Исполнитель

**Duration**: 10-15 минут

**Steps**:
1. **Заявитель**: Создать заявку (US-002)
2. **Менеджер**: Назначить исполнителя вручную (US-004)
3. **Исполнитель**: Принять заявку (US-005)
4. **Исполнитель**: Завершить заявку (US-006)
5. **Заявитель**: Проверить статус "Выполнена"

**Success Criteria**:
- ✅ Заявка прошла все статусы без ошибок
- ✅ Все уведомления доставлены
- ✅ Время выполнения < 15 минут

---

### Critical Path 2: AI Auto-Assignment

**Описание**: Автоматическое назначение с помощью AI

**Duration**: 5-10 минут

**Steps**:
1. **Заявитель**: Создать заявку (категория: Сантехника, срочность: Срочно)
2. **Менеджер**: Использовать "🤖 Автоназначение"
3. Проверить, что AI выбрал оптимального исполнителя
4. **Исполнитель**: Принять и завершить

**Success Criteria**:
- ✅ AI назначил за < 5 секунд
- ✅ Выбран исполнитель с правильной специализацией
- ✅ Учтена нагрузка исполнителей

---

### Critical Path 3: Shift Management

**Описание**: Создание смены и передача

**Duration**: 5-7 минут

**Steps**:
1. **Менеджер**: Создать смену на завтра (US-007)
2. **Исполнитель 1**: Получить уведомление
3. **Исполнитель 1**: Передать смену исполнителю 2 (US-008)
4. **Исполнитель 2**: Принять передачу

**Success Criteria**:
- ✅ Смена создана корректно
- ✅ Передача прошла успешно
- ✅ Все уведомления доставлены

---

### Critical Path 4: Quarterly Planning

**Описание**: Массовое создание смен

**Duration**: 2-3 минуты

**Steps**:
1. **Менеджер**: Открыть квартальное планирование (US-009)
2. Выбрать Q1 2026
3. Создать смены по шаблону "Пн-Пт 08:00-17:00"
4. Дождаться завершения

**Success Criteria**:
- ✅ Все смены созданы за < 60 секунд
- ✅ Нет пересечений
- ✅ Равномерное распределение

---

## Чеклист функциональности

### Модуль: Аутентификация и Онбординг

- [ ] 1.1 Регистрация нового пользователя через /start
- [ ] 1.2 Выбор языка (RU/UZ)
- [ ] 1.3 Выбор квартиры из списка
- [ ] 1.4 Сохранение профиля в БД
- [ ] 1.5 Повторный /start показывает меню
- [ ] 1.6 Смена языка в профиле
- [ ] 1.7 Смена квартиры в профиле

**Priority**: P0 (Critical)

---

### Модуль: Заявки (Applicant)

- [ ] 2.1 Создание заявки с описанием
- [ ] 2.2 Выбор категории (Сантехника, Электрика, и т.д.)
- [ ] 2.3 Выбор срочности (Срочно, Обычная, Плановая)
- [ ] 2.4 Прикрепление фото (1-5 шт)
- [ ] 2.5 Присвоение уникального номера (YYMMDD-NNN)
- [ ] 2.6 Просмотр списка своих заявок
- [ ] 2.7 Просмотр деталей заявки
- [ ] 2.8 Отслеживание статуса
- [ ] 2.9 Добавление комментариев
- [ ] 2.10 Получение уведомлений о статусе

**Priority**: P0 (Critical)

---

### Модуль: Заявки (Manager)

- [ ] 3.1 Просмотр всех заявок (не только своих)
- [ ] 3.2 Фильтрация по статусу
- [ ] 3.3 Фильтрация по категории
- [ ] 3.4 Фильтрация по исполнителю
- [ ] 3.5 Поиск по номеру
- [ ] 3.6 Назначение исполнителя вручную
- [ ] 3.7 Автоназначение через AI
- [ ] 3.8 Изменение статуса любой заявки
- [ ] 3.9 Возврат заявки на доработку
- [ ] 3.10 Просмотр истории изменений

**Priority**: P0 (Critical)

---

### Модуль: Заявки (Executor)

- [ ] 4.1 Просмотр назначенных заявок
- [ ] 4.2 Принятие заявки
- [ ] 4.3 Отклонение заявки с причиной
- [ ] 4.4 Изменение статуса на "В работе"
- [ ] 4.5 Завершение заявки с отчетом
- [ ] 4.6 Прикрепление фото результата
- [ ] 4.7 Отметка "Не выполнена" с причиной
- [ ] 4.8 Запрос уточнения у заявителя
- [ ] 4.9 Получение уведомлений о новых назначениях

**Priority**: P0 (Critical)

---

### Модуль: Смены (Manager)

- [ ] 5.1 Создание смены вручную
- [ ] 5.2 Выбор даты через календарь
- [ ] 5.3 Указание времени начала/конца
- [ ] 5.4 Выбор исполнителя
- [ ] 5.5 Выбор специализации
- [ ] 5.6 Проверка пересечений смен
- [ ] 5.7 Редактирование смены
- [ ] 5.8 Удаление смены
- [ ] 5.9 Массовое создание смен по шаблону
- [ ] 5.10 Квартальное планирование

**Priority**: P1 (High)

---

### Модуль: Смены (Executor)

- [ ] 6.1 Просмотр своих смен
- [ ] 6.2 Фильтр по дате (сегодня, завтра, неделя)
- [ ] 6.3 Начало смены (check-in)
- [ ] 6.4 Завершение смены (check-out)
- [ ] 6.5 Передача смены другому исполнителю
- [ ] 6.6 Указание причины передачи
- [ ] 6.7 Принятие переданной смены
- [ ] 6.8 Отклонение переданной смены
- [ ] 6.9 Получение напоминаний о смене (за 1 час)
- [ ] 6.10 Просмотр истории смен

**Priority**: P1 (High)

---

### Модуль: AI Auto-Assignment

- [ ] 7.1 Автоназначение с учетом специализации (35%)
- [ ] 7.2 Автоназначение с учетом географии (25%)
- [ ] 7.3 Автоназначение с учетом нагрузки (20%)
- [ ] 7.4 Автоназначение с учетом рейтинга (15%)
- [ ] 7.5 Автоназначение с учетом срочности (5%)
- [ ] 7.6 Показ факторов выбора
- [ ] 7.7 Время назначения < 5 секунд
- [ ] 7.8 Fallback при отсутствии подходящих исполнителей

**Priority**: P1 (High) - Phase 2B feature

---

### Модуль: Статистика и Отчеты

- [ ] 8.1 Просмотр общей статистики
- [ ] 8.2 Фильтр по периоду (день, неделя, месяц, квартал)
- [ ] 8.3 Метрики по заявкам (количество, статусы)
- [ ] 8.4 Среднее время выполнения
- [ ] 8.5 Загрузка исполнителей
- [ ] 8.6 Рейтинг исполнителей
- [ ] 8.7 Топ категорий заявок
- [ ] 8.8 График заявок по дням
- [ ] 8.9 Экспорт в Excel
- [ ] 8.10 Планирование на основе workload prediction

**Priority**: P2 (Medium)

---

### Модуль: Управление пользователями (Admin)

- [ ] 9.1 Просмотр списка всех пользователей
- [ ] 9.2 Поиск пользователя по имени/ID
- [ ] 9.3 Изменение роли пользователя
- [ ] 9.4 Верификация исполнителя
- [ ] 9.5 Добавление специализации
- [ ] 9.6 Блокировка пользователя
- [ ] 9.7 Разблокировка пользователя
- [ ] 9.8 Просмотр истории активности
- [ ] 9.9 Экспорт списка пользователей

**Priority**: P1 (High)

---

### Модуль: Адресная система (Manager)

- [ ] 10.1 Просмотр списка дворов
- [ ] 10.2 Добавление нового двора
- [ ] 10.3 Редактирование двора
- [ ] 10.4 Удаление двора (с проверкой связей)
- [ ] 10.5 Просмотр домов во дворе
- [ ] 10.6 Добавление дома
- [ ] 10.7 Редактирование дома
- [ ] 10.8 Просмотр квартир в доме
- [ ] 10.9 Добавление квартиры
- [ ] 10.10 Редактирование квартиры
- [ ] 10.11 Связывание квартиры с пользователем

**Priority**: P2 (Medium)

---

### Модуль: Уведомления

- [ ] 11.1 Уведомление о новой заявке (исполнителю)
- [ ] 11.2 Уведомление о назначении (исполнителю)
- [ ] 11.3 Уведомление о статусе (заявителю)
- [ ] 11.4 Уведомление о смене (исполнителю за 1 час)
- [ ] 11.5 Уведомление о передаче смены
- [ ] 11.6 Уведомление о комментарии
- [ ] 11.7 Уведомление менеджеру о проблеме
- [ ] 11.8 Системные уведомления (админу)
- [ ] 11.9 Настройка уведомлений в профиле
- [ ] 11.10 Отключение уведомлений

**Priority**: P1 (High)

---

### Модуль: Комментарии и Общение

- [ ] 12.1 Добавление текстового комментария
- [ ] 12.2 Прикрепление фото к комментарию
- [ ] 12.3 Просмотр истории комментариев
- [ ] 12.4 Уведомление участников о новом комментарии
- [ ] 12.5 Упоминание пользователей (@username)
- [ ] 12.6 Запрос уточнения (special state)
- [ ] 12.7 Ответ на запрос уточнения
- [ ] 12.8 Возврат заявки на доработку

**Priority**: P2 (Medium)

---

### Модуль: Профиль пользователя

- [ ] 13.1 Просмотр своего профиля
- [ ] 13.2 Редактирование имени
- [ ] 13.3 Редактирование телефона
- [ ] 13.4 Смена языка
- [ ] 13.5 Смена квартиры
- [ ] 13.6 Просмотр своей статистики
- [ ] 13.7 Просмотр рейтинга (для исполнителя)
- [ ] 13.8 Настройки уведомлений

**Priority**: P2 (Medium)

---

### Модуль: Health Check и Мониторинг

- [ ] 14.1 Healthcheck endpoint отвечает
- [ ] 14.2 Бот отвечает на /start
- [ ] 14.3 База данных доступна
- [ ] 14.4 Redis доступен
- [ ] 14.5 Media Service доступен
- [ ] 14.6 Планировщик работает (9 задач)
- [ ] 14.7 Логи без критических ошибок

**Priority**: P0 (Critical)

---

## Тестовые данные

### Тестовые аккаунты

Создайте следующие тестовые аккаунты:

#### Applicant (Заявитель)
```
Имя: Тест Заявитель
Telegram: @test_applicant
Роль: applicant
Квартира: Двор 1, Дом 1, Кв. 10
Язык: Русский
```

#### Executor 1 (Исполнитель - Сантехник)
```
Имя: Иван Сантехник
Telegram: @test_executor_plumber
Роль: executor
Специализация: Сантехника
Рейтинг: 4.5
Верифицирован: Да
```

#### Executor 2 (Исполнитель - Электрик)
```
Имя: Петр Электрик
Telegram: @test_executor_electrician
Роль: executor
Специализация: Электрика
Рейтинг: 4.8
Верифицирован: Да
```

#### Manager (Менеджер)
```
Имя: Мария Менеджер
Telegram: @test_manager
Роль: manager
Доступ: Все функции менеджера
```

#### Admin (Администратор)
```
Имя: Админ Системы
Telegram: @test_admin
Роль: admin
Доступ: Полный (используйте супер-админа из init_admin.py)
```

---

### Тестовые заявки

Создайте разнообразные заявки для тестирования:

#### Заявка 1: Сантехника (Срочная)
```
Категория: Сантехника
Подкатегория: Течь из крана
Описание: Сильно капает кран на кухне, вода не перекрывается
Срочность: Срочно
Фото: Да (1-2 фото)
Квартира: Двор 1, Дом 1, Кв. 10
```

#### Заявка 2: Электрика (Обычная)
```
Категория: Электрика
Подкатегория: Не работает розетка
Описание: Не работает розетка в спальне, искрит при включении
Срочность: Обычная
Фото: Нет
Квартира: Двор 1, Дом 2, Кв. 15
```

#### Заявка 3: Уборка (Плановая)
```
Категория: Уборка
Подкатегория: Генеральная уборка
Описание: Требуется генеральная уборка подъезда
Срочность: Плановая
Фото: Нет
Квартира: Двор 2, Дом 1, Кв. 5
```

#### Заявка 4: С запросом уточнения
```
Категория: Сантехника
Описание: Проблема с водой (неясное описание)
Срочность: Обычная
→ Менеджер запрашивает уточнение
→ Заявитель отвечает с деталями
→ Заявка обрабатывается
```

---

### Тестовые смены

Создайте смены для разных сценариев:

#### Смена 1: Обычная смена
```
Дата: Завтра
Время: 08:00 - 17:00
Исполнитель: Иван Сантехник
Специализация: Сантехника
Статус: Запланирована
```

#### Смена 2: Вечерняя смена
```
Дата: Послезавтра
Время: 17:00 - 21:00
Исполнитель: Петр Электрик
Специализация: Электрика
Статус: Запланирована
```

#### Смена 3: Для передачи
```
Дата: +3 дня
Время: 08:00 - 17:00
Исполнитель: Иван Сантехник
→ Передается Петру
```

---

### Тестовые адреса

Убедитесь, что есть адресная структура:

```
Двор 1 (Северный)
├─ Дом 1
│  ├─ Кв. 1-20
│  └─ Подъезды: 1-2
├─ Дом 2
│  ├─ Кв. 21-40
│  └─ Подъезды: 1-2

Двор 2 (Южный)
├─ Дом 1
│  ├─ Кв. 1-15
│  └─ Подъезд: 1
```

---

### SQL скрипты для подготовки данных

#### Создание тестовых пользователей
```sql
-- Applicant
INSERT INTO users (telegram_id, username, first_name, role, language, apartment_id)
VALUES (111111111, 'test_applicant', 'Тест Заявитель', 'applicant', 'ru', 10);

-- Executor 1
INSERT INTO users (telegram_id, username, first_name, role, language, specialization, rating, is_verified)
VALUES (222222222, 'test_executor_plumber', 'Иван Сантехник', 'executor', 'ru', 'Сантехника', 4.5, true);

-- Executor 2
INSERT INTO users (telegram_id, username, first_name, role, language, specialization, rating, is_verified)
VALUES (333333333, 'test_executor_electrician', 'Петр Электрик', 'executor', 'ru', 'Электрика', 4.8, true);

-- Manager
INSERT INTO users (telegram_id, username, first_name, role, language)
VALUES (444444444, 'test_manager', 'Мария Менеджер', 'manager', 'ru');
```

#### Очистка тестовых данных
```sql
-- Удалить тестовые заявки
DELETE FROM requests WHERE request_number LIKE 'TEST-%';

-- Удалить тестовые смены
DELETE FROM shifts WHERE executor_id IN (
  SELECT id FROM users WHERE username LIKE 'test_%'
);

-- Удалить тестовых пользователей (осторожно!)
-- DELETE FROM users WHERE username LIKE 'test_%';
```

---

## Known Issues

### P0 (Critical) - NONE ✅

Все критические проблемы решены.

---

### P1 (High) - NONE ✅

Все высокоприоритетные проблемы решены.

---

### P2 (Medium)

#### Issue 1: RequestAssignment.assigned_to ошибка
**Описание**: Ошибка синхронизации назначений
**Воспроизведение**: Происходит автоматически при синхронизации
**Impact**: Логируется ошибка, но не влияет на функциональность
**Workaround**: Нет
**Fix ETA**: Phase 3, Week 1

---

### P3 (Low)

#### Issue 1: HistoricalData.total_count missing
**Описание**: Fallback на default prediction при отсутствии данных
**Воспроизведение**: Использовать workload prediction без исторических данных
**Impact**: Используется default prediction вместо ML
**Workaround**: Система работает корректно с fallback
**Fix ETA**: Phase 3, Week 1

---

## Reporting Bugs

### Bug Report Template

```markdown
### Bug #XXX: [Краткое описание]

**Priority**: P0/P1/P2/P3
**Module**: [Модуль, например: Заявки, Смены]
**Reporter**: [Ваше имя]
**Date**: [Дата обнаружения]

#### Environment
- Bot: @infrasafebot
- Docker: [версия]
- Database: PostgreSQL 15

#### Steps to Reproduce
1. [Шаг 1]
2. [Шаг 2]
3. [Шаг 3]

#### Expected Behavior
[Что должно происходить]

#### Actual Behavior
[Что происходит на самом деле]

#### Screenshots
[Прикрепить скриншоты]

#### Logs
[Логи из Docker, если есть]

#### Additional Context
[Дополнительная информация]

#### Proposed Solution (Optional)
[Ваше предложение по исправлению]
```

---

### Priority Definitions

**P0 (Critical)**: Блокирует работу, нужно исправить немедленно
- Бот не отвечает
- Невозможно создать заявку
- Данные не сохраняются
- Критическая ошибка безопасности

**P1 (High)**: Серьезная проблема, исправить в течение 1-2 дней
- Функциональность работает частично
- Уведомления не доставляются
- AI auto-assignment не работает

**P2 (Medium)**: Проблема среднего приоритета, исправить в течение недели
- UI глюки
- Медленная работа
- Неудобство использования

**P3 (Low)**: Минорная проблема, исправить когда будет время
- Опечатки в текстах
- Незначительные UI улучшения
- Nice-to-have features

---

## Testing Metrics

### Coverage Goals

| Module | Target Coverage | Current Status |
|--------|----------------|----------------|
| Authentication | 100% | ✅ |
| Requests (CRUD) | 100% | ✅ |
| Shifts Management | 95% | ✅ |
| AI Auto-Assignment | 100% | ✅ |
| User Management | 90% | 🟡 |
| Address System | 85% | 🟡 |
| Statistics | 80% | 🟡 |

**Legend**: ✅ Achieved | 🟡 In Progress | ❌ Not Started

---

### Test Execution Tracking

Use this table to track test execution:

| Test ID | Module | Scenario | Status | Tester | Date | Notes |
|---------|--------|----------|--------|--------|------|-------|
| US-001-1 | Auth | Happy Path Registration | ✅ | | | |
| US-002-1 | Requests | Create with photo | ✅ | | | |
| US-003-1 | Requests | View list | ✅ | | | |
| US-004-1 | Requests | Manual assignment | 🟡 | | | |
| US-005-1 | Requests | Accept request | ❌ | | | |
| ... | ... | ... | ... | | | |

---

## Appendix A: Command Reference

### Useful Bot Commands

```
/start - Начать работу с ботом
/help - Помощь
/menu - Главное меню
/cancel - Отменить текущее действие
/status - Статус системы (для админов)
/stats - Статистика (для менеджеров)
```

---

### Useful Docker Commands

```bash
# Просмотр логов бота
docker-compose -f docker-compose.dev.yml logs -f app

# Перезапуск бота
docker-compose -f docker-compose.dev.yml restart app

# Проверка статуса сервисов
docker-compose -f docker-compose.dev.yml ps

# Подключение к базе данных
docker-compose -f docker-compose.dev.yml exec postgres \
  psql -U uk_bot uk_management

# Просмотр метрик
docker stats uk-management-bot-dev
```

---

### Useful SQL Queries

```sql
-- Количество заявок по статусам
SELECT status, COUNT(*)
FROM requests
GROUP BY status;

-- Последние 10 заявок
SELECT request_number, status, created_at, user_id
FROM requests
ORDER BY created_at DESC
LIMIT 10;

-- Смены на сегодня
SELECT s.id, u.first_name, s.start_time, s.end_time, s.status
FROM shifts s
JOIN users u ON s.executor_id = u.id
WHERE DATE(s.start_time) = CURRENT_DATE;

-- Загрузка исполнителей
SELECT u.first_name, COUNT(r.id) as active_requests
FROM users u
LEFT JOIN requests r ON r.executor_id = u.id AND r.status = 'В работе'
WHERE u.role = 'executor'
GROUP BY u.id, u.first_name;
```

---

## Appendix B: Testing Checklist Summary

### Before Testing
- [ ] Docker services running
- [ ] Test accounts created
- [ ] Test data prepared
- [ ] Clean state (no old test data)

### During Testing
- [ ] Follow test scenarios exactly
- [ ] Take screenshots of bugs
- [ ] Note unexpected behavior
- [ ] Check notifications delivery
- [ ] Verify database changes

### After Testing
- [ ] Fill test execution table
- [ ] Report all bugs found
- [ ] Clean up test data
- [ ] Document new test cases

---

## Appendix C: Performance Benchmarks

### Expected Response Times

| Action | Expected Time | Acceptable |
|--------|---------------|------------|
| Bot responds to /start | < 1s | < 2s |
| Create request | < 2s | < 5s |
| AI auto-assignment | < 5s | < 10s |
| Load requests list | < 1s | < 3s |
| Upload photo | < 3s | < 10s |
| Generate statistics | < 5s | < 15s |
| Quarterly planning | < 60s | < 120s |

**Note**: Measure and report if any action exceeds "Acceptable" time.

---

**Document Version**: 1.0
**Last Updated**: 20 October 2025, 20:30 MSK
**Next Review**: 27 October 2025
**Maintained By**: QA Team / Development Team

---

**Happy Testing!** 🚀
