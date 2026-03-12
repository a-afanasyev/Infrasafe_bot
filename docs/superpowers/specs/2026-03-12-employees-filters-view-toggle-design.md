# Employees Page: Filters & View Toggle — Design Spec

**Goal:** Add specialization filter chips and a tile/table view toggle to the employees page.

**Architecture:** Pure frontend change. No backend modifications needed — the `/api/v2/shifts/employees?specialization=` param already exists. State lives in `EmployeesPage` component; the new `StaffTable` component is extracted to `frontend/src/components/employees/StaffTable.tsx`.

**Tech Stack:** React 18 + TypeScript, existing CSS-in-JS (inline styles with CSS vars), `@tanstack/react-query`

---

## Filter Bar

Three chip groups separated by vertical dividers, view toggle pinned to the right end:

```
[Все] [Исполнители] [Менеджеры]  |  [Все статусы] [На смене] [Верифицированы]  |  [Все спец.] [⚡ Электрика] [🔧 Сантехника] ... [+ ещё N]   ⊞ ☰
```

**Role group** — existing, unchanged: `all` / `executor` / `manager`

**Status group** — existing, unchanged: `all` / `on_shift` / `verified`

**Specialization group** — new, single-select:
- First chip: «Все спец.» (value `all`) — always shown, resets spec filter
- Then one chip per entry in `SPEC_DISPLAY` from `employeeUtils.ts` (8 specs)
- Active chip: highlighted with spec's accent color (from `SPEC_COLORS`), matching existing chip style
- When a spec is active, `specialization` query param is passed to `useEmployees`
- No "show more" collapse needed — 8 chips + «Все спец.» fit on one line at normal viewport

**View toggle** — new, right-aligned:
- Two icon buttons in a segmented control: ⊞ (tile) and ☰ (table)
- Active button: `var(--accent)` background, white icon
- Inactive button: transparent background, muted icon
- State: `viewMode: 'tile' | 'table'`, `useState`, default `'tile'`
- Persisted in `localStorage` key `employees_view_mode` so preference survives page reload

---

## Tile View (existing, unchanged)

`auto-fill minmax(340px, 1fr)` grid of `StaffCard` components — no changes to this component.

---

## Table View (new)

New component: `frontend/src/components/employees/StaffTable.tsx`

**Columns:**

| # | Header | Content |
|---|--------|---------|
| 1 | Сотрудник | Avatar (32px) + status dot + Name + phone (mono) |
| 2 | Специализация | Spec chips (same style as StaffCard) |
| 3 | Верификация | Badge: «✓ Верифицирован» (emerald) or «⏳ На проверке» (amber) |
| 4 | Статус | «● На смене» (emerald) or «● Не на смене» (muted) |
| 5 | Смена | Shift ID mono (`#142`) or «—» |
| 6 | Действия | «Назначить» (blue link) + «Блок»/«Разблок» (red/amber link) |

**Visual:**
- Full-width table inside a `bg-card` rounded container
- Header row: `bg-surface`, 10px uppercase muted labels
- Rows: alternating hover, 1px border-bottom separator
- Blocked employees: row at 60% opacity with "Заблокирован" badge in actions cell
- Empty state: same `<EmptyState>` component as tile view

**Props:**
```typescript
interface StaffTableProps {
  employees: EmployeeBrief[]
  onAssign: (e: EmployeeBrief) => void
  onBlock: (e: EmployeeBrief) => void
  isBlockPending: boolean
}
```

---

## EmployeesPage changes

1. Add `specFilter: string` state (default `'all'`)
2. Add `viewMode: 'tile' | 'table'` state (default from localStorage or `'tile'`)
3. Pass `specFilter !== 'all' ? { specialization: specFilter } : {}` to `apiFilters`
4. Render specialization chips in the filter row (after status group, before toggle)
5. Render toggle buttons (⊞ / ☰) at the right end of filter row
6. Conditionally render `<StaffTable>` or the existing tile grid based on `viewMode`
7. Persist `viewMode` to localStorage on change

---

## Files

- **Modify:** `frontend/src/pages/EmployeesPage.tsx`
- **Create:** `frontend/src/components/employees/StaffTable.tsx`
