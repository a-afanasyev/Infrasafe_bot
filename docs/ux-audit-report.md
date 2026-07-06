# UX/UI Audit Report: UK Management Frontend

> ⚫ **ИСТОРИЧЕСКИЙ АУДИТ (2026-03) — до модернизации фронта.** Большинство замечаний
> уже реализовано. Читать как исторический артефакт, не как текущее состояние UI.

**Дата аудита**: 19 марта 2026
**Версия приложения**: 0.0.0 (pre-release)
**Аудитор**: Enterprise UX Architect
**Область**: `/Users/andreyafanasyev/Code/UK/frontend/`

---

## Executive Summary

UK Management -- enterprise B2B веб-приложение для управляющей компании жилых комплексов. Система охватывает управление заявками (Kanban), сотрудниками, сменами, шаблонами смен, адресами (дворы/здания/квартиры), аналитику и публичное информационное табло для жителей. Также присутствует отдельный TWA-интерфейс (Telegram Web App) для жителей.

### Общая оценка

| Критерий | Оценка (1-5) | Комментарий |
|---|---|---|
| Learnability (обучаемость) | 3 | Интуитивная навигация, но отсутствие onboarding и help |
| Efficiency (эффективность) | 3 | Нет горячих клавиш, нет batch-операций на многих экранах |
| Error prevention | 2 | Использование `window.confirm()` и `window.alert()`, нет undo |
| Consistency | 2 | Критическая проблема: смешение inline-стилей и Tailwind CSS |
| Accessibility | 1 | Практически отсутствует a11y поддержка |
| Scalability | 3 | Работает для малых датасетов, нет пагинации и виртуализации |
| Design system maturity | 2 | Есть CSS-переменные (дизайн-токены), но нет компонентной библиотеки |

### Ключевые находки

1. **CRITICAL**: Полное отсутствие accessibility (a11y) -- ни ARIA-атрибутов, ни keyboard navigation, ни focus management
2. **CRITICAL**: Смешение двух несовместимых подходов стилизации (inline styles + Tailwind CSS) -- приводит к визуальной несогласованности
3. **HIGH**: Отсутствие компонентной библиотеки -- каждый компонент определяет собственные стили заново
4. **HIGH**: Деструктивные действия (удаление) используют нативный `window.confirm()`, что разрушает UX enterprise-приложения
5. **HIGH**: Нет пагинации, виртуализации и поддержки больших наборов данных

---

## 1. Архитектура фронтенда

### 1.1 Технологический стек

| Технология | Назначение | Оценка |
|---|---|---|
| React 19 + TypeScript 5.9 | UI-фреймворк | Современный, адекватный выбор |
| Vite 7 | Сборка | Оптимальный выбор |
| React Router 7 | Маршрутизация | Адекватно |
| TanStack React Query 5 | Серверный стейт | Правильный выбор для enterprise |
| Zustand 5 | Клиентский стейт | Легковесно, но достаточно |
| Tailwind CSS 4 | Стилизация (частично) | Проблема: используется непоследовательно |
| Recharts 3 | Графики | Приемлемо |
| @dnd-kit | Drag & Drop | Хороший выбор для Kanban |
| lucide-react | Иконки | Хороший выбор |
| date-fns / date-fns-tz | Даты | Адекватно |

**Замечание**: Отсутствует UI-библиотека компонентов (Ant Design, Radix, shadcn/ui), что приводит к ручной реализации всех UI-элементов -- модальных окон, дропдаунов, тоглов, таблиц и т.д.

### 1.2 Структура проекта

```
src/
  api/client.ts          -- Axios с interceptors (refresh token)
  stores/authStore.ts    -- Zustand auth store с persist
  contexts/TopbarContext  -- Контекст для динамических действий в topbar
  hooks/                 -- Custom hooks (useKanban, useEmployees, useShifts...)
  types/api.ts           -- Централизованные TypeScript типы
  utils/                 -- Утилиты (employeeUtils, timezone, isTWA)
  layouts/DashboardLayout -- Sidebar + Topbar + Outlet
  pages/                 -- 10 страниц (включая 3 TWA)
  components/            -- Компоненты по доменам (kanban/, employees/, shifts/, addresses/)
  components/shared/     -- LoadingSpinner, EmptyState (всего 2 компонента)
```

**Проблемы структуры**:
- `components/shared/` содержит всего 2 компонента -- Button, Input, Modal, Select, Badge, Table и др. отсутствуют
- Нет директории `components/ui/` или `components/common/` для переиспользуемых элементов
- Стили хранятся inline в каждом компоненте вместо отдельных файлов или CSS Modules

### 1.3 Маршрутизация

**Файл**: `/Users/andreyafanasyev/Code/UK/frontend/src/App.tsx`

```
/login                    -- Страница входа
/dashboard                -- DashboardLayout (sidebar + topbar)
  /dashboard              -- KanbanPage (Заявки) -- index route
  /dashboard/analytics    -- AnalyticsPage (Дашборд)
  /dashboard/shifts       -- ShiftsPage (Смены)
  /dashboard/employees    -- EmployeesPage (Сотрудники)
  /dashboard/employees/:id -- EmployeeDetailPage
  /dashboard/templates    -- TemplatesPage (Шаблоны)
  /dashboard/addresses    -- AddressesPage (Адреса)
/resident-board           -- ResidentBoardPage (публичное табло, standalone)
/twa                      -- TWAHomePage (Telegram Web App)
/twa/create               -- TWACreatePage
/twa/requests/:number     -- TWARequestDetailPage
```

**Проблемы маршрутизации**:
- Навигация в sidebar имеет "Дашборд" (аналитика) как первый пункт, но index route (`/dashboard`) ведёт на Kanban, а не на аналитику. Это вводит в заблуждение
- Нет 404 страницы -- всё перенаправляется на `/`
- `/resident-board` вынесен за пределы `DashboardLayout` как standalone, что обосновано (публичный экран), но теряется sidebar-навигация при переходе

