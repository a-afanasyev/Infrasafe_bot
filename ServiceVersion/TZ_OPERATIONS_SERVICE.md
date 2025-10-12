# Техническое задание: Operations Service

## 1. Общее описание

### 1.1 Назначение
Operations Service - сервис управления операционной деятельностью, включающий управление сменами, расписаниями, назначением исполнителей и планированием работ.

### 1.2 Цели
- Автоматизация планирования смен
- Интеллектуальное назначение исполнителей
- Оптимизация распределения нагрузки
- Управление расписаниями и графиками работы

### 1.3 Ключевые характеристики
- **Порт**: 8002
- **Тип нагрузки**: Compute-intensive для оптимизации
- **Критичность**: Высокая
- **Масштабирование**: Вертикальное (CPU-intensive)

## 2. Функциональные требования

### 2.1 Модуль управления сменами

#### 2.1.1 Shift Planning
- Создание смен на день/неделю/месяц/квартал
- Шаблоны смен (standard, 24h, flexible, rotating, custom)
- Автоматическое планирование по шаблонам
- Копирование смен из прошлых периодов
- Массовое создание смен

#### 2.1.2 Shift Templates (Q2.3)

**Принято решение**: Все параметры смен настраиваются через админку

**Типы смен** (примеры):
- **8×5** - Пятидневка по 8 часов
- **8×6** - Шестидневка по 8 часов
- **12 hours** - Двенадцатичасовая смена
- **24 hours** - Суточная дежурная смена
- **Flexible** - Гибкий график
- **Custom** - Произвольный график

**Настраиваемые параметры шаблона**:
- Продолжительность смены (часов)
- Время начала/окончания
- Количество рабочих дней
- Перерывы
- Минимальный отдых между сменами
- Максимум смен подряд
- Пересменка (время передачи дел)
- Специализации
- Минимальное количество исполнителей

**Важно**:
- Система НЕ учитывает требования ТК РФ
- Система НЕ считает сверхурочные
- Все правила настраиваются администратором
- Поддержка разных стран и компаний

#### 2.1.3 Shift Management
- CRUD операций для смен
- Статусы: planned, active, completed, cancelled
- История изменений смены
- Объединение и разделение смен
- Экстренные смены

#### 2.1.4 Shift Transfer
- Передача смен между исполнителями
- Approval workflow (запрос → одобрение → подтверждение)
- Автоматическая проверка совместимости
- Уведомления всех участников
- История передач

#### 2.1.5 Shift Specializations
12 типов специализаций:
- Сантехник
- Электрик
- Плотник
- Дворник
- Разнорабочий
- Уборщик
- Садовник
- Маляр
- Слесарь
- Кровельщик
- Системный администратор
- Универсал

### 2.2 Модуль назначения исполнителей

#### 2.2.1 Basic Assignment (без ML)
Алгоритмы назначения:
- **Balanced** - равномерное распределение
- **Nearest** - по географической близости
- **Rating** - по рейтингу исполнителя
- **Specialization** - по специализации
- **Availability** - по доступности

#### 2.2.2 Assignment Weights
- Специализация: 35%
- География: 25%
- Текущая загрузка: 20%
- Рейтинг: 15%
- Срочность: 5%

#### 2.2.3 Assignment Rules
- Максимальная дистанция: 10 км
- Максимальная загрузка: 80%
- Минимальный рейтинг: 3.0
- Обязательное соответствие специализации
- Учет рабочего времени

#### 2.2.4 Fallback Strategies
- Расширение радиуса поиска
- Снижение требований к рейтингу
- Поиск универсальных специалистов
- Ручное назначение как последний вариант

#### 2.2.5 Load Balancing
- Равномерное распределение заявок
- Учет сложности задач
- Предотвращение перегрузки
- Динамическая балансировка

### 2.3 Модуль расписаний

#### 2.3.1 Schedule Management
- Индивидуальные графики работы
- Групповые расписания
- Исключения и переносы
- Праздники и выходные
- Отпуска и больничные

#### 2.3.2 Availability Tracking
- Статусы доступности в реальном времени
- Календарь доступности
- Предварительное бронирование времени
- Конфликты расписаний

#### 2.3.3 Working Hours
- Гибкие рабочие часы
- Сверхурочные
- Ночные смены
- Подсчет отработанного времени
- Интеграция с системой оплаты

### 2.4 Модуль оптимизации

#### 2.4.1 Route Optimization
- Построение оптимальных маршрутов
- Группировка заявок по локациям
- Минимизация времени в пути
- Учет трафика

#### 2.4.2 Resource Optimization
- Оптимальное использование ресурсов
- Предсказание пиковых нагрузок
- Резервирование ресурсов
- Анализ эффективности

#### 2.4.3 Capacity Planning
- Прогнозирование потребности в исполнителях
- Планирование найма
- Анализ загрузки по периодам
- Recommendations для менеджмента

## 3. API Specifications

### 3.1 RESTful API

