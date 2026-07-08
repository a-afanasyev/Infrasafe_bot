# Code Review: UK Management Frontend Modernization

> _Последнее редактирование: 2026-03-20_

**Date**: 2026-03-19
**Reviewer**: Claude Opus 4.6 (Senior Code Reviewer)
**Scope**: 8 commits `89320d4..c9994f7` -- full diff against `a658ade`
**Files changed**: 57 (excluding `package-lock.json`)

---

## Executive Summary

The modernization covers four phases:
- **Phase 0**: Tailwind @theme, cn() utility, shadcn/ui setup, Error Boundaries, a11y fixes
- **Phase 1**: UI components (Button, Dialog, AlertDialog, ConfirmDialog, Input, Label, Select, Textarea), Toast (sonner), removal of all `window.confirm/alert`
- **Phase 2**: Responsive sidebar (3 states), role-based routing, page titles, user dropdown
- **Phase 3**: Migration of ALL pages and components from inline styles to Tailwind CSS

**Overall Assessment**: The modernization is well-executed and thorough. TypeScript compiles cleanly (`tsc --noEmit` passes with zero errors). All `window.confirm()` and `window.alert()` calls are eliminated. Toast notifications are consistently applied across all mutations. The architecture follows established shadcn/ui patterns correctly. There are several medium-severity consistency issues and a handful of potential bugs worth addressing.

**Verdict**: **Approved with minor issues.** No critical or high-severity blockers. The issues below are categorized as Medium, Low, or Suggestion.

---

## 1. What Was Done Well

### 1.1 Clean Architecture
- shadcn/ui component structure follows the canonical pattern: primitives in `components/ui/`, composites in `components/shared/`
- `cn()` utility (`clsx` + `tailwind-merge`) is properly centralized in `lib/utils.ts`
- Path aliases (`@/`) configured correctly in both `tsconfig.app.json` and `components.json`

### 1.2 TypeScript
- Zero compilation errors
- Strong typing on all component props (`ConfirmDialogProps`, `NavItem`, `KpiCardProps`, etc.)
- Proper use of `React.ComponentProps`, `VariantProps`, discriminated unions

### 1.3 A11y
- `lang="ru"` set correctly on `<html>`
- `focus-visible` ring uses accent color with proper offset
- Dialog close button has `sr-only` label ("Закрыть")
- AlertDialog blocks pointer-outside-dismiss and Escape (correct for destructive confirmations)
- `aria-label` on hamburger, theme toggle, sidebar collapse buttons
- User dropdown has `aria-expanded`, `aria-haspopup`, `role="menu"`, `role="menuitem"`

### 1.4 Business Logic Preservation
- DnD logic (KanbanBoard) preserved: `VALID_TRANSITIONS`, `MODAL_STATUSES`, optimistic updates, valid-target highlighting
- WebSocket integration (`useShiftsWebSocket`) unchanged
- Call Center modal flow intact
- Request detail modal: all contextual blocks (materials, notes, completion report, return reason, force-accept, reminder) preserved

### 1.5 Toast Consistency
- All 27+ mutations across 4 hook files (`useAddresses`, `useEmployees`, `useShifts`, `useTemplates`) have both `onSuccess` and `onError` with `toast.success/error`
- Component-level mutations (RequestDetailModal, CallCenterModal) also use toast
- Login page has toast on error

### 1.6 Error Boundaries
- Two-layer approach: `GlobalErrorBoundary` (full-page crash) + `PageErrorBoundary` (per-route, with "try again" and "go home")
- Correctly uses inline styles in error boundary render (the component must not depend on Tailwind which may have caused the crash)

---

## 2. Issues Found

### MEDIUM Severity

#### M1. Inconsistent font-family syntax across components
**Files**: Multiple files
**Pattern**: Two different syntaxes used for custom fonts:
- `font-[family-name:var(--font-display)]` (correct Tailwind 4 syntax, used in ~106 places)
- `font-[var(--font-display)]` (incorrect shorthand, used in ~30 places)