---

## 2. Анализ UI-компонентов и паттернов

### 2.1 Layout (DashboardLayout)

**Файл**: `/Users/andreyafanasyev/Code/UK/frontend/src/layouts/DashboardLayout.tsx`

**Структура**: Fixed sidebar (260px) + Fixed topbar (64px) + Content area

**Положительные стороны**:
- Компактный sidebar с иконками + текстом
- Группировка навигации ("Основное" / "Внешнее")
- Пользовательский блок с меню внизу sidebar
- Поддержка тёмной/светлой темы через toggle

**Проблемы**:

| # | Приоритет | Описание | Файл |
|---|---|---|---|
| L-1 | HIGH | Sidebar не адаптивен -- нет hamburger-меню для мобильных/планшетов. При ширине экрана < 1024px контент будет обрезаться | `DashboardLayout.tsx:82` |
| L-2 | MEDIUM | Topbar всегда показывает полупрозрачный тёмный фон (`rgba(10,15,24,0.8)`) даже в light theme -- визуальное несоответствие | `DashboardLayout.tsx:19` |
| L-3 | MEDIUM | Меню пользователя (Профиль/Выйти) не имеет keyboard navigation -- нельзя навигировать Tab/Enter | `DashboardLayout.tsx:209-252` |
| L-4 | LOW | Логотип "УК" использует hardcoded `color: '#000'` вместо CSS-переменной | `DashboardLayout.tsx:109` |
| L-5 | MEDIUM | Кнопка темы не имеет `aria-label`, screen reader не поймёт назначение | `DashboardLayout.tsx:32-44` |
| L-6 | LOW | Иконки из emoji (👤 и →) в меню пользователя вместо lucide-react -- стилистическое несоответствие | `DashboardLayout.tsx:234,249` |

### 2.2 Kanban Board (Управление заявками)

**Файлы**:
- `/Users/andreyafanasyev/Code/UK/frontend/src/pages/KanbanPage.tsx`
- `/Users/andreyafanasyev/Code/UK/frontend/src/components/kanban/KanbanBoard.tsx`
- `/Users/andreyafanasyev/Code/UK/frontend/src/components/kanban/KanbanColumn.tsx`
- `/Users/andreyafanasyev/Code/UK/frontend/src/components/kanban/RequestCard.tsx`
- `/Users/andreyafanasyev/Code/UK/frontend/src/components/kanban/RequestDetailModal.tsx`
- `/Users/andreyafanasyev/Code/UK/frontend/src/components/kanban/TransitionModal.tsx`

**Положительные стороны**:
- Drag & drop с валидацией переходов (VALID_TRANSITIONS) -- отличный паттерн
- Визуальная индикация при drag: зелёная граница для валидных, красная для невалидных целей
- Optimistic updates при перемещении карточек
- WebSocket-обновления в реальном времени
- "Замороженные" колонки (Принято/Отменена) -- нельзя перетаскивать

**Проблемы**:

| # | Приоритет | Описание | Файл |
|---|---|---|---|
| K-1 | HIGH | Нет фильтров на Kanban-доске -- нельзя фильтровать по категории, срочности, исполнителю | `KanbanPage.tsx` |
| K-2 | HIGH | Нет поиска заявок -- при большом количестве карточек невозможно найти нужную | `KanbanPage.tsx` |
| K-3 | HIGH | Колонки имеют `maxWidth: 260` -- при 8 колонках горизонтальная прокрутка неизбежна, но нет визуальных индикаторов overflow | `KanbanColumn.tsx:39` |
| K-4 | MEDIUM | RequestDetailModal не имеет Escape-клавиши для закрытия | `RequestDetailModal.tsx` |
| K-5 | MEDIUM | TransitionModal использует Tailwind CSS (`className`), а RequestDetailModal использует inline styles -- несогласованность | `TransitionModal.tsx` vs `RequestDetailModal.tsx` |
| K-6 | MEDIUM | Нет индикатора количества скрытых карточек в колонке -- если заявок 50, все рендерятся без виртуализации | `KanbanColumn.tsx` |
| K-7 | LOW | При клике на карточку нет визуального отличия клика от начала drag -- используется distance threshold (8px), что может быть неочевидно | `RequestCard.tsx:52-63` |
| K-8 | MEDIUM | Кнопка "Создать по звонку" в topbar доступна только на Kanban-странице, но может быть нужна с других страниц | `KanbanPage.tsx:14-35` |

### 2.3 Call Center Modal

**Файл**: `/Users/andreyafanasyev/Code/UK/frontend/src/components/callcenter/CallCenterModal.tsx`

**CRITICAL ISSUE (K-9)**: Этот модал полностью написан на Tailwind CSS (`className`), тогда как все остальные компоненты используют inline styles. Результат:
- В тёмной теме модал отображается с белым фоном (`bg-white`), белым текстом -- нечитаемо
- Цвета жёстко закодированы (`text-gray-400`, `border-blue-500`), не реагируют на переключение темы
- Визуально выглядит как элемент из другого приложения

### 2.4 Страница сотрудников

**Файлы**:
- `/Users/andreyafanasyev/Code/UK/frontend/src/pages/EmployeesPage.tsx`
- `/Users/andreyafanasyev/Code/UK/frontend/src/components/employees/StaffCard.tsx`
- `/Users/andreyafanasyev/Code/UK/frontend/src/components/employees/StaffTable.tsx`

**Положительные стороны**:
- Два режима отображения (плитки/таблица) с сохранением в localStorage
- Секция "Ожидают одобрения" с inline-действиями
- KPI-карточки сверху для быстрого обзора
- Три группы фильтров (роль, статус, специализация)

**Проблемы**:

