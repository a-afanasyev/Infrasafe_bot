# Архитектурный план модернизации фронтенда UK Management

> ⚫ **ИСТОРИЧЕСКИЙ ПЛАН (2026-03-19) — ВЫПОЛНЕН, не AS-IS.** Описанные проблемы
> (inline-стили, отсутствие shared-компонентов/error boundaries/role-guard/i18n) уже
> устранены в коде: shadcn/ui `components/ui/*`, `GlobalErrorBoundary`/`PageErrorBoundary`,
> `ProtectedRoute allowedRoles`, i18n ru/uz. Читать как историю решений, не как текущее состояние.

**Дата**: 19 марта 2026
**Автор**: Senior Fullstack Architect
**Версия**: 1.0
**Статус**: Draft
**Входные данные**: UX-аудит (`docs/ux-audit-report.md`), анализ исходного кода `frontend/src/`

---

## 1. Текущее состояние: архитектурная оценка

### 1.1 Что работает хорошо

| Аспект | Оценка | Комментарий |
|--------|--------|-------------|
| Стек технологий | Современный, адекватный | React 19 + Vite 7 + TanStack Query 5 + Zustand 5 -- актуальный стек 2025-2026 |
| Серверный стейт | Грамотно | TanStack Query с invalidation, optimistic updates на Kanban |
| Маршрутизация | Базово корректная | Lazy-loading всех страниц, разделение dashboard/TWA/public |
| Типизация | Единый источник правды | `types/api.ts` -- централизованные типы ответов API |
| API-клиент | Корректный | Axios с refresh-token interceptor, race condition protection |
| Доменные хуки | Правильный паттерн | useKanban, useEmployees, useShifts -- инкапсуляция логики |
| CSS-переменные | Хорошая основа | Продуманная система токенов с поддержкой тёмной/светлой темы |
| WebSocket | Реализован | Real-time обновления для Kanban и Shifts |

### 1.2 Критические проблемы

| # | Проблема | Масштаб | Влияние |
|---|----------|---------|---------|
| 1 | **673 inline `style={{}}` в 32 файлах** | Системная | Невозможно поддерживать консистентность, тёмная тема ломается |
| 2 | **2 shared-компонента** из ~20 нужных | Системная | Дублирование кода, визуальная несогласованность |
| 3 | **Нулевой a11y** | Системная | WCAG 2.1 не соблюдён ни на одном уровне |
| 4 | **Tailwind/inline конфликт** | Критический | CallCenterModal и TransitionModal нечитаемы в тёмной теме |
| 5 | **13 `window.confirm/alert`** в 5 файлах | UX-критический | Нативные диалоги разрушают UX enterprise-приложения |
| 6 | **Нет Error Boundary** | Архитектурный | Одна ошибка в компоненте обрушит всё приложение |
| 7 | **Нет роутинг-гарда по ролям** | Безопасность | Любой авторизованный пользователь видит все разделы |
| 8 | **Desktop-only layout** | UX | Sidebar 260px фиксированный, нет responsive |

### 1.3 Количественные метрики кодовой базы

```
Файлов .tsx:           41
Файлов .ts:            15
Итого:                 56

Страниц:               12 (9 dashboard + 3 TWA)
Компонентов:           ~25
Shared-компонентов:     2 (LoadingSpinner, EmptyState)

Inline style={{}}:      673 вхождения в 32 файлах
className (Tailwind):   используется в 5 файлах (CallCenterModal, TransitionModal, TWA*)
window.confirm/alert:   13 вхождений в 5 файлах
clsx/cva/tailwind-merge: установлены в package.json, но НЕ импортируются нигде
```

---

## 2. Архитектурные решения

### 2.1 Компонентная библиотека: shadcn/ui

**Вердикт: shadcn/ui**

#### Анализ альтернатив

| Критерий | shadcn/ui | Radix Primitives | Свои компоненты |
|----------|-----------|------------------|-----------------|
| A11y из коробки | Да (строится на Radix) | Да | Нет -- ручная работа |
| Стилизация | Tailwind CSS (уже в стеке) | Без стилей | Inline/Tailwind |
| Темизация | CSS-переменные (совместимо с текущей системой) | Ручная | Ручная |
| Контроль кода | Полный (код копируется в проект) | API-контроль | Полный |
| Скорость внедрения | Высокая (copy-paste + кастомизация) | Средняя | Низкая |
| Зависимости | class-variance-authority, clsx, tailwind-merge -- **уже установлены** | @radix-ui/* | Нет |
| Поддержка TypeScript | Полная | Полная | Ручная |
| Размер бандла | Минимальный (только нужные компоненты) | Минимальный | Зависит |

#### Обоснование выбора shadcn/ui

1. **Зависимости уже установлены**: `class-variance-authority`, `clsx`, `tailwind-merge` присутствуют в `package.json`, но нигде не используются. Это говорит о том, что shadcn/ui уже планировался.

2. **Tailwind CSS 4 уже настроен**: `@tailwindcss/vite` плагин, `@import "tailwindcss"` в `index.css`, path alias `@` в `vite.config.ts`.

3. **A11y бесплатно**: shadcn/ui строится на Radix Primitives -- ARIA-роли, focus trap, keyboard navigation встроены в каждый компонент.

4. **CSS-переменные совместимы**: shadcn/ui использует CSS-переменные для темизации. Текущая система токенов (`--bg-root`, `--text-primary`, `--accent`) легко маппится на shadcn-конвенции.

5. **Ownership кода**: в отличие от Ant Design или MUI, код компонентов живёт в проекте. Можно модифицировать под нужды без fork-а библиотеки.

#### Complexity Audit: shadcn/ui

- **YAGNI Check**: Нужен сейчас -- 673 inline styles и 2 shared-компонента при 41 TSX-файле. Проблема реальна.
- **Technology Check**: Проще альтернативы нет -- Radix требует больше ручной стилизации, свои компоненты требуют ещё больше работы.
- **Scale Check**: Подходит для текущего масштаба (~25 компонентов) без overheada.

**Оценка: Appropriate**

#### Необходимые компоненты shadcn/ui (21 шт.)

**Фаза 0 -- Foundation (блокирует всё остальное):**

| Компонент | Замещает | Файлы-потребители |
|-----------|----------|-------------------|
| `Button` | 5+ вариантов `primaryBtnStyle`, `secondaryBtnStyle`, `navBtnStyle` | Все страницы |
| `Dialog` | 6+ кастомных модалов (inline + Tailwind) | RequestDetailModal, CallCenterModal, TransitionModal, ShiftDetailModal, формы адресов |
| `AlertDialog` | 13 `window.confirm()` | EmployeesPage, TemplatesPage, AddressesPage, AddressTable, ShiftDetailModal |
| `Input` | Inline `<input style={inputStyle}>` в каждой форме | Все формы |
| `Label` | Отсутствующие `<label htmlFor>` связки | Все формы |
| `Select` | Inline `<select style={...}>` | Фильтры, формы |

**Фаза 1 -- Core UI:**

| Компонент | Замещает |
|-----------|----------|
| `Table` | CSS Grid div-таблицы (StaffTable, AddressTable) + `<table>` в TemplatesPage |
| `Badge` | `chipStyle()`, `badgeStyle()`, inline бейджи в 10+ местах |
| `Card` | 4 варианта stats cards + карточки сотрудников/адресов |
| `DropdownMenu` | ActionMenu в AddressesPage, user menu в DashboardLayout |
| `Switch` | Кастомный div-toggle в TemplatesPage |
| `Tabs` | Tab-переключатели в AddressesPage (directory/moderation) |
| `Breadcrumb` | `<span onClick>` breadcrumb в AddressesPage |
| `Tooltip` | Отсутствует -- нужен для иконочных кнопок |

**Фаза 2 -- Enhanced:**

| Компонент | Назначение |
|-----------|------------|
| `Toast` (sonner) | Система уведомлений |
| `Sheet` | Responsive sidebar (mobile overlay) |
| `Skeleton` | Замена LoadingSpinner на скелетоны |
| `Separator` | Визуальные разделители |
| `ScrollArea` | Kanban-колонки с виртуализацией |
| `Command` | Command Palette (Ctrl+K) |
| `Pagination` | Пагинация таблиц |

---

### 2.2 Стратегия миграции стилей

#### Текущая ситуация

```
673 inline style={{}} ---- основной подход (90% компонентов)
  5 файлов className ------- Tailwind (CallCenterModal, TransitionModal, TWA*)
  0 файлов clsx/cva -------- установлены, не используются
```

#### Целевая архитектура стилей

```
Tailwind CSS 4 utility classes ---- основной подход
  + CSS-переменные (index.css) ---- дизайн-токены (сохраняются)
  + cva (class-variance-authority) - варианты компонентов (Button, Badge и т.д.)
  + clsx + tailwind-merge (cn()) -- условная композиция классов
```

#### Утилита `cn()` -- первый шаг

Создать `src/lib/utils.ts`:

```typescript
import { type ClassValue, clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}
```

Это стандартная утилита shadcn/ui, которая уже де-факто стала конвенцией в экосистеме React + Tailwind.

#### Стратегия миграции: постепенная, bottom-up

**Принцип**: НЕ мигрировать все 673 inline styles за один PR. Миграция происходит при каждом касании файла ("boy scout rule") + целенаправленно для shared-компонентов.

**Порядок миграции:**

1. **shared-компоненты** (Button, Dialog, Input...) -- создаются сразу на Tailwind + cva
2. **DashboardLayout** -- мигрируется целиком (центральный layout, влияет на всё)
3. **Модалы с Tailwind** (CallCenterModal, TransitionModal) -- приводятся к использованию CSS-переменных через Tailwind (например, `bg-[var(--bg-card)]` или кастомные утилиты)
4. **Страницы** -- мигрируются по одной при работе над фичами/фиксами
5. **TWA-страницы** -- отдельный контекст, Tailwind уже используется корректно, только убрать hardcoded цвета

#### Интеграция CSS-переменных с Tailwind CSS 4

В Tailwind CSS 4 можно определить кастомные утилиты через `@theme` в `index.css`:

```css
@import "tailwindcss";

@theme {
  --color-bg-root: var(--bg-root);
  --color-bg-primary: var(--bg-primary);
  --color-bg-card: var(--bg-card);
  --color-bg-surface: var(--bg-surface);
  --color-bg-sidebar: var(--bg-sidebar);

  --color-text-primary: var(--text-primary);
  --color-text-secondary: var(--text-secondary);
  --color-text-muted: var(--text-muted);

  --color-accent: var(--accent);
  --color-accent-dim: var(--accent-dim);

  --color-border-default: var(--border);
  --color-border-active: var(--border-active);

  --radius-default: var(--radius);
  --radius-sm: var(--radius-sm);
}
```

Это позволит писать `bg-bg-card`, `text-text-primary`, `border-border-default` вместо `bg-[var(--bg-card)]`.

#### Complexity Audit: миграция стилей

- **YAGNI Check**: Необходимо -- текущее смешение inline/Tailwind ломает тёмную тему.
- **Abstraction Check**: `cn()` + `cva` -- это минимально необходимый уровень абстракции для Tailwind-компонентов.
- **Scale Check**: Инкрементальная миграция -- правильная стратегия для ~40 файлов. Полная миграция за один спринт -- рискованна и не нужна.

**Оценка: Appropriate**

---

### 2.3 Accessibility (a11y)

#### Текущее состояние: WCAG 2.1 -- полный провал

- 0 ARIA-атрибутов
- 0 focus trap в модалах
- 0 `aria-label` на иконочных кнопках
- `<html lang="en">` вместо `lang="ru"`
- `outline: none` без `:focus-visible` замены
- Таблицы как CSS Grid `<div>` без ARIA table roles
- Toggle-switch как `<div onClick>` без `role="switch"`

#### Подход: Radix Primitives через shadcn/ui

**Вердикт**: НЕ использовать `react-aria` отдельно. shadcn/ui уже строится на Radix Primitives, которые обеспечивают:

| Radix Primitive | A11y фичи |
|----------------|-----------|
| `Dialog` | `role="dialog"`, `aria-modal`, focus trap, Escape закрытие |
| `AlertDialog` | То же + aria-describedby для описания действия |
| `DropdownMenu` | `role="menu"`, keyboard navigation (Arrow keys, Enter, Escape) |
| `Switch` | `role="switch"`, `aria-checked`, keyboard toggle (Space) |
| `Tabs` | `role="tablist"`, `aria-selected`, arrow key navigation |
| `Select` | `role="listbox"`, typeahead, keyboard navigation |
| `Tooltip` | `role="tooltip"`, delay, dismiss on Escape |

#### Ручная работа (не покрывается shadcn/ui)

1. **`<html lang="ru">`** -- одна правка в `index.html`
2. **`:focus-visible` стили** -- глобально в `index.css`
3. **Skip-navigation link** -- один компонент в DashboardLayout
4. **Контраст** -- обновить `--text-muted` (текущий 3.7:1, нужен 4.5:1) и `--border` (текущий 1.1:1)
5. **Семантические таблицы** -- при миграции StaffTable и AddressTable заменить CSS Grid div на `<table>` с shadcn Table
6. **`<label htmlFor>`** -- при миграции форм на shadcn Input + Label
7. **Emoji -> lucide-react** -- постепенно при касании компонентов
8. **`aria-label` на иконочных кнопках** -- при миграции на shadcn Button

#### Целевой уровень: WCAG 2.1 AA

Полное соответствие AAA не оправдано для B2B-приложения с 10-20 пользователями. AA -- стандартный уровень для enterprise.

#### Complexity Audit: a11y

- **YAGNI Check**: Да, нужно. Даже для малой аудитории -- это best practice и может стать требованием при масштабировании.
- **Technology Check**: Radix через shadcn/ui -- оптимальный путь. Альтернативы (ручная реализация, react-aria) дороже.
- **Scale Check**: AA -- правильный уровень. AAA -- избыточен.

**Оценка: Appropriate**

---

### 2.4 Toast-система

#### Анализ альтернатив

| Критерий | sonner | react-hot-toast | Своя |
|----------|--------|-----------------|------|
| A11y | `role="status"`, aria-live | Базовый | Ручная |
| Стилизация | Tailwind-совместимый | CSS-in-JS | Ручная |
| shadcn/ui интеграция | Официальный выбор shadcn/ui | Нет | Нет |
| Размер | 5.3 KB gzipped | 3.5 KB gzipped | 0 KB |
| Stacking, positioning, swipe | Да | Частично | Ручная |
| Поддержка promise | `toast.promise()` | `toast.promise()` | Ручная |

**Вердикт: sonner**

Обоснование:
1. Официальная интеграция с shadcn/ui (`npx shadcn@latest add sonner`)
2. `toast.promise()` -- идеально для мутаций TanStack Query
3. Tailwind-стилизация из коробки
4. Минимальная интеграция: один `<Toaster />` в `App.tsx`

#### Паттерн использования с TanStack Query

```typescript
// Пример паттерна (не код для реализации):
// В хуках useEmployees, useAddresses и т.д. -- toast при onSuccess/onError мутаций
// toast.promise(mutation.mutateAsync(data), { loading, success, error })
```

#### Complexity Audit: toast-система

- **YAGNI Check**: Необходимо. Пользователь не получает обратной связи о результате действий.
- **Technology Check**: sonner -- минимальная библиотека с максимальной совместимостью со стеком.
- **Abstraction Check**: Одна зависимость, один `<Toaster />` -- абстракция оправдана.

**Оценка: Appropriate**

---

### 2.5 Пагинация

#### Анализ данных

| Сущность | Текущий объём | Прогнозный рост | Подход |
|----------|---------------|-----------------|--------|
| Заявки (Kanban) | ~50 | Сотни | Lazy loading по колонкам |
| Сотрудники | ~20 | 50-100 | Client-side пагинация (до 200), потом серверная |
| Дворы | ~5 | 10-20 | Клиентская, без пагинации |
| Здания | ~20 | 50-100 | Клиентская пагинация |
| Квартиры | ~200 | 1000+ | Серверная пагинация |
| Шаблоны | ~10 | 20-30 | Без пагинации |

#### Стратегия

**Серверная пагинация** -- только там, где данных заведомо больше 100 записей:
- Квартиры (apartments) -- limit/offset через API
- Заявки в Kanban -- опционально, при >50 карточек в колонке

**Клиентская пагинация** -- для средних датасетов:
- Сотрудники -- отображать 20-50 за раз, фильтрация уже сужает выборку
- Здания -- аналогично

**Без пагинации** -- для малых датасетов:
- Дворы, шаблоны, смены за один день

**Виртуализация (@tanstack/react-virtual)** -- отложить:
- Kanban-колонки с 50+ карточками -- только если станет реальной проблемой
- Большие таблицы -- только если client-side пагинация не решит проблему

#### Компонент Pagination (shadcn/ui)

Использовать shadcn/ui Pagination компонент + кастомный хук `usePagination`:

```
usePagination({ totalItems, pageSize, currentPage }) => {
  pages, canPrev, canNext, goToPage, nextPage, prevPage
}
```

#### Complexity Audit: пагинация

- **YAGNI Check**: Серверная для квартир -- нужна сейчас (200+ записей). Для остальных -- клиентская достаточна.
- **Scale Check**: Виртуализация -- преждевременна. Отложить до доказанной проблемы.

**Оценка: Appropriate (серверная для квартир), Defer (виртуализация)**

---

### 2.6 Error Boundaries

#### Текущее состояние

Ноль Error Boundaries. Единственная защита -- `<Suspense fallback={<LoadingSpinner />}>` для lazy-загрузки.

#### Стратегия: трёхуровневая защита

```
App.tsx
  |-- GlobalErrorBoundary          <-- Ловит всё, показывает "Что-то пошло не так"
       |-- DashboardLayout
            |-- PageErrorBoundary   <-- Ловит ошибки страницы, показывает "Ошибка, попробуйте обновить"
                 |-- KanbanPage
                 |-- EmployeesPage
                 |   |-- ComponentErrorBoundary  <-- Опционально для виджетов
                 |   |   |-- StaffCard (если один StaffCard упадёт, остальные работают)
```

**Три уровня:**

1. **GlobalErrorBoundary** (App.tsx)
   - Ловит необработанные ошибки
   - Показывает полноэкранную страницу с кнопкой "Обновить"
   - Логирует ошибку (console.error, в будущем -- Sentry)

2. **PageErrorBoundary** (каждый Route)
   - Ловит ошибки внутри страницы
   - Показывает сообщение в content area, sidebar остаётся рабочим
   - Кнопка "Попробовать снова" (reset error boundary)

3. **ComponentErrorBoundary** (опционально)
   - Для изолированных виджетов (charts, cards) где падение одного не должно ронять страницу
   - Показывает fallback вместо сломанного компонента

#### Реализация

Использовать `react-error-boundary` (де-факто стандарт, 1 KB) или написать свой -- класс ErrorBoundary в React тривиален (~30 строк).

**Рекомендация**: написать свой -- одна зависимость меньше, код тривиален, лучше контроль.

#### Complexity Audit: Error Boundaries

- **YAGNI Check**: Необходимо. Без Error Boundary одна ошибка в рендере обрушит всё приложение.
- **Abstraction Check**: 2-3 компонента -- минимальная абстракция.
- **Technology Check**: Свой код (30 строк) vs библиотека -- свой предпочтительнее.

**Оценка: Appropriate**

---

### 2.7 Responsive Design

#### Текущее состояние

- Sidebar: фиксированный 260px, не коллапсируемый
- Topbar: `left: var(--sidebar-w)` -- привязан к sidebar
- Content: `marginLeft: var(--sidebar-w)` -- привязан к sidebar
- Kanban: `minWidth: 1200px` на timeline
- Таблицы: фиксированные ширины
- Мобильный: нет поддержки (кроме TWA, которые отдельная история)

#### Стратегия: Desktop-first responsive (не mobile-first)

**Обоснование**: Это enterprise B2B-приложение для управляющей компании. Основной сценарий -- рабочее место диспетчера/менеджера за десктопом. Mobile-first не оправдан.

**Breakpoints:**

```
>= 1280px  -- Полный layout (sidebar 260px + content)
>= 1024px  -- Collapsed sidebar (64px, только иконки) + content
>= 768px   -- Sidebar скрыт, hamburger в topbar, content full-width
<  768px   -- Mobile: sidebar как Sheet (overlay), упрощённые таблицы
```

**Реализация через CSS-переменные + Tailwind:**

1. **Sidebar**: три состояния через `data-sidebar-state="expanded|collapsed|hidden"`
   - `expanded`: ширина 260px, иконки + текст
   - `collapsed`: ширина 64px, только иконки, tooltip с текстом
   - `hidden`: sidebar не рендерится, Sheet компонент для мобильного меню

2. **Topbar**: реагирует на состояние sidebar через CSS-переменную `--sidebar-w`

3. **Content area**: использует `margin-left: var(--sidebar-w)` -- автоматически подстраивается

4. **Таблицы на мобильных**: вертикальные карточки вместо горизонтальных таблиц (`< md:` breakpoint)

5. **Kanban на мобильных**: горизонтальный скролл колонок с snap-точками

#### Complexity Audit: responsive design

- **YAGNI Check**: Для < 768px -- опционально (основная аудитория за десктопами). Collapsed sidebar (1024-1280px) -- реально нужен для ноутбуков.
- **Scale Check**: Три breakpoint -- достаточно. Не нужно 5-6 breakpoints.

**Оценка: Appropriate для collapsed sidebar, Optional для mobile**

---

### 2.8 Роутинг-гард по ролям

#### Текущее состояние

```typescript
// App.tsx:32-36
function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated } = useAuthStore()
  if (!isAuthenticated) return <Navigate to="/login" replace />
  return <>{children}</>
}
```

Проверяется только `isAuthenticated`. Роли (`user.roles`) хранятся в authStore, но не используются для ограничения доступа.

#### Целевое решение

```typescript
// Расширенный ProtectedRoute
interface ProtectedRouteProps {
  children: React.ReactNode
  allowedRoles?: string[]  // если не указаны -- доступ для всех авторизованных
}

function ProtectedRoute({ children, allowedRoles }: ProtectedRouteProps) {
  const { isAuthenticated, user } = useAuthStore()
  if (!isAuthenticated) return <Navigate to="/login" replace />
  if (allowedRoles && !user?.roles?.some(r => allowedRoles.includes(r))) {
    return <Navigate to="/dashboard" replace />  // или <ForbiddenPage />
  }
  return <>{children}</>
}
```

Также добавить хук `useHasRole(role: string): boolean` для условного рендеринга UI-элементов (кнопки, пункты меню).

#### Complexity Audit: роутинг-гард

- **YAGNI Check**: Необходимо. Данные о ролях уже есть в authStore -- нужно только использовать.
- **Abstraction Check**: Минимальная -- расширение существующего ProtectedRoute + один хук.

**Оценка: Appropriate**

---

## 3. Структура файлов и папок

### 3.1 Текущая структура

```
src/
  api/client.ts
  stores/authStore.ts
  contexts/TopbarContext.tsx
  hooks/                        -- доменные хуки
  types/api.ts
  utils/
  layouts/DashboardLayout.tsx
  pages/                        -- все страницы
  components/
    shared/                     -- 2 компонента (LoadingSpinner, EmptyState)
    kanban/
    callcenter/
    employees/
    shifts/
    templates/
    addresses/
```

### 3.2 Целевая структура

```
src/
  api/
    client.ts                    -- (без изменений)

  lib/
    utils.ts                     -- cn() утилита

  components/
    ui/                          -- shadcn/ui компоненты (21 шт.)
      button.tsx
      dialog.tsx
      alert-dialog.tsx
      input.tsx
      label.tsx
      select.tsx
      table.tsx
      badge.tsx
      card.tsx
      dropdown-menu.tsx
      switch.tsx
      tabs.tsx
      breadcrumb.tsx
      tooltip.tsx
      toast.tsx (sonner)
      sheet.tsx
      skeleton.tsx
      separator.tsx
      scroll-area.tsx
      command.tsx
      pagination.tsx

    shared/                      -- бизнес-shared (не UI-примитивы)
      LoadingSpinner.tsx          -- (мигрировать на Skeleton)
      EmptyState.tsx              -- (мигрировать на Tailwind)
      ConfirmDialog.tsx           -- обёртка над AlertDialog для деструктивных действий
      PageErrorBoundary.tsx
      GlobalErrorBoundary.tsx

    kanban/                      -- (без изменений в структуре)
    callcenter/
    employees/
    shifts/
    templates/
    addresses/

  hooks/                         -- (без изменений)
    useTheme.ts
    useKanban.ts
    useEmployees.ts
    useShifts.ts
    useTemplates.ts
    useAddresses.ts
    useAnalytics.ts
    useWebSocket.ts
    useTWAAuth.ts
    usePagination.ts             -- новый
    useHasRole.ts                -- новый

  stores/
    authStore.ts                 -- (без изменений)

  contexts/
    TopbarContext.tsx             -- (без изменений)

  types/
    api.ts                       -- (без изменений)

  utils/
    employeeUtils.ts
    timezone.ts
    isTWA.ts

  layouts/
    DashboardLayout.tsx          -- мигрировать на Tailwind + responsive

  pages/                         -- (без изменений в структуре)
    twa/                         -- (без изменений)
```

### 3.3 Принципы организации

1. **`components/ui/`** -- только headless/styled UI-примитивы из shadcn/ui. Один компонент = один файл. Не содержат бизнес-логики.

2. **`components/shared/`** -- бизнес-level shared-компоненты (ConfirmDialog, ErrorBoundary). Используют `ui/` компоненты внутри.

3. **`components/{domain}/`** -- доменные компоненты. Используют `ui/` и `shared/`.

4. **`pages/`** -- страницы. Композиция доменных компонентов. Минимум логики отображения.

5. **НЕ делать**: `components/common/`, `components/core/`, `components/base/` -- одного уровня `ui/` достаточно.

---

## 4. Риски и зависимости

### 4.1 Карта зависимостей между задачами

```
[Tailwind @theme setup] ─────────────────────────────┐
         │                                            │
         v                                            v
[cn() утилита] ──> [shadcn/ui Button] ──> [Все страницы]
         │              │
         │              v
         │         [shadcn/ui Dialog] ──> [ConfirmDialog] ──> [Замена window.confirm]
         │              │
         │              v
         │         [shadcn/ui AlertDialog]
         │
         v
   [shadcn/ui Input] ──> [Миграция форм]
         │
         v
   [shadcn/ui Label] ──> [a11y форм]

[Error Boundaries] ────── независимо от всего

[Toast (sonner)] ────── зависит от shadcn/ui setup, но не от миграции стилей

[Responsive sidebar] ── зависит от shadcn/ui Sheet + миграции DashboardLayout

[Роутинг-гард] ──────── независимо от всего

[Пагинация] ──────────── зависит от shadcn/ui Table + Pagination
```

### 4.2 Что можно делать параллельно

| Трек A (UI Foundation) | Трек B (Инфраструктура) | Трек C (Фиксы) |
|------------------------|------------------------|-----------------|
| Настройка Tailwind @theme | Error Boundaries | `<html lang="ru">` |
| cn() утилита | Роутинг-гард по ролям | `:focus-visible` стили |
| shadcn/ui компоненты | Toast (sonner) | Контраст: --text-muted, --border |
| Миграция DashboardLayout | | Замена emoji на lucide-react |

### 4.3 Что строго последовательно

1. Tailwind @theme setup -> cn() -> shadcn/ui компоненты -> миграция страниц
2. shadcn/ui Dialog -> ConfirmDialog -> замена window.confirm()
3. shadcn/ui Sheet -> Responsive sidebar
4. shadcn/ui Table -> Пагинация таблиц

### 4.4 Риски

| Риск | Вероятность | Влияние | Митигация |
|------|-------------|---------|-----------|
| **Конфликт inline styles и Tailwind при миграции** | Высокая | Среднее | Мигрировать файл целиком, не смешивать подходы в одном файле |
| **Поломка тёмной темы при миграции на Tailwind** | Средняя | Высокое | @theme конфигурация первой, тестировать обе темы при каждом PR |
| **Регрессия визуала при замене компонентов** | Средняя | Среднее | Screenshot-тесты (Playwright) для ключевых экранов перед началом |
| **shadcn/ui несовместимость с Tailwind CSS 4** | Низкая | Высокое | shadcn/ui уже поддерживает Tailwind CSS 4 (v4-канонический формат) |
| **Scope creep**: "раз уж трогаем, давайте добавим фичу X" | Высокая | Среднее | Строгий scope каждой фазы, фичи -- отдельными PR |
| **TWA-страницы ломаются от изменений в index.css** | Низкая | Среднее | TWA изолированы стилистически, но проверять |

---

## 5. Поэтапный план реализации

### Фаза 0: Infrastructure (2-3 дня)

**Цель**: Подготовить техническую базу для всех последующих фаз. Ничего видимого для пользователя не меняется.

| # | Задача | Зависимости | Effort |
|---|--------|-------------|--------|
| 0.1 | Настроить Tailwind CSS 4 `@theme` с текущими CSS-переменными | -- | 0.5 дня |
| 0.2 | Создать `src/lib/utils.ts` с функцией `cn()` | -- | 0.5 часа |
| 0.3 | Инициализировать shadcn/ui (`components.json`) | 0.1, 0.2 | 0.5 часа |
| 0.4 | Исправить `<html lang="ru">` в `index.html` | -- | 5 минут |
| 0.5 | Добавить глобальные `:focus-visible` стили в `index.css` | -- | 0.5 часа |
| 0.6 | Обновить `--text-muted` для контраста >= 4.5:1 | -- | 0.5 часа |
| 0.7 | Обновить `--border` для видимости | -- | 0.5 часа |
| 0.8 | Добавить GlobalErrorBoundary в App.tsx | -- | 0.5 дня |
| 0.9 | Добавить PageErrorBoundary в DashboardLayout | 0.8 | 0.5 дня |

**Параллелизация**: 0.1-0.3 -- один трек; 0.4-0.7 -- другой трек; 0.8-0.9 -- третий трек. Все три можно вести параллельно.

**Критерий завершения**: `cn()` работает, shadcn/ui инициализирован, Error Boundaries ловят ошибки, контраст исправлен.

---

### Фаза 1: Core Components (3-5 дней)

**Цель**: Создать базовые UI-компоненты, заменить `window.confirm/alert`, добавить toast.

| # | Задача | Зависимости | Effort |
|---|--------|-------------|--------|
| 1.1 | Добавить shadcn/ui Button | Фаза 0 | 0.5 дня |
| 1.2 | Добавить shadcn/ui Dialog | Фаза 0 | 0.5 дня |
| 1.3 | Добавить shadcn/ui AlertDialog | Фаза 0 | 0.5 часа |
| 1.4 | Создать ConfirmDialog (обёртка AlertDialog) | 1.3 | 0.5 дня |
| 1.5 | Заменить все 13 `window.confirm()` на ConfirmDialog | 1.4 | 1 день |
| 1.6 | Заменить `window.alert()` в TemplatesPage | 1.1 | 0.5 часа |
| 1.7 | Добавить shadcn/ui Input + Label | Фаза 0 | 0.5 дня |
| 1.8 | Добавить shadcn/ui Select | Фаза 0 | 0.5 дня |
| 1.9 | Установить sonner, добавить `<Toaster />` в App.tsx | Фаза 0 | 0.5 часа |
| 1.10 | Добавить toast-уведомления в существующие мутации | 1.9 | 1 день |

**Параллелизация**: 1.1-1.3 параллельно с 1.7-1.8. Toast (1.9-1.10) параллельно со всем.

**Критерий завершения**: Ноль `window.confirm()`, ноль `window.alert()`. Все мутации дают обратную связь через toast. Button, Dialog, Input, Select, Label доступны.

---

### Фаза 2: Layout & Navigation (3-4 дня)

**Цель**: Responsive sidebar, исправленная навигация, role-based routing.

| # | Задача | Зависимости | Effort |
|---|--------|-------------|--------|
| 2.1 | Мигрировать DashboardLayout на Tailwind | Фаза 1 (Button) | 1 день |
| 2.2 | Добавить shadcn/ui Sheet | Фаза 0 | 0.5 часа |
| 2.3 | Реализовать responsive sidebar (expanded/collapsed/hidden) | 2.1, 2.2 | 1.5 дня |
| 2.4 | Добавить shadcn/ui DropdownMenu | Фаза 0 | 0.5 часа |
| 2.5 | Заменить user menu на DropdownMenu | 2.4, 2.1 | 0.5 дня |
| 2.6 | Расширить ProtectedRoute: добавить allowedRoles | -- | 0.5 дня |
| 2.7 | Добавить хук useHasRole | -- | 0.5 часа |
| 2.8 | Применить role-based routing к маршрутам | 2.6 | 0.5 часа |

**Параллелизация**: 2.1-2.5 (layout) параллельно с 2.6-2.8 (routing).

**Критерий завершения**: Sidebar коллапсируется на ноутбуках, скрывается на планшетах. User menu работает с клавиатуры. Роли ограничивают доступ к разделам.

---

### Фаза 3: Component Migration (5-7 дней)

**Цель**: Мигрировать ключевые страницы на shadcn/ui компоненты, убрать inline styles.

| # | Задача | Зависимости | Effort |
|---|--------|-------------|--------|
| 3.1 | Добавить shadcn/ui Table, Badge, Card, Tabs, Breadcrumb, Switch, Tooltip | Фаза 1 | 1 день |
| 3.2 | Мигрировать CallCenterModal: Tailwind -> CSS vars + shadcn Dialog | Фаза 1 (Dialog) | 0.5 дня |
| 3.3 | Мигрировать TransitionModal: Tailwind -> CSS vars + shadcn Dialog | Фаза 1 (Dialog) | 0.5 дня |
| 3.4 | Мигрировать EmployeesPage: inline -> Tailwind + shadcn компоненты | 3.1 | 1 день |
| 3.5 | Мигрировать StaffTable: CSS Grid div -> shadcn Table | 3.1 | 0.5 дня |
| 3.6 | Мигрировать AddressesPage (942 строки): декомпозиция + Tailwind | 3.1 | 1.5 дня |
| 3.7 | Мигрировать AddressTable | 3.1 | 0.5 дня |
| 3.8 | Мигрировать TemplatesPage: inline -> Tailwind + shadcn Switch для toggle | 3.1 | 0.5 дня |
| 3.9 | Мигрировать ShiftsPage | 3.1 | 0.5 дня |
| 3.10 | Мигрировать AnalyticsPage | 3.1 | 0.5 дня |

**Параллелизация**: 3.2-3.3 (модалы) -- приоритет (критическая проблема тёмной темы). 3.4-3.10 можно вести параллельно разными разработчиками.

**Критерий завершения**: Все компоненты используют Tailwind + CSS-переменные. Тёмная и светлая тема работают корректно на всех экранах. StaffTable и AddressTable -- семантические `<table>`.

---

### Фаза 4: Data & UX (3-4 дня)

**Цель**: Пагинация, улучшенный Kanban, горячие клавиши.

| # | Задача | Зависимости | Effort |
|---|--------|-------------|--------|
| 4.1 | Добавить shadcn/ui Pagination | Фаза 3 | 0.5 дня |
| 4.2 | Серверная пагинация для квартир (API + UI) | 4.1 | 1 день |
| 4.3 | Клиентская пагинация для сотрудников | 4.1 | 0.5 дня |
| 4.4 | Фильтры и поиск на Kanban-доске | Фаза 1 (Input) | 1 день |
| 4.5 | Badge-счётчики в sidebar навигации | Фаза 2 | 0.5 дня |
| 4.6 | Обновление `document.title` для каждой страницы | -- | 0.5 часа |
| 4.7 | Offline-индикатор | -- | 0.5 дня |

**Критерий завершения**: Квартиры пагинированы. Kanban имеет поиск. Sidebar показывает счётчики.

---

### Фаза 5: Polish (2-3 дня, может идти параллельно с Фазой 4)

**Цель**: A11y финализация, keyboard shortcuts, мелкие улучшения.

| # | Задача | Зависимости | Effort |
|---|--------|-------------|--------|
| 5.1 | Замена emoji-иконок на lucide-react по всему проекту | -- | 0.5 дня |
| 5.2 | `aria-label` для всех иконочных кнопок | Фаза 3 | 0.5 дня |
| 5.3 | `<label htmlFor>` связки во всех формах | Фаза 3 | 0.5 дня |
| 5.4 | Skip-navigation link | Фаза 2 | 0.5 часа |
| 5.5 | Command Palette (Ctrl+K) с shadcn Command | Фаза 3 | 1 день |
| 5.6 | Базовые горячие клавиши (N, Escape, ?) | 5.5 | 0.5 дня |
| 5.7 | Исправить `navigate(-1)` на явные пути | -- | 0.5 часа |
| 5.8 | Skeleton вместо LoadingSpinner для страниц | Фаза 3 | 0.5 дня |

---

## 6. Суммарная оценка

### Общий объём

| Фаза | Название | Effort | Тип |
|-------|----------|--------|-----|
| 0 | Infrastructure | 2-3 дня | Блокирующая |
| 1 | Core Components | 3-5 дней | Блокирующая |
| 2 | Layout & Navigation | 3-4 дня | Частично параллельная с 1 |
| 3 | Component Migration | 5-7 дней | Основной объём |
| 4 | Data & UX | 3-4 дня | Параллельная с 5 |
| 5 | Polish | 2-3 дня | Параллельная с 4 |
| **Итого** | | **18-26 дней** | **4-6 недель для 1 разработчика** |

### Что НЕ включено в план (сознательно отложено)

| Элемент | Причина | Когда делать |
|---------|---------|-------------|
| Storybook | Полезно, но не критично для команды 1-3 разработчика | Когда команда > 3 человек |
| Виртуализация (@tanstack/react-virtual) | Нет доказанной проблемы производительности | Когда Kanban > 100 карточек в колонке |
| i18n | Текущая аудитория -- только русскоязычная | Когда появится потребность в мультиязычности |
| CSS Modules / styled-components | Tailwind + CSS vars покрывает потребности | Никогда (избыточная абстракция) |
| Micro-frontends | Одно приложение, одна команда | Никогда для текущего масштаба |
| Анимации page transitions | Декоративное, не влияет на функциональность | После всех фаз, если будет время |
| SSR / SSG | B2B-приложение за логином, SEO не нужен | Не нужно |
| ResidentBoard переработка | Standalone-экран, своя стилистика оправдана | Отдельный спринт, низкий приоритет |

---

## 7. Критерии успеха (DoD)

### По завершении всех фаз

1. **Ноль inline `style={{}}`** в новых и мигрированных компонентах
2. **Ноль `window.confirm()` / `window.alert()`** во всём проекте
3. **WCAG 2.1 AA** для основных пользовательских путей (Kanban, Employees, Addresses)
4. **Тёмная и светлая тема** работают корректно на всех экранах (включая модалы)
5. **Sidebar** коллапсируется на экранах < 1280px
6. **Error Boundaries** -- ошибка в компоненте не обрушивает приложение
7. **Toast-уведомления** -- каждая мутация даёт обратную связь пользователю
8. **Пагинация** -- квартиры, сотрудники при > 50 записях
9. **Роли** -- маршруты защищены по ролям
10. **21 UI-компонент** в `components/ui/` -- переиспользуемая библиотека

### Метрики для отслеживания

- Количество `style={{}}` в проекте (цель: < 50, текущее: 673)
- Количество файлов с `window.confirm/alert` (цель: 0, текущее: 5)
- Lighthouse Accessibility score (цель: > 80, текущее: ~30)
- Количество компонентов в `components/ui/` (цель: 21, текущее: 0)
- Количество компонентов в `components/shared/` (цель: 5+, текущее: 2)

---

## Приложение A: Новые зависимости

| Пакет | Назначение | Размер (gzip) |
|-------|------------|---------------|
| `sonner` | Toast-уведомления | 5.3 KB |
| `@radix-ui/react-dialog` | Dialog/AlertDialog (через shadcn) | 8 KB |
| `@radix-ui/react-dropdown-menu` | DropdownMenu (через shadcn) | 10 KB |
| `@radix-ui/react-switch` | Switch (через shadcn) | 3 KB |
| `@radix-ui/react-tabs` | Tabs (через shadcn) | 5 KB |
| `@radix-ui/react-tooltip` | Tooltip (через shadcn) | 6 KB |
| `@radix-ui/react-select` | Select (через shadcn) | 15 KB |
| `@radix-ui/react-scroll-area` | ScrollArea (через shadcn) | 5 KB |
| `cmdk` | Command palette (через shadcn) | 4 KB |
| **Итого** | | **~61 KB** |

Зависимости, которые уже установлены и не используются (будут использоваться):
- `class-variance-authority` -- варианты компонентов
- `clsx` -- условные классы
- `tailwind-merge` -- слияние Tailwind-классов

## Приложение B: Маппинг CSS-переменных для Tailwind @theme

```
Текущая переменная        ->  Tailwind utility class
------------------------------------------------------
var(--bg-root)            ->  bg-bg-root
var(--bg-primary)         ->  bg-bg-primary
var(--bg-card)            ->  bg-bg-card
var(--bg-card-hover)      ->  bg-bg-card-hover
var(--bg-surface)         ->  bg-bg-surface
var(--bg-sidebar)         ->  bg-bg-sidebar
var(--text-primary)       ->  text-text-primary
var(--text-secondary)     ->  text-text-secondary
var(--text-muted)         ->  text-text-muted
var(--accent)             ->  bg-accent / text-accent / border-accent
var(--accent-dim)         ->  bg-accent-dim
var(--border)             ->  border-border-default
var(--border-active)      ->  border-border-active
var(--radius)             ->  rounded-default
var(--radius-sm)          ->  rounded-sm
var(--blue)               ->  text-blue / bg-blue
var(--red)                ->  text-red / bg-red
var(--amber)              ->  text-amber / bg-amber
var(--violet)             ->  text-violet / bg-violet
```

## Приложение C: Декомпозиция AddressesPage (942 строки)

Рекомендуется разбить `AddressesPage.tsx` на:

```
pages/AddressesPage.tsx              -- 150 строк (routing state, tab switch)
  components/addresses/
    AddressDirectory.tsx             -- 200 строк (directory view с breadcrumb)
    AddressCardGrid.tsx              -- 150 строк (tile view)
    AddressTable.tsx                 -- (уже существует)
    AddressBreadcrumb.tsx            -- 50 строк (breadcrumb навигация)
    AddressActionMenu.tsx            -- 50 строк (context menu)
    AddressStatsBar.tsx              -- 80 строк (KPI-карточки)
    ModerationPanel.tsx              -- (уже существует)
    YardFormModal.tsx                -- (уже существует)
    BuildingFormModal.tsx            -- (уже существует)
    ApartmentFormModal.tsx           -- (уже существует)
    BulkCreateModal.tsx              -- (уже существует)
    ApartmentProfileModal.tsx        -- (уже существует)
```
