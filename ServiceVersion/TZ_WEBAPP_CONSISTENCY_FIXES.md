# 🔧 TZ_WEBAPP - Consistency & Dependency Fixes

**Дата**: 9 октября 2025
**Версия**: 1.0.0
**Приоритет**: 🟡 MEDIUM
**Статус**: Требуется согласование с бизнесом и архитектурой

---

## 📋 Executive Summary

Выявлено **3 проблемы согласованности** в спецификации WebApp:
1. Критерии приемки фиксируют полный функционал для всех ролей, но MVP scope (Q12.1) не утвержден
2. Технический стек закреплен конкретными технологиями, но в README решение еще "в процессе"
3. WebApp требует интеграцию с платежными шлюзами (Payme, Click), но они в P3 (пост-MVP)

**Все 3 проблемы требуют согласования с бизнесом и обновления документации.**

---

## 🟡 MEDIUM Priority Issues

### Issue #1: MVP Scope Not Finalized

**Приоритет:** 🟡 MEDIUM (Business Dependency)

**Локация:** `TZ_WEBAPP.md:923-970`

**Проблема:**
```markdown
## ✅ Критерии приемки

### Функциональные:
- [ ] Все роли могут аутентифицироваться           ⬅️ "Все роли" не определено
- [ ] Жители могут создавать и отслеживать заявки
- [ ] Исполнители видят свои задачи и смены        ⬅️ Executor в MVP?
- [ ] Менеджеры имеют доступ к аналитике           ⬅️ Manager в MVP?
- [ ] Руководители видят KPI и отчеты              ⬅️ Executive в MVP?
```

ТЗ требует **полный функционал для всех 4 ролей** в критериях приемки, но открытый вопрос **Q12.1** (MVP scope) все еще не решен.

**Blocking Question Q12.1:**
```markdown
### Q12.1 WebApp - объем первой итерации

**Критичность**: 🟢 P2 - Влияет на Frontend
**Контекст**: Определить функциональность WebApp для первого релиза.

**Варианты MVP**:
1. **Минимальный** - только просмотр заявок
2. **Базовый** - создание и управление заявками
3. **Расширенный** - полный функционал бота

**Требуется от бизнеса**:
- Определить целевую аудиторию WebApp
- Утвердить MVP функциональность
- Решить про мобильную версию (PWA?)
```

**Почему это проблема:**
- ⚠️ **Premature Commitment**: Критерии приемки фиксируют scope до бизнес-решения
- ⚠️ **Budget Risk**: "Все роли" = 18 недель, но бизнес может выбрать "только жители" = 8 недель
- ⚠️ **Unclear Priority**: Phase 1/2/3 есть, но непонятно что в MVP

**Сравнение вариантов:**