| # | Приоритет | Описание | Файл |
|---|---|---|---|
| E-1 | HIGH | Деструктивные действия (блокировка сотрудника) используют `window.confirm()` -- нативный диалог, не стилизуемый, не поддерживает тему | `EmployeesPage.tsx:332-339` |
| E-2 | HIGH | StaffTable использует CSS Grid вместо `<table>` -- проблемы с a11y (screen readers не распознают как таблицу) | `StaffTable.tsx:46-67` |
| E-3 | MEDIUM | Нет пагинации -- при 100+ сотрудниках все рендерятся одновременно | `EmployeesPage.tsx` |
| E-4 | MEDIUM | Кнопки "Экспорт" и "+ Добавить" объявлены, но не функциональны | `EmployeesPage.tsx:117-118` |
| E-5 | MEDIUM | StaffCard имеет hover-эффект `translateY(-2px)` -- декоративная анимация, замедляющая взаимодействие в enterprise-контексте | `StaffCard.tsx:34` |
| E-6 | LOW | Кнопка "Блок" -- слишком сокращённая метка, непонятно без контекста | `StaffCard.tsx:259` |

### 2.5 Детальная страница сотрудника

**Файл**: `/Users/andreyafanasyev/Code/UK/frontend/src/pages/EmployeeDetailPage.tsx`

**Проблемы**:

| # | Приоритет | Описание | Файл |
|---|---|---|---|
| ED-1 | MEDIUM | Кнопка "Назад" (`navigate(-1)`) ненадёжна -- если пользователь пришёл по прямой ссылке, `-1` вернёт на внешний сайт | `EmployeeDetailPage.tsx:29` |
| ED-2 | MEDIUM | Страница ограничена `maxWidth: 720` -- много неиспользуемого пространства на широких мониторах | `EmployeeDetailPage.tsx:26` |
| ED-3 | LOW | Нет возможности редактировать данные сотрудника с этой страницы | `EmployeeDetailPage.tsx` |
| ED-4 | LOW | Нет истории смен и заявок сотрудника -- только текущая смена | `EmployeeDetailPage.tsx` |

### 2.6 Страница смен

**Файлы**:
- `/Users/andreyafanasyev/Code/UK/frontend/src/pages/ShiftsPage.tsx`
- `/Users/andreyafanasyev/Code/UK/frontend/src/components/shifts/ShiftTimeline.tsx`
- `/Users/andreyafanasyev/Code/UK/frontend/src/components/shifts/ShiftCoverageHeatmap.tsx`

**Положительные стороны**:
- Timeline (таймлайн) смен с 24-часовой сеткой -- отличная визуализация для диспетчеров
- Индикатор текущего часа
- Навигация по дням (вперёд/назад/сегодня)
- KPI-карточки с покрытием и нагрузкой
- WebSocket для real-time обновлений
- Тепловая карта покрытия

**Проблемы**:

| # | Приоритет | Описание | Файл |
|---|---|---|---|
| S-1 | MEDIUM | Нет возможности выбрать дату из календаря (datepicker) -- только пошаговая навигация вперёд/назад | `ShiftsPage.tsx:163-195` |
| S-2 | MEDIUM | Timeline использует минимальную ширину 1200px, но нет sticky-элементов для ориентации | `ShiftTimeline.tsx:144` |
| S-3 | LOW | Показаны только 3 первых запроса на передачу из списка, нет "Показать все" | `ShiftsPage.tsx:357` |

### 2.7 Страница шаблонов

**Файл**: `/Users/andreyafanasyev/Code/UK/frontend/src/pages/TemplatesPage.tsx`

**Проблемы**:

| # | Приоритет | Описание | Файл |
|---|---|---|---|
| T-1 | HIGH | Кнопка "Ред." вызывает `window.alert('Редактирование в разработке')` -- stub-функция в production-коде | `TemplatesPage.tsx:616` |
| T-2 | MEDIUM | Кнопка "Удал." -- чрезмерно сокращённая метка | `TemplatesPage.tsx:87` |
| T-3 | MEDIUM | Toggle автосоздания реализован как `div` с `onClick`, не как `<input type="checkbox">` или `<button role="switch">` -- нет keyboard accessibility | `TemplatesPage.tsx:558-589` |
| T-4 | LOW | Таблица использует `<table>` (правильно), но заголовок `font-size: 0.65rem` (10.4px) -- слишком мелкий | `TemplatesPage.tsx:184` |

### 2.8 Страница адресов

**Файл**: `/Users/andreyafanasyev/Code/UK/frontend/src/pages/AddressesPage.tsx` (самый большой файл -- 942 строки)

**Положительные стороны**:
- Иерархическая навигация (Дворы -> Здания -> Квартиры) с breadcrumb
- Два режима просмотра (плитки/таблица)
- Inline-действия (редактировать, деактивировать, удалить)
- Модерация как отдельная вкладка
- Функция "Автозаполнение" для массового создания квартир
- Профиль квартиры в модальном окне

**Проблемы**:

| # | Приоритет | Описание | Файл |
|---|---|---|---|
| A-1 | HIGH | Файл содержит 942 строки -- нарушает принцип Single Responsibility. Внутренние компоненты `ActionMenu`, `MenuItem` должны быть вынесены | `AddressesPage.tsx` |
| A-2 | MEDIUM | Удаление через `window.confirm()` -- повторяющаяся проблема | `AddressesPage.tsx:576-579` |
| A-3 | MEDIUM | Breadcrumb реализован как `<span>` с `onClick` -- не семантичный HTML | `AddressesPage.tsx:477-511` |
| A-4 | MEDIUM | При переключении на view=moderation, breadcrumb и view toggle скрываются, но логика сложна | `AddressesPage.tsx:466-468` |

### 2.9 Аналитика (Dashboard)

**Файл**: `/Users/andreyafanasyev/Code/UK/frontend/src/pages/AnalyticsPage.tsx`

**Положительные стороны**:
- KPI-карточки с цветовой кодировкой
- Bar chart (заявки по дням) и Pie chart (по категориям) -- адекватный выбор визуализаций
- Progress bars для статусов заявок
- Таблица лидеров исполнителей
- Лента последних действий
- Выбор периода (7/30/90 дней)

