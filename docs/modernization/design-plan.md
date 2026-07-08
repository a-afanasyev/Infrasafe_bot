# Дизайн-план модернизации: UK Management Frontend

> _Последнее редактирование: 2026-03-19_

**Дата**: 19 марта 2026
**Автор**: Enterprise UX Architect
**На основе**: UX-аудит от 19.03.2026 (`docs/ux-audit-report.md`)
**Целевая аудитория документа**: фронтенд-разработчики

---

## Содержание

1. [Дизайн-система](#1-дизайн-система)
2. [Компонентный каталог](#2-компонентный-каталог)
3. [Макеты страниц](#3-макеты-страниц)
4. [UX-паттерны](#4-ux-паттерны)
5. [Навигация и информационная архитектура](#5-навигация-и-информационная-архитектура)

---

## 1. Дизайн-система

### 1.1 Стратегическое решение по стилизации

**Единый подход**: Tailwind CSS 4 + CSS-переменные для темизации.

Все inline `style={{}}` объекты подлежат миграции на Tailwind utility-классы. CSS-переменные (design tokens) остаются в `index.css` и используются через `var()` в Tailwind-конфигурации и кастомных утилитах.

Утилитарные зависимости, уже установленные в проекте:
- `class-variance-authority` (CVA) -- для вариантов компонентов
- `clsx` -- для условных классов
- `tailwind-merge` -- для разрешения конфликтов Tailwind-классов

Рекомендуемый хелпер `cn()`:

```ts
// src/lib/utils.ts
import { type ClassValue, clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}
```

### 1.2 Design Tokens (обновленные)

#### 1.2.1 Цветовая палитра

Все цвета проверены на соответствие WCAG 2.1 AA (контраст >= 4.5:1 для текста, >= 3:1 для крупного текста и UI-элементов).

```css
:root {
  /* ── Background ── */
  --bg-root: #080c14;
  --bg-primary: #0c1220;
  --bg-secondary: #111927;
  --bg-card: #151e2e;
  --bg-card-hover: #1a2740;
  --bg-surface: #1e2d42;
  --bg-sidebar: #0a0e18;
  --bg-overlay: rgba(0, 0, 0, 0.6);

  /* ── Accent (brand) ── */
  --accent: #00d4aa;
  --accent-hover: #00eabc;
  --accent-dim: rgba(0, 212, 170, 0.12);
  --accent-glow: rgba(0, 212, 170, 0.25);
  --accent-on: #002e24;  /* текст на accent-фоне */

  /* ── Semantic ── */
  --color-success: #22c55e;
  --color-success-dim: rgba(34, 197, 94, 0.12);
  --color-warning: #f59e0b;
  --color-warning-dim: rgba(245, 158, 11, 0.12);
  --color-error: #ef4444;
  --color-error-dim: rgba(239, 68, 68, 0.12);
  --color-info: #3b82f6;
  --color-info-dim: rgba(59, 130, 246, 0.12);

  /* ── Extended palette ── */
  --blue: #3b82f6;
  --violet: #8b5cf6;
  --amber: #f59e0b;
  --cyan: #06b6d4;
  --emerald: #10b981;
  --green: #22c55e;
  --teal: #14b8a6;
  --red: #ef4444;

  /* ── Text ── */
  --text-primary: #edf2f7;          /* на --bg-root: контраст 15.2:1 */
  --text-secondary: #94a3b8;        /* на --bg-root: контраст 6.8:1  */
  --text-muted: #6b7b8f;            /* на --bg-root: контраст 4.6:1  -- исправлено с #5a6a7a (3.7:1) */
  --text-on-accent: #002e24;        /* на --accent фоне */
  --text-on-color: #ffffff;         /* на semantic color фонах */

  /* ── Border ── */
  --border: rgba(255, 255, 255, 0.10);    /* исправлено с 0.06 для видимости */
  --border-hover: rgba(255, 255, 255, 0.18);
  --border-active: rgba(0, 212, 170, 0.4);
  --border-error: rgba(239, 68, 68, 0.5);
  --border-focus: rgba(0, 212, 170, 0.6);

  /* ── Radius ── */
  --radius-xs: 4px;
  --radius-sm: 6px;
  --radius: 8px;
  --radius-md: 10px;
  --radius-lg: 12px;
  --radius-xl: 16px;
  --radius-full: 9999px;

  /* ── Typography ── */
  --font-display: 'Outfit', system-ui, sans-serif;
  --font-body: 'DM Sans', system-ui, sans-serif;
  --font-mono: 'IBM Plex Mono', ui-monospace, monospace;

  /* ── Layout ── */
  --sidebar-w: 260px;
  --sidebar-w-collapsed: 64px;
  --topbar-h: 56px;      /* уменьшено с 64px -- экономия вертикального пространства */
  --page-padding: 24px;
  --content-max-w: 1440px;

  /* ── Z-index ── */
  --z-dropdown: 100;
  --z-sticky: 200;
  --z-overlay: 300;
  --z-modal: 400;
  --z-toast: 500;
  --z-tooltip: 600;
}

body.light {
  --bg-root: #f1f5f9;
  --bg-primary: #ffffff;
  --bg-secondary: #f8fafc;
  --bg-card: #ffffff;
  --bg-card-hover: #f1f5f9;
  --bg-surface: #e2e8f0;
  --bg-sidebar: #ffffff;
  --bg-overlay: rgba(0, 0, 0, 0.4);

  --accent-on: #ffffff;

  --text-primary: #0f172a;          /* на --bg-root: контраст 13.1:1 */
  --text-secondary: #475569;        /* на --bg-root: контраст 7.1:1  */
  --text-muted: #64748b;            /* на --bg-root: контраст 5.2:1  */
  --text-on-accent: #ffffff;

  --border: rgba(0, 0, 0, 0.10);
  --border-hover: rgba(0, 0, 0, 0.18);
  --border-active: rgba(0, 212, 170, 0.5);
  --border-error: rgba(239, 68, 68, 0.5);
  --border-focus: rgba(0, 212, 170, 0.6);
}
```

#### 1.2.2 Типографическая шкала

Базовый размер: 14px (для enterprise-приложений оптимален). Шкала основана на Major Second (1.125).

| Токен           | Размер | Высота строки | Начертание | Шрифт        | Использование                     |
|-----------------|--------|---------------|------------|--------------|-----------------------------------|
| `text-xs`       | 11px   | 16px (1.45)   | 400        | --font-body  | Метки, timestamps, подписи        |
| `text-sm`       | 12px   | 18px (1.5)    | 400        | --font-body  | Secondary text, descriptions      |
| `text-base`     | 14px   | 20px (1.43)   | 400        | --font-body  | Основной текст, ячейки таблиц     |
| `text-md`       | 15px   | 22px (1.47)   | 500        | --font-body  | Выделенный текст, навигация       |
| `text-lg`       | 16px   | 24px (1.5)    | 600        | --font-display| Section titles                    |
| `text-xl`       | 18px   | 26px (1.44)   | 600        | --font-display| Page subtitle, card header        |
| `text-2xl`      | 22px   | 28px (1.27)   | 700        | --font-display| Page title                        |
| `text-3xl`      | 28px   | 34px (1.21)   | 700        | --font-display| KPI values                        |
| `text-mono-sm`  | 12px   | 18px (1.5)    | 500        | --font-mono  | Телефоны, коды, timestamps        |
| `text-mono-lg`  | 22px   | 28px (1.27)   | 600        | --font-mono  | KPI числа, метрики                |

**Загрузка шрифтов**: Добавить в `index.html` до любых стилей:

```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,400;0,9..40,500;0,9..40,600;0,9..40,700;1,9..40,400&family=IBM+Plex+Mono:wght@400;500;600&family=Outfit:wght@400;500;600;700&display=swap" rel="stylesheet">
```

#### 1.2.3 Spacing System (4px grid)

Все отступы, padding, gap, margin задаются кратно 4px.

| Токен   | Значение | Использование                                    |
|---------|----------|--------------------------------------------------|
| `sp-0`  | 0px      |                                                  |
| `sp-0.5`| 2px      | Micro gap (между badge и текстом)                |
| `sp-1`  | 4px      | Tight gap (inline элементы, gap в badge-группах)  |
| `sp-2`  | 8px      | Small gap (gap между кнопками, padding в badge)   |
| `sp-3`  | 12px     | Medium gap (gap между карточками в ряду)          |
| `sp-4`  | 16px     | Default gap (padding карточек, gap между секциями)|
| `sp-5`  | 20px     | Section padding                                  |
| `sp-6`  | 24px     | Page padding, large gap                          |
| `sp-8`  | 32px     | Section separator                                |
| `sp-10` | 40px     | Large section separator                          |
| `sp-12` | 48px     | Empty state padding                              |

**Правило**: Никогда не использовать значения вне сетки (10px, 14px, 18px, 28px и т.д.). Исключение -- размеры шрифтов и line-height, которые следуют типографической шкале.

Маппинг в Tailwind (стандартный spacing Tailwind уже на 4px-сетке):
- `p-1` = 4px, `p-2` = 8px, `p-3` = 12px, `p-4` = 16px, `p-5` = 20px, `p-6` = 24px, `p-8` = 32px

#### 1.2.4 Elevation / Shadow System

| Уровень     | CSS                                              | Использование                      |
|-------------|--------------------------------------------------|------------------------------------|
| `shadow-xs` | `0 1px 2px rgba(0,0,0,0.20)`                    | Card default (dark theme)          |
| `shadow-sm` | `0 2px 8px rgba(0,0,0,0.25)`                    | Card hover, input focus            |
| `shadow-md` | `0 4px 16px rgba(0,0,0,0.30)`                   | Dropdown, popover                  |
| `shadow-lg` | `0 8px 32px rgba(0,0,0,0.35)`                   | Modal, side sheet                  |
| `shadow-xl` | `0 16px 48px rgba(0,0,0,0.40)`                  | Full-screen overlay                |

Светлая тема использует меньшую opacity:
| Уровень     | CSS (light)                                      |
|-------------|--------------------------------------------------|
| `shadow-xs` | `0 1px 2px rgba(0,0,0,0.06)`                    |
| `shadow-sm` | `0 2px 8px rgba(0,0,0,0.08)`                    |
| `shadow-md` | `0 4px 16px rgba(0,0,0,0.12)`                   |
| `shadow-lg` | `0 8px 32px rgba(0,0,0,0.16)`                   |
| `shadow-xl` | `0 16px 48px rgba(0,0,0,0.20)`                  |

#### 1.2.5 Transition / Animation Tokens

| Токен              | Значение                       | Использование              |
|--------------------|--------------------------------|----------------------------|
| `duration-fast`    | 100ms                          | Hover color change         |
| `duration-normal`  | 200ms                          | Button press, toggle       |
| `duration-slow`    | 300ms                          | Modal enter/exit, sidebar  |
| `easing-default`   | cubic-bezier(0.4, 0, 0.2, 1)  | Большинство transitions    |
| `easing-in`        | cubic-bezier(0.4, 0, 1, 1)    | Exit animations            |
| `easing-out`       | cubic-bezier(0, 0, 0.2, 1)    | Enter animations           |

**Убрать**: все `translateY(-2px)` hover-эффекты на карточках. Enterprise-UI не должен "прыгать" -- достаточно border-color + box-shadow change.

#### 1.2.6 Иконки

Единственный источник иконок: `lucide-react`. Все emoji подлежат замене на Lucide-иконки.

| Текущее | Замена (lucide-react)     | Контекст               |
|---------|--------------------------|------------------------|
| `👥`    | `<Users />`              | KPI сотрудников        |
| `🟢`    | `<CircleDot />`          | Статус "на смене"      |
| `⏳`    | `<Clock />`              | Ожидание               |
| `✓`     | `<Check />`              | Верификация            |
| `📋`    | `<ClipboardList />`      | Шаблоны                |
| `🏘`    | `<Building />`           | Дворы                  |
| `🏢`    | `<Building2 />`          | Здания                 |
| `🏠`    | `<Home />`               | Квартиры               |
| `👥`    | `<Users />`              | Жители                 |
| `👤`    | `<User />`               | Профиль                |
| `→`     | `<LogOut />`             | Выход                  |
| `⊞`     | `<LayoutGrid />`         | Вид плитки             |
| `☰`     | `<List />`               | Вид таблицы            |
| `📊`    | `<BarChart3 />`          | Нет данных (аналитика) |
| `🥇🥈🥉`| `<Trophy />` + цвет     | Рейтинг                |
| `🤖📱🌐📞`| `<Bot />` `<Smartphone />` `<Globe />` `<Phone />`| Источник заявки |

Размеры иконок:
- В кнопках: 16px
- В навигации: 18px
- В KPI/stats: 24px
- В empty states: 48px (внутри контейнера 64x64)

---

## 2. Компонентный каталог

Все компоненты размещаются в `src/components/ui/`.
Каждый компонент реализуется через CVA для вариантов.

### 2.1 Button

**Файл**: `src/components/ui/Button.tsx`

**Варианты (variant)**:
| Variant     | Фон                    | Текст               | Border               | Использование             |
|-------------|------------------------|----------------------|----------------------|---------------------------|
| `primary`   | var(--accent)          | var(--text-on-accent)| none                 | CTA, основное действие    |
| `secondary` | transparent            | var(--text-secondary)| 1px solid var(--border)| Альтернативное действие  |
| `ghost`     | transparent            | var(--text-secondary)| none                 | Третичное действие        |
| `danger`    | var(--color-error-dim) | var(--red)           | 1px solid var(--border-error)| Деструктивное действие |
| `danger-filled` | var(--red)         | white                | none                 | Confirm delete в диалоге  |

**Размеры (size)**:
| Size    | Padding (v/h) | Font size | Height | Icon size |
|---------|---------------|-----------|--------|-----------|
| `sm`    | 4px 12px      | 12px      | 28px   | 14px      |
| `md`    | 6px 16px      | 13px      | 32px   | 16px      |
| `lg`    | 8px 20px      | 14px      | 40px   | 18px      |

**Состояния**:
- **default**: Как описано в таблице
- **hover**: `primary` -- bg lighten 8%; `secondary/ghost` -- bg = var(--bg-surface); `danger` -- bg opacity +10%
- **active (pressed)**: Scale(0.98), bg darken 5%
- **focus-visible**: `outline: 2px solid var(--border-focus); outline-offset: 2px`
- **disabled**: `opacity: 0.5; cursor: not-allowed; pointer-events: none`
- **loading**: Содержимое заменяется на Spinner (16px) + текст "..." или кастомный loadingText. Button disabled во время loading.

**Дополнительные props**:
- `iconLeft?: ReactNode` -- иконка слева от текста
- `iconRight?: ReactNode` -- иконка справа от текста
- `iconOnly?: boolean` -- кнопка только с иконкой (квадратная, padding равный)
- `fullWidth?: boolean` -- width: 100%
- `loading?: boolean`

**A11y**:
- Нативный `<button>` или `<a>` (если `asLink`)
- `aria-disabled="true"` при disabled (вместо HTML disabled для focusability)
- `aria-busy="true"` при loading
- `aria-label` обязателен для iconOnly-кнопок
- `:focus-visible` outline обязателен (НЕ `outline: none`)

**ASCII-mockup** (size=md, variant=primary, с иконкой):
```
+-----------------------------+
|  [icon]  Создать заявку     |
+-----------------------------+
     16px    gap=8px   text
```

### 2.2 Input

**Файл**: `src/components/ui/Input.tsx`

**Размеры**:
| Size    | Height | Padding     | Font size |
|---------|--------|-------------|-----------|
| `sm`    | 32px   | 6px 12px    | 13px      |
| `md`    | 36px   | 8px 12px    | 14px      |
| `lg`    | 44px   | 10px 16px   | 15px      |

**Структура**:
```
[Label]                        [helper counter "3/100"]
+--[prefix-icon]---[input text]---[suffix/clear-btn]--+
|                                                      |
+------------------------------------------------------+
[Error message / Help text]
```

**Состояния**:
- **default**: bg = var(--bg-card), border = var(--border), text = var(--text-primary)
- **hover**: border = var(--border-hover)
- **focus**: border = var(--border-focus), box-shadow = `0 0 0 3px var(--accent-dim)`
- **error**: border = var(--border-error), error message красным ниже
- **disabled**: opacity: 0.5, bg = var(--bg-surface), cursor: not-allowed
- **readonly**: bg = var(--bg-surface), border = var(--border), cursor: default

**Дополнительные props**:
- `label?: string` -- текст лейбла над инпутом
- `error?: string` -- текст ошибки под инпутом
- `hint?: string` -- вспомогательный текст
- `prefixIcon?: ReactNode` -- иконка слева (внутри поля)
- `suffix?: ReactNode` -- элемент справа (иконка, кнопка очистки)
- `clearable?: boolean` -- кнопка очистки при наличии значения

**A11y**:
- `<label>` связан с `<input>` через `htmlFor`/`id` (автогенерируемый id если не указан)
- `aria-describedby` связывает с error/hint текстом
- `aria-invalid="true"` при наличии error
- `aria-required="true"` при required
- `:focus-visible` на input (НЕ `outline: none`)

### 2.3 Select

**Файл**: `src/components/ui/Select.tsx`

Реализация на базе нативного `<select>` для максимальной accessibility. Для complex-случаев (multi-select, search, groups) -- отдельный компонент `Combobox`.

**Внешний вид**: Идентичен Input, но с `<ChevronDown />` справа.

**Состояния**: Аналогичны Input.

**A11y**:
- Нативный `<select>` -- полная keyboard accessibility из коробки
- `<label>` обязателен
- `aria-describedby` для error/hint

### 2.4 Textarea

**Файл**: `src/components/ui/Textarea.tsx`

Аналогичен Input, но многострочный. Дополнительные props:
- `rows?: number` (default: 3)
- `maxLength?: number` -- с отображением счётчика символов справа вверху
- `autoResize?: boolean` -- автоматическое увеличение высоты по содержимому

### 2.5 Modal / Dialog

**Файл**: `src/components/ui/Modal.tsx`

**КРИТИЧЕСКИ ВАЖНЫЙ КОМПОНЕНТ** -- заменяет все 6+ текущих реализаций модальных окон.

**Размеры**:
| Size    | Max-width | Использование                        |
|---------|-----------|--------------------------------------|
| `sm`    | 400px     | Confirm dialog, простые формы        |
| `md`    | 560px     | Формы, детали объекта                |
| `lg`    | 720px     | Сложные формы, таблицы внутри        |
| `xl`    | 960px     | RequestDetailModal, report views     |
| `full`  | calc(100vw - 48px) | Максимальное, почти full-screen |

**Структура**:
```
+============================================+
|  (overlay: var(--bg-overlay), click=close) |
|  +--------------------------------------+  |
|  |  [Title]               [X close btn] |  |  <-- Header (sticky)
|  +--------------------------------------+  |
|  |                                      |  |
|  |  [Content area, scrollable]          |  |  <-- Body
|  |                                      |  |
|  +--------------------------------------+  |
|  |  [Secondary btn]   [Primary btn]     |  |  <-- Footer (sticky, optional)
|  +--------------------------------------+  |
+============================================+
```

**Props**:
- `open: boolean`
- `onClose: () => void`
- `title: string`
- `description?: string` -- подзаголовок
- `size?: 'sm' | 'md' | 'lg' | 'xl' | 'full'`
- `children: ReactNode` -- body content
- `footer?: ReactNode` -- footer content (кнопки)
- `closeOnOverlayClick?: boolean` (default: true)
- `closeOnEscape?: boolean` (default: true)
- `preventClose?: boolean` -- для форм с несохранёнными данными

**Анимация**:
- Вход: overlay fadeIn 200ms, dialog scaleIn(0.95->1) + fadeIn 200ms
- Выход: overlay fadeOut 150ms, dialog scaleOut(1->0.95) + fadeOut 150ms

**A11y**:
- `role="dialog"`, `aria-modal="true"`
- `aria-labelledby` -> title element id
- `aria-describedby` -> description element id
- **Focus trap**: При открытии фокус перемещается на первый focusable element внутри. Tab/Shift+Tab циклически перемещаются внутри модала.
- **Escape**: Закрывает модал (если closeOnEscape=true)
- **Return focus**: При закрытии фокус возвращается на элемент, который открыл модал
- Close button: `aria-label="Закрыть"`

### 2.6 ConfirmDialog

**Файл**: `src/components/ui/ConfirmDialog.tsx`

Построен поверх Modal (size="sm"). Заменяет все `window.confirm()`.

**Props**:
- `open: boolean`
- `onConfirm: () => void`
- `onCancel: () => void`
- `title: string` -- "Удаление двора"
- `message: string | ReactNode` -- описание последствий
- `confirmLabel?: string` (default: "Подтвердить")
- `cancelLabel?: string` (default: "Отмена")
- `variant?: 'danger' | 'warning' | 'default'`
- `loading?: boolean` -- для async confirm

**Layout**:
```
+--------------------------------------+
|  [WarningTriangle icon]              |
|                                      |
|  Удаление двора                      |
|                                      |
|  Вы уверены, что хотите удалить      |
|  двор "Центральный"? Будут удалены   |
|  все здания и квартиры.              |
|  Это действие нельзя отменить.       |
|                                      |
|  +------------+   +---------------+  |
|  |   Отмена   |   |   Удалить     |  |
|  +------------+   +---------------+  |
|  (secondary)       (danger-filled)   |
+--------------------------------------+
```

**A11y**:
- `role="alertdialog"` (не `dialog` -- для destructive actions)
- При открытии фокус на кнопку "Отмена" (безопасное действие)
- Enter на "Отмена" -- закрывает. Tab -> "Удалить" -> Enter подтверждает.

### 2.7 Toast / Notification

**Файл**: `src/components/ui/Toast.tsx` + `src/components/ui/Toaster.tsx`

Рекомендуемая библиотека: `sonner` (2KB, React 19 compatible, accessible).

**Варианты**:
| Variant   | Иконка          | Border left color   | Использование              |
|-----------|-----------------|---------------------|----------------------------|
| `success` | `<Check />`     | var(--color-success)| Успешные мутации           |
| `error`   | `<X />`         | var(--color-error)  | Ошибки API, валидации      |
| `warning` | `<AlertTriangle/>` | var(--color-warning)| Предупреждения          |
| `info`    | `<Info />`      | var(--color-info)   | Информационные сообщения   |

**Позиция**: top-right, с отступом 16px от краёв.
**Поведение**: Стек (до 3 видимых одновременно), auto-dismiss через 4 секунды (error -- 6 секунд). Hover приостанавливает таймер. Swipe right для dismiss.

**Структура одного toast**:
```
+--+--------------------------------------+-+
|  |  [icon] Сотрудник заблокирован       |X|
|  |         Иванов И.И. заблокирован     | |
|  |         [Отменить]                   | |
+--+--------------------------------------+-+
 ^  border-left 3px color
```

**API использования**:
```tsx
import { toast } from 'sonner'

// После успешной мутации:
toast.success('Двор создан', { description: `"${name}" добавлен в справочник` })

// При ошибке:
toast.error('Не удалось сохранить', { description: error.message })

// С undo:
toast.success('Сотрудник заблокирован', {
  description: `${name} заблокирован`,
  action: { label: 'Отменить', onClick: () => unblock(id) },
})
```

**A11y**:
- `role="status"`, `aria-live="polite"` (для success/info)
- `role="alert"`, `aria-live="assertive"` (для error/warning)
- Close button: `aria-label="Закрыть уведомление"`

### 2.8 Badge / Chip

**Файл**: `src/components/ui/Badge.tsx`

**Варианты (variant)**:
| Variant     | Фон                                   | Текст            | Использование              |
|-------------|----------------------------------------|------------------|----------------------------|
| `default`   | var(--bg-surface)                      | var(--text-secondary) | Default, counts        |
| `accent`    | var(--accent-dim)                      | var(--accent)    | Active filters, counts     |
| `success`   | var(--color-success-dim)               | var(--color-success) | Verified, active       |
| `warning`   | var(--color-warning-dim)               | var(--color-warning) | Pending                |
| `error`     | var(--color-error-dim)                 | var(--color-error)   | Blocked, critical      |
| `info`      | var(--color-info-dim)                  | var(--color-info)    | Info badges            |

**Размеры**:
| Size | Padding   | Font size | Height |
|------|-----------|-----------|--------|
| `sm` | 2px 6px   | 10px      | 18px   |
| `md` | 2px 8px   | 11px      | 22px   |
| `lg` | 4px 12px  | 12px      | 26px   |

**Дополнительные props**:
- `dot?: boolean` -- цветная точка слева от текста (для статусов)
- `removable?: boolean` -- кнопка X для удаления (фильтры)
- `onRemove?: () => void`

**border-radius**: var(--radius-full) (pill shape).

### 2.9 Table

**Файл**: `src/components/ui/Table.tsx`

**КРИТИЧЕСКИ ВАЖНО**: Всегда использовать семантический `<table>`, `<thead>`, `<tbody>`, `<tr>`, `<th>`, `<td>`. Никаких CSS Grid `<div>` таблиц.

**Структура**:
```
+====================================================================+
| [Checkbox] | Имя          | Роль       | Статус    | Действия     |  <-- thead
+--------------------------------------------------------------------+
| [x]        | Иванов И.И.  | Исполнитель| [On shift]| [...]        |  <-- tbody tr
| [ ]        | Петров П.П.  | Менеджер   | [Off]     | [...]        |
| [ ]        | Сидоров С.С. | Исполнитель| [Blocked] | [...]        |
+--------------------------------------------------------------------+
|  Выбрано: 1  [Заблокировать]  [Экспорт]           | 1-25 из 143   |  <-- tfoot
+====================================================================+
```

**Props**:
- `columns: Column[]` -- определение колонок (key, header, width, sortable, align)
- `data: T[]` -- данные
- `sortBy?: string` -- текущая колонка сортировки
- `sortOrder?: 'asc' | 'desc'`
- `onSort?: (key: string) => void`
- `selectable?: boolean` -- checkbox-колонка
- `selectedIds?: Set<string|number>`
- `onSelectionChange?: (ids: Set<string|number>) => void`
- `onRowClick?: (item: T) => void`
- `stickyHeader?: boolean` (default: true)
- `emptyState?: ReactNode`
- `loading?: boolean`

**Плотность (density)**:
| Density     | Row height | Cell padding |
|-------------|------------|--------------|
| `compact`   | 36px       | 6px 12px     |
| `comfortable`| 48px      | 10px 16px    |
| `spacious`  | 56px       | 14px 16px    |

Default: `comfortable`.

**Состояния строки**:
- **default**: bg transparent
- **hover**: bg = var(--bg-card-hover)
- **selected**: bg = var(--accent-dim), border-left = 3px solid var(--accent)
- **striped** (опционально): четные строки bg = var(--bg-secondary)

**A11y**:
- Семантический `<table>` с `<caption>` (screen reader only если визуально скрыт)
- `<th scope="col">` для заголовков
- `aria-sort="ascending|descending|none"` для sortable-заголовков
- Checkbox: `aria-label="Выбрать строку {name}"` / `aria-label="Выбрать все"`
- Keyboard: Tab между rows, Enter/Space для select, arrow keys для navigation внутри строки

### 2.10 Card

**Файл**: `src/components/ui/Card.tsx`

**Варианты**:
| Variant    | Описание                                   |
|------------|--------------------------------------------|
| `default`  | bg=card, border, radius                    |
| `outlined` | bg=transparent, border only                |
| `elevated` | bg=card, shadow-sm, no border              |
| `interactive` | default + hover border-color change + cursor pointer |

**Props**:
- `variant?: 'default' | 'outlined' | 'elevated' | 'interactive'`
- `padding?: 'none' | 'sm' | 'md' | 'lg'` (default: 'md' = 16px)
- `onClick?: () => void` (автоматически переключает в interactive mode)
- `header?: ReactNode`
- `footer?: ReactNode`
- `children: ReactNode`

**Hover для interactive**:
- border-color: var(--accent) -- НЕ translateY. Только border и shadow.
- box-shadow: shadow-sm
- Transition: duration-fast

### 2.11 Toggle / Switch

**Файл**: `src/components/ui/Toggle.tsx`

**КРИТИЧЕСКИ ВАЖНО**: Использовать `<button role="switch">`, НЕ `<div onClick>`.

**Размеры**:
| Size | Track W | Track H | Thumb  |
|------|---------|---------|--------|
| `sm` | 32px    | 18px    | 14px   |
| `md` | 40px    | 22px    | 18px   |

**Состояния**:
- **off**: Track bg = var(--bg-surface), thumb left
- **on**: Track bg = var(--accent), thumb right
- **disabled**: opacity 0.5
- **focus-visible**: outline на track

**Props**:
- `checked: boolean`
- `onChange: (checked: boolean) => void`
- `disabled?: boolean`
- `label?: string` -- текст справа от переключателя
- `size?: 'sm' | 'md'`

**A11y**:
- `<button role="switch" aria-checked={checked}>`
- `aria-label` или связанный label
- Space/Enter для toggle
- НЕ `<input type="checkbox">` стилизованный -- именно `role="switch"` для семантики switch

### 2.12 Dropdown / Menu

**Файл**: `src/components/ui/DropdownMenu.tsx`

Заменяет текущий `ActionMenu` из AddressesPage и user menu из DashboardLayout.

**Структура**:
```
[Trigger button]
       |
       v
+----------------------------+
|  MenuItem: Редактировать   |
|  MenuItem: Деактивировать  |
|  ─────────────────── (sep) |
|  MenuItem: Удалить  (red)  |
+----------------------------+
```

**Props (Root)**:
- `trigger: ReactNode` -- элемент, открывающий меню
- `align?: 'start' | 'center' | 'end'` (default: 'end')
- `side?: 'top' | 'bottom'` (default: 'bottom')

**Props (MenuItem)**:
- `label: string`
- `icon?: ReactNode`
- `onClick: () => void`
- `danger?: boolean` -- красный текст
- `disabled?: boolean`
- `shortcut?: string` -- отображение горячей клавиши справа

**A11y**:
- Trigger: `aria-haspopup="menu"`, `aria-expanded`
- Menu container: `role="menu"`
- Items: `role="menuitem"`
- Separator: `role="separator"`
- Keyboard: Enter/Space на trigger открывает. Arrow Down/Up навигируют. Enter на item -- action. Escape закрывает.
- Click outside закрывает.

### 2.13 Breadcrumb

**Файл**: `src/components/ui/Breadcrumb.tsx`

**Структура**:
```
Дворы  >  Центральный  >  ул. Пушкина 10
 ^link      ^link            ^current (no link)
```

**Props**:
```ts
interface BreadcrumbItem {
  label: string
  href?: string       // если есть -- кликабельный
  onClick?: () => void // альтернатива href
}

interface BreadcrumbProps {
  items: BreadcrumbItem[]
}
```

**A11y**:
- `<nav aria-label="Навигация">`
- `<ol>` с `<li>` для каждого элемента
- Separator: `aria-hidden="true"` (визуальный `>` или `ChevronRight`)
- Последний элемент: `aria-current="page"`

### 2.14 Tabs

**Файл**: `src/components/ui/Tabs.tsx`

Заменяет текущие tab-кнопки в AddressesPage ("Справочник"/"Модерация").

**Варианты**:
| Variant    | Описание                                           |
|------------|-----------------------------------------------------|
| `underline`| Нижняя линия под активным табом (default)           |
| `pill`     | Active tab имеет pill-background (как сейчас)       |

**Props**:
- `tabs: { key: string, label: string, badge?: number, icon?: ReactNode }[]`
- `activeKey: string`
- `onChange: (key: string) => void`
- `variant?: 'underline' | 'pill'`

**A11y**:
- `role="tablist"` на контейнере
- `role="tab"` на каждом табе
- `aria-selected`, `tabindex`
- Arrow Left/Right для навигации между табами
- `role="tabpanel"` на контенте
- `aria-labelledby` связывает panel с tab

### 2.15 Tooltip

**Файл**: `src/components/ui/Tooltip.tsx`

**Props**:
- `content: string | ReactNode`
- `side?: 'top' | 'bottom' | 'left' | 'right'` (default: 'top')
- `delay?: number` (default: 400ms)
- `children: ReactNode` -- trigger element

**Стиль**: bg = var(--bg-surface), border = var(--border), shadow-md, font-size: 12px, padding: 6px 10px, border-radius: var(--radius-sm), max-width: 240px.

**A11y**:
- `role="tooltip"`, `id` уникальный
- Trigger: `aria-describedby={tooltipId}`
- Появляется при hover и focus (не только hover)
- Escape скрывает tooltip

### 2.16 Pagination

**Файл**: `src/components/ui/Pagination.tsx`

**Структура**:
```
Показано 1-25 из 143       [<] [1] [2] [3] ... [6] [>]
     ^info                          ^page buttons
```

**Props**:
- `page: number` -- текущая страница (1-based)
- `pageSize: number`
- `total: number`
- `onPageChange: (page: number) => void`
- `onPageSizeChange?: (size: number) => void`
- `pageSizeOptions?: number[]` (default: [25, 50, 100])

**A11y**:
- `<nav aria-label="Пагинация">`
- Кнопки: `aria-label="Страница 3"`, `aria-current="page"` для текущей
- Previous/Next: `aria-label="Предыдущая страница"` / `aria-label="Следующая страница"`
- Disabled при первой/последней странице

### 2.17 EmptyState (обновлённый)

**Файл**: `src/components/ui/EmptyState.tsx`

Обновление существующего компонента с добавлением CTA.

**Props**:
- `icon: ReactNode` -- Lucide icon (НЕ emoji)
- `title: string`
- `description?: string`
- `action?: { label: string, onClick: () => void, icon?: ReactNode }` -- кнопка CTA
- `compact?: boolean` -- уменьшенная версия для inline-использования

**Layout**:
```
         +------+
         | icon |    (48px, color = var(--text-muted))
         +------+
     Сотрудники не найдены     (text-lg, text-primary)
  Попробуйте изменить фильтры  (text-sm, text-muted)
      +-----------------+
      | + Добавить      |      (Button, variant=primary, size=md)
      +-----------------+
```

### 2.18 Skeleton

**Файл**: `src/components/ui/Skeleton.tsx`

Заменяет текущий `LoadingSpinner` для большинства случаев.

**Варианты**:
- `Skeleton.Line` -- прямоугольная полоска (для текста, badges)
- `Skeleton.Circle` -- круг (для аватаров)
- `Skeleton.Card` -- прямоугольник (для карточек)
- `Skeleton.Table` -- скелет таблицы (header + n rows)

**Props (базовый)**:
- `width?: string | number`
- `height?: string | number`
- `borderRadius?: string`

**Стиль**: bg = var(--bg-surface), animated shimmer gradient (left to right, infinite, 1.5s duration).

```css
@keyframes shimmer {
  0% { background-position: -200% 0; }
  100% { background-position: 200% 0; }
}
```

**Правило использования** (определяет где skeleton, где spinner):
- **Skeleton**: Первоначальная загрузка страницы, когда известна структура контента (таблицы, карточки, KPI)
- **Spinner**: Inline-действия (кнопка "Сохранить"), refresh данных при уже загруженной странице

### 2.19 Avatar

**Файл**: `src/components/ui/Avatar.tsx`

Заменяет текущие inline-реализации аватаров (DashboardLayout user, StaffCard, AnalyticsPage top executors).

**Размеры**:
| Size | Dimensions | Font size |
|------|------------|-----------|
| `xs` | 24x24      | 10px      |
| `sm` | 32x32      | 12px      |
| `md` | 40x40      | 14px      |
| `lg` | 56x56      | 20px      |
| `xl` | 72x72      | 26px      |

**Props**:
- `src?: string` -- URL изображения
- `initials?: string` -- fallback инициалы
- `name?: string` -- для alt и автогенерации инициалов
- `size?: 'xs' | 'sm' | 'md' | 'lg' | 'xl'`
- `gradient?: string` -- gradient background для initials
- `status?: 'online' | 'offline' | 'busy'` -- status dot
- `statusPosition?: 'bottom-right' | 'top-right'`

**Status dot**:
- `online`: var(--color-success) + border 2px solid var(--bg-card)
- `offline`: var(--text-muted) + border 2px solid var(--bg-card)
- `busy`: var(--color-error) + border 2px solid var(--bg-card)

---

## 3. Макеты страниц

### 3.1 DashboardLayout (Shell)

**Файл**: `src/layouts/DashboardLayout.tsx`

#### Responsive-поведение

| Breakpoint     | Sidebar               | Topbar             | Content              |
|----------------|----------------------|--------------------|-----------------------|
| >= 1280px      | Expanded (260px)     | Full               | margin-left: 260px   |
| 1024-1279px    | Collapsed (64px)     | Full               | margin-left: 64px    |
| 768-1023px     | Hidden (overlay)     | + Hamburger btn    | margin-left: 0       |
| < 768px        | Hidden (overlay)     | + Hamburger btn    | Full width            |

#### Desktop layout (>= 1280px):
```
+----------+--------------------------------------------------+
|          |  [hamburger]  [page title / breadcrumb]  ... [actions] [theme] |
|  SIDEBAR |--------------------------------------------------+
|  260px   |                                                  |
|  fixed   |              CONTENT AREA                        |
|          |              padding: 24px                       |
|  Logo    |              max-width: 1440px                   |
|  Nav     |              (scrollable)                        |
|  User    |                                                  |
+----------+--------------------------------------------------+
```

#### Collapsed sidebar (1024-1279px):
```
+---+--------------------------------------------------+
|   |  [=]  Page Title         [actions] [theme]       |
| S |--------------------------------------------------+
| 64|                                                  |
| px|              CONTENT AREA                        |
|   |                                                  |
+---+--------------------------------------------------+
```
- Только иконки, без текста
- Tooltip на hover показывает label
- Logo -- только значок "УК"
- User block -- только аватар

#### Mobile sidebar (<1024px):
```
+--------------------------------------------------+
|  [=]  Page Title              [actions] [theme]  |
|--------------------------------------------------+
|                                                  |
|              CONTENT AREA                        |
|              padding: 16px                       |
|              (scrollable)                        |
|                                                  |
+--------------------------------------------------+

При нажатии [=]:
+----------+--------------------------------------+
|          |                                      |
|  SIDEBAR |  (overlay, backdrop, click=close)    |
|  280px   |                                      |
|  overlay |                                      |
|          |                                      |
+----------+--------------------------------------+
```

#### Обновлённый Topbar:
```
+--------------------------------------------------------------+
| [=] | [Breadcrumb: Адреса > Центральный > ул. Пушкина 10]  ... | [page actions] | [theme] |
+--------------------------------------------------------------+
```

- Hamburger: только при width < 1024px
- Page title / Breadcrumb: слева (flex: 1)
- Page actions: topbar actions из `useTopbar()`
- Theme toggle: иконка Sun/Moon с `aria-label`

### 3.2 KanbanPage

#### Desktop layout:
```
+--------------------------------------------------------------+
| Topbar: [breadcrumb: Заявки]  ... [Фильтры] [Поиск] [Создать по звонку]|
+--------------------------------------------------------------+
|                                                              |
|  +-- Filter bar (collapsible) --+                            |
|  | [Категория v] [Срочность v] [Исполнитель v] [Сбросить] |  |
|  +-------------------------------+                           |
|                                                              |
|  +--------+ +--------+ +--------+ +--------+ +--------+     |
|  |Новая(5)| |В работе| |Назначена| |Завершена| |Отменена|   |
|  |        | |  (3)   | |  (2)    | |  (12)  | |  (1)  |    |
|  | [card] | | [card] | | [card]  | | [card] | | [card]|    |
|  | [card] | | [card] | |         | | [card] | |       |    |
|  | [card] | |        | |         | | [card] | |       |    |
|  | [card] | |        | |         | |  ...   | |       |    |
|  |  ...   | |        | |         | | +more  | |       |    |
|  +--------+ +--------+ +--------+ +--------+ +--------+     |
|  <- horizontal scroll ->                                     |
+--------------------------------------------------------------+
```

**Ключевые изменения**:
1. **Поиск в topbar**: Input с иконкой `Search`, debounce 300ms, поиск по номеру/описанию/категории
2. **Фильтры**: Collapsible панель под topbar с chip-фильтрами:
   - Категория (multi-select chips)
   - Срочность (multi-select chips)
   - Исполнитель (dropdown)
   - Источник (chips: bot, twa, web, call_center)
   - Кнопка "Сбросить" (видна только при активных фильтрах)
   - Badge с количеством активных фильтров
3. **Колонки**: min-width: 280px, max-width: 320px. При 5+ колонках -- горизонтальный scroll с fade-индикаторами по краям.
4. **Виртуализация колонок**: При 50+ карточках в колонке -- показывать первые 20 + кнопка "Показать еще N". Или использовать `@tanstack/react-virtual` для виртуализации скролла внутри колонки.
5. **Счётчик**: В заголовке каждой колонки показывать count.

#### Tablet (768-1023px):
- Колонки min-width: 260px
- Horizontal scroll с sticky-заголовками
- Фильтры в sheet (slide-in снизу)

#### Mobile (< 768px):
- Не Kanban, а список заявок с группировкой по статусу (accordions)
- Поиск full-width сверху
- Фильтры в bottom sheet

### 3.3 EmployeesPage

#### Desktop layout:
```
+--------------------------------------------------------------+
| Topbar: [breadcrumb: Сотрудники]  ... [Поиск] [Экспорт] [+ Добавить] |
+--------------------------------------------------------------+
|                                                              |
|  +------+ +------+ +------+ +------+                        |
|  | KPI1 | | KPI2 | | KPI3 | | KPI4 |   <-- StatsCard x4    |
|  +------+ +------+ +------+ +------+                        |
|                                                              |
|  +-- Pending approvals (collapsible) --------------------+   |
|  |  [PendingCard]  [PendingCard]  [PendingCard]          |   |
|  +-------------------------------------------------------+   |
|                                                              |
|  [Все] [Исполнители] [Менеджеры] | [Все статусы] [На смене] | [Спец...] | [Grid/List] |
|                                                              |
|  +====================================================+     |
|  | [ ] | Имя          | Роль    | Статус | Действия   |     | <-- Table (viewMode=table)
|  |----|---------------|---------|--------|------------|     |
|  | [ ] | Иванов И.И.  | Исп.   | [badge]| [...]      |     |
|  | [ ] | Петров П.П.  | Мен.   | [badge]| [...]      |     |
|  +====================================================+     |
|  | Выбрано: 0               | Стр. 1 из 6  [< 1 2 3 >]|    |
|  +====================================================+     |
|                                                              |
|  ИЛИ (viewMode=tile):                                        |
|  +--------+ +--------+ +--------+                            |
|  | Card1  | | Card2  | | Card3  |                            |
|  +--------+ +--------+ +--------+                            |
|  +--------+ +--------+ +--------+                            |
|  | Card4  | | Card5  | | Card6  |                            |
|  +--------+ +--------+ +--------+                            |
|                          [Показать еще] или пагинация        |
+--------------------------------------------------------------+
```

**Ключевые изменения**:
1. **Пагинация**: 25 items per page (server-side), компонент Pagination внизу
2. **Batch-операции**: Checkbox в таблице, floating action bar при selection ("Выбрано: 3 [Заблокировать] [Экспорт]")
3. **Debounce поиска**: 300ms
4. **StatsCard**: Использовать unified Card + иконки Lucide вместо emoji
5. **StaffTable**: Мигрировать с CSS Grid `<div>` на семантический `<table>`
6. **StaffCard**: Убрать `translateY(-2px)` hover. Заменить на border-color change.
7. **Кнопка "Блок"**: Переименовать в "Заблокировать" / "Разблокировать"

#### Tablet:
- KPI: 2 колонки вместо 4
- Grid cards: 2 колонки
- Table: горизонтальный scroll

#### Mobile:
- KPI: 2 колонки, уменьшенные
- Только card view (нет table toggle)
- 1 колонка карточек
- Фильтры в bottom sheet

### 3.4 ShiftsPage

#### Desktop layout:
```
+--------------------------------------------------------------+
| Topbar: [breadcrumb: Смены]  ... [Шаблоны] [+ Создать смену] |
+--------------------------------------------------------------+
|                                                              |
|  [<] [>]  Понедельник, 19 марта 2026   [Сегодня] [Календарь]|
|                                                              |
|  +------+ +------+ +------+ +------+ +------+               |
|  | KPI1 | | KPI2 | | KPI3 | | KPI4 | | KPI5 |  <-- Stats   |
|  +------+ +------+ +------+ +------+ +------+               |
|                                                              |
|  +-- Расписание смен --------------------------------+       |
|  | [Имя (sticky)]| 00 | 01 | 02 | ... | 22 | 23 |  |       |
|  |---------------+----+----+----+-----+----+----+---|       |
|  | Иванов И.     | =========== shift ============|  |       |
|  | Петров П.     |           ======= shift ======|  |       |
|  | Сидоров С.    | ==== shift ====                |  |       |
|  +---------------------------------------------------+       |
|                                                              |
|  +-- Тепловая карта --+  +-- Запросы на передачу ---+        |
|  |  [heatmap grid]    |  |  [transfer 1]            |        |
|  |                    |  |  [transfer 2]            |        |
|  |                    |  |  [Показать все (5)]      |        |
|  |                    |  |  ─── Шаблоны смен ───    |        |
|  |                    |  |  [template 1]            |        |
|  |                    |  |  [template 2]            |        |
|  +--------------------+  +--------------------------+        |
+--------------------------------------------------------------+
```

**Ключевые изменения**:
1. **Datepicker**: Добавить кнопку "Календарь" (CalendarDays icon), открывающую date picker popover для быстрого перехода к произвольной дате.
2. **Timeline sticky**: Колонка с именами -- sticky left при горизонтальном скролле.
3. **Передачи**: Добавить кнопку "Показать все (N)" когда transfer.length > 3.
4. **Stats cards**: Единый компонент StatsCard с Lucide иконками.

#### Tablet:
- KPI: 3-2 колонки
- Timeline: horizontal scroll с sticky names
- Bottom panels: стеком (1 колонка)

### 3.5 AddressesPage

#### Desktop layout:
```
+--------------------------------------------------------------+
| Topbar: [breadcrumb: Адреса]  ... [Поиск] [+ Добавить двор]  |
+--------------------------------------------------------------+
|                                                              |
|  +------+ +------+ +------+ +------+                        |
|  |Дворы | |Здания| |Кварт.| |Жители|   <-- Stats (clickable)|
|  | 5/5  | | 12   | | 243  | | 180  |                        |
|  +------+ +------+ +------+ +------+                        |
|                                                              |
|  [Справочник] [Модерация (3)]     [Grid/List] [x] Неактивные|
|                                                              |
|  Дворы > Центральный > ул. Пушкина 10       <-- Breadcrumb  |
|                                                              |
|  +====================================================+     |
|  |  Table or Cards (depending on viewMode)             |     |
|  |  ...                                               |     |
|  +====================================================+     |
|  | Стр. 1 из 3  [< 1 2 3 >]                           |     |
|  +====================================================+     |
+--------------------------------------------------------------+
```

**Ключевые изменения**:
1. **Breadcrumb**: Мигрировать с `<span onClick>` на семантический `<Breadcrumb>` компонент
2. **Декомпозиция**: Разбить файл 942 строки:
   - `AddressesPage.tsx` -- layout, stats, tabs, breadcrumb
   - `YardGrid.tsx` / `YardList.tsx` -- отображение дворов
   - `BuildingGrid.tsx` / `BuildingList.tsx` -- отображение зданий
   - `ApartmentGrid.tsx` / `ApartmentList.tsx` -- отображение квартир
   - `ActionMenu` вынести в `DropdownMenu` (shared component)
3. **ConfirmDialog**: Все `window.confirm()` заменить на `ConfirmDialog`
4. **Пагинация**: client-side при > 50 элементов

### 3.6 AnalyticsPage

#### Desktop layout:
```
+--------------------------------------------------------------+
| Topbar: [breadcrumb: Аналитика]  ...                          |
+--------------------------------------------------------------+
|                                                              |
|  [7 дней] [30 дней] [90 дней]           Обновлено: 14:32    |
|                                                              |
|  +-------+ +-------+ +-------+ +-------+                    |
|  | Total | | Avg   | | Sat   | | Shift |  <-- KPI cards     |
|  | 247   | | 4.2ч  | | 4.3   | | 8     |                    |
|  +-------+ +-------+ +-------+ +-------+                    |
|                                                              |
|  +-- Заявки по дням (2/3) ---+  +-- По категориям (1/3) -+  |
|  |  [Bar chart]              |  |  [Donut chart]          |  |
|  |                           |  |  [Legend]               |  |
|  +---------------------------+  +-------------------------+  |
|                                                              |
|  +-- По статусам ---+ +-- Топ исп. ---+ +-- Действия ---+   |
|  |  [progress bars] | |  [leaderboard]| |  [activity]   |   |
|  |                  | |               | |  [feed]       |   |
|  +------------------+ +---------------+ +---------------+   |
+--------------------------------------------------------------+
```

**Ключевые изменения**:
1. **KPI cards**: Убрать `translateY(-2px)` hover. Добавить реальные данные change вместо "---".
2. **Часовой пояс**: Определять автоматически из `Intl.DateTimeFormat().resolvedOptions().timeZone`, с fallback на настройку пользователя.
3. **Emoji в rankings**: Заменить medals emoji на `<Trophy />` с цветом (#FFD700, #C0C0C0, #CD7F32).

#### Tablet:
- KPI: 2x2 grid
- Charts: стеком (1 колонка)
- Bottom: стеком (1 колонка)

#### Mobile:
- KPI: 2x2
- Charts: 1 колонка, полная ширина
- Bottom: 1 колонка

---

## 4. UX-паттерны

### 4.1 Confirmation Dialogs

**Правило**: Любое деструктивное действие (удаление, блокировка, деактивация) требует ConfirmDialog.

**Шаблон текста**:
| Действие          | Title                  | Message                                                    | Confirm label  |
|-------------------|------------------------|------------------------------------------------------------|----------------|
| Удаление двора    | Удаление двора         | Вы уверены, что хотите удалить двор "{name}"? Все здания и квартиры внутри также будут удалены. Это действие нельзя отменить. | Удалить        |
| Удаление здания   | Удаление здания        | Вы уверены, что хотите удалить здание "{address}"? Все квартиры внутри также будут удалены. | Удалить        |
| Удаление квартиры | Удаление квартиры      | Вы уверены, что хотите удалить квартиру {number}?          | Удалить        |
| Блокировка сотрудника | Блокировка сотрудника | Сотрудник {name} будет заблокирован и не сможет принимать заявки. | Заблокировать |
| Разблокировка     | Разблокировка сотрудника | Сотрудник {name} будет разблокирован и сможет принимать заявки. | Разблокировать |
| Выход             | Выход из системы       | Вы уверены, что хотите выйти из системы?                   | Выйти          |

**Недеструктивные действия** (деактивация, изменение статуса) используют variant="warning", НЕ "danger".

### 4.2 Toast Notifications

**Правило**: Каждая мутация (create, update, delete) показывает toast.

| Действие          | Variant   | Title                        | Description (пример)           |
|-------------------|-----------|------------------------------|-------------------------------|
| Создание успешно  | success   | {Объект} создан              | Двор "Центральный" добавлен   |
| Обновление успешно| success   | Изменения сохранены          | Данные сотрудника обновлены   |
| Удаление успешно  | success   | {Объект} удален              | Двор "Центральный" удален     |
| Ошибка сети       | error     | Ошибка соединения            | Проверьте подключение к сети  |
| Ошибка сервера    | error     | Не удалось выполнить действие| {error.message}               |
| Ошибка валидации  | warning   | Проверьте данные             | {field}: {error}              |
| WebSocket reconnect | info    | Соединение восстановлено     | Данные обновлены              |

### 4.3 Loading States

**Skeleton vs Spinner -- матрица решений**:

| Контекст                       | Loading-паттерн           | Описание                         |
|--------------------------------|---------------------------|----------------------------------|
| Первая загрузка страницы       | Skeleton                  | Скелет полной страницы           |
| Перезагрузка данных (refetch)  | Inline spinner + old data | Маленький spinner в углу, данные видны |
| Кнопка submit                  | Button loading state      | Spinner в кнопке, disabled        |
| Drag & drop переход (Kanban)   | Optimistic update         | Мгновенное перемещение + rollback |
| Подгрузка следующей страницы   | Skeleton rows             | Скелет-строки в конце таблицы     |
| Поиск (debounce)               | Subtle spinner в input    | Spinner вместо search icon        |
| Тяжелое действие (bulk)        | Progress indicator        | Progress bar или процент          |

**Скелет для каждого типа контента**:

KPI Cards:
```
+------------------+
| [=== skeleton] |    <- value line (width: 60%, height: 28px)
| [=== skel]     |    <- label line (width: 80%, height: 14px)
+------------------+
```

Table:
```
+====================================================+
| [======]   | [========]  | [====]   | [=======]    |  <- header (static)
|-----------+-------------+----------+-------------|
| [======]   | [==========]| [====]   | [===]        |  <- skeleton rows x5
| [========] | [======]    | [======] | [=====]      |
| [====]     | [=========] | [====]   | [=======]    |
+====================================================+
```

### 4.4 Empty States

**Контекстные empty states** -- каждый с CTA, если применимо:

| Контекст              | Иконка               | Title                    | Description                          | CTA              |
|-----------------------|----------------------|--------------------------|--------------------------------------|------------------|
| Нет заявок (Kanban)   | `<ClipboardList />`  | Нет заявок               | Заявки появятся здесь                | Создать заявку   |
| Нет сотрудников       | `<Users />`          | Сотрудники не найдены    | Попробуйте другой фильтр            | Сбросить фильтры |
| Нет смен              | `<Clock />`          | Нет смен на эту дату     | Создайте смену или выберите другой день | Создать смену |
| Нет дворов            | `<Building />`       | Дворы не найдены         | Добавьте первый двор для начала работы | Добавить двор  |
| Нет данных аналитики  | `<BarChart3 />`      | Нет данных               | Данные за выбранный период отсутствуют | -- (no CTA)     |
| Поиск без результатов | `<Search />`         | Ничего не найдено        | Попробуйте изменить поисковый запрос  | Очистить поиск  |
| Ошибка загрузки       | `<AlertTriangle />`  | Ошибка загрузки          | Не удалось загрузить данные          | Повторить        |

### 4.5 Error States

**Три уровня ошибок**:

#### Inline (field-level):
Под полем формы, красный текст, иконка `<AlertCircle size={14} />` слева.
```
[Input: email]
[AlertCircle] Введите корректный email
```

#### Section-level (banner):
В начале секции, dismissible.
```
+-- warning/error banner ------------------------------------------+
| [AlertTriangle] Не удалось загрузить данные аналитики.           |
|                  Проверьте соединение.    [Повторить] [Закрыть]  |
+------------------------------------------------------------------+
```

Стиль: bg = var(--color-error-dim), border = 1px solid var(--border-error), border-radius.

#### Page-level (full page):
Когда вся страница не может загрузиться.
```
         [AlertTriangle icon, 48px]
      Ошибка загрузки страницы
  Не удалось подключиться к серверу.
  Проверьте соединение и попробуйте снова.
      +------------------+
      |    Повторить     |
      +------------------+
```

### 4.6 Keyboard Shortcuts

**Глобальные** (работают на любой странице):
| Shortcut      | Действие                        | Описание              |
|---------------|----------------------------------|-----------------------|
| `Cmd/Ctrl+K`  | Открыть Command Palette          | Глобальный поиск      |
| `Escape`      | Закрыть модал/dropdown/palette   | Выход из текущего контекста |
| `?`           | Показать список горячих клавиш   | Help overlay          |

**Command Palette** (Cmd+K):
```
+----------------------------------------------+
| > Поиск команд и объектов...                 |
|----------------------------------------------|
| Заявки                                       |
|   Заявка #1234 - Протечка крана              |
|   Заявка #1235 - Замена лампочки             |
| Страницы                                     |
|   Перейти к Аналитике                        |
|   Перейти к Сотрудникам                      |
| Действия                                     |
|   Создать заявку                             |
|   Создать смену                              |
+----------------------------------------------+
```

**Страничные** (работают только на конкретной странице):

Kanban:
| Shortcut | Действие              |
|----------|-----------------------|
| `N`      | Новая заявка (call center modal) |
| `F`      | Фокус на поиск        |

Employees:
| Shortcut | Действие              |
|----------|-----------------------|
| `F`      | Фокус на поиск        |
| `V`      | Переключить вид (grid/table) |

### 4.7 Responsive Breakpoints

| Токен      | Ширина       | Описание              | Tailwind     |
|------------|-------------|----------------------|--------------|
| `mobile`   | < 640px     | Телефон               | `sm:`        |
| `tablet`   | 640-1023px  | Планшет               | `md:`, `lg:` |
| `desktop`  | 1024-1279px | Ноутбук               | `xl:`        |
| `wide`     | >= 1280px   | Широкий монитор       | `2xl:`       |

**Поведение на breakpoints**:

| Элемент              | Mobile         | Tablet          | Desktop         | Wide            |
|----------------------|----------------|-----------------|-----------------|-----------------|
| Sidebar              | overlay        | overlay         | collapsed (64px)| expanded (260px)|
| KPI cards            | 2 col          | 2 col           | 4 col           | 4-5 col         |
| Data grid            | card list      | 2 col cards     | table           | table           |
| Kanban               | grouped list   | 3 cols scroll   | 5 cols scroll   | 5 cols scroll   |
| Chart row            | stack          | stack           | 2 cols          | 2 cols          |
| Page padding         | 12px           | 16px            | 24px            | 24px            |
| Filter bar           | bottom sheet   | inline          | inline          | inline          |

### 4.8 Offline / Connection Status

**Индикатор**:
- При потере WebSocket: Banner сверху страницы "Соединение потеряно. Данные могут быть неактуальны. [Переподключение...]"
- При восстановлении: toast.info("Соединение восстановлено")
- Цвет banner: var(--color-warning-dim), border-bottom: 2px solid var(--color-warning)

### 4.9 Unsaved Changes Guard

При наличии несохранённых данных в формах (создание/редактирование):
- Попытка закрыть модал: ConfirmDialog "Несохранённые изменения. Вы уверены, что хотите закрыть? Изменения будут потеряны."
- Попытка навигации: `beforeunload` event + React Router blocker

---

## 5. Навигация и информационная архитектура

### 5.1 Обновлённая структура Sidebar

```
+--------------------------------------+
|  [Logo: УК]  УК Панель               |
|              management system        |
+--------------------------------------+
|                                      |
|  ОСНОВНОЕ                            |
|                                      |
|  [BarChart3]   Аналитика             |  <- переименовано с "Дашборд"
|  [ListChecks]  Заявки         (12)   |  <- badge: new requests count
|  [Users]       Сотрудники     (3)    |  <- badge: pending approvals
|  [Clock]       Смены                 |
|  [MapPin]      Адреса         (2)    |  <- badge: pending moderation
|                                      |
|  ─────────────────────────────       |
|                                      |
|  УПРАВЛЕНИЕ                          |  <- новая группа
|                                      |
|  [Table2]      Шаблоны смен          |
|  [Settings]    Настройки             |  <- новый раздел
|                                      |
|  ─────────────────────────────       |
|                                      |
|  ВНЕШНЕЕ                             |
|                                      |
|  [Monitor]     Табло жителей  [ext]  |  <- иконка external link
|                                      |
+--------------------------------------+
|  [Avatar]  Иванов И.И.         [^]   |
|            manager                   |
+--------------------------------------+
```

**Ключевые изменения**:
1. **Переименование**: "Дашборд" -> "Аналитика" (решает confusion с default route)
2. **Default route**: `/dashboard` -> `AnalyticsPage` (или оставить Kanban как index, но переименовать sidebar item)
3. **Badge-счётчики**: Динамические бейджи с количеством pending items
4. **Группа "Управление"**: Шаблоны вынесены из основного потока + новый раздел "Настройки"
5. **Настройки**: Часовой пояс, формат дат, плотность UI, горячие клавиши, профиль

### 5.2 Badge-счётчики

| Пункт навигации | Что считает                          | API endpoint                    | Обновление     |
|-----------------|--------------------------------------|---------------------------------|----------------|
| Заявки          | Кол-во заявок в статусе "Новая"      | GET /requests?status=new        | WebSocket      |
| Сотрудники      | Кол-во pending verification          | GET /employees?verification_status=pending | Poll 60s |
| Адреса          | Кол-во pending moderation            | GET /addresses/moderation/pending | Poll 60s     |

**Визуал бейджа в sidebar**:
- Позиция: справа от label
- Стиль: min-width 20px, height 20px, border-radius: full, bg: var(--accent), color: var(--text-on-accent), font-size: 11px, font-weight: 700
- При 0: бейдж скрыт
- При 99+: показывать "99+"

### 5.3 Breadcrumb Logic

**Правила формирования breadcrumb** (отображается в topbar):

| Страница              | Breadcrumb                                         |
|------------------------|-----------------------------------------------------|
| Аналитика             | Аналитика                                          |
| Заявки                | Заявки                                             |
| Заявка (modal)        | Заявки (в topbar, модал поверх)                    |
| Сотрудники            | Сотрудники                                         |
| Сотрудник (детальная)  | Сотрудники > Иванов Иван                            |
| Смены                 | Смены                                              |
| Шаблоны               | Управление > Шаблоны смен                           |
| Адреса (дворы)        | Адреса                                             |
| Адреса (здания)       | Адреса > {Yard.name}                                |
| Адреса (квартиры)     | Адреса > {Yard.name} > {Building.address}           |
| Настройки             | Настройки                                          |

### 5.4 Page Titles

`document.title` обновляется для каждой страницы через `useEffect`:

| Страница         | document.title                   |
|------------------|----------------------------------|
| Login            | Вход - УК Панель                 |
| Аналитика        | Аналитика - УК Панель            |
| Заявки           | Заявки - УК Панель               |
| Сотрудники       | Сотрудники - УК Панель           |
| Сотрудник детали | {Имя} - Сотрудники - УК Панель   |
| Смены            | Смены - УК Панель                |
| Шаблоны          | Шаблоны смен - УК Панель         |
| Адреса           | Адреса - УК Панель               |
| Настройки        | Настройки - УК Панель            |
| Табло жителей    | Информационное табло             |

### 5.5 URL-структура (обновлённая)

```
/login                       -- Авторизация
/                            -- Redirect -> /app
/app                         -- DashboardLayout
  /app                       -- AnalyticsPage (index route, бывший /dashboard/analytics)
  /app/requests              -- KanbanPage (бывший /dashboard)
  /app/employees             -- EmployeesPage
  /app/employees/:id         -- EmployeeDetailPage
  /app/shifts                -- ShiftsPage
  /app/settings              -- SettingsPage (новая)
  /app/settings/templates    -- TemplatesPage (вложен в настройки)
  /app/addresses             -- AddressesPage
/board                       -- ResidentBoardPage (standalone)
/twa                         -- TWA pages (Telegram, без изменений)
  /twa/create
  /twa/requests/:number
/404                         -- NotFoundPage (новая)
```

**Примечание**: Переименование `/dashboard` -> `/app` -- опционально. Если критично сохранить обратную совместимость URL, оставить `/dashboard`, но исправить маршрутизацию index route.

---

## Приложение A: Приоритезация реализации

### Phase 1: Foundation (неделя 1-2)

| Приоритет | Компонент / Задача                       | Зависимости     |
|-----------|------------------------------------------|-----------------|
| P0        | `cn()` утилита + Tailwind config update  | --               |
| P0        | Button                                   | cn()             |
| P0        | Input, Select, Textarea                  | cn()             |
| P0        | Modal / Dialog                           | cn(), Button     |
| P0        | ConfirmDialog                            | Modal, Button    |
| P0        | Toast (установить sonner)                | --               |
| P0        | Badge                                    | cn()             |
| P1        | Avatar                                   | cn()             |
| P1        | Card                                     | cn()             |
| P1        | EmptyState (обновить)                    | Button, Icon     |
| P1        | Skeleton                                 | cn()             |
| P1        | Toggle                                   | cn()             |

### Phase 2: Core UX (неделя 3-4)

| Приоритет | Компонент / Задача                       | Зависимости       |
|-----------|------------------------------------------|--------------------|
| P0        | Table                                    | Badge, Button, Checkbox |
| P0        | DropdownMenu                             | --                 |
| P0        | Responsive sidebar                       | --                 |
| P0        | Topbar с breadcrumb                      | Breadcrumb         |
| P1        | Breadcrumb                               | cn()               |
| P1        | Tabs                                     | cn()               |
| P1        | Pagination                               | Button             |
| P1        | Tooltip                                  | cn()               |
| P1        | Badge-счётчики в sidebar                 | Badge, API hooks   |

### Phase 3: Миграция страниц (неделя 5-8)

| Приоритет | Задача                                   | Компоненты          |
|-----------|------------------------------------------|---------------------|
| P0        | Заменить все window.confirm() на ConfirmDialog | ConfirmDialog |
| P0        | Заменить все window.alert() на Toast     | Toast               |
| P0        | Мигрировать CallCenterModal на CSS vars  | Modal, Input        |
| P0        | Мигрировать TransitionModal на CSS vars  | Modal, Select       |
| P1        | EmployeesPage: Table + Pagination        | Table, Pagination   |
| P1        | AddressesPage: декомпозиция + Breadcrumb | Breadcrumb, Table   |
| P1        | KanbanPage: фильтры + поиск             | Input, Badge, Filter|
| P2        | AnalyticsPage: fix KPI + timezone        | Card, Badge         |
| P2        | ShiftsPage: datepicker + sticky timeline | --                  |

### Phase 4: A11y + Polish (неделя 9-10)

| Приоритет | Задача                                   |
|-----------|------------------------------------------|
| P0        | ARIA roles для всех модалов              |
| P0        | Focus trap в модальных окнах             |
| P0        | :focus-visible стили глобально           |
| P0        | Keyboard navigation в DropdownMenu       |
| P1        | lang="ru" + label/htmlFor связки         |
| P1        | Семантические таблицы (StaffTable)       |
| P1        | Skip navigation link                     |
| P2        | Command Palette                          |
| P2        | Keyboard shortcuts                       |

---

## Приложение B: Файловая структура после модернизации

```
src/
  lib/
    utils.ts                     -- cn(), formatDate(), pluralize()

  components/
    ui/                          -- Shared UI components (19 компонентов)
      Avatar.tsx
      Badge.tsx
      Breadcrumb.tsx
      Button.tsx
      Card.tsx
      ConfirmDialog.tsx
      DropdownMenu.tsx
      EmptyState.tsx
      Input.tsx
      Modal.tsx
      Pagination.tsx
      Select.tsx
      Skeleton.tsx
      Table.tsx
      Tabs.tsx
      Textarea.tsx
      Toast.tsx                  -- re-export sonner config
      Toggle.tsx
      Tooltip.tsx

    layout/                      -- Layout-specific components
      Sidebar.tsx
      SidebarNav.tsx
      SidebarUser.tsx
      Topbar.tsx
      TopbarBreadcrumb.tsx
      TopbarActions.tsx
      CommandPalette.tsx
      KeyboardShortcuts.tsx

    kanban/                      -- Domain: Kanban
      KanbanBoard.tsx
      KanbanColumn.tsx
      RequestCard.tsx
      RequestDetailModal.tsx
      TransitionModal.tsx
      KanbanFilters.tsx          -- новый

    callcenter/
      CallCenterModal.tsx

    employees/
      StaffCard.tsx
      StaffTable.tsx
      PendingApprovalCard.tsx
      AssignRequestModal.tsx
      EmployeeFilters.tsx        -- новый

    shifts/
      ShiftTimeline.tsx
      ShiftCoverageHeatmap.tsx
      CreateShiftModal.tsx
      ShiftDetailModal.tsx
      DatePicker.tsx             -- новый

    addresses/
      YardGrid.tsx               -- вынесено из AddressesPage
      BuildingGrid.tsx           -- вынесено из AddressesPage
      ApartmentGrid.tsx          -- вынесено из AddressesPage
      YardFormModal.tsx
      BuildingFormModal.tsx
      ApartmentFormModal.tsx
      BulkCreateModal.tsx
      ModerationPanel.tsx
      ApartmentProfileModal.tsx
      AddressTable.tsx

    analytics/
      KpiCard.tsx                -- вынесено из AnalyticsPage
      BarTooltip.tsx             -- вынесено из AnalyticsPage
      PieTooltip.tsx             -- вынесено из AnalyticsPage

  hooks/
    useMediaQuery.ts             -- новый: responsive breakpoints
    useKeyboardShortcut.ts       -- новый: keyboard shortcuts
    useDebounce.ts               -- новый: debounce для поиска
    useFocusTrap.ts              -- новый: focus trap для модалов
    usePageTitle.ts              -- новый: document.title
    ... (existing hooks)

  layouts/
    DashboardLayout.tsx
    PublicLayout.tsx              -- для ResidentBoard, 404

  pages/
    ... (existing pages)
    NotFoundPage.tsx             -- новый: 404
    SettingsPage.tsx             -- новый
```

---

*Документ является руководством к реализации. Для каждого компонента и страницы указаны конкретные спецификации, которые разработчик может использовать без дополнительных уточнений. При возникновении вопросов по визуальным деталям -- обращаться к дизайн-токенам из раздела 1.*
