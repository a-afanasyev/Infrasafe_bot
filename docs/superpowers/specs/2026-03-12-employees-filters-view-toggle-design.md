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
- First chip: «Все спец.» (value `'all'`) — always shown, resets spec filter
- Then one chip per entry in `SPEC_DISPLAY` from `employeeUtils.ts` (8 specs)
- Chip label: Russian display name from `SPEC_DISPLAY` (e.g. `'⚡ Электрика'`)
- Chip value (filter key): English backend key from `SPEC_DISPLAY` (e.g. `'electrician'`)
- Backend accepts `?specialization=electrician` and does `LIKE '%electrician%'` on the JSON array column
- When active, chip uses its spec color from `SPEC_COLORS` (e.g. Электрика → `var(--amber)`) as background tint + border, with matching text color — NOT `var(--accent)`. Example active style: `background: SPEC_COLORS[label]+'22', border: SPEC_COLORS[label]+'55', color: SPEC_COLORS[label]`
- Inactive chips use the standard `chipStyle(false)` from EmployeesPage
- When spec is active, `{ specialization: specKey }` is merged into `apiFilters`
- No "show more" collapse needed — 8 chips + «Все спец.» fit on one line at normal viewport

**View toggle** — new, right-aligned:
- Two icon buttons in a segmented control: ⊞ (tile) and ☰ (table)
- Active button: `var(--accent)` background, white icon
- Inactive button: transparent background, muted icon
- State: `viewMode: 'tile' | 'table'`, initialized from localStorage with try/catch fallback:
  ```typescript
  const [viewMode, setViewMode] = useState<'tile' | 'table'>(() => {
    try { return (localStorage.getItem('employees_view_mode') as 'tile' | 'table') || 'tile' }
    catch { return 'tile' }
  })
  // persist on change:
  useEffect(() => {
    try { localStorage.setItem('employees_view_mode', viewMode) } catch {}
  }, [viewMode])
  ```

---

## Tile View (existing, unchanged)

`auto-fill minmax(340px, 1fr)` grid of `StaffCard` components — no changes to this component.

---

## Table View (new)

New component: `frontend/src/components/employees/StaffTable.tsx`

**Columns:**

| # | Header | Content |
|---|--------|---------|
| 1 | Сотрудник | Avatar (32px, gradient) + status dot (10px, absolute bottom-right, emerald if on shift else `#5a6a7a`, 2px card-bg border — mirrors StaffCard:60-69) + Name + phone (mono) |
| 2 | Специализация | Spec chips (same style as StaffCard) |
| 3 | Верификация | Badge: «✓ Верифицирован» (emerald) or «⏳ На проверке» (amber) |
| 4 | Статус | «● На смене» (emerald) or «● Не на смене» (muted) |
| 5 | Смена | Shift ID mono (`#142`) or «—» |
| 6 | Действия | If verified: «Назначить» (blue link, calls `onAssign`). If blocked: show «Заблокирован» badge (red tint) + «Разблок» (amber text, calls `onBlock`). If not blocked: «Блок» (red text, calls `onBlock`). Matches StaffCard action logic exactly. |

**Visual:**
- Full-width table inside a `bg-card` rounded container
- Header row: `bg-surface`, 10px uppercase muted labels
- Rows: alternating hover, 1px border-bottom separator
- Blocked employees: row at 60% opacity with "Заблокирован" badge in actions cell
- Empty state: `<EmptyState>` centered inside the full-width table container (same props as tile view)
- Blocked row: entire row at `opacity: 0.6`, actions cell maintains full opacity for clickability

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
