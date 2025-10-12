# Shift Service - Roadmap к 80% Coverage

**Текущее состояние**: 32% coverage, 107 unit tests passing
**Целевое состояние**: 80% coverage, production-ready
**Временной горизонт**: 4-6 недель

---

## 📊 Текущий Анализ

### Покрытие Сервисов (Текущее)

| Сервис | Coverage | Тесты | Приоритет | Цель |
|--------|----------|-------|-----------|------|
| ✅ template_service | 73% | 9 | ✅ Done | - |
| ✅ analytics_service | 72% | 20 | ✅ Done | - |
| ✅ ai_integration | 72% | 20 | ✅ Done | - |
| 🟡 schedule_service | 64% | ? | P1 | 75% |
| 🟡 shift_planning_service | 62% | ? | P1 | 75% |
| 🟡 shift_service | 60% | 33 | P1 | 70% |
| 🟡 workload_predictor | 57% | ? | P2 | 70% |
| 🟡 transfer_service | 53% | 8 | P2 | 65% |
| 🔴 scheduler_service | 49% | 17 | P2 | 60% |
| 🔴 specialization_planning | 31% | ? | P3 | 60% |

### Тестовое Покрытие

**Unit Tests**:
- ✅ Services: 107 passing
- 🔴 Models: 0/136 tests running
- 🔴 Tasks: 0/~60 tests running
- 🔴 Utils: 0/161 tests running

**Integration Tests**:
- ✅ API: Большинство проходят
- ⚠️ Database: Некоторые проблемы
- 🟡 Phase2 fixes: 0/196 running

**Всего тестов**: 559 (много отключены)

---

## 🎯 Стратегический План

### Фаза 1: Быстрые Победы (Неделя 1-2)
**Цель**: 32% → 45% (+13%)

#### День 1-3: Schedule Service (64% → 75%)
**Текущие проблемы**:
- 64 missed lines из 178
- Основные методы работают
- Нужно добавить edge cases

**Действия**:
1. Проанализировать текущие тесты
2. Добавить тесты для:
   - Weekly planning (строки 106-151)
   - Conflict detection (строки 277-315)
   - Auto-generation (строки 434-469)
3. Edge cases и error handling

**Ожидаемый результат**: +11% coverage

#### День 4-6: Shift Planning Service (62% → 75%)
**Текущие проблемы**:
- 79 missed lines из 206
- Quarterly planning не покрыто (строки 283-320)
- Template generation не покрыто (строки 443-506)

**Действия**:
1. Quarterly planning tests
2. Template generation tests
3. Specialization planning tests
4. Validation tests

**Ожидаемый результат**: +13% coverage, но меньший вес

#### День 7: Shift Service (60% → 70%)
**Текущие проблемы**:
- 114 missed lines из 282
- Bulk operations не покрыты (строки 533-564)
- Complex validation не покрыта (строки 79-111)

**Действия**:
1. Bulk create/update tests
2. Complex validation tests
3. Error scenarios
4. Concurrent operations

**Ожидаемый результат**: +10% coverage на большом сервисе

### Фаза 2: Средние Улучшения (Неделя 3-4)
**Цель**: 45% → 60% (+15%)

#### День 8-10: Workload Predictor (57% → 70%)
**Проблемы**:
- 149 missed lines из 343 (большой сервис)
- ML предсказания не покрыты (строки 505-538)
- Historical analysis (строки 568-596)
- Pattern detection (строки 640-679)

**Действия**:
1. ML prediction tests (mock data)
2. Historical data analysis tests
3. Pattern detection tests
4. Accuracy tests

#### День 11-13: Transfer Service (53% → 65%)
**Проблемы**:
- 113 missed lines из 240
- Workflow logic (строки 109-156)
- Complex approval flows (строки 179-209)
- Auto-assignment logic (строки 269-304)

**Действия**:
1. Восстановить 5 удалённых тестов:
   - test_create_transfer_invalid_shift
   - test_list_transfers
   - test_reject_transfer
   - test_get_shift_transfer_history
   - test_get_executor_transfers
2. Workflow tests
3. Complex scenarios

#### День 14: Scheduler Service (49% → 60%)
**Проблемы**:
- 70 missed lines из 137
- Background task scheduling (строки 36-157)
- Task execution monitoring

**Действия**:
1. Включить 17 существующих тестов
2. Исправить проблемы
3. Добавить missing coverage

### Фаза 3: Сложные Сервисы (Неделя 5-6)
**Цель**: 60% → 75% (+15%)

#### День 15-18: Specialization Planning (31% → 60%)
**Самый проблемный сервис**:
- 233 missed lines из 339
- Очень сложная логика
- ML-based planning (строки 422-521)
- Optimization algorithms (строки 653-942)

**Действия**:
1. Анализ алгоритмов
2. Базовые тесты
3. Algorithm tests (genetic, simulated annealing)
4. Integration tests

#### День 19-21: Integration Tests
**Проблемы**:
- API tests частично работают
- Database tests имеют проблемы
- Phase2 fixes отключены

**Действия**:
1. Исправить datetime issues в analytics API
2. Включить database tests
3. Исправить phase2 tests
4. End-to-end scenarios

### Фаза 4: Полировка (Неделя 6)
**Цель**: 75% → 80% (+5%)

#### День 22-24: Model Tests
**Текущее**: 0/136 tests running

**Действия**:
1. Включить model tests
2. Исправить проблемы
3. Relationships tests
4. Validation tests

#### День 25-27: Task Tests
**Текущее**: 0/~60 tests running

**Действия**:
1. Включить background task tests
2. Celery/APScheduler tests
3. Cron job tests

#### День 28: Final Cleanup
1. Utils tests
2. Edge cases
3. Error scenarios
4. Documentation

---

## 🚀 Немедленные Шаги (Следующая Сессия)

### Приоритет 1: Schedule Service (3-4 часа)

**Шаг 1**: Анализ текущего состояния
```bash
docker exec shift-service pytest tests/unit/services/test_schedule_service.py -v
docker exec shift-service pytest tests/unit/services/test_schedule_service.py --cov=services/schedule_service --cov-report=term-missing
```

**Шаг 2**: Прочитать сервис и найти непокрытые методы
```bash
docker exec shift-service cat services/schedule_service.py | grep "async def"
```

**Шаг 3**: Добавить тесты для:
1. `generate_weekly_schedule()` - строки 106-151
2. `detect_conflicts()` - строки 277-315
3. `auto_fill_shifts()` - строки 434-469

**Ожидаемый результат**: 64% → 75% (+11%)

### Приоритет 2: Shift Planning Service (3-4 часа)

**Анализ**:
- 206 statements, 79 missed
- Quarterly planning не покрыто
- Template generation не покрыто

**План**:
1. Quarterly planning tests (5 тестов)
2. Template generation tests (4 теста)
3. Specialization planning tests (3 теста)

**Ожидаемый результат**: 62% → 75% (+13%)

### Приоритет 3: Shift Service Bulk Operations (2-3 часа)

**Анализ**:
- 282 statements, 114 missed
- Bulk operations (строки 533-564) - 32 строки
- Validation (строки 79-111) - 33 строки

**План**:
1. Bulk create tests (3 теста)
2. Bulk update tests (3 теста)
3. Complex validation tests (4 теста)

**Ожидаемый результат**: 60% → 70% (+10%)

---

## 📈 Ожидаемый Прогресс

```
Неделя 1: 32% → 40% (+8%)  - Schedule + Planning
Неделя 2: 40% → 48% (+8%)  - Shift Service + Workload
Неделя 3: 48% → 56% (+8%)  - Transfer + Scheduler
Неделя 4: 56% → 64% (+8%)  - Specialization (начало)
Неделя 5: 64% → 72% (+8%)  - Specialization + Integration
Неделя 6: 72% → 80% (+8%)  - Models + Tasks + Cleanup
```

---

## 🎯 Метрики Успеха

### Количественные
- ✅ **Overall Coverage**: 32% → 80%
- ✅ **Unit Tests**: 107 → 300+
- ✅ **Services >70%**: 4 → 8
- ✅ **Integration Tests**: ~50% → 80%

### Качественные
- ✅ **Production Ready**: Да
- ✅ **CI/CD Ready**: Да
- ✅ **Regression Protection**: Отличная
- ✅ **Team Confidence**: Очень высокая

---

## 🛠️ Технические Долги

### Высокий Приоритет
1. ⚠️ **Datetime issues**: Timezone-aware vs naive в analytics
2. ⚠️ **Missing fixtures**: transfer_factory не существует
3. ⚠️ **Model tests**: Полностью отключены
4. ⚠️ **Task tests**: Полностью отключены

### Средний Приоритет
1. 🟡 **API tests**: Частично работают
2. 🟡 **Database tests**: Некоторые проблемы
3. 🟡 **Phase2 fixes**: Не запускаются

### Низкий Приоритет
1. 🟢 **Utils tests**: Можно включить позже
2. 🟢 **Performance tests**: Пока не критично
3. 🟢 **E2E tests**: После 80% coverage

---

## 💡 Рекомендации

### Краткосрочные (1-2 недели)
1. **Фокус на services**: Довести все до 60%+
2. **Quick wins**: Schedule, Planning, Shift
3. **Fix datetime**: Исправить timezone issues
4. **Enable tests**: Включить отключённые тесты

### Среднесрочные (3-4 недели)
1. **Specialization service**: Самый сложный
2. **Integration tests**: Полное покрытие
3. **Model tests**: Включить и исправить
4. **Task tests**: Background jobs

### Долгосрочные (5-6 недель)
1. **80% coverage**: Достичь цели
2. **Performance tests**: Load testing
3. **Contract tests**: Service-to-service
4. **Documentation**: Полная

---

## 📋 Чек-лист Следующей Сессии

### Подготовка
- [ ] Проверить статус всех сервисов
- [ ] Выбрать приоритетный сервис (Schedule)
- [ ] Прочитать код сервиса
- [ ] Найти непокрытые методы

### Выполнение
- [ ] Написать тесты для 3 непокрытых методов
- [ ] Довести Schedule Service до 75%
- [ ] Запустить все тесты
- [ ] Проверить coverage

### Завершение
- [ ] Обновить отчёт
- [ ] Зафиксировать прогресс
- [ ] Планировать следующий сервис

---

## 🎯 Финальная Цель

**Vision**: Shift Service с 80%+ coverage, полностью протестированный, production-ready, с высокой уверенностью команды в качестве кода.

**Timeline**: 6 недель
**Effort**: ~80-100 часов
**ROI**: Высокий (меньше багов, быстрая разработка)

---

**Статус**: 📋 План готов к исполнению
**Следующий шаг**: Schedule Service (64% → 75%)
**Приоритет**: P1 - Высокий
**Время**: 3-4 часа

**Created**: 2025-10-03
**Version**: 1.0