The `font-[var(--font-display)]` shorthand in Tailwind 4 generates `font: var(--font-display)` which is the CSS `font` shorthand property, NOT `font-family`. This sets font-size, line-height, AND font-family at once, potentially overriding other font-size/line-height utilities on the same element.

Affected files:
- `/Users/andreyafanasyev/Code/UK/frontend/src/pages/EmployeesPage.tsx` (lines 144, 159, 193, 213, 227, 243)
- `/Users/andreyafanasyev/Code/UK/frontend/src/pages/ShiftsPage.tsx` (lines 145, 164, 182, 196, 206, 250)
- `/Users/andreyafanasyev/Code/UK/frontend/src/pages/TemplatesPage.tsx` (lines 175, 327, 398)
- `/Users/andreyafanasyev/Code/UK/frontend/src/components/employees/PendingApprovalCard.tsx` (lines 21, 29)
- `/Users/andreyafanasyev/Code/UK/frontend/src/components/employees/StaffTable.tsx` (lines 42, 78, 91, 95, 155, 171, 183, 192)
- `/Users/andreyafanasyev/Code/UK/frontend/src/components/employees/StaffCard.tsx` (lines 41, 57, 61, 127)
- `/Users/andreyafanasyev/Code/UK/frontend/src/components/shifts/ShiftTimeline.tsx` (line 251)

**Recommendation**: Replace all `font-[var(--font-display)]` with `font-[family-name:var(--font-display)]`, and similarly for `--font-mono` and `--font-body`. A global search-and-replace would fix this.

---

#### M2. Missing ESLint exhaustive-deps warnings on useEffect
**File**: `/Users/andreyafanasyev/Code/UK/frontend/src/pages/KanbanPage.tsx`, line 27
```tsx
useEffect(() => {
    setActions(...)
    return clearActions
}, []) // Missing: setActions, clearActions
```

**File**: `/Users/andreyafanasyev/Code/UK/frontend/src/pages/ShiftsPage.tsx`, line 77
```tsx
useEffect(() => {
    setActions(...)
    return clearActions
}, [setActions, clearActions]) // Correct here
```

KanbanPage has `[]` while ShiftsPage correctly has `[setActions, clearActions]`. Since `setActions` and `clearActions` come from context, they are stable references, so the behavior is the same, but the inconsistency will trigger ESLint `react-hooks/exhaustive-deps` warnings.

**Recommendation**: Add `setActions` and `clearActions` to the dependency array in KanbanPage (line 27) to match the pattern used in ShiftsPage, EmployeesPage, TemplatesPage, and AddressesPage.

---

#### M3. Unused Radix Select dependency
**File**: `/Users/andreyafanasyev/Code/UK/frontend/package.json`, line 18
```json
"@radix-ui/react-select": "^2.2.6",
```

The `Select` component at `/Users/andreyafanasyev/Code/UK/frontend/src/components/ui/select.tsx` is a native `<select>` element, not a Radix Select. The `@radix-ui/react-select` package is installed but never imported anywhere in the codebase (confirmed via grep).

This adds ~48KB gzipped to `node_modules` without benefit. The `@floating-ui/*` dependencies (`core`, `dom`, `react-dom`, `utils`) were also pulled in transitively.

**Recommendation**: Either remove `@radix-ui/react-select` from `package.json` and run `npm install`, or plan to migrate the Select component to Radix Select for better a11y (keyboard navigation, ARIA combobox pattern).

---

#### M4. Hardcoded hex colors instead of @theme tokens
Several components use raw hex values instead of the Tailwind `@theme` token mappings defined in `index.css`:

**File**: `/Users/andreyafanasyev/Code/UK/frontend/src/components/kanban/KanbanColumn.tsx`, lines 15-23
```tsx
const STATUS_DOT: Record<string, string> = {
  'Новая':     'bg-[#60a5fa]',   // should be bg-blue
  'В работе':  'bg-[#fbbf24]',   // should be bg-amber
  'Закуп':     'bg-[#a78bfa]',   // should be bg-violet
  'Уточнение': 'bg-[#22d3ee]',   // should be bg-cyan
  'Выполнена': 'bg-[#34d399]',   // should be bg-emerald
  'Принято':   'bg-[#4ade80]',   // should be bg-green
  'Отменена':  'bg-[#f87171]',   // should be bg-red
}
```