**Проблемы**:

| # | Приоритет | Описание | Файл |
|---|---|---|---|
| AN-1 | MEDIUM | Часы отображают время в зоне Asia/Tashkent hardcoded -- нет настройки часового пояса пользователя | `AnalyticsPage.tsx:256-264` |
| AN-2 | LOW | KPI "change" всегда показывает "---" -- placeholder, который забыли убрать | `AnalyticsPage.tsx:389-406` |
| AN-3 | LOW | Hover-эффект `translateY(-2px)` на KPI-карточках -- избыточная анимация для dashboard | `AnalyticsPage.tsx:122` |

### 2.10 Resident Board (Информационное табло)

**Файл**: `/Users/andreyafanasyev/Code/UK/frontend/src/pages/ResidentBoardPage.tsx`

Отдельный standalone-экран для отображения на мониторе в подъезде/холле.

**Положительные стороны**:
- Ticker с бегущей строкой
- Часы реального времени
- Визуализация pipeline заявок
- Расписание работы с подсветкой текущего дня
- Объявления
- Автообновление через WebSocket

**Проблемы**:

| # | Приоритет | Описание | Файл |
|---|---|---|---|
| RB-1 | HIGH | Используется свой собственный шрифт (Nunito/Sora), загружаемый через Google Fonts inline в `<style>` -- блокирует рендер, нет preload | `ResidentBoardPage.tsx:99-100` |
| RB-2 | HIGH | Жёстко закодированные данные объявлений (ANNOUNCEMENTS array) -- не загружаются с сервера | `ResidentBoardPage.tsx:51-55` |
| RB-3 | MEDIUM | Стиль полностью отличается от основного приложения -- hardcoded цвета (`#1a6b52`, `#f7f5f0`) вместо CSS-переменных | `ResidentBoardPage.tsx:97` |
| RB-4 | LOW | Использует `@import url(...)` в `<style>` вместо `<link>` в `<head>` -- ухудшает производительность | `ResidentBoardPage.tsx:100` |

### 2.11 TWA (Telegram Web App)

**Файлы**:
- `/Users/andreyafanasyev/Code/UK/frontend/src/pages/twa/TWAHomePage.tsx`
- `/Users/andreyafanasyev/Code/UK/frontend/src/pages/twa/TWACreatePage.tsx`
- `/Users/andreyafanasyev/Code/UK/frontend/src/pages/twa/TWARequestDetailPage.tsx`

TWA-страницы полностью используют Tailwind CSS -- визуально несовместимы с основным приложением (это ожидаемо, т.к. они предназначены для мобильного Telegram).

**Проблема**: TWA-маршруты (`/twa/*`) не защищены `ProtectedRoute`, хотя делают API-запросы. Аутентификация выполняется через `useTWAAuth()` hook, что корректно для Telegram, но важно понимать разницу в security model.

---

## 3. Информационная архитектура и навигация

### 3.1 Навигационная структура

**Sidebar навигация** (`DashboardLayout.tsx:52-59`):

```
Основное:
  1. Дашборд (LayoutGrid)     -> /dashboard/analytics
  2. Заявки (ListChecks)       -> /dashboard (index)
  3. Сотрудники (Users)        -> /dashboard/employees
  4. Смены (Clock)             -> /dashboard/shifts
  5. Шаблоны (Table2)          -> /dashboard/templates
  6. Адреса (MapPin)           -> /dashboard/addresses

Внешнее:
  7. Табло жителей (BookOpen)  -> /resident-board
```

**Проблемы информационной архитектуры**:

| # | Приоритет | Описание |
|---|---|---|
| IA-1 | HIGH | **Противоречие "Дашборд" vs default route**: пункт "Дашборд" ведёт на аналитику, но root URL `/dashboard` показывает Kanban (Заявки). Пользователь, нажимающий "Дашборд", ожидает увидеть то, что открывается по умолчанию |
| IA-2 | MEDIUM | **Шаблоны** -- подраздел смен, но вынесен как отдельный пункт навигации верхнего уровня. Лучше вложить в "Смены" или использовать вкладки на странице смен |
| IA-3 | MEDIUM | **Отсутствуют**: Настройки, Уведомления, Помощь/Документация -- стандартные разделы enterprise-приложения |
| IA-4 | LOW | **Нет badge-индикаторов** в навигации (количество новых заявок, ожидающих одобрения сотрудников, pending модерации) |
| IA-5 | LOW | **"Табло жителей"** в основной навигации может путать -- это публичный экран, не часть рабочего инструмента менеджера |

### 3.2 Topbar Context Pattern

Приложение использует интересный паттерн `TopbarProvider/useTopbar()` для динамического размещения действий (кнопок, поиска) в topbar, зависящих от текущей страницы.

**Оценка**: Паттерн работает, но имеет ограничения:
- Действия не типизированы (принимают `ReactNode`)
- Нет стандартизации расположения (каждая страница решает сама)
- При переключении страниц бывает мерцание (clearing + setting)

---

## 4. Дизайн-система

### 4.1 Design Tokens (CSS Variables)

**Файл**: `/Users/andreyafanasyev/Code/UK/frontend/src/index.css`

Определены CSS-переменные для:
- Цвета фона: `--bg-root`, `--bg-primary`, `--bg-secondary`, `--bg-card`, `--bg-surface`, `--bg-sidebar`
- Акцентные цвета: `--accent`, `--blue`, `--violet`, `--amber`, `--cyan`, `--emerald`, `--green`, `--teal`, `--red`
- Текст: `--text-primary`, `--text-secondary`, `--text-muted`
- Границы: `--border`, `--border-active`
- Радиусы: `--radius` (12px), `--radius-sm` (8px)
- Шрифты: `--font-display` (Outfit), `--font-body` (DM Sans), `--font-mono` (IBM Plex Mono)
- Размеры: `--sidebar-w` (260px), `--topbar-h` (64px)