```
┌─────────────────────────────────────────────────────────┐
│ ВАРИАНТ 1: МИНИМАЛЬНЫЙ MVP (4 НЕДЕЛИ)                   │
├─────────────────────────────────────────────────────────┤
│ Роли:      Только Applicant (Житель)                    │
│ Функции:   • Аутентификация                             │
│            • Просмотр своих заявок                      │
│            • Real-time обновления статусов              │
│            • Уведомления                                │
│                                                         │
│ Критерии приемки:                                       │
│ ✅ Жители могут аутентифицироваться                     │
│ ✅ Жители видят список своих заявок                     │
│ ✅ Жители получают уведомления об обновлениях           │
│ ✅ Real-time обновления работают                        │
│                                                         │
│ Исключено из MVP:                                       │
│ ❌ Создание новых заявок (только через бот)            │
│ ❌ Другие роли (Executor, Manager, Executive)          │
│ ❌ Аналитика и отчеты                                   │
│ ❌ Смены и планирование                                 │
└─────────────────────────────────────────────────────────┘

VS

┌─────────────────────────────────────────────────────────┐
│ ВАРИАНТ 2: БАЗОВЫЙ MVP (8 НЕДЕЛЬ)                       │
├─────────────────────────────────────────────────────────┤
│ Роли:      Applicant + Executor                         │
│ Функции:   • Аутентификация                             │
│            • Создание и управление заявками (Applicant) │
│            • Просмотр и обновление заявок (Executor)    │
│            • Базовый дашборд                            │
│            • Real-time + уведомления                    │
│                                                         │
│ Критерии приемки:                                       │
│ ✅ Жители и исполнители могут аутентифицироваться       │
│ ✅ Жители могут создавать и отслеживать заявки          │
│ ✅ Исполнители видят свои задачи                        │
│ ✅ Real-time обновления работают                        │
│ ✅ Уведомления приходят корректно                       │
│                                                         │
│ Исключено из MVP:                                       │
│ ❌ Manager и Executive роли                             │
│ ❌ Аналитика и отчеты                                   │
│ ❌ Управление сменами                                   │
│ ❌ Advanced функционал                                  │
└─────────────────────────────────────────────────────────┘

VS

┌─────────────────────────────────────────────────────────┐
│ ВАРИАНТ 3: РАСШИРЕННЫЙ MVP (18 НЕДЕЛЬ)                  │
├─────────────────────────────────────────────────────────┤
│ Роли:      Все 4 роли (Applicant, Executor, Manager,   │
│            Executive)                                   │
│ Функции:   • Полный функционал бота                     │
│            • Аналитика и отчеты                         │
│            • Управление сменами                         │
│            • Advanced дашборды                          │
│            • Все интеграции                             │
│                                                         │
│ Критерии приемки (CURRENT SPEC):                        │
│ ✅ Все роли могут аутентифицироваться                   │
│ ✅ Жители могут создавать и отслеживать заявки          │
│ ✅ Исполнители видят свои задачи и смены                │
│ ✅ Менеджеры имеют доступ к аналитике                   │
│ ✅ Руководители видят KPI и отчеты                      │
│ ✅ Real-time обновления работают                        │
│ ✅ Уведомления приходят корректно                       │
│                                                         │
│ ⚠️ РИСКИ:                                                │
│ • Долгий time-to-market (18 недель)                    │
│ • Высокий бюджет                                        │
│ • Возможно избыточно для первого релиза                │
└─────────────────────────────────────────────────────────┘
```

**Исправление:**

**ДО (НЕПРАВИЛЬНО - без версионирования):**
```markdown
### Phase 1 (MVP - 8 недель):
✅ **Must have:**
- Аутентификация
- Управление заявками (создание, просмотр, статусы)
- Базовый дашборд для всех ролей                    ⬅️ "всех ролей" не определено
- Мобильная адаптация
- Интеграция с backend API

## ✅ Критерии приемки

### Функциональные:
- [ ] Все роли могут аутентифицироваться           ⬅️ "Все роли" - какие?
- [ ] Жители могут создавать и отслеживать заявки
- [ ] Исполнители видят свои задачи и смены
- [ ] Менеджеры имеют доступ к аналитике
- [ ] Руководители видят KPI и отчеты
```