These hex colors are close-but-not-identical to the `@theme` tokens (e.g., `#60a5fa` vs `--blue: #3b82f6`). This creates visual inconsistency and defeats the purpose of the token system.

**File**: `/Users/andreyafanasyev/Code/UK/frontend/src/pages/LoginPage.tsx`:
- Line 114: `text-[#001a14]` -- no theme token
- Line 128: `border-white/[.08]` -- should use `border-border-default`
- Line 137: `bg-white/[.07]` -- no theme token for dividers
- Line 191: `text-[#f87171]` -- should be `text-red`
- Line 199: `text-[#001a14]` -- same as above
- Line 202: `hover:bg-[#00f0c0]` -- should be a variant of `--accent`

**File**: `/Users/andreyafanasyev/Code/UK/frontend/src/components/kanban/RequestCard.tsx`, line 9
```tsx
'Средняя': { ..., text: 'text-[#d97706]' }, // should be text-amber
```

**File**: `/Users/andreyafanasyev/Code/UK/frontend/src/pages/EmployeeDetailPage.tsx`, lines 52, 108
```tsx
style={{ background: isOnShift ? 'var(--emerald)' : '#5a6a7a' }}
```

**File**: `/Users/andreyafanasyev/Code/UK/frontend/src/pages/AnalyticsPage.tsx`, lines 70-78
```tsx
const PIE_PALETTE = ['#00d4aa', '#3b82f6', ...]
```
These are hardcoded colors for Recharts which is acceptable (Recharts requires direct color strings), but the values should reference the same palette as `@theme` tokens.

**Recommendation**: Replace hardcoded hex values with `@theme` token classes where possible. For `style={{}}` props (Recharts, gradients), use `var(--accent)` etc. For the LoginPage dark-specific colors like `#001a14`, consider adding a `--text-on-accent` token.

---

#### M5. ConfirmDialog calls onConfirm and closes simultaneously -- potential race condition
**File**: `/Users/andreyafanasyev/Code/UK/frontend/src/components/shared/ConfirmDialog.tsx`, lines 54-57
```tsx
<AlertDialogAction
  onClick={() => {
    onConfirm()
    onOpenChange(false)  // Closes immediately
  }}
```

If `onConfirm` triggers a mutation, the dialog closes before the mutation completes. If the mutation fails, the user has no visual indication because the dialog is already gone. The `loading` prop exists but the dialog forcefully closes regardless.

**Recommendation**: Let the parent control the close behavior. Change to:
```tsx
onClick={() => {
    onConfirm()
    // Don't call onOpenChange(false) here -- let parent close via loading/success
}}
```
Or better: add an `onConfirm` that returns a Promise and close after it resolves. Current callers already close via state management, so removing the `onOpenChange(false)` here would also prevent double-close.

---

#### M6. ResidentBoardPage not migrated to Tailwind
**File**: `/Users/andreyafanasyev/Code/UK/frontend/src/pages/ResidentBoardPage.tsx`

This page was not part of the diff (not modified) and still uses 100% inline styles. While it is a standalone public-facing page (not inside DashboardLayout), it creates an inconsistency in the codebase.

**Recommendation**: Document this as intentionally excluded from the migration scope, or plan a separate migration pass. The page has a fundamentally different visual language (light theme, different fonts) so it may warrant a separate design system.

---

### LOW Severity

#### L1. Missing React.memo on frequently re-rendered list items
**Pattern**: No usage of `React.memo` anywhere in the codebase (confirmed via grep).

The following components would benefit from `React.memo`:
- `RequestCard` -- rendered N times per column, all re-render on any KanbanBoard state change
- `KanbanColumn` -- 8 columns re-render on any drag state change
- `StaffCard` / `StaffTable` row -- re-render on any filter change
- `TemplateRow` -- re-renders when any row's hover state changes (managed via `useState`)

