# Universal Project Audit — Code Quality & Architecture

Полный аудит проекта. Код НЕ менять. Только анализ.

Перед началом: прочитай README, package.json, docker-compose,
структуру директорий. Понять архитектуру до анализа кода.

═══ ЭТАП 0: РАЗВЕДКА (5 мин) ═══

```bash
# Структура проекта
find . -maxdepth 3 -type f -name "*.ts" -o -name "*.tsx" \
  -o -name "*.js" -o -name "*.py" -o -name "*.go" \
  -o -name "*.rs" -o -name "*.java" | head -100

# Размер кодовой базы
find . -name "*.ts" -o -name "*.tsx" | grep -v node_modules \
  | grep -v dist | xargs wc -l 2>/dev/null | tail -1

# Зависимости
cat package.json 2>/dev/null | jq '.dependencies | length'
cat requirements.txt 2>/dev/null | wc -l
cat go.mod 2>/dev/null | grep -c "require"

# Тесты
find . -name "*.test.*" -o -name "*.spec.*" \
  -o -name "test_*" | grep -v node_modules | wc -l

# Docker
ls docker-compose* Dockerfile* 2>/dev/null

# CI/CD
ls .github/workflows/* .gitlab-ci.yml Jenkinsfile 2>/dev/null

# Конфиги
ls .env* *.config.* tsconfig* 2>/dev/null
```

Записать:
- Язык(и)
- Фреймворк(и)
- Архитектура (monolith / microservices / monorepo)
- Количество сервисов / модулей
- Строк кода (без тестов)
- Строк тестов
- Инфраструктура (Docker? K8s? Serverless?)

═══ ЭТАП 1: АРХИТЕКТУРА ═══

### 1.1 Структура проекта
- Логична ли организация файлов?
- Можно ли понять назначение модуля по имени папки?
- Есть ли convention и следуется ли он?
- Глубина вложенности: адекватна или слишком глубоко?

### 1.2 Разделение ответственности
- Каждый модуль/сервис делает одно?
- Есть ли God-objects (файлы > 500 строк)?
- Есть ли God-services (сервис с 10+ доменами)?
- Бизнес-логика отделена от transport (HTTP/WS)?
- Data access отделён от бизнес-логики?

### 1.3 Зависимости между модулями
- Есть ли циклические зависимости?
- Направление зависимостей корректно?
  (domain не зависит от infrastructure)
- Coupling: модули связаны слабо или сильно?
- Cohesion: внутри модуля всё связано?

### 1.4 Масштабируемость архитектуры
- Что сломается первым при 10x нагрузке?
- Single points of failure?
- Stateful vs stateless компоненты?
- Database bottlenecks?

═══ ЭТАП 2: KISS — Keep It Simple ═══

Искать:

### 2.1 Overcomplicated Logic
- Функции > 50 строк
- Вложенность > 3 уровней
- Цепочки .then().then().then() или callback hell
- Сложные generic типы где конкретный тип достаточен
- Абстракции ради абстракций (Factory → Builder → Strategy
  для одного use case)

### 2.2 Over-Abstraction
- Wrapper-классы которые просто проксируют
- Base classes с одним наследником
- Interfaces с одной реализацией
- Service → Repository → DAO → Model 
  (4 слоя где хватит 2)
- Config файлы > 100 строк

### 2.3 Unnecessary Complexity
- Middleware chains > 5 слоёв
- Event systems для синхронной логики
- Message queues для 10 сообщений/час
- Caching layer для данных которые не кешируются
- Microservices для 50 пользователей

Для каждого finding:
```
KISS-001 | HIGH | file.ts:45
Функция processOrder (78 строк, 5 уровней вложенности)
Можно разделить на: validateOrder, calculateTotal, saveOrder
```

═══ ЭТАП 3: DRY — Don't Repeat Yourself ═══

Искать:

### 3.1 Copy-Paste Code
```bash
# Поиск похожих блоков (для TypeScript/JavaScript)
# Файлы > 80% похожие
find . -name "*.ts" -not -path "*/node_modules/*" \
  -not -path "*/dist/*" | xargs -I{} md5sum {} \
  | sort | uniq -w32 -d

# Одинаковые функции в разных файлах
grep -rn "function validateInput\|function parseResponse\|function handleError" \
  --include="*.ts" | sort
```

### 3.2 Repeated Patterns
- Одинаковый boilerplate в каждом файле/модуле
- try/catch с одинаковой обработкой
- HTTP client setup с одинаковыми headers
- Validation logic повторяется
- Database queries с одинаковой структурой

### 3.3 Type Duplication
- Одинаковые интерфейсы в разных файлах
- Re-declaration типов вместо import
- Enum определён в нескольких местах

### 3.4 Configuration Duplication
- Одинаковые env vars в нескольких конфигах
- Docker setup повторяется между сервисами
- Build config дублируется

Для каждого finding:
```
DRY-001 | MEDIUM | auth/utils.ts:12, users/utils.ts:15
Функция formatDate идентична в обоих файлах (8 строк)
Извлечь в shared/utils
```

═══ ЭТАП 4: YAGNI — You Ain't Gonna Need It ═══

Искать:

### 4.1 Dead Code
```bash
# Unused exports (TypeScript)
# Файлы которые ничто не импортирует
for f in $(find . -name "*.ts" -not -path "*/node_modules/*" \
  -not -name "*.test.*" -not -name "*.spec.*" \
  -not -name "index.ts" -not -path "*/dist/*"); do
  BASENAME=$(basename "$f" .ts)
  IMPORTS=$(grep -rl "$BASENAME" --include="*.ts" \
    --include="*.tsx" . 2>/dev/null | grep -v node_modules \
    | grep -v "$f" | wc -l)
  if [ "$IMPORTS" -eq 0 ]; then
    echo "UNUSED: $f"
  fi
done

# Unused functions
grep -rn "export function\|export const\|export class" \
  --include="*.ts" | while read line; do
  FUNC=$(echo "$line" | grep -oP "(?:function|const|class)\s+\K\w+")
  FILE=$(echo "$line" | cut -d: -f1)
  USES=$(grep -rl "$FUNC" --include="*.ts" --include="*.tsx" . \
    2>/dev/null | grep -v node_modules | grep -v "$FILE" | wc -l)
  if [ "$USES" -eq 0 ]; then
    echo "UNUSED EXPORT: $FUNC in $FILE"
  fi
done

# Unused dependencies
# (для npm)
npx depcheck 2>/dev/null
```

### 4.2 Premature Generalization
- Generic решения для единственного use case
- Plugin systems без plugins
- Strategy pattern с одной strategy
- Configuration для вещей которые никогда не меняются
- Интернационализация без второго языка

### 4.3 Unused Features
- Endpoints без вызывающего кода (frontend/client)
- Feature flags для несуществующих фич
- Stub сервисы с только health endpoint
- TODO/FIXME которые старше 3 месяцев
- Commented-out code

### 4.4 Over-Engineering для текущего масштаба
- Caching для 50 concurrent users
- Message brokers для 10 events/min
- Horizontal scaling infra для single instance
- Complex RBAC для 3 roles
- Audit logging для internal admin tool

Для каждого finding:
```
YAGNI-001 | LOW | services/geofence/
Весь сервис geofence (340 строк) не используется ни одним frontend.
Рекомендация: удалить или перенести в Phase 10
```

═══ ЭТАП 5: SOLID (где применимо) ═══

### 5.1 Single Responsibility
- Файлы с > 3 несвязанными функциями
- Классы/модули с > 2 причинами для изменения
- Service файлы > 300 строк (вероятно > 1 ответственность)

### 5.2 Open/Closed
- Длинные switch/case или if-else chains (> 5 веток)
- Функции которые нужно менять при добавлении нового типа
- Hardcoded списки вместо registry/config

### 5.3 Liskov Substitution
- Функции которые проверяют конкретный тип аргумента
  (instanceof, typeof) вместо полиморфизма
- Наследование где дочерний класс ломает контракт

### 5.4 Interface Segregation
- Интерфейсы > 10 методов
- Классы реализующие интерфейс но бросающие NotImplemented
- Optional поля в интерфейсах > 50% от общего числа

### 5.5 Dependency Inversion
- Прямые import конкретных реализаций в бизнес-логике
- new ConcreteClass() внутри бизнес-логики
- Тесты требуют реальных зависимостей (нет DI)

═══ ЭТАП 6: SECURITY QUICK SCAN ═══

```bash
# Секреты в коде
grep -rn "password\|secret\|api_key\|apikey\|token\|private_key" \
  --include="*.ts" --include="*.js" --include="*.py" \
  | grep -v node_modules | grep -v test | grep -v ".d.ts" \
  | grep -v "process.env\|config\.\|interface\|type " | head -30

# SQL injection vectors
grep -rn "\$queryRaw\|\.query(\|execute(" \
  --include="*.ts" | grep -v node_modules | head -20

# eval / exec
grep -rn "eval(\|exec(\|Function(" \
  --include="*.ts" --include="*.js" | grep -v node_modules

# Hardcoded URLs/IPs
grep -rn "http://\|https://" --include="*.ts" \
  | grep -v node_modules | grep -v test | grep -v ".d.ts" \
  | grep -v "localhost\|127.0.0.1\|0.0.0.0" | head -20

# .env в git
git log --all --diff-filter=A -- ".env" "*.pem" "*.key"
```