#### Shifts Endpoints
```
GET    /api/v1/shifts
GET    /api/v1/shifts/{id}
POST   /api/v1/shifts
PUT    /api/v1/shifts/{id}
DELETE /api/v1/shifts/{id}
POST   /api/v1/shifts/bulk
POST   /api/v1/shifts/{id}/transfer
POST   /api/v1/shifts/{id}/approve
GET    /api/v1/shifts/templates
POST   /api/v1/shifts/templates
POST   /api/v1/shifts/plan
GET    /api/v1/shifts/calendar
```

#### Assignments Endpoints
```
POST   /api/v1/assignments/auto
POST   /api/v1/assignments/manual
GET    /api/v1/assignments/{id}
PUT    /api/v1/assignments/{id}
POST   /api/v1/assignments/{id}/reassign
GET    /api/v1/assignments/suggestions
POST   /api/v1/assignments/optimize
GET    /api/v1/assignments/load-balance
```

#### Schedules Endpoints
```
GET    /api/v1/schedules
GET    /api/v1/schedules/{executor_id}
POST   /api/v1/schedules
PUT    /api/v1/schedules/{id}
GET    /api/v1/schedules/availability
POST   /api/v1/schedules/availability
GET    /api/v1/schedules/conflicts
POST   /api/v1/schedules/working-hours
```

### 3.2 WebSocket API
```
/ws/operations/assignments - Real-time assignment updates
/ws/operations/shifts - Shift changes
/ws/operations/availability - Executor availability
```

## 4. Асинхронные задачи

### 4.1 Очереди и приоритеты

#### HIGH Priority (9-10)
- `ops.emergency.assign` - Экстренное назначение
- `ops.shift.urgent` - Срочная смена

#### MEDIUM Priority (4-8)
- `ops.shift.plan` - Планирование смен
- `ops.assignment.basic` - Базовое назначение
- `ops.schedule.update` - Обновление расписания
- `ops.assignment.optimize` - Оптимизация назначений

#### LOW Priority (1-3)
- `ops.shift.template` - Создание по шаблону
- `ops.capacity.analyze` - Анализ мощностей
- `ops.route.optimize` - Оптимизация маршрутов

### 4.2 Фоновые задачи (Scheduled)

#### Daily Tasks
- `ops.shift.auto_create` - 00:00 - Создание смен на следующий день
- `ops.schedule.sync` - 01:00 - Синхронизация расписаний
- `ops.availability.update` - Every 4 hours - Обновление доступности

#### Weekly Tasks
- `ops.shift.weekly_plan` - Sunday 18:00 - Планирование на неделю
- `ops.load.analyze` - Monday 09:00 - Анализ загрузки
- `ops.efficiency.report` - Friday 17:00 - Отчет эффективности

#### Monthly Tasks
- `ops.shift.monthly_plan` - 25th, 18:00 - План на месяц
- `ops.capacity.forecast` - 1st, 10:00 - Прогноз мощностей

## 5. Алгоритмы оптимизации

### 5.1 Basic Assignment Algorithm
```
1. Фильтрация по специализации
2. Фильтрация по доступности
3. Расчет расстояния до объекта
4. Проверка текущей загрузки
5. Расчет weighted score
6. Выбор топ-3 кандидатов
7. Применение business rules
8. Финальный выбор
```

### 5.2 Load Balancing Algorithm
```
1. Расчет текущей загрузки всех исполнителей
2. Определение перегруженных (>80%)
3. Определение недогруженных (<40%)
4. Перераспределение будущих заявок
5. Валидация constraints
6. Применение изменений
```

### 5.3 Route Optimization (TSP variant)
```
1. Группировка заявок по районам
2. Построение матрицы расстояний
3. Применение эвристики nearest neighbor
4. Оптимизация 2-opt swaps
5. Учет временных окон
6. Финализация маршрутов
```

### 5.4 Graceful Degradation при недоступности AI Service
```
if ai_service.is_healthy():
    result = ai_service.optimize_assignment(request)
else:
    result = basic_assignment_algorithm(request)

// Всегда возвращаем результат, система не блокируется
return result
```

## 6. События и интеграции

### 6.1 Публикуемые события
```
shift.created
shift.updated
shift.cancelled
shift.transfer.requested
shift.transfer.approved
shift.transfer.completed
assignment.created
assignment.changed
assignment.optimized
schedule.updated
executor.available
executor.busy
capacity.warning
```

### 6.2 Подписки на события
```
core.request.created - Для автоматического назначения
core.request.cancelled - Для освобождения исполнителя
core.user.role.changed - Для обновления доступных исполнителей
ai.optimization.completed - Для применения ML оптимизации (опционально)
```

**Примечание**: При недоступности событий используется fallback на polling или кеш.

## 6.3 Отказоустойчивость и Fallback (Q6.2)

### 6.3.1 Graceful Degradation

**При недоступности зависимых сервисов**:

| Сервис недоступен | Влияние на Operations | Fallback стратегия |
|-------------------|----------------------|-------------------|
| **Core Service** | Критично | Readonly режим из Redis кеша, операции в очередь |
| **AI/ML Service** | Некритично | Базовый алгоритм назначения (всегда работает) |
| **Communication Hub** | Некритично | Логирование уведомлений, повтор при восстановлении |
| **Analytics Service** | Некритично | Пропуск метрик, отложенная отправка |