Также определена светлая тема (`body.light`) с переопределением фоновых и текстовых переменных.

**Положительные стороны**:
- Чёткая система токенов
- Поддержка темной/светлой темы
- Три типа шрифтов (display, body, mono) -- хорошая типографическая система

**Проблемы**:

| # | Приоритет | Описание |
|---|---|---|
| DS-1 | CRITICAL | **Смешение стилей**: CallCenterModal и TransitionModal используют Tailwind CSS классы, остальное -- inline styles. Это вызывает несовместимость с темной темой (модалы остаются белыми) |
| DS-2 | HIGH | **Нет компонентной библиотеки**: кнопки, инпуты, модалы, таблицы, чипы, бейджи определяются ad-hoc в каждом компоненте. Каждая страница определяет собственный `primaryBtnStyle`, `secondaryBtnStyle`, `inputStyle` и т.д. |
| DS-3 | HIGH | **Нет spacing scale**: padding/margin задаются произвольно (10px, 12px, 14px, 16px, 20px, 24px, 28px, 32px) без единой шкалы |
| DS-4 | MEDIUM | **Шрифты не загружаются**: в `index.css` определены `Outfit`, `DM Sans`, `IBM Plex Mono`, но нет `@import` или `<link>` для их загрузки. Работает только если Tailwind подтягивает их |
| DS-5 | MEDIUM | **Hardcoded цвета**: в нескольких компонентах используются цвета напрямую (`#000`, `#001a14`, `#f87171`, `rgba(239,68,68,0.12)`) вместо CSS-переменных |

### 4.2 Повторяющиеся паттерны, которые должны быть компонентами

По результатам анализа кода, следующие UI-элементы реализованы повторно (copy-paste) и должны быть вынесены в shared-компоненты:

1. **Button** -- минимум 5 вариантов стилей определяются inline в разных файлах:
   - `primaryBtnStyle` в `EmployeesPage.tsx`, `AddressesPage.tsx`, `TemplatesPage.tsx`
   - `secondaryBtnStyle` в `EmployeesPage.tsx`
   - `navBtnStyle` в `ShiftsPage.tsx`
   - Произвольные inline-стили в `RequestDetailModal.tsx`

2. **Modal** -- реализован 6+ раз с разными стилями:
   - `CallCenterModal` (Tailwind)
   - `TransitionModal` (Tailwind)
   - `RequestDetailModal` (inline styles)
   - `CreateShiftModal` (?)
   - `ApartmentFormModal`, `BuildingFormModal`, `YardFormModal`

3. **Badge/Chip** -- `chipStyle()` в EmployeesPage, `badgeStyle()` в AddressesPage, inline бейджи в RequestCard, StaffCard

4. **Table** -- 3 разные реализации:
   - `<table>` в TemplatesPage
   - CSS Grid в StaffTable
   - CSS Grid в AddressTable

5. **Stats Card** -- реализован 4 раза с немного разным дизайном:
   - `EmployeesPage.tsx` (с иконками-emoji)
   - `ShiftsPage.tsx` (с цветной полоской снизу)
   - `AnalyticsPage.tsx` (KpiCard с hover-эффектом)
   - `AddressesPage.tsx` (кликабельные)

6. **Toggle/Switch** -- кастомный div в `TemplatesPage.tsx:558-589`, не переиспользуемый

7. **Action Menu (dropdown)** -- `ActionMenu` в `AddressesPage.tsx`, user menu в `DashboardLayout.tsx` -- разные реализации

---

## 5. Юзабилити-проблемы (сводная таблица)

### 5.1 Critical

| ID | Проблема | Где | Воздействие |
|---|---|---|---|
| C-1 | CallCenterModal и TransitionModal используют Tailwind CSS, не реагируют на тёмную тему -- белый фон, нечитаемый текст | `CallCenterModal.tsx`, `TransitionModal.tsx` | Невозможно использовать в тёмной теме |
| C-2 | Полное отсутствие accessibility: нет ARIA, нет focus management, нет keyboard navigation | Все компоненты | Приложение непригодно для пользователей с ограничениями |
| C-3 | Нет роутинг-гарда для ролей -- любой аутентифицированный пользователь видит все разделы | `App.tsx:32-36` | Потенциальная security/UX проблема |

### 5.2 High

| ID | Проблема | Где | Воздействие |
|---|---|---|---|
| H-1 | `window.confirm()` для деструктивных действий (удаление, блокировка) | 7+ мест в коде | Разрушает UX, не стилизуется, нет undo |
| H-2 | `window.alert()` для незавершённой функциональности | `TemplatesPage.tsx:616` | Непрофессионально для production |
| H-3 | Нет пагинации/виртуализации для списков | Employees, Kanban, Addresses | При 1000+ записей интерфейс зависнет |
| H-4 | Нет обработки offline-состояния | Все страницы | Пользователь не знает о потере соединения |
| H-5 | Нет breadcrumbs / заголовков страниц в topbar | Все страницы | Пользователь теряет контекст "где я?" |
| H-6 | Нет системы уведомлений (toast/snackbar) | Все страницы | Пользователь не видит результат действий (успех/ошибка) |
| H-7 | Отсутствие горячих клавиш | Все страницы | Снижает продуктивность опытных пользователей |

### 5.3 Medium

| ID | Проблема | Где | Воздействие |
|---|---|---|---|
| M-1 | Нет сброса фильтров одной кнопкой | EmployeesPage | Неудобно при активных фильтрах |
| M-2 | Нет индикатора активных фильтров (счётчик) | EmployeesPage | Пользователь забывает о фильтрах |
| M-3 | Нет confirmation при выходе из формы с несохранёнными данными | CreateShiftModal, все FormModals | Потеря данных при случайном закрытии |
| M-4 | Нет debounce на поиск | EmployeesPage, AddressesPage | Лишние API-запросы при вводе |
| M-5 | Sidebar не показывает текущую секцию при вложенной навигации | DashboardLayout | При переходе на /employees/:id sidebar теряет активный пункт |
| M-6 | Формат даты в модалях использует `toLocaleString('ru')` -- зависит от настроек ОС | RequestDetailModal | Непредсказуемый формат |
| M-7 | Нет drag handle на карточках Kanban -- вся карточка является drag target | RequestCard | Конфликт с кликом на карточку |

### 5.4 Low

| ID | Проблема | Где | Воздействие |
|---|---|---|---|
| L-7 | Emoji используются как иконки (👥, ⏳, ✓, 📋) -- не масштабируются, разный рендер на разных ОС | Многие компоненты | Визуальная несогласованность |
| L-8 | Нет favicon и page title для разных разделов | App.tsx | SEO, юзабилити (множество вкладок) |
| L-9 | Нет анимации при переходе между страницами | App.tsx | Резкие переходы |
| L-10 | Кнопка "Профиль" в StaffCard не имеет стилей кнопки -- выглядит как текст | StaffCard.tsx:196-207 | Неочевидно, что это действие |

---

## 6. Accessibility (a11y)

### 6.1 Текущее состояние: КРИТИЧЕСКОЕ

Приложение **не соответствует** ни одному уровню WCAG 2.1. Ключевые нарушения:

#### 6.1.1 Perceivable (Воспринимаемость)

| WCAG | Описание | Статус |
|---|---|---|
| 1.1.1 Non-text Content | Emoji используются как иконки без `aria-label` | FAIL |
| 1.3.1 Info and Relationships | Таблицы сотрудников/адресов реализованы как CSS Grid `<div>`, не `<table>` -- screen reader не может определить структуру | FAIL |
| 1.4.1 Use of Color | Статусы сотрудников отличаются только цветом (зелёный/серый dot), нет текстовых подписей в некоторых местах | PARTIAL FAIL |
| 1.4.3 Contrast | CSS-переменные `--text-muted: #5a6a7a` на `--bg-root: #060a10` -- контраст 3.7:1, ниже требуемого 4.5:1 | FAIL |
| 1.4.11 Non-text Contrast | Границы элементов (`--border: rgba(255,255,255,0.06)`) практически невидимы -- контраст 1.1:1 | FAIL |

#### 6.1.2 Operable (Управляемость)

| WCAG | Описание | Статус |
|---|---|---|
| 2.1.1 Keyboard | Модальные окна не trap-ят фокус, нет Escape для закрытия, dropdown-меню не навигируемы с клавиатуры | FAIL |
| 2.1.2 No Keyboard Trap | Не тестируемо (фокус нигде не управляется) | FAIL |
| 2.4.1 Bypass Blocks | Нет skip-navigation link | FAIL |
| 2.4.3 Focus Order | Нет управления focus order | FAIL |
| 2.4.7 Focus Visible | Нет кастомных :focus-visible стилей, `outline: none` явно задан на инпутах | FAIL |

#### 6.1.3 Understandable (Понятность)

| WCAG | Описание | Статус |
|---|---|---|
| 3.1.1 Language | `<html lang="...">` не установлен в `index.html` (скорее всего) | LIKELY FAIL |
| 3.2.2 On Input | Некоторые select-элементы изменяют фильтры немедленно без кнопки "Применить" -- допустимо, но требует внимания | PASS |
| 3.3.1 Error Identification | Ошибки форм показываются inline -- это правильно | PARTIAL PASS |
| 3.3.2 Labels | Некоторые input-элементы имеют `<label>`, но не связаны через `htmlFor`/`id` | FAIL |

#### 6.1.4 Robust (Устойчивость)

| WCAG | Описание | Статус |
|---|---|---|
| 4.1.2 Name, Role, Value | Custom toggle switches не имеют `role="switch"`, dropdown-меню не имеют `role="menu"`, модалы не имеют `role="dialog"` | FAIL |

### 6.2 Приоритетные исправления a11y

1. Добавить `role="dialog"`, `aria-modal="true"`, `aria-labelledby` ко всем модальным окнам
2. Реализовать focus trap в модальных окнах
3. Добавить `aria-label` к иконочным кнопкам (тема, навигация, закрытие)
4. Заменить CSS Grid `<div>` таблицы на семантические `<table>` или добавить ARIA table roles
5. Добавить `:focus-visible` стили вместо `outline: none`
6. Добавить `lang="ru"` к `<html>`
7. Связать `<label>` с `<input>` через `htmlFor`/`id`

---

## 7. Рекомендации по улучшению

### 7.1 Архитектурные

#### R-1: Внедрить UI-библиотеку компонентов [CRITICAL]

Рекомендуемый подход: **shadcn/ui** (уже совместим со стеком: React, Tailwind, CVA, clsx, tailwind-merge -- все зависимости присутствуют в `package.json`).

Минимальный набор компонентов для создания:
- `Button` (primary, secondary, ghost, danger variants)
- `Modal/Dialog` (с focus trap, Escape, overlay click)
- `ConfirmDialog` (замена `window.confirm`)
- `Input`, `Textarea`, `Select`
- `Table` (с сортировкой, пагинацией)
- `Badge/Chip`
- `Toast/Notification`
- `Dropdown/Menu`
- `Toggle/Switch`
- `Card`
- `Breadcrumb`
- `Tabs`
- `Tooltip`

#### R-2: Унифицировать стилевой подход [CRITICAL]

Выбрать **один** подход и мигрировать:
- **Рекомендация**: Tailwind CSS + CSS variables для темизации
- Удалить все inline `style={{}}` объекты
- Мигрировать CallCenterModal и TransitionModal на CSS variables для поддержки тем

#### R-3: Добавить Error Boundary [HIGH]

Ни один компонент не обёрнут в React Error Boundary. Необработанная ошибка в любом компоненте обрушит всё приложение.

#### R-4: Добавить роутинг-гард по ролям [HIGH]

Текущий `ProtectedRoute` проверяет только `isAuthenticated`. Необходимо добавить проверку ролей для ограничения доступа к разделам.

### 7.2 UX-паттерны

#### R-5: Заменить `window.confirm()` на кастомный ConfirmDialog [HIGH]

```
Текущее: window.confirm("Удалить двор?")
Целевое: <ConfirmDialog
           title="Удаление двора"
           message={`Вы уверены, что хотите удалить двор "${name}"? Это действие нельзя отменить.`}
           confirmLabel="Удалить"
           variant="danger"
           onConfirm={...}
         />
```

#### R-6: Добавить систему уведомлений (Toast) [HIGH]

Для всех мутаций (создание, обновление, удаление) показывать toast-уведомление с результатом. Рекомендация: react-hot-toast или sonner.

#### R-7: Добавить пагинацию [HIGH]

Для всех списочных экранов:
- Employees: server-side pagination с offset/limit
- Addresses (yards, buildings, apartments): client-side pagination или virtual scroll
- Kanban: lazy loading при скролле внутри колонки

#### R-8: Добавить горячие клавиши [MEDIUM]

Минимальный набор:
- `Ctrl+K` / `Cmd+K` -- глобальный поиск (Command Palette)
- `N` -- создать новую заявку (на Kanban-странице)
- `Escape` -- закрыть модал/вернуться
- `?` -- показать список горячих клавиш

#### R-9: Добавить заголовки страниц и breadcrumbs [MEDIUM]

В topbar должны отображаться:
- Название текущего раздела
- Breadcrumb (для вложенных страниц: Сотрудники > Иванов)
- `document.title` должен обновляться для каждой страницы

#### R-10: Sidebar -- responsive design [MEDIUM]

- На ширине < 1200px: sidebar collapsible (только иконки)
- На ширине < 768px: sidebar скрыт, hamburger-кнопка в topbar
- На мобильных: sidebar как overlay с backdrop

### 7.3 Performance

#### R-11: Виртуализация списков [MEDIUM]

Для Kanban-колонок с 50+ карточками и таблиц с 100+ строками. Рекомендация: `@tanstack/react-virtual`.

#### R-12: Мемоизация тяжёлых компонентов [LOW]

`KanbanColumn`, `RequestCard`, `StaffCard`, `TemplateRow` должны быть обёрнуты в `React.memo()` для предотвращения лишних ре-рендеров.

### 7.4 Конкретные фиксы

#### R-13: Исправить навигационную архитектуру [HIGH]

- Переименовать "Дашборд" в "Аналитика" в sidebar
- Или сделать аналитику default route (`/dashboard` -> AnalyticsPage)
- Добавить badge-счётчики к навигации (кол-во новых заявок, pending сотрудников)

#### R-14: Убрать `window.alert()` стабы [HIGH]

`TemplatesPage.tsx:616` -- заменить на `<Tooltip>` "В разработке" или disabled-кнопку.

#### R-15: Исправить `navigate(-1)` [MEDIUM]

Заменить на `navigate('/dashboard/employees')` или проверять наличие истории:
```ts
const canGoBack = window.history.length > 1
```

---

## 8. Roadmap улучшений

### Phase 1: Foundation (1-2 недели) -- Critical fixes

| Задача | Приоритет | Estimated effort |
|---|---|---|
| Создать базовые shared-компоненты (Button, Modal, ConfirmDialog, Input) | CRITICAL | 3 дня |
| Мигрировать CallCenterModal и TransitionModal на CSS variables | CRITICAL | 1 день |
| Убрать `window.confirm()` -- заменить на ConfirmDialog | CRITICAL | 1 день |
| Убрать `window.alert()` стабы | CRITICAL | 0.5 дня |
| Добавить Toast-систему (react-hot-toast) | HIGH | 0.5 дня |
| Добавить Error Boundary | HIGH | 0.5 дня |

### Phase 2: Core UX (2-3 недели) -- High priority

| Задача | Приоритет | Estimated effort |
|---|---|---|
| Responsive sidebar (collapsible) | HIGH | 2 дня |
| Пагинация для таблиц (Employees, Addresses) | HIGH | 2 дня |
| Фильтры и поиск на Kanban-доске | HIGH | 2 дня |
| Заголовки страниц + breadcrumbs в topbar | HIGH | 1 день |
| Роутинг-гард по ролям | HIGH | 1 день |
| Исправление навигационной архитектуры (Дашборд vs Аналитика) | HIGH | 0.5 дня |
| Keyboard navigation в модальных окнах (focus trap, Escape) | HIGH | 2 дня |
| Badge-счётчики в sidebar навигации | MEDIUM | 1 день |

### Phase 3: Accessibility (2-3 недели) -- Compliance

| Задача | Приоритет | Estimated effort |
|---|---|---|
| ARIA-роли для модалов, меню, switch-элементов | HIGH | 3 дня |
| Focus-visible стили | HIGH | 1 день |
| Семантические таблицы (заменить Grid div на table) | MEDIUM | 2 дня |
| Контраст: обновить --text-muted и --border | MEDIUM | 1 день |
| lang="ru", label/htmlFor связки, skip-navigation | MEDIUM | 1 день |
| Тестирование с VoiceOver/NVDA | MEDIUM | 2 дня |

### Phase 4: Polish & Performance (2-3 недели) -- Enhancement

| Задача | Приоритет | Estimated effort |
|---|---|---|
| Command Palette (Ctrl+K) | MEDIUM | 2 дня |
| Горячие клавиши | MEDIUM | 1 день |
| Виртуализация длинных списков | MEDIUM | 2 дня |
| Отзывчивый дизайн для планшетов | MEDIUM | 3 дня |
| Datepicker для страницы смен | MEDIUM | 1 день |
| Offline-индикатор | MEDIUM | 0.5 дня |
| Page transitions (анимация) | LOW | 1 день |
| Dark/light theme persistence + system preference detection | LOW | 0.5 дня |

### Phase 5: Design System Maturity (ongoing)

| Задача | Приоритет | Estimated effort |
|---|---|---|
| Документация компонентов (Storybook) | MEDIUM | 3 дня |
| Spacing scale и типографическая шкала | MEDIUM | 1 день |
| Унифицировать все inline styles в Tailwind utility classes | MEDIUM | 5 дней (incremental) |
| Иконки: заменить все emoji на lucide-react | LOW | 2 дня |
| ResidentBoard: вынести шрифты в head, загружать объявления с сервера | LOW | 1 день |

---

## Приложение A: Файловая карта компонентов

```
src/
  App.tsx                                    -- Routing, ProtectedRoute
  main.tsx                                   -- Entry point
  index.css                                  -- Design tokens (CSS vars), Tailwind import

  api/
    client.ts                                -- Axios instance + refresh interceptor

  stores/
    authStore.ts                             -- Zustand auth (user, login, logout)

  contexts/
    TopbarContext.tsx                         -- Dynamic topbar actions

  hooks/
    useKanban.ts                             -- Kanban data + WebSocket
    useEmployees.ts                          -- Employee CRUD + mutations
    useShifts.ts                             -- Shift schedule, stats, transfers
    useTemplates.ts                          -- Shift templates CRUD
    useAddresses.ts                          -- Yards, Buildings, Apartments CRUD
    useAnalytics.ts                          -- Analytics data fetching
    useWebSocket.ts                          -- WebSocket connection management
    useTheme.ts                              -- Dark/Light theme toggle
    useTWAAuth.ts                            -- Telegram WebApp auth

  types/
    api.ts                                   -- All API response types (single source of truth)

  utils/
    employeeUtils.ts                         -- Avatar gradients, specialization maps
    timezone.ts                              -- Tashkent timezone formatting
    isTWA.ts                                 -- TWA detection

  layouts/
    DashboardLayout.tsx                      -- Sidebar + Topbar + Outlet

  pages/
    LoginPage.tsx                            -- Email/password + Telegram widget login
    KanbanPage.tsx                           -- Kanban board wrapper
    EmployeesPage.tsx                        -- Employee list (card/table views)
    EmployeeDetailPage.tsx                   -- Single employee profile
    ShiftsPage.tsx                           -- Shift schedule + timeline
    TemplatesPage.tsx                        -- Shift template management
    AddressesPage.tsx                        -- Yards/Buildings/Apartments directory
    AnalyticsPage.tsx                        -- Dashboard with charts
    ResidentBoardPage.tsx                    -- Public display board
    twa/TWAHomePage.tsx                      -- Telegram: request list
    twa/TWACreatePage.tsx                    -- Telegram: create request
    twa/TWARequestDetailPage.tsx             -- Telegram: request detail

  components/
    shared/
      LoadingSpinner.tsx                     -- Full-page spinner
      EmptyState.tsx                         -- Empty state placeholder
    kanban/
      KanbanBoard.tsx                        -- DnD context + columns + transition logic
      KanbanColumn.tsx                       -- Droppable column
      RequestCard.tsx                        -- Draggable request card
      RequestDetailModal.tsx                 -- Request detail + actions
      TransitionModal.tsx                    -- Status transition form (Tailwind!)
    callcenter/
      CallCenterModal.tsx                    -- Create request by phone (Tailwind!)
    employees/
      StaffCard.tsx                          -- Employee tile card
      StaffTable.tsx                         -- Employee table row (CSS Grid)
      PendingApprovalCard.tsx                -- Pending verification card
      AssignRequestModal.tsx                 -- Assign request to employee
    shifts/
      ShiftTimeline.tsx                      -- 24h Gantt-style timeline
      ShiftCoverageHeatmap.tsx               -- Coverage visualization
      CreateShiftModal.tsx                   -- Create new shift
      ShiftDetailModal.tsx                   -- Shift details
    templates/
      CreateTemplateModal.tsx                -- Create shift template
    addresses/
      YardFormModal.tsx                      -- Create/edit yard
      BuildingFormModal.tsx                  -- Create/edit building
      ApartmentFormModal.tsx                 -- Create/edit apartment
      BulkCreateModal.tsx                    -- Bulk apartment creation
      ModerationPanel.tsx                    -- Resident moderation
      ApartmentProfileModal.tsx              -- Apartment detail with residents
      AddressTable.tsx                       -- Table view for all address levels
```

---

## Приложение B: Сравнение с enterprise-стандартами

| Критерий | SAP Fiori / IBM Carbon стандарт | Текущее состояние UK Management |
|---|---|---|
| Компонентная библиотека | Полная библиотека 50+ компонентов | 2 shared-компонента |
| Accessibility | WCAG 2.1 AA обязательно | Практически отсутствует |
| Responsive design | Mobile-first или adaptive | Desktop-only |
| Keyboard navigation | Все действия доступны с клавиатуры | Отсутствует |
| Internationalization | Готовность к i18n | Hardcoded русский |
| Error handling | Structured error pages, retry | `window.alert()`, basic error states |
| Loading states | Skeleton screens, progressive | Single spinner |
| Empty states | Contextual with CTA | Generic icon + text |
| Batch operations | Multi-select + bulk actions | Отсутствует (кроме BulkCreate) |
| Undo/Redo | Undo для деструктивных действий | Отсутствует |
| Audit trail | Visible history of changes | Частично (comments only) |
| Help system | Contextual help, tooltips | Отсутствует |
| Data export | CSV, Excel, PDF | Stub "Экспорт" кнопка |

---

*Отчёт подготовлен на основе статического анализа исходного кода фронтенд-приложения. Для полной оценки рекомендуется дополнительное функциональное тестирование и юзабилити-тестирование с реальными пользователями.*