═══ ЭТАП 7: TESTING QUALITY ═══

### 7.1 Coverage
- Есть ли тесты для каждого модуля?
- Соотношение: строки тестов / строки кода
- Критическая бизнес-логика без тестов?
- Модули с 0 тестами?

### 7.2 Test Quality
- Тесты проверяют поведение или имплементацию?
- Excessive mocking (всё замокано — тест ничего не проверяет)?
- Test setup > 50 строк (too complex)?
- Naming: понятно что проверяется?
- One assert per test? Или 10 asserts в одном тесте?

### 7.3 Test Patterns
```bash
# Тесты без assertions
grep -rl "it(\|test(" --include="*.test.*" | xargs grep -L "expect\|assert"

# Тесты с .skip
grep -rn "\.skip\|xit(\|xtest(" --include="*.test.*" | wc -l

# Empty test files
find . -name "*.test.*" -empty
```

═══ ЭТАП 8: PERFORMANCE RED FLAGS ═══

### 8.1 Database
- N+1 queries (loop с query внутри)
- Missing indexes (query по полю без index)
- Unbounded queries (SELECT * без LIMIT)
- Large transactions

### 8.2 Memory
- Accumulating arrays/maps без cleanup
- Large objects в closure
- Event listeners без removeListener
- Unbounded caches

### 8.3 Network
- Sequential API calls где можно parallel
- No timeout на HTTP requests
- No retry strategy
- Large payloads без pagination

### 8.4 Frontend (если есть)
- Bundle size: dynamic imports для тяжёлых компонентов?
- Re-renders: memo/useMemo/useCallback где нужно?
- Images: оптимизированы?
- State management: глобальный state для локальных данных?

═══ ЭТАП 9: DOCUMENTATION & DX ═══

### 9.1 Документация
- README существует и актуален?
- API документация?
- Setup guide работает?
- Architecture Decision Records?
- Inline comments: полезные или noise?

### 9.2 Developer Experience
- Сколько шагов для запуска проекта?
- Есть ли скрипты для частых операций?
- Error messages понятные разработчику?
- Debugging: есть ли source maps, structured logs?

═══ ИТОГОВЫЙ ОТЧЁТ ═══

## Code Quality Report — [Project Name]

### Quick Stats
| Metric | Value |
|--------|-------|
| Languages | |
| Frameworks | |
| Total files | |
| Lines of code | |
| Lines of tests | |
| Test/Code ratio | |
| Services/Modules | |
| Dependencies | |
| Docker containers | |

### Findings Summary

| Category | Critical | High | Medium | Low | Total |
|----------|----------|------|--------|-----|-------|
| KISS | | | | | |
| DRY | | | | | |
| YAGNI | | | | | |
| SOLID | | | | | |
| Security | | | | | |
| Testing | | | | | |
| Performance | | | | | |
| **TOTAL** | | | | | |

### Code Health Score

| Criterion | Score /10 | Comment |
|-----------|----------|---------|
| Readability | | |
| Maintainability | | |
| Testability | | |
| Simplicity | | |
| Consistency | | |
| Security | | |
| Performance | | |
| Documentation | | |
| **OVERALL** | **/10** | |

### Top-10 Issues

| # | Category | Severity | File | Description |
|---|----------|----------|------|-------------|

### Dead Code Inventory

| File/Function | Lines | Last used | Action |
|-------------|-------|-----------|--------|

### DRY Extraction Candidates

| Pattern | Occurrences | Files | Extract to |
|---------|-------------|-------|-----------|

### YAGNI Removal Candidates

| Feature | Files | Lines | Needed? | Action |
|---------|-------|-------|---------|--------|

### Architecture Recommendations

| # | Recommendation | Impact | Effort | Priority |
|---|---------------|--------|--------|----------|

### Positive Patterns
Что сделано хорошо — конкретные примеры.

═══ ПРАВИЛА АУДИТА ═══

1. Код НЕ менять. Только анализ.
2. Каждый finding: файл + строка + конкретный пример
3. Severity определять по impact:
   - CRITICAL: баги, security holes, data loss
   - HIGH: значительно усложняет maintenance
   - MEDIUM: code smell, стоит исправить
   - LOW: стилистическое, nice-to-have
4. Не придираться к стилю если есть linter
5. Учитывать контекст: MVP ≠ enterprise
6. Хвалить хорошие решения, не только критиковать
7. Рекомендации должны быть actionable 
   (не "улучшить", а "извлечь функцию X из Y в Z")