# QA Report: Frontend Modernization

**Дата:** 2026-03-19
**Проект:** UK Management Frontend
**Путь:** `/Users/andreyafanasyev/Code/UK/frontend/`
**Аналитик:** QA Analyst Agent

---

## Что проверялось

Комплексный QA-анализ модернизации фронтенда UK Management:
1. Удаление `window.confirm` / `window.alert`
2. Корректность использования `ConfirmDialog`
3. Покрытие Toast-уведомлениями всех мутаций
4. Error Boundaries в `App.tsx`
5. Hardcoded цвета (vs. семантические токены)
6. Responsive sidebar в `DashboardLayout`
7. Мертвый код и общее качество

---

## 1. window.confirm / window.alert

**Статус: PASSED**

Grep по `window.confirm`, `window.alert`, `confirm(`, `alert(` в `frontend/src/` --
**0 совпадений**. Все нативные диалоги успешно заменены на `ConfirmDialog`.

---

## 2. ConfirmDialog -- использование и state management

**Статус: PASSED с замечаниями**

### Найденные использования (8 мест):

| Файл | Паттерн state | `loading` проп | Verdict |
|---|---|---|---|
| `EmployeesPage.tsx:309` | `confirmState { open, title, description, onConfirm }` | `blockEmployee.isPending \|\| unblockEmployee.isPending` | OK |
| `TemplatesPage.tsx:258` | `confirmState { open, templateId }` | `deleteTemplate.isPending` | OK |
| `AddressesPage.tsx:708` | `confirmState { open, title, description, onConfirm }` | **НЕ ПЕРЕДАН** | BUG |
| `AddressTable.tsx:140` (Yards) | `confirmDelete { open, id }` | **НЕ ПЕРЕДАН** | BUG |
| `AddressTable.tsx:227` (Buildings) | `confirmDelete { open, id }` | **НЕ ПЕРЕДАН** | BUG |
| `AddressTable.tsx:316` (Apartments) | `confirmDelete { open, id }` | **НЕ ПЕРЕДАН** | BUG |
| `ShiftDetailModal.tsx:210` | `confirmEndOpen: boolean` | `endShift.isPending` | OK |

### BUG-01: Отсутствует `loading` проп в AddressesPage и AddressTable

- **Серьезность:** Средняя
- **Описание:** В `AddressesPage.tsx:708` и во всех трех таблицах `AddressTable.tsx` (строки 140, 227, 316) `ConfirmDialog` не получает проп `loading`. Это означает, что:
  1. Кнопка "Удалить" в диалоге не блокируется во время запроса
  2. Пользователь может кликнуть "Удалить" несколько раз, вызвав дублированные запросы
  3. Текст кнопки не меняется на "Выполняется..." во время операции
- **Ожидаемый результат:** `loading={deleteYard.isPending || deleteBuilding.isPending || deleteApartment.isPending}`
- **Рекомендация для AddressesPage.tsx:**
  ```tsx
  <ConfirmDialog
    ...
    loading={deleteYard.isPending || deleteBuilding.isPending || deleteApartment.isPending}
  />
  ```
- **Рекомендация для AddressTable.tsx:** Пропрокинуть `isPending` через пропсы или передать mutation status.

### BUG-02: ConfirmDialog закрывается ДО завершения async операции

- **Серьезность:** Средняя
- **Описание:** В `ConfirmDialog.tsx:54-56`:
  ```tsx
  onClick={() => {
    onConfirm()
    onOpenChange(false)
  }}
  ```
  `onOpenChange(false)` вызывается синхронно сразу после `onConfirm()`. Если `onConfirm` запускает async mutation (что и происходит повсюду), диалог закроется мгновенно, до завершения запроса. Пользователь не увидит состояние загрузки и может повторить действие.
- **Ожидаемый результат:** Диалог должен оставаться открытым до завершения операции (или закрываться через `onSuccess` callback мутации).
- **Рекомендация:** Убрать `onOpenChange(false)` из `onClick` и закрывать диалог через `onOpenChange` из вызывающего компонента (в `onSuccess` мутации) или через проп `loading` + автозакрытие.

---

## 3. Toast покрытие мутаций

**Статус: PASSED**

Все 28 мутаций (`useMutation`) проверены:

### hooks/useAddresses.ts (12 мутаций)
- `useCreateYard` -- toast.success + toast.error
- `useUpdateYard` -- toast.success + toast.error
- `useDeleteYard` -- toast.success + toast.error
- `useCreateBuilding` -- toast.success + toast.error
- `useUpdateBuilding` -- toast.success + toast.error
- `useDeleteBuilding` -- toast.success + toast.error
- `useCreateApartment` -- toast.success + toast.error
- `useUpdateApartment` -- toast.success + toast.error
- `useDeleteApartment` -- toast.success + toast.error
- `useBulkCreateApartments` -- toast.success + toast.error
- `useApproveModeration` -- toast.success + toast.error
- `useRejectModeration` -- toast.success + toast.error

### hooks/useTemplates.ts (4 мутации)
- `useCreateTemplate` -- toast.success + toast.error
- `useUpdateTemplate` -- toast.success + toast.error
- `useDeleteTemplate` -- toast.success + toast.error
- `useCreateShiftFromTemplate` -- toast.success + toast.error

### hooks/useShifts.ts (3 мутации)
- `useCreateShift` -- toast.success + toast.error
- `useEndShift` -- toast.success + toast.error
- `useHandleTransfer` -- toast.success + toast.error

### hooks/useEmployees.ts (4 мутации)
- `useApproveEmployee` -- toast.success + toast.error
- `useRejectEmployee` -- toast.success + toast.error
- `useBlockEmployee` -- toast.success + toast.error
- `useUnblockEmployee` -- toast.success + toast.error

### components/kanban/RequestDetailModal.tsx (3 мутации)
- `updateRequest` -- toast.success + toast.error
- `forceAccept` -- toast.success + toast.error
- `postComment` -- toast.success + toast.error

### components/employees/AssignRequestModal.tsx (1 мутация)
- `assignMutation` -- toast.success + toast.error

### Inline async (не useMutation):
- `sendReminder` (RequestDetailModal.tsx:111-122) -- toast.success + toast.error
- Login (LoginPage.tsx:29, 78) -- toast.error (success не нужен -- redirect)

**Все мутации полностью покрыты.**

---

## 4. Error Boundaries

**Статус: PASSED**

### App.tsx структура (строки 49-85):
```
QueryClientProvider
  Toaster
  GlobalErrorBoundary          <-- оборачивает BrowserRouter
    BrowserRouter
      Suspense
        Routes
          /login               -- LoginPage (без boundary, OK -- standalone)
          /dashboard/*         -- ProtectedRoute > DashboardLayout
            index              -- PageErrorBoundary > KanbanPage
            analytics          -- PageErrorBoundary > AnalyticsPage
            shifts             -- PageErrorBoundary > ShiftsPage
            employees          -- PageErrorBoundary > EmployeesPage
            employees/:id      -- PageErrorBoundary > EmployeeDetailPage
            templates          -- PageErrorBoundary > TemplatesPage
            addresses          -- PageErrorBoundary > AddressesPage
          /resident-board      -- ProtectedRoute > PageErrorBoundary > ResidentBoardPage
          /twa/*               -- PageErrorBoundary > TWA*Page
```

- GlobalErrorBoundary (`GlobalErrorBoundary.tsx`) -- полноэкранный fallback с кнопкой "Обновить страницу". Использует CSS variables, не Tailwind (правильно для crash fallback).
- PageErrorBoundary (`PageErrorBoundary.tsx`) -- fallback для отдельных страниц с "Попробовать снова" и "На главную". Использует CSS variables.
- Toaster вынесен выше GlobalErrorBoundary (корректно -- тосты продолжат работать при ошибке внутри boundary).

**Архитектура Error Boundaries корректна.**

---

## 5. Hardcoded цвета

**Статус: PASSED с замечаниями**

### TWA файлы (ИСКЛЮЧЕНЫ из проверки -- ожидаемо используют стандартный Tailwind):
- `TWAHomePage.tsx` -- `bg-gray-50`, `bg-white`, `text-gray-*`, `bg-blue-*`
- `TWACreatePage.tsx` -- аналогично
- `TWARequestDetailPage.tsx` -- аналогично

### Найденные проблемы в НЕ-TWA файлах:

#### BUG-03: DashboardPage.tsx -- полностью hardcoded colors

- **Серьезность:** Низкая (мертвый код)
- **Описание:** `DashboardPage.tsx` содержит `bg-white`, `text-blue-600`, `text-gray-500`, `bg-green-600`. Однако этот файл **не импортируется нигде** в `App.tsx` и является мертвым кодом (заменен на `KanbanPage` внутри `DashboardLayout`).
- **Рекомендация:** Удалить файл `DashboardPage.tsx`.

#### RISK-01: `bg-white` в toggle-кнопке шаблонов

- **Серьезность:** Низкая
- **Файлы:**
  - `TemplatesPage.tsx:422` -- `bg-white` для ручки toggle-переключателя
  - `CreateTemplateModal.tsx:317` -- аналогично
- **Описание:** Toggle "авто-создание" использует `bg-white` для круглого индикатора. Это работает в обоих темах (белый кружок на цветном фоне), но формально нарушает правило "no hardcoded colors".
- **Рекомендация:** Оставить как есть или заменить на `bg-bg-card` если нужна строгая консистентность.

#### RISK-02: `bg-white/[.07]` в LoginPage

- **Серьезность:** Низкая
- **Файл:** `LoginPage.tsx:137, 139`
- **Описание:** Используется `bg-white/[.07]` для разделительных линий на странице логина. Это полупрозрачный белый, работает только в темной теме.
- **Рекомендация:** Заменить на `bg-border-default` или `bg-text-muted/10`.

#### RISK-03: Hardcoded hex colors для статусов (канбан, смены, аналитика)

- **Серьезность:** Низкая (архитектурный долг)
- **Файлы:**
  - `KanbanColumn.tsx:15-22` -- `bg-[#60a5fa]`, `bg-[#fbbf24]`, etc.
  - `RequestCard.tsx:9-10` -- `text-[#d97706]`, `text-[#ea580c]`
  - `RequestDetailModal.tsx:20, 26` -- аналогично
  - `ShiftDetailModal.tsx:28-38` -- `#3b82f6`, `#ef4444`, etc.
  - `ShiftTimeline.tsx:14-33` -- аналогично
  - `AnalyticsPage.tsx:70-77` -- PIE_PALETTE с hex-значениями
  - `StaffCard.tsx:50`, `StaffTable.tsx:86, 147` -- `bg-[#5a6a7a]`, `text-[#5a6a7a]`
  - `EmployeeDetailPage.tsx:52, 108` -- `#5a6a7a`
- **Описание:** Hex-цвета используются напрямую вместо CSS-переменных. Однако большинство из них -- это цвета статусов, типов, рангов, которые не меняются между темами.
- **Рекомендация:** Вынести в CSS-переменные (`--status-new`, `--status-in-progress`, etc.) для полной поддержки тем, или принять как допустимый паттерн для декоративных цветов.

#### ResidentBoardPage.tsx -- полностью inline styles

- **Серьезность:** Низкая (особый случай)
- **Описание:** Вся страница написана на inline styles с hardcoded hex-цветами. Это **standalone публичное табло для жителей** -- не использует dashboard layout и не поддерживает смену тем. Это допустимый подход.

---

## 6. Responsive Sidebar (DashboardLayout)

**Статус: PASSED**

### Три состояния sidebar:
```typescript
type SidebarState = 'expanded' | 'collapsed' | 'hidden'
```

| Breakpoint | SidebarState | Sidebar width | Content margin |
|---|---|---|---|
| >= 1280px (desktop) | `expanded` | `var(--sidebar-w)` = 260px | `ml-[var(--sidebar-w)]` |
| 1024-1279px (tablet) | `collapsed` | `var(--sidebar-w-collapsed)` = 64px | `ml-[var(--sidebar-w-collapsed)]` |
| < 1024px (mobile) | `hidden` | 0 | `ml-0` |

### CSS-переменные (index.css):
- `--sidebar-w: 260px` -- expanded width
- `--sidebar-w-collapsed: 64px` -- collapsed width
- `--topbar-h: 64px` -- topbar height

### Mobile overlay:
- Backdrop: `bg-black/50 backdrop-blur-sm` с z-index 250
- Sidebar panel: `w-[280px]` с z-index 260
- Закрывается по: клику на backdrop, по Escape, по навигации (`onNavClick={closeMobileMenu}`)

### Manual toggle:
- `manualToggle` state позволяет пользователю переключить expanded/collapsed
- Сбрасывается при смене breakpoint (`useEffect` на `isDesktop`, `isTablet`)

### Topbar:
- z-index 100, fixed, backdrop-blur
- Left offset синхронизирован с sidebar state
- Hamburger показывается только в `hidden` state

### Tooltip для collapsed sidebar:
- `NavTooltip` компонент -- появляется при hover

### UserDropdown:
- Закрывается по click outside и Escape
- `aria-expanded`, `aria-haspopup`, `role="menu"`, `role="menuitem"` -- accessibility OK

**Sidebar реализован корректно.**

---

## 7. Общее качество кода

### BUG-04: Мертвый файл DashboardPage.tsx

- **Серьезность:** Низкая
- **Описание:** `DashboardPage.tsx` не импортируется нигде. Содержит устаревший код с hardcoded цветами и прямыми `<a>` ссылками вместо `NavLink`.
- **Рекомендация:** Удалить файл.

### BUG-05: `useMemo` с неполными зависимостями в EmployeesPage

- **Серьезность:** Средняя
- **Описание:** В `EmployeesPage.tsx:91-102`:
  ```tsx
  const actionsNode = useMemo(() => (
    <div className="flex items-center gap-2">
      <Input value={search} onChange={e => setSearch(e.target.value)} />
      ...
    </div>
  ), [search])
  ```
  `useMemo` зависит только от `search`, но содержит `setSearch`. Формально `setSearch` стабилен (из `useState`), но `setSearch` не указан в deps. Lint может предупредить.
- **Рекомендация:** Добавить `setSearch` в зависимости или оставить как есть (React гарантирует стабильность setter).

### RISK-04: ProtectedRoute не проверяет загрузку auth state

- **Серьезность:** Средняя
- **Описание:** В `App.tsx:40-47`:
  ```tsx
  function ProtectedRoute({ children, allowedRoles }: ProtectedRouteProps) {
    const { isAuthenticated, user } = useAuthStore()
    if (!isAuthenticated) return <Navigate to="/login" replace />
    ...
  }
  ```
  Нет обработки состояния "auth загружается" (например, при восстановлении сессии из localStorage). Если `useAuthStore` возвращает `isAuthenticated: false` до полной инициализации, пользователь будет перенаправлен на логин даже при наличии валидного токена.
- **Рекомендация:** Добавить `isLoading` состояние в authStore.

### RISK-05: `QueryClient` создается снаружи компонента

- **Серьезность:** Низкая
- **Описание:** В `App.tsx:27-33` `queryClient` создается на уровне модуля. При SSR или тестах это может вызвать shared state. Для SPA-приложения это допустимо.

### RISK-06: LoginPage использует `(window as any).onTelegramAuth`

- **Серьезность:** Низкая
- **Описание:** Глобальная функция на window для Telegram Widget. Корректно очищается в cleanup (`delete (window as any).onTelegramAuth`). Допустимый подход для интеграции с Telegram Widget.

---

## Чеклист покрытия