**Recommendation**: Add `React.memo` to `RequestCard`, `KanbanColumn`, and `TemplateRow` components. For `TemplateRow`, the `onToggleAutoCreate`, `onDelete`, `onCreateFromToday` callbacks should be stable (wrapped in `useCallback`) for memoization to be effective -- they already are in the parent.

---

#### L2. Avatar gradient uses inline `style` instead of Tailwind
**Files**:
- `/Users/andreyafanasyev/Code/UK/frontend/src/layouts/DashboardLayout.tsx`, lines 161, 237
- `/Users/andreyafanasyev/Code/UK/frontend/src/pages/LoginPage.tsx`, line 115
```tsx
style={{ background: 'linear-gradient(135deg, var(--accent), #0099aa)' }}
```

The `#0099aa` is a hardcoded value not in the `@theme` system.

**Recommendation**: Consider adding a `--accent-dark` or `--accent-secondary` token to `@theme` and using it consistently. The gradient pattern is repeated 3 times.

---

#### L3. Inline styles in Error Boundaries
**Files**:
- `/Users/andreyafanasyev/Code/UK/frontend/src/components/shared/GlobalErrorBoundary.tsx` (lines 29-65)
- `/Users/andreyafanasyev/Code/UK/frontend/src/components/shared/PageErrorBoundary.tsx` (lines 29-79)

These use inline styles intentionally (fallback when Tailwind CSS may not be loaded/working). This is actually a correct pattern for error boundaries, but should be documented with a comment explaining why.

**Recommendation**: Add a comment at the top of each render method:
```tsx
// Inline styles used intentionally -- error boundary must not depend on
// Tailwind/CSS which may have caused the crash
```

---

#### L4. Text-secondary and text-muted map to the same value
**File**: `/Users/andreyafanasyev/Code/UK/frontend/src/index.css`, lines 61-63
```css
--text-secondary: #8899aa;
--text-muted: #8899aa;
```

Both dark and light themes have identical values for `--text-secondary` and `--text-muted`. Having two tokens that always resolve to the same value is confusing for developers.

**Recommendation**: Either differentiate them (e.g., muted could be slightly more transparent) or consolidate into a single token. Currently the codebase uses both interchangeably, which suggests they should either be merged or given distinct roles.

---

#### L5. `@theme` missing `--color-text-on-accent` for contrast
**File**: `/Users/andreyafanasyev/Code/UK/frontend/src/index.css`

The Button component uses `text-white` for the default/destructive variants:
```tsx
default: "bg-accent text-white hover:bg-accent/90"
```

But the LoginPage submit button uses `text-[#001a14]` (dark greenish-black) on accent background. There is no semantic token for "text on accent background," leading to inconsistency.

**Recommendation**: Add `--text-on-accent: #001a14` (or `#fff` depending on design intent) to `@theme` and use `text-text-on-accent` consistently.

---

#### L6. `border-3` utility may not exist in Tailwind 4
**File**: `/Users/andreyafanasyev/Code/UK/frontend/src/components/shared/LoadingSpinner.tsx`, line 4
```tsx
<div className="h-9 w-9 rounded-full border-3 border-border-default border-t-accent animate-spin" />
```

Tailwind 4 provides `border`, `border-0`, `border-2`, `border-4`, `border-8` by default. `border-3` is not a standard utility and may not render the intended 3px border unless extended.

**Recommendation**: Verify this renders correctly. If not, use `border-[3px]` as an arbitrary value.

---

#### L7. `queryClient` created outside component causes issues with SSR/testing
**File**: `/Users/andreyafanasyev/Code/UK/frontend/src/App.tsx`, lines 27-33
```tsx
const queryClient = new QueryClient({...})
```

The `queryClient` is created at module scope (outside the component). This is generally fine for a SPA that never server-renders, but makes testing harder (shared state between tests).

**Recommendation**: For now this is acceptable for a Vite SPA. If tests are added later, move the instantiation inside the component or a provider factory.