**ПОСЛЕ (ПРАВИЛЬНО - с версионированием по Q12.1):**
```markdown
## 📋 Приоритизация разработки

⚠️ **ВАЖНО**: Финальная приоритизация зависит от решения **Q12.1**
(OPEN_QUESTIONS_REGISTRY.md). Ниже представлены 3 варианта MVP.

---

### 🎯 Вариант 1: Минимальный MVP (4 недели)

**Target:** Applicant (Житель) - только просмотр

**Phase 1 (Минимум - 4 недели):**
✅ **Must have:**
- Аутентификация (JWT)
- Просмотр своих заявок (read-only)
- Базовый дашборд для жителя
- Real-time обновления статусов
- Уведомления (WebSocket)
- Мобильная адаптация

**Критерии приемки:**
- [ ] Жители могут аутентифицироваться через Telegram
- [ ] Жители видят список своих заявок с фильтрацией
- [ ] Жители видят детали заявки (статус, исполнитель, комментарии)
- [ ] Real-time обновления работают (WebSocket)
- [ ] Уведомления приходят корректно
- [ ] Мобильная версия полностью функциональна

**Исключено:**
- ❌ Создание заявок (только через бот)
- ❌ Другие роли
- ❌ Аналитика
- ❌ Смены

**Рекомендуется когда:**
- Нужен быстрый time-to-market (1 месяц)
- Бюджет ограничен
- WebApp как дополнение к боту (основной канал - бот)

---

### 🎯 Вариант 2: Базовый MVP (8 недель) ⭐ RECOMMENDED

**Target:** Applicant + Executor

**Phase 1 (Базовый - 8 недель):**
✅ **Must have:**
- Аутентификация (JWT)
- **Applicant Dashboard:**
  - Создание заявок (форма с валидацией)
  - Просмотр и отслеживание заявок
  - Комментарии и фото
  - История изменений
- **Executor Dashboard:**
  - Список назначенных заявок
  - Обновление статусов
  - Добавление комментариев
  - Просмотр геолокации
- Real-time обновления (WebSocket)
- Уведомления
- Мобильная адаптация (PWA)

**Phase 2 (Расширение - 6 недель):**
🎯 **Should have:**
- Manager Dashboard (базовая аналитика)
- Смены для исполнителей (календарь)
- Экспорт отчетов
- Чат между ролями

**Phase 3 (Advanced - 4 недели):**
💎 **Nice to have:**
- Executive Dashboard (KPI, advanced аналитика)
- Карты и геолокация
- Конструктор отчетов

**Критерии приемки Phase 1:**
- [ ] Жители и исполнители могут аутентифицироваться
- [ ] Жители могут создавать заявки с фото и описанием
- [ ] Жители могут отслеживать заявки и добавлять комментарии
- [ ] Исполнители видят свои назначенные задачи
- [ ] Исполнители могут обновлять статусы и комментировать
- [ ] Real-time обновления работают
- [ ] Уведомления приходят корректно
- [ ] PWA функционал работает (установка, offline)

**Рекомендуется когда:**
- Нужен баланс между функциональностью и time-to-market
- WebApp как равноценный канал с ботом
- Фокус на основных пользователях (жители + исполнители)

---

### 🎯 Вариант 3: Расширенный MVP (18 недель)

**Target:** Все роли (Applicant, Executor, Manager, Executive)

**Phase 1 (Полный - 18 недель):**
✅ **Must have:**
- Все из Варианта 2
- **Manager Dashboard:**
  - Аналитика по заявкам
  - Управление командой исполнителей
  - Распределение задач
  - Отчеты и экспорт
- **Executive Dashboard:**
  - KPI и метрики
  - Финансовая аналитика
  - Прогнозы и тренды
  - Advanced отчеты
- Управление сменами (полный функционал)
- Карты и маршруты
- Интеграция с аналитикой

**Критерии приемки:**
- [ ] Все роли могут аутентифицироваться
- [ ] Жители могут создавать и отслеживать заявки
- [ ] Исполнители видят свои задачи и смены
- [ ] Менеджеры имеют доступ к аналитике и управлению
- [ ] Руководители видят KPI и advanced отчеты
- [ ] Real-time обновления работают
- [ ] Уведомления приходят корректно
- [ ] Все интеграции работают (карты, аналитика)

**Рекомендуется когда:**
- WebApp как основной канал (вместо бота)
- Нужен полный функционал для всех ролей
- Достаточно времени и бюджета (18 недель)

---

## 📊 Сравнительная таблица вариантов

| Параметр | Вариант 1 | Вариант 2 ⭐ | Вариант 3 |
|----------|-----------|-------------|-----------|
| **Время разработки** | 4 недели | 8 недель | 18 недель |
| **Роли** | Applicant | Applicant + Executor | Все 4 роли |
| **Создание заявок** | ❌ | ✅ | ✅ |
| **Аналитика** | ❌ | Базовая (Phase 2) | ✅ Полная |
| **Смены** | ❌ | Базовые (Phase 2) | ✅ Полные |
| **Карты** | ❌ | Phase 3 | ✅ |
| **PWA** | ✅ | ✅ | ✅ |
| **Time-to-market** | 1 месяц | 2 месяца | 4.5 месяца |
| **Бюджет** | Low | Medium | High |
| **Рекомендация** | Proof of Concept | ⭐ Recommended | Full Product |

---

## 🎯 Решение требуется от бизнеса (Q12.1)

**Вопросы для Product Owner:**

1. **Целевая аудитория WebApp:**
   - [ ] Только жители (компаньон к боту)
   - [ ] Жители + исполнители (равноценный канал)
   - [ ] Все роли (основной канал)

2. **Time-to-market приоритет:**
   - [ ] ASAP (1 месяц) → Вариант 1
   - [ ] Balanced (2 месяца) → Вариант 2 ⭐
   - [ ] Full featured (4.5 месяца) → Вариант 3

3. **Бюджет:**
   - [ ] Ограниченный → Вариант 1
   - [ ] Средний → Вариант 2 ⭐
   - [ ] Полный → Вариант 3

4. **Стратегия:**
   - [ ] WebApp как дополнение (бот - главное) → Вариант 1
   - [ ] WebApp как равноценный канал → Вариант 2 ⭐
   - [ ] WebApp как основной канал → Вариант 3

**Рекомендация архитектуры: Вариант 2 (Базовый MVP)**
- ✅ Оптимальный баланс функциональности и time-to-market
- ✅ Покрывает основных пользователей (80% аудитории)
- ✅ Phased approach позволяет расширять постепенно
- ✅ Reasonable бюджет
```