- [x] window.confirm / window.alert -- удалены
- [x] ConfirmDialog -- используется корректно (с замечаниями по `loading`)
- [x] Toast покрытие -- 100% мутаций покрыто
- [x] Error Boundaries -- GlobalErrorBoundary + PageErrorBoundary на всех маршрутах
- [x] Hardcoded цвета -- допустимы в TWA, ResidentBoard; найдены minor issues в toggle и login
- [x] Responsive sidebar -- три состояния, CSS variables, mobile overlay, keyboard navigation
- [x] Мертвый код -- DashboardPage.tsx (удалить)
- [x] Lazy loading -- все не-critical страницы загружаются через `lazy()`
- [x] Accessibility -- aria-labels на sidebar, user dropdown, dialogs

---

## Сводка багов и рисков

### Баги (требуют исправления)

| # | Серьезность | Описание | Файл |
|---|---|---|---|
| BUG-01 | Средняя | Отсутствует `loading` проп в ConfirmDialog для адресов | `AddressesPage.tsx:708`, `AddressTable.tsx:140,227,316` |
| BUG-02 | Средняя | ConfirmDialog закрывается до завершения async операции | `ConfirmDialog.tsx:54-56` |
| BUG-03 | Низкая | Мертвый файл DashboardPage.tsx с hardcoded цветами | `DashboardPage.tsx` |
| BUG-04 | Низкая | Мертвый файл (дубль BUG-03) | `DashboardPage.tsx` |
| BUG-05 | Низкая | `useMemo` без `setSearch` в deps | `EmployeesPage.tsx:102` |

### Риски (мониторинг)

| # | Описание | Файл |
|---|---|---|
| RISK-01 | `bg-white` в toggle-кнопках (работает, но формально hardcoded) | `TemplatesPage.tsx:422` |
| RISK-02 | `bg-white/[.07]` на login page (только dark theme) | `LoginPage.tsx:137` |
| RISK-03 | Hex-цвета для статусов вместо CSS-переменных | Kanban, Shifts, Analytics |
| RISK-04 | ProtectedRoute не проверяет загрузку auth state | `App.tsx:40-47` |
| RISK-05 | QueryClient на уровне модуля | `App.tsx:27-33` |
| RISK-06 | `window.onTelegramAuth` глобальная функция | `LoginPage.tsx:20` |

---

## Что реализовано корректно

1. **Полная замена window.confirm/alert** -- все деструктивные действия используют ConfirmDialog с variant="danger" или "warning".
2. **Toast-уведомления** -- каждая из 28 мутаций имеет и success, и error toast с описательным текстом на русском.
3. **Error Boundaries** -- двухуровневая система (Global + Page) с грамотным fallback UI на CSS variables.
4. **Lazy loading** -- все тяжелые страницы загружаются через `React.lazy()` с `Suspense` fallback.
5. **Responsive sidebar** -- три состояния с CSS-переменными, mobile overlay с backdrop-blur, keyboard navigation (Escape).
6. **Semantic tokens** -- основной UI использует `bg-bg-card`, `text-text-primary`, `border-border-default` и т.д. через Tailwind CSS 4 `@theme`.
7. **Role-based routing** -- `ProtectedRoute` с `allowedRoles` prop (хотя пока не используется нигде кроме auth check).
8. **Topbar context** -- гибкая система для page-specific действий в topbar через `TopbarProvider`.
9. **UserDropdown** -- полноценное меню с click-outside detection, Escape, accessibility attributes.
10. **Dark/Light theme toggle** -- `useTheme` хук с body class `light`.

---

## Приоритетные действия

1. **[Средний]** Добавить `loading` проп в ConfirmDialog для AddressesPage и AddressTable
2. **[Средний]** Исправить ConfirmDialog: не закрывать автоматически при клике "Подтвердить" (оставить управление вызывающему коду)
3. **[Низкий]** Удалить мертвый `DashboardPage.tsx`
4. **[Низкий]** Рассмотреть вынос hex-цветов статусов в CSS-переменные