---

### SUGGESTIONS (Nice to Have)

#### S1. Extract repeated stat-card pattern into a shared component
The stat card pattern (icon + value + label) is duplicated across:
- `AddressesPage.tsx` (lines 201-230)
- `EmployeesPage.tsx` (lines 109-114, 131-153)
- `ShiftsPage.tsx` (lines 117-123, 157-178)
- `TemplatesPage.tsx` (lines 100-125, 161-186)

**Recommendation**: Extract a `StatCard` component:
```tsx
interface StatCardProps {
  icon: string
  iconBg: string
  label: string
  value: string | number
}
```

---

#### S2. Extract repeated filter pill button pattern
The filter pill pattern (rounded-full, active/inactive states) is repeated in:
- `AddressesPage.tsx` (lines 273-294)
- `EmployeesPage.tsx` (lines 184-256)

**Recommendation**: Create a `FilterPill` component.

---

#### S3. Consider using Radix DropdownMenu for ActionMenu and UserDropdown
Both `ActionMenu` (AddressesPage) and `UserDropdown` (DashboardLayout) implement click-outside and Escape handling manually. Radix `@radix-ui/react-dropdown-menu` would handle this with built-in focus management and ARIA.

---

#### S4. Add `aria-label` to stat cards and icon-only elements
Stat cards in AddressesPage have `onClick` handlers but no `role="button"` or `aria-label`. Similarly, the "..." action menu trigger button uses literal text "..." rather than an accessible label.

**File**: `/Users/andreyafanasyev/Code/UK/frontend/src/pages/AddressesPage.tsx`, line 63-64
```tsx
<button className="...">
  ...
</button>
```

**Recommendation**: Add `aria-label="Действия"` or similar to the action menu trigger.

---

#### S5. Add `key` to ConfirmDialog children for transition animations
ConfirmDialog instances rendered with dynamic content (title, description) will not animate between different confirm actions because React sees the same component tree.

---

## 3. Checklist Summary

| Check | Status | Notes |
|-------|--------|-------|
| TypeScript compilation | PASS | Zero errors |
| All window.confirm removed | PASS | Verified via grep |
| All window.alert removed | PASS | Verified via grep |
| Toast on all mutations | PASS | 27+ mutations covered |
| Error Boundaries | PASS | Global + Page level |
| ARIA/a11y basics | PASS | lang=ru, focus-visible, sr-only labels |
| Tailwind @theme usage | PARTIAL | ~30 instances of wrong `font-[var(...)]` syntax |
| No hardcoded colors | PARTIAL | ~25 hex values should use tokens |
| Consistent patterns | PARTIAL | Font syntax, empty deps array |
| DnD business logic | PASS | VALID_TRANSITIONS, optimistic updates intact |
| WebSocket integration | PASS | useShiftsWebSocket unchanged |
| Role-based routing | PASS | ProtectedRoute with allowedRoles |
| Responsive sidebar | PASS | 3 states: expanded, collapsed, hidden |
| Performance | NOTE | No React.memo; acceptable for current scale |

---

## 4. Recommended Action Items (Priority Order)

1. **Fix `font-[var(--font-*)]` to `font-[family-name:var(--font-*)]`** across ~30 occurrences (M1) -- global find/replace
2. **Add missing deps to KanbanPage useEffect** (M2) -- 1-line fix
3. **Remove unused `@radix-ui/react-select`** from package.json (M3) -- or plan to use it
4. **Replace hardcoded hex colors** with `@theme` tokens in KanbanColumn STATUS_DOT, LoginPage, RequestCard (M4) -- cosmetic but important for maintainability
5. **Fix ConfirmDialog double-close** behavior (M5) -- minor logic fix
6. **Add explanatory comments** to Error Boundary inline styles (L3)
7. **Consider React.memo** for list item components (L1) -- performance improvement for large datasets

---

*Review performed on commit `c9994f7` against baseline `a658ade`.*
*Total lines of frontend code changed: ~8,500+ (excluding package-lock.json).*