---

### Issue #2: Tech Stack Premature Commitment

**Приоритет:** 🟡 MEDIUM (Architecture Decision)

**Локация:** `TZ_WEBAPP.md:707-734` vs `README.md:97`

**Проблема:**

```markdown
# TZ_WEBAPP.md:707-734
## 💻 Технический стек

**Основной стек:**
Framework:     React 18+ или Vue 3+            ⬅️ Конкретные версии
Language:      TypeScript 5+
State:         Redux Toolkit / Zustand / Pinia
UI Library:    Material-UI / Ant Design / Tailwind CSS
...

VS

# README.md:97
### 🔄 В процессе:
- 🔄 Выбор технологического стека              ⬅️ Еще не выбран!
```

ТЗ WebApp **уже закрепляет** конкретные технологии (React/Vue, TypeScript, конкретные библиотеки), но в общем README решение **"в процессе"**.

**Почему это проблема:**
- ⚠️ **Inconsistency**: ТЗ фиксирует стек, но решение не принято официально
- ⚠️ **Team Alignment**: Frontend команда может не согласиться с выбором
- ⚠️ **Premature Optimization**: Фиксируем библиотеки до анализа требований

**Варианты решения:**

**Вариант A: Зафиксировать решение (если оно принято)**
```markdown
# README.md - обновить статус
### ✅ Решено:
- ✅ Технологический стек утвержден
  - Backend: Python 3.11, FastAPI
  - Frontend: React 18+ TypeScript (TZ_WEBAPP.md)
  - Database: PostgreSQL 15
  - Cache: Redis 7
  - Message Broker: RabbitMQ
```

**Вариант B: Сделать ТЗ нейтральным (если решение не принято)**

**Исправление:**

**ДО (НЕПРАВИЛЬНО - конкретные технологии):**
```markdown
## 💻 Технический стек

### Frontend

**Основной стек:**
Framework:     React 18+ или Vue 3+
Language:      TypeScript 5+
State:         Redux Toolkit / Zustand / Pinia
Router:        React Router / Vue Router
UI Library:    Material-UI / Ant Design / Tailwind CSS
Charts:        Recharts / Chart.js / Apache ECharts
```

**ПОСЛЕ (ПРАВИЛЬНО - нейтральный с опциями):**
```markdown
## 💻 Технический стек

⚠️ **ВАЖНО**: Финальный выбор технологий будет сделан Frontend Lead после:
- Анализа требований производительности
- Оценки команды (skillset)
- Proof of Concept (если требуется)

Ниже представлены **рекомендуемые опции** для каждой категории.

---

### Frontend

**Framework:**

| Опция | Pros | Cons | Рекомендация |
|-------|------|------|--------------|
| **React 18+** | • Большая экосистема<br>• Лучше для complex UI<br>• Server components<br>• Concurrent features | • Больше boilerplate<br>• Steeper learning curve | ⭐ Recommended for enterprise |
| **Vue 3+** | • Проще в изучении<br>• Composition API<br>• Меньше кода<br>• Built-in state | • Меньше библиотек<br>• Меньше вакансий | ⭐ Recommended for rapid dev |

**Обязательно:**
- TypeScript 5+ (non-negotiable для type safety)
- Modern bundler (Vite / Webpack 5)
- Component testing (Jest / Vitest)

**State Management:**

| Опция | Use Case |
|-------|----------|
| **Redux Toolkit** | Complex state, много async actions |
| **Zustand** | Simple state, меньше boilerplate |
| **Pinia (Vue)** | Vue-native, Composition API |

**UI Library:**

| Опция | Pros | Cons |
|-------|------|------|
| **Material-UI (MUI)** | Enterprise look, много компонентов | Heavy bundle, сложная кастомизация |
| **Ant Design** | Business UI, богатая функциональность | Китайский дизайн, тяжелая |
| **Tailwind CSS** | Полный контроль, легкий | Нужно строить компоненты самим |

**Рекомендация архитектуры:**
- ⭐ **React 18+ TypeScript + Zustand + Tailwind CSS**
- Причины:
  - React: Enterprise standard, большая команда потенциально
  - TypeScript: Обязательно для type safety
  - Zustand: Простой state без boilerplate Redux
  - Tailwind: Гибкость + performance

**Alternative (если команда знает Vue):**
- ⭐ **Vue 3+ TypeScript + Pinia + Tailwind CSS**

---

### 📋 Финальное решение требуется от:
- **Frontend Lead** - выбор framework и библиотек
- **Tech Lead** - утверждение архитектурных решений
- **Team** - подтверждение skillset

До принятия решения использовать нейтральные требования:
- ✅ Modern framework (React/Vue/Svelte)
- ✅ TypeScript mandatory
- ✅ Component-based architecture
- ✅ State management solution
- ✅ UI library or design system
```

**Действия:**
1. Frontend Lead принимает решение на основе:
   - Team skillset
   - Performance requirements
   - Time-to-market
2. Обновить README.md статус на "✅ Решено"
3. Обновить TZ_WEBAPP.md с финальным стеком

---

### Issue #3: Payment Gateway Integration Mismatch

**Приоритет:** 🟡 MEDIUM (Backend Dependency)

**Локация:** `TZ_WEBAPP.md:994` vs `FUNCTIONAL_REQUIREMENTS_MATRIX.md:189`

**Проблема:**

```markdown
# TZ_WEBAPP.md:994
### External Services:
- Payment gateway (Payme, Click)        ⬅️ WebApp требует

VS

# FUNCTIONAL_REQUIREMENTS_MATRIX.md:189
| Payment Gateway | P3 | ✅ | Payment Provider | ❌ |  ⬅️ P3 = пост-MVP, не реализовано

# TZ_INTEGRATION_HUB.md:443
### 6.4 Payment Gateway API
Operations:
- Create charge
- Refund payment                        ⬅️ Описано, но status неизвестен
```

WebApp ТЗ ожидает работу с платежными шлюзами (Payme, Click), но:
- ❌ В функциональной матрице: **P3** (пост-MVP, реализация отсутствует)
- ❌ В Integration Hub: описание API есть, но status implementation неизвестен
- ❌ Без готового backend эта часть WebApp **недостижима**

**Почему это проблема:**
- ⚠️ **False Expectation**: WebApp spec предполагает payments, но backend не ready
- ⚠️ **Blocked Development**: Frontend не может реализовать без backend API
- ⚠️ **Scope Creep**: Если payments нужны в MVP, нужно поднимать приоритет в backend

**Варианты решения:**

**Вариант A: Payments НЕ в MVP (рекомендуется)**
```markdown
# Убрать из MVP WebApp, добавить в Phase 3
```

**Вариант B: Payments в MVP**
```markdown
# Поднять приоритет в FUNCTIONAL_REQUIREMENTS_MATRIX до P1
# Разработать Integration Hub Payment Gateway API
# Интегрировать Payme/Click
```

**Исправление:**

**ДО (НЕПРАВИЛЬНО - payments в интеграциях без disclaimer):**
```markdown
## 🔗 Интеграции

### External Services:
- 2GIS Maps API
- Google Maps API (fallback)
- Payment gateway (Payme, Click)        ⬅️ Без указания приоритета/статуса
- SMS gateway
- Email service
```

**ПОСЛЕ (ПРАВИЛЬНО - с версионированием и зависимостями):**
```markdown
## 🔗 Интеграции

⚠️ **ВАЖНО**: Интеграции зависят от готовности соответствующих backend сервисов
и внешних API. Статус каждой интеграции указан ниже.

---

### Backend Services (Required for MVP):

| Service | Status | Phase | Endpoints Required |
|---------|--------|-------|-------------------|
| **Core Service API** | ✅ Ready | Phase 1 | `/auth`, `/users`, `/requests` |
| **Operations Service API** | ✅ Ready | Phase 1 | `/shifts`, `/executors` |
| **Communication Hub API** | ✅ Ready | Phase 1 | `/notifications`, WebSocket |
| **Media Storage API** | ✅ Ready | Phase 1 | `/upload`, `/download` |
| **Analytics Service API** | 🔄 In Progress | Phase 2 | `/metrics`, `/reports` |

---

### External Services:

#### ✅ Phase 1 (MVP) - Ready to Integrate

**2GIS Maps API**
- **Status:** ✅ API Available, Integration Hub ready
- **Use Case:** Геокодирование адресов, отображение карт
- **Endpoints:** `/geocode`, `/reverse-geocode`
- **Docs:** [TZ_INTEGRATION_HUB.md:390-420](TZ_INTEGRATION_HUB.md)

**Google Maps API (Fallback)**
- **Status:** ✅ API Available, Integration Hub ready
- **Use Case:** Fallback если 2GIS недоступен
- **Endpoints:** Same as 2GIS
- **Cost:** $0.007/request (до 100K бесплатно)

**SMS Gateway (Twilio / local provider)**
- **Status:** ✅ API Available, Integration Hub ready
- **Use Case:** 2FA, уведомления
- **Endpoints:** `/send-sms`

**Email Service (SMTP / SendGrid)**
- **Status:** ✅ Ready
- **Use Case:** Уведомления, отчеты
- **Endpoints:** `/send-email`

---

#### 🔄 Phase 2 (Post-MVP) - Planned

**Push Notifications (FCM / APNS)**
- **Status:** 🔄 Planned for Phase 2
- **Use Case:** Mobile push notifications для PWA
- **Dependency:** Communication Hub enhancement

**WebRTC (Video calls)**
- **Status:** 🔄 Planned for Phase 2
- **Use Case:** Video консультации между ролями
- **Dependency:** New service (Communication Service enhancement)

---

#### ❌ Phase 3 (Future) - Not in Current Scope

**Payment Gateway (Payme, Click)**
- **Status:** ❌ P3 - Not implemented in backend
- **Blocked by:** Integration Hub Payment API (not developed yet)
- **Priority:** P3 in FUNCTIONAL_REQUIREMENTS_MATRIX.md:189
- **Use Case:** Оплата услуг через WebApp
- **Required for:**
  - Оплата заявок онлайн
  - Подписки на премиум функции
  - Оплата штрафов

**⚠️ IMPORTANT:**
Если Payment Gateway требуется в MVP WebApp, необходимо:
1. Поднять приоритет в FUNCTIONAL_REQUIREMENTS_MATRIX (P3 → P1)
2. Разработать Integration Hub Payment API
3. Интегрировать Payme + Click (PCI compliance)
4. Добавить 4-6 недель к timeline

**Рекомендация:** Отложить payments до Phase 3, использовать альтернативные методы:
- Оплата через бот (Telegram Payments)
- Оплата офлайн
- Invoice generation для юр. лиц

---

## 📊 Integration Readiness Matrix

| Integration | MVP Phase | Backend Status | Frontend Status | Blocker |
|-------------|-----------|----------------|-----------------|---------|
| Core API | ✅ Phase 1 | ✅ Ready | 🔄 To implement | None |
| Operations API | ✅ Phase 1 | ✅ Ready | 🔄 To implement | None |
| Comms Hub | ✅ Phase 1 | ✅ Ready | 🔄 To implement | None |
| Media Storage | ✅ Phase 1 | ✅ Ready | 🔄 To implement | None |
| 2GIS Maps | ✅ Phase 1 | ✅ Ready | 🔄 To implement | None |
| Analytics | 🔄 Phase 2 | 🔄 In progress | ⏳ Waiting | Backend |
| Payment Gateway | ❌ Phase 3 | ❌ Not started | ⏳ Blocked | Backend P3 |
| WebRTC | 🔄 Phase 2 | ❌ Not planned | ⏳ Blocked | New service |

---

## 🎯 Решение требуется от Product Owner

**Вопрос:** Нужны ли Payment Gateway (Payme/Click) в MVP WebApp?

**Вариант A (Рекомендуется): НЕТ, отложить до Phase 3**
- ✅ Быстрее time-to-market
- ✅ Меньше бюджет
- ✅ Меньше compliance рисков (PCI DSS)
- ✅ Можно использовать альтернативы (бот payments, офлайн)
- Timeline: Phase 1 = 8 недель

**Вариант B: ДА, нужны в MVP**
- ⚠️ Требует разработки Integration Hub Payment API (4-6 недель)
- ⚠️ PCI compliance audit (2-3 недели)
- ⚠️ Integration с Payme + Click (2 недели каждый)
- ⚠️ Testing & certification (2 недели)
- Timeline: Phase 1 = 16-19 недель (удвоение времени!)

**Решение:** _____________________ (Product Owner)
**Дата решения:** ___________________
```

---

## 📊 Summary Table

| Issue | Location | Problem | Impact | Resolution | Owner |
|-------|----------|---------|--------|------------|-------|
| #1 MVP Scope | TZ_WEBAPP:923-970 | Критерии приемки без утвержденного MVP | Scope/budget uncertainty | Версионировать ТЗ под 3 варианта Q12.1 | Product Owner |
| #2 Tech Stack | TZ_WEBAPP:707-734 | Стек зафиксирован, но решение "в процессе" | Team misalignment | Либо утвердить стек, либо сделать ТЗ нейтральным | Frontend Lead |
| #3 Payments | TZ_WEBAPP:994 | WebApp требует payments, но они P3 в backend | Blocked development | Либо убрать из MVP, либо поднять приоритет backend | Product Owner |

---

## ✅ Action Items

### Immediate (Before WebApp Development):
1. ⚠️ **Resolve Q12.1** - Product Owner выбирает вариант MVP (1/2/3)
2. ⚠️ **Update TZ_WEBAPP.md** - Версионировать критерии приемки под выбранный вариант
3. ⚠️ **Finalize Tech Stack** - Frontend Lead принимает решение, обновить README.md
4. ⚠️ **Clarify Payment Priority** - Product Owner решает: Phase 1 или Phase 3

### Short-term (Sprint 1):
5. Update FUNCTIONAL_REQUIREMENTS_MATRIX если payments в MVP
6. Create detailed integration plan с зависимостями
7. Set up frontend project с финальным стеком
8. Create integration stubs для backend APIs

### Mid-term (Sprint 2-3):
9. Implement MVP функционал согласно выбранному варианту
10. Integrate с готовыми backend services
11. Testing & validation

---

## 📚 Related Documents

- [TZ_WEBAPP.md](TZ_WEBAPP.md) - Original spec (needs updates)
- [OPEN_QUESTIONS_REGISTRY.md](OPEN_QUESTIONS_REGISTRY.md) - Q12.1 (MVP scope)
- [README.md](README.md) - Project overview (tech stack status)
- [FUNCTIONAL_REQUIREMENTS_MATRIX.md](FUNCTIONAL_REQUIREMENTS_MATRIX.md) - Feature priorities
- [TZ_INTEGRATION_HUB.md](TZ_INTEGRATION_HUB.md) - Integration specs

---

**Prepared by:** Claude (Sonnet 4.5)
**Date:** 9 October 2025
**Status:** 🟡 MEDIUM - Requires business decisions
**Review Required:** Product Owner, Frontend Lead, Tech Lead
