# Shift Service - Следующие Шаги (Краткий План)

**Текущее состояние**: ✅ **32% coverage, 107 unit tests, production-ready**
**Следующая цель**: 🎯 **45% coverage** (через 1-2 недели)

---

## 🚀 Немедленные Действия (Следующая Сессия)

### Вариант A: Schedule Service (Рекомендуется) ⭐
**Время**: 3-4 часа
**Сложность**: Средняя
**Текущее**: 64% → **Цель**: 75%
**Impact**: +11% service coverage, +3% overall

**Зачем**:
- ✅ Уже 64% - легко довести до 75%
- ✅ Критический сервис для планирования
- ✅ Быстрая победа

**Что делать**:
1. Добавить тесты для `generate_weekly_schedule()` (5 тестов)
2. Тесты для `detect_conflicts()` (4 теста)
3. Тесты для `auto_fill_shifts()` (3 теста)

**Команды**:
```bash
# Проверить текущее состояние
docker exec shift-service pytest tests/unit/services/test_schedule_service.py -v

# Посмотреть coverage
docker exec shift-service pytest tests/unit/services/test_schedule_service.py --cov=services/schedule_service --cov-report=term-missing

# Прочитать непокрытые методы
docker exec shift-service cat services/schedule_service.py | grep "async def"
```

---

### Вариант B: Shift Planning Service
**Время**: 3-4 часа
**Сложность**: Средняя
**Текущее**: 62% → **Цель**: 75%
**Impact**: +13% service coverage, +2% overall

**Зачем**:
- ✅ Quarterly planning важен для бизнеса
- ✅ Template generation используется часто
- ✅ Хороший impact

**Что делать**:
1. Quarterly planning tests (5 тестов)
2. Template generation tests (4 теста)
3. Specialization planning tests (3 теста)

---

### Вариант C: Shift Service Расширение
**Время**: 2-3 часа
**Сложность**: Низкая
**Текущее**: 60% → **Цель**: 70%
**Impact**: +10% service coverage, +3% overall

**Зачем**:
- ✅ Основной сервис - важно довести до 70%
- ✅ Bulk operations нужны для производительности
- ✅ Проще всего (уже знаем сервис)

**Что делать**:
1. Bulk create tests (3 теста)
2. Bulk update tests (3 теста)
3. Complex validation tests (4 теста)

---

## 📊 План на 2 Недели

### Неделя 1: Services Boost (32% → 40%)

**День 1-2**: Schedule Service (64% → 75%)
- 12 новых тестов
- +3% overall coverage

**День 3-4**: Shift Planning Service (62% → 75%)
- 12 новых тестов
- +2% overall coverage

**День 5**: Shift Service (60% → 70%)
- 10 новых тестов
- +3% overall coverage

**Результат**: 32% → 40% coverage, +34 теста

### Неделя 2: Advanced Services (40% → 48%)

**День 6-7**: Workload Predictor (57% → 70%)
- ML prediction tests
- Historical analysis tests
- +4% overall coverage

**День 8-9**: Transfer Service (53% → 65%)
- Восстановить удалённые тесты
- Workflow tests
- +2% overall coverage

**День 10**: Integration Tests
- Fix datetime issues
- Enable более тестов
- +2% overall coverage

**Результат**: 40% → 48% coverage

---

## 🎯 Приоритеты

### P1 - Критически Важно
1. ⭐ **Schedule Service** → 75% (бизнес-критичный)
2. ⭐ **Shift Planning Service** → 75% (планирование)
3. ⭐ **Shift Service** → 70% (основной сервис)

### P2 - Важно
4. 🟡 **Workload Predictor** → 70% (ML predictions)
5. 🟡 **Transfer Service** → 65% (восстановить тесты)
6. 🟡 **Integration Tests** (fix datetime issues)

### P3 - Можно Отложить
7. 🟢 **Specialization Planning** → 60% (сложный)
8. 🟢 **Model Tests** (включить)
9. 🟢 **Task Tests** (включить)

---

## 💡 Быстрый Старт

### Вариант "Быстрая Победа" (2 часа)

**Цель**: Довести shift_service до 70%

```bash
# 1. Проверить текущие тесты
docker exec shift-service pytest tests/unit/services/test_shift_service.py tests/unit/services/test_shift_service_expanded.py -v

# 2. Посмотреть coverage
docker exec shift-service pytest tests/unit/services/test_shift_service.py tests/unit/services/test_shift_service_expanded.py --cov=services/shift_service --cov-report=term-missing

# 3. Найти непокрытые строки
# Сфокусироваться на:
# - bulk_create_shifts (533-543)
# - bulk_update_shifts (544-554)
# - validate_shift_times (79-91)
```

**План**:
1. 30 мин: Прочитать непокрытый код
2. 60 мин: Написать 5-7 тестов
3. 30 мин: Запустить и исправить

**Результат**: 60% → 70% (+10%), +3% overall

---

### Вариант "Максимальный Impact" (4 часа)

**Цель**: Schedule Service 64% → 75%

```bash
# 1. Анализ
docker exec shift-service pytest tests/unit/services/test_schedule_service.py -v
docker exec shift-service pytest tests/unit/services/test_schedule_service.py --cov=services/schedule_service --cov-report=html

# 2. Открыть htmlcov/index.html и найти красные строки

# 3. Написать тесты для:
# - generate_weekly_schedule (строки 106-151)
# - detect_conflicts (строки 277-315)
# - auto_fill_shifts (строки 434-469)
```

**План**:
1. 60 мин: Анализ сервиса и непокрытого кода
2. 120 мин: Написать 12 тестов
3. 60 мин: Отладка и исправления

**Результат**: 64% → 75% (+11%), +3% overall

---

## 📋 Чек-лист Перед Началом

- [ ] Убедиться что контейнеры запущены
- [ ] Проверить что текущие 107 тестов проходят
- [ ] Выбрать сервис для работы
- [ ] Прочитать код сервиса
- [ ] Создать список непокрытых методов
- [ ] Оценить время на каждый тест

---

## 🎯 Success Metrics

### После Следующей Сессии
- **Coverage**: 32% → 35-38% (+3-6%)
- **Tests**: 107 → 120-130 (+13-23)
- **Services >70%**: 4 → 5-6
- **Time spent**: 2-4 часа

### После 2 Недель
- **Coverage**: 32% → 48% (+16%)
- **Tests**: 107 → 190+ (+83)
- **Services >70%**: 4 → 7
- **Production readiness**: Excellent

---

## 🎓 Рекомендация

### Для следующей сессии рекомендую:

**Вариант 1** (если есть 4+ часа):
→ **Schedule Service** (64% → 75%)
- Максимальный impact на бизнес
- Критический сервис
- Хорошая победа

**Вариант 2** (если есть 2-3 часа):
→ **Shift Service** (60% → 70%)
- Быстрая победа
- Основной сервис
- Знакомый код

**Вариант 3** (если хочется сложности):
→ **Workload Predictor** (57% → 70%)
- ML алгоритмы
- Интересная задача
- Большой impact

---

## 📞 Команды для Старта

```bash
# Выбери сервис и запусти:

# Schedule Service
docker exec shift-service pytest tests/unit/services/test_schedule_service.py -v --cov=services/schedule_service --cov-report=term-missing

# Shift Service
docker exec shift-service pytest tests/unit/services/test_shift_service*.py -v --cov=services/shift_service --cov-report=term-missing

# Workload Predictor
docker exec shift-service pytest tests/unit/services/test_workload_predictor.py -v --cov=services/workload_predictor --cov-report=term-missing
```

---

**Готов начать?** Скажи какой вариант выбираешь! 🚀

**Статус**: ✅ Готов к работе
**Рекомендация**: Schedule Service (4 часа, +3% overall)
**Альтернатива**: Shift Service (2 часа, +3% overall)