**SLA восстановления** (согласно Q6.2):
- Блокирующие сервисы (Core): не более 1 суток
- Некритичные сервисы: не более 3 суток

**Уведомление пользователей**:
- При действиях в боте/webapp показывать предупреждение
- Массовой рассылки о деградации НЕ делаем
- В логах фиксировать все fallback переключения

## 7. Интеграция с AI/ML Service (опционально)

### 7.1 Fallback Strategy
- Всегда есть базовый алгоритм
- AI Service улучшает, но не блокирует
- Graceful degradation при недоступности
- Метрики сравнения basic vs AI

### 7.2 AI Service Integration Points
```
POST /api/v1/ai/optimize-assignment
POST /api/v1/ai/predict-duration
POST /api/v1/ai/suggest-executors
GET  /api/v1/ai/health
```

### 7.3 Hybrid Approach
- Basic algorithm: < 50ms response
- With AI optimization: < 500ms response
- Timeout на AI: 400ms
- Fallback при timeout

## 8. Производительность

### 8.1 Требования
- Assignment decision: < 100ms (basic), < 500ms (with AI)
- Shift planning: < 2s для недели
- Route optimization: < 1s для 10 точек
- Concurrent operations: 100

### 8.2 Оптимизации
- Кеширование матриц расстояний
- Предрасчет доступности
- Индексирование по геолокации
- Batch processing для массовых операций

### 8.3 Кеширование
- Executor availability: 5 min
- Distance matrix: 1 hour
- Shift templates: 24 hours
- Assignment scores: 1 min

## 9. База данных

### 9.1 Схема данных

#### Shifts Table
- id
- date
- start_time
- end_time
- type (standard, 24h, flexible)
- specialization
- min_executors
- max_executors
- status
- created_by
- created_at
- updated_at

#### Shift_Executors Table
- shift_id
- executor_id
- role (main, backup)
- confirmed_at
- check_in_time
- check_out_time

#### Shift_Transfers Table
- id
- shift_id
- from_executor_id
- to_executor_id
- reason
- status (requested, approved, completed, rejected)
- requested_at
- approved_at
- approved_by

#### Assignments Table
- id
- request_id
- executor_id
- assigned_at
- assigned_by
- method (auto, manual, ai)
- score
- distance
- estimated_duration
- actual_duration
- status

#### Schedules Table
- id
- executor_id
- date
- start_time
- end_time
- type (work, vacation, sick, training)
- recurring
- recurrence_pattern

#### Executor_Availability Table
- executor_id
- date
- time_slot
- available
- reason
- updated_at

### 9.2 Индексы
- shifts(date, status)
- shifts(specialization, date)
- assignments(executor_id, date)
- assignments(request_id)
- schedules(executor_id, date)
- spatial index для геолокации

## 10. Мониторинг

### 10.1 Метрики
- Assignment success rate
- Average assignment time
- Executor utilization
- Shift coverage
- Transfer requests rate
- Optimization improvement (basic vs AI)

### 10.2 Алерты
- Low executor availability (< 30%)
- High rejection rate (> 20%)
- Assignment failures
- Shift conflicts
- Capacity warnings

### 10.3 Dashboards
- Real-time executor map
- Shift calendar
- Load distribution
- Assignment analytics
- Efficiency metrics

## 11. Безопасность

### 11.1 Авторизация
- Role-based shift management
- Executor can only view own shifts
- Manager can manage team shifts
- Transfer approval hierarchy

### 11.2 Audit
- All assignment decisions logged
- Shift changes tracked
- Transfer requests audited
- Manual overrides recorded

## 12. Тестирование

### 12.1 Unit Tests
- Assignment algorithms
- Optimization logic
- Schedule calculations
- Conflict detection

### 12.2 Integration Tests
- End-to-end assignment flow
- Shift planning scenarios
- Transfer workflows
- AI service integration

### 12.3 Performance Tests
- 1000 concurrent assignments
- Route optimization with 100 points
- Shift planning for 1000 executors

### 12.4 Chaos Testing
- AI service failure
- Database slowdown
- High load scenarios
- Network partitions

## 13. Ограничения

### 13.1 Системные
- Max executors per shift: 100
- Max assignments per executor per day: 50
- Max distance for assignment: 50 km
- Shift planning horizon: 90 days

### 13.2 Бизнес-правила
- Minimum rest between shifts: 8 hours
- Maximum working hours per day: 12
- Maximum consecutive working days: 6
- Mandatory specialization match for critical tasks

## 14. Roadmap

### Phase 1 (MVP)
- Basic shift management
- Simple assignment algorithm
- Manual scheduling
- Basic load balancing

### Phase 2
- Shift templates
- Transfer workflow
- Route optimization
- Capacity planning

### Phase 3
- AI integration
- Predictive planning
- Advanced analytics
- Mobile app for executors