# Employees Filters & View Toggle — Implementation Plan

> _Последнее редактирование: 2026-03-12_

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a specialization filter (single-select chips) and a tile/table view toggle (persisted in localStorage) to the employees page, with a new `StaffTable` component for the table view.

**Architecture:** Frontend-only. Two tasks: (1) create `StaffTable` component, (2) update `EmployeesPage` to add filters and toggle. No backend changes needed — `GET /api/v2/shifts/employees?specialization=electrician` already works.

**Tech Stack:** React 18, TypeScript, inline styles with CSS custom properties (`var(--accent)` etc.), `@tanstack/react-query`

---

## Task 1: Create StaffTable component

**Files:**
- Create: `frontend/src/components/employees/StaffTable.tsx`

**Context — existing utilities to import:**
- `AVATAR_GRADIENTS`, `SPEC_COLORS`, `SPEC_DISPLAY`, `getInitials` — from `../../utils/employeeUtils`
- `SPEC_COLORS` keys are plain Russian names: `'Электрика'`, `'Сантехника'`, etc.
- `SPEC_DISPLAY` maps English backend keys → Russian labels with emoji: `{ 'electrician': '⚡ Электрика', ... }`
- To get color for a spec key: `SPEC_DISPLAY[key]` → `'⚡ Электрика'` → strip emoji prefix → `'Электрика'` → `SPEC_COLORS['Электрика']`
- `EmployeeBrief` type has: `id`, `first_name`, `last_name`, `phone`, `specialization: string[]`, `active_shift_id: number | null`, `verification_status`, `status`

- [ ] **Step 1: Create the file with full implementation**

```typescript
// frontend/src/components/employees/StaffTable.tsx
import type { EmployeeBrief } from '../../hooks/useEmployees'
import { AVATAR_GRADIENTS, SPEC_COLORS, SPEC_DISPLAY, getInitials } from '../../utils/employeeUtils'
import EmptyState from '../shared/EmptyState'

interface Props {
  employees: EmployeeBrief[]
  onAssign: (e: EmployeeBrief) => void
  onBlock: (e: EmployeeBrief) => void
  isBlockPending: boolean
}

const HEADERS = ['Сотрудник', 'Специализация', 'Верификация', 'Статус', 'Смена', 'Действия']
const COLS = '2.2fr 1.6fr 1fr 0.8fr 0.8fr 1fr'

function specColor(key: string): string {
  const label = (SPEC_DISPLAY[key] ?? key).replace(/^\S+\s/, '') // strip emoji prefix
  return SPEC_COLORS[label] ?? 'var(--text-muted)'
}

export default function StaffTable({ employees, onAssign, onBlock, isBlockPending }: Props) {
  if (employees.length === 0) {
    return (
      <div style={{
        background: 'var(--bg-card)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius)',
        padding: '40px',
      }}>
        <EmptyState icon="👥" title="Сотрудники не найдены" subtitle="Попробуйте другой фильтр" />
      </div>
    )
  }

  return (
    <div style={{
      background: 'var(--bg-card)',
      border: '1px solid var(--border)',
      borderRadius: 'var(--radius)',
      overflow: 'hidden',
    }}>
      {/* Header */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: COLS,
        background: 'var(--bg-surface)',
        borderBottom: '1px solid var(--border)',
        padding: '10px 16px',
        gap: '8px',
      }}>
        {HEADERS.map(h => (
          <span key={h} style={{
            color: 'var(--text-muted)',
            fontSize: '10px',
            fontWeight: 700,
            textTransform: 'uppercase',
            letterSpacing: '0.5px',
            fontFamily: 'var(--font-display)',
          }}>
            {h}
          </span>
        ))}
      </div>

      {/* Rows */}
      {employees.map((emp, idx) => {
        const gradient = AVATAR_GRADIENTS[emp.id % AVATAR_GRADIENTS.length]
        const initials = getInitials(emp.first_name, emp.last_name)
        const isOnShift = emp.active_shift_id !== null
        const isVerified = emp.verification_status === 'verified'
        const isBlocked = emp.status === 'blocked'
        const name = [emp.first_name, emp.last_name].filter(Boolean).join(' ') || 'Без имени'
        const isLast = idx === employees.length - 1

        return (
          <div
            key={emp.id}
            style={{
              display: 'grid',
              gridTemplateColumns: COLS,
              padding: '10px 16px',
              gap: '8px',
              borderBottom: isLast ? 'none' : '1px solid var(--border)',
              alignItems: 'center',
              opacity: isBlocked ? 0.6 : 1,
            }}
          >
            {/* Сотрудник */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <div style={{ position: 'relative', flexShrink: 0 }}>
                <div style={{
                  width: 32, height: 32, borderRadius: '50%', background: gradient,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  color: '#fff', fontSize: '11px', fontWeight: 700,
                  fontFamily: 'var(--font-display)',
                }}>
                  {initials}
                </div>
                <div style={{
                  position: 'absolute', bottom: 0, right: 0,
                  width: 10, height: 10, borderRadius: '50%',
                  background: isOnShift ? 'var(--emerald)' : '#5a6a7a',
                  border: '2px solid var(--bg-card)',
                }} />
              </div>
              <div style={{ minWidth: 0 }}>
                <div style={{
                  fontFamily: 'var(--font-display)', fontWeight: 600,
                  fontSize: '12px', color: 'var(--text-primary)',
                  whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                }}>
                  {name}
                </div>
                {emp.phone && (
                  <div style={{ fontSize: '10px', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                    {emp.phone}
                  </div>
                )}
              </div>
            </div>

            {/* Специализация */}
            <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap' }}>
              {emp.specialization.length > 0
                ? emp.specialization.map(spec => {
                    const label = SPEC_DISPLAY[spec] ?? spec
                    const color = specColor(spec)
                    return (
                      <span key={spec} style={{
                        fontSize: '10px', fontWeight: 600, padding: '2px 7px', borderRadius: 10,
                        background: color + '22', color,
                      }}>
                        {label}
                      </span>
                    )
                  })
                : <span style={{ color: 'var(--text-muted)', fontSize: '11px' }}>—</span>
              }
            </div>

            {/* Верификация */}
            <div>
              <span style={{
                fontSize: '10px', fontWeight: 600, padding: '2px 7px', borderRadius: 10,
                background: isVerified ? 'rgba(16,185,129,0.15)' : 'rgba(245,158,11,0.15)',
                color: isVerified ? 'var(--emerald)' : 'var(--amber)',
              }}>
                {isVerified ? '✓ Верифицирован' : '⏳ На проверке'}
              </span>
            </div>

            {/* Статус */}
            <div>
              <span style={{
                color: isOnShift ? 'var(--emerald)' : '#5a6a7a',
                fontSize: '11px',
                fontWeight: isOnShift ? 600 : 400,
              }}>
                ● {isOnShift ? 'На смене' : 'Не на смене'}
              </span>
            </div>

            {/* Смена */}
            <div style={{ color: 'var(--text-muted)', fontSize: '11px', fontFamily: 'var(--font-mono)' }}>
              {emp.active_shift_id !== null ? `#${emp.active_shift_id}` : '—'}
            </div>

            {/* Действия — opacity: 1 to restore from row 0.6 not possible in CSS,
                but buttons remain clickable regardless of parent opacity */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              {isBlocked ? (
                <>
                  <span style={{
                    fontSize: '10px', fontWeight: 600, padding: '2px 7px', borderRadius: 10,
                    background: 'rgba(239,68,68,0.15)', color: 'var(--red)',
                  }}>
                    Заблокирован
                  </span>
                  <button
                    onClick={() => onBlock(emp)}
                    disabled={isBlockPending}
                    style={{
                      background: 'none', border: 'none', cursor: isBlockPending ? 'not-allowed' : 'pointer',
                      fontSize: '11px', color: 'var(--amber)',
                      fontFamily: 'var(--font-display)', opacity: isBlockPending ? 0.5 : 1,
                    }}
                  >
                    Разблок
                  </button>
                </>
              ) : (
                <>
                  {isVerified && (
                    <button
                      onClick={() => onAssign(emp)}
                      style={{
                        background: 'none', border: 'none', cursor: 'pointer',
                        fontSize: '11px', color: 'var(--accent)',
                        fontFamily: 'var(--font-display)', fontWeight: 600,
                      }}
                    >
                      Назначить
                    </button>
                  )}
                  <button
                    onClick={() => onBlock(emp)}
                    disabled={isBlockPending}
                    style={{
                      background: 'none', border: 'none', cursor: isBlockPending ? 'not-allowed' : 'pointer',
                      fontSize: '11px', color: 'var(--red)',
                      fontFamily: 'var(--font-display)', opacity: isBlockPending ? 0.5 : 1,
                    }}
                  >
                    Блок
                  </button>
                </>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/employees/StaffTable.tsx
git commit -m "feat: add StaffTable component for employees table view"
```

---

## Task 2: Update EmployeesPage — spec filter + view toggle

**Files:**
- Modify: `frontend/src/pages/EmployeesPage.tsx`

**Context — what to change:**
- Add 3 new imports: `useEffect` (already imported but add if missing), `SPEC_DISPLAY`, `SPEC_COLORS` from `employeeUtils`, `StaffTable` from `../components/employees/StaffTable`
- Add 2 new state variables: `specFilter` (string, default `'all'`) and `viewMode` ('tile'|'table', from localStorage)
- Merge `specFilter` into `apiFilters`
- In the filters `<div>`, add a 3rd chip group for specialization after the status group
- Add view toggle buttons at the right end of the filter row
- In the staff section, conditionally render `<StaffTable>` or the existing grid

**Current filter row is at line ~222 in EmployeesPage.tsx. Current staff grid is at line ~248.**

- [ ] **Step 1: Add imports at the top of EmployeesPage.tsx**

Find this block (around line 1–15):
```typescript
import { useEffect, useMemo, useState } from 'react'
import { useTopbar } from '../contexts/TopbarContext'
import {
  useEmployees,
  useApproveEmployee,
  useRejectEmployee,
  useBlockEmployee,
  useUnblockEmployee,
} from '../hooks/useEmployees'
import type { EmployeeBrief } from '../hooks/useEmployees'
import StaffCard from '../components/employees/StaffCard'
import PendingApprovalCard from '../components/employees/PendingApprovalCard'
import EmptyState from '../components/shared/EmptyState'
import LoadingSpinner from '../components/shared/LoadingSpinner'
import AssignRequestModal from '../components/employees/AssignRequestModal'
```

Replace with (adds `SPEC_DISPLAY`, `SPEC_COLORS`, `StaffTable`):
```typescript
import { useEffect, useMemo, useState } from 'react'
import { useTopbar } from '../contexts/TopbarContext'
import {
  useEmployees,
  useApproveEmployee,
  useRejectEmployee,
  useBlockEmployee,
  useUnblockEmployee,
} from '../hooks/useEmployees'
import type { EmployeeBrief } from '../hooks/useEmployees'
import StaffCard from '../components/employees/StaffCard'
import StaffTable from '../components/employees/StaffTable'
import PendingApprovalCard from '../components/employees/PendingApprovalCard'
import EmptyState from '../components/shared/EmptyState'
import LoadingSpinner from '../components/shared/LoadingSpinner'
import AssignRequestModal from '../components/employees/AssignRequestModal'
import { SPEC_DISPLAY, SPEC_COLORS } from '../utils/employeeUtils'
```

- [ ] **Step 2: Add specFilter and viewMode state**

Find (around line 58–60):
```typescript
  const [roleFilter, setRoleFilter] = useState<string>('all')
  const [statusFilter, setStatusFilter] = useState<string>('all')
  const [search, setSearch] = useState<string>('')
```

Replace with:
```typescript
  const [roleFilter, setRoleFilter] = useState<string>('all')
  const [statusFilter, setStatusFilter] = useState<string>('all')
  const [specFilter, setSpecFilter] = useState<string>('all')
  const [search, setSearch] = useState<string>('')
  const [viewMode, setViewMode] = useState<'tile' | 'table'>(() => {
    try { return (localStorage.getItem('employees_view_mode') as 'tile' | 'table') || 'tile' }
    catch { return 'tile' }
  })

  useEffect(() => {
    try { localStorage.setItem('employees_view_mode', viewMode) } catch {}
  }, [viewMode])
```

- [ ] **Step 3: Add specFilter to apiFilters**

Find (around line 62–66):
```typescript
  const apiFilters: Record<string, string | boolean | undefined> = {
    ...(roleFilter !== 'all' ? { role: roleFilter } : {}),
    ...(statusFilter === 'on_shift' ? { has_active_shift: true } : {}),
    ...(statusFilter === 'verified' ? { verification_status: 'verified' } : {}),
  }
```

Replace with:
```typescript
  const apiFilters: Record<string, string | boolean | undefined> = {
    ...(roleFilter !== 'all' ? { role: roleFilter } : {}),
    ...(statusFilter === 'on_shift' ? { has_active_shift: true } : {}),
    ...(statusFilter === 'verified' ? { verification_status: 'verified' } : {}),
    ...(specFilter !== 'all' ? { specialization: specFilter } : {}),
  }
```

- [ ] **Step 4: Replace the filter row and add spec chips + toggle**

Find (around line 221–242):
```typescript
      {/* Filters */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
        {[
          { key: 'all', label: 'Все' },
          { key: 'executor', label: 'Исполнители' },
          { key: 'manager', label: 'Менеджеры' },
        ].map(f => (
          <button key={f.key} onClick={() => setRoleFilter(f.key)} style={chipStyle(roleFilter === f.key)}>
            {f.label}
          </button>
        ))}
        <div style={{ width: 1, height: 24, background: 'var(--border)', margin: '0 4px' }} />
        {[
          { key: 'all', label: 'Все статусы' },
          { key: 'on_shift', label: 'На смене' },
          { key: 'verified', label: 'Верифицированы' },
        ].map(f => (
          <button key={f.key} onClick={() => setStatusFilter(f.key)} style={chipStyle(statusFilter === f.key)}>
            {f.label}
          </button>
        ))}
      </div>
```

Replace with:
```typescript
      {/* Filters + view toggle */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '8px', flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap' }}>
          {/* Role */}
          {[
            { key: 'all', label: 'Все' },
            { key: 'executor', label: 'Исполнители' },
            { key: 'manager', label: 'Менеджеры' },
          ].map(f => (
            <button key={f.key} onClick={() => setRoleFilter(f.key)} style={chipStyle(roleFilter === f.key)}>
              {f.label}
            </button>
          ))}
          <div style={{ width: 1, height: 24, background: 'var(--border)', margin: '0 2px' }} />
          {/* Status */}
          {[
            { key: 'all', label: 'Все статусы' },
            { key: 'on_shift', label: 'На смене' },
            { key: 'verified', label: 'Верифицированы' },
          ].map(f => (
            <button key={f.key} onClick={() => setStatusFilter(f.key)} style={chipStyle(statusFilter === f.key)}>
              {f.label}
            </button>
          ))}
          <div style={{ width: 1, height: 24, background: 'var(--border)', margin: '0 2px' }} />
          {/* Specialization — single select */}
          <button
            onClick={() => setSpecFilter('all')}
            style={chipStyle(specFilter === 'all')}
          >
            Все спец.
          </button>
          {Object.entries(SPEC_DISPLAY).map(([key, label]) => {
            const isActive = specFilter === key
            const color = SPEC_COLORS[label.replace(/^\S+\s/, '')] ?? 'var(--text-muted)'
            return (
              <button
                key={key}
                onClick={() => setSpecFilter(isActive ? 'all' : key)}
                style={isActive ? {
                  background: color + '22',
                  border: `1px solid ${color}55`,
                  borderRadius: 20,
                  cursor: 'pointer',
                  fontSize: '12px',
                  color,
                  padding: '5px 12px',
                  fontFamily: 'var(--font-display)',
                  fontWeight: 600,
                  transition: 'all 0.15s',
                } : chipStyle(false)}
              >
                {label}
              </button>
            )
          })}
        </div>
        {/* View toggle */}
        <div style={{
          display: 'flex',
          background: 'var(--bg-card)',
          border: '1px solid var(--border)',
          borderRadius: 8,
          overflow: 'hidden',
          flexShrink: 0,
        }}>
          {(['tile', 'table'] as const).map((mode) => (
            <button
              key={mode}
              onClick={() => setViewMode(mode)}
              title={mode === 'tile' ? 'Плитки' : 'Таблица'}
              style={{
                padding: '6px 12px',
                background: viewMode === mode ? 'var(--accent)' : 'transparent',
                border: 'none',
                cursor: 'pointer',
                color: viewMode === mode ? '#fff' : 'var(--text-muted)',
                fontSize: '16px',
                display: 'flex',
                alignItems: 'center',
                transition: 'all 0.15s',
              }}
            >
              {mode === 'tile' ? '⊞' : '☰'}
            </button>
          ))}
        </div>
      </div>
```

- [ ] **Step 5: Replace the staff grid section with conditional render**

Find (around line 244–270):
```typescript
      {/* Staff grid */}
      {employees.length === 0 ? (
        <EmptyState icon="👥" title="Сотрудники не найдены" subtitle="Попробуйте другой фильтр" />
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))', gap: '16px' }}>
          {employees.map(emp => (
            <StaffCard
              key={emp.id}
              employee={emp}
              onAssign={(e) => setAssignTarget(e)}
              onBlock={(e) => {
                const empName = [e.first_name, e.last_name].filter(Boolean).join(' ') || `#${e.id}`
                if (e.status === 'blocked') {
                  if (window.confirm(`Разблокировать сотрудника ${empName}?`)) {
                    unblockEmployee.mutate(e.id)
                  }
                } else {
                  if (window.confirm(`Заблокировать сотрудника ${empName}?`)) {
                    blockEmployee.mutate(e.id)
                  }
                }
              }}
              isBlockPending={blockEmployee.isPending || unblockEmployee.isPending}
            />
          ))}
        </div>
      )}
```

Replace with:
```typescript
      {/* Staff — tile or table */}
      {viewMode === 'table' ? (
        <StaffTable
          employees={employees}
          onAssign={(e) => setAssignTarget(e)}
          onBlock={(e) => {
            const empName = [e.first_name, e.last_name].filter(Boolean).join(' ') || `#${e.id}`
            if (e.status === 'blocked') {
              if (window.confirm(`Разблокировать сотрудника ${empName}?`)) {
                unblockEmployee.mutate(e.id)
              }
            } else {
              if (window.confirm(`Заблокировать сотрудника ${empName}?`)) {
                blockEmployee.mutate(e.id)
              }
            }
          }}
          isBlockPending={blockEmployee.isPending || unblockEmployee.isPending}
        />
      ) : employees.length === 0 ? (
        <EmptyState icon="👥" title="Сотрудники не найдены" subtitle="Попробуйте другой фильтр" />
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))', gap: '16px' }}>
          {employees.map(emp => (
            <StaffCard
              key={emp.id}
              employee={emp}
              onAssign={(e) => setAssignTarget(e)}
              onBlock={(e) => {
                const empName = [e.first_name, e.last_name].filter(Boolean).join(' ') || `#${e.id}`
                if (e.status === 'blocked') {
                  if (window.confirm(`Разблокировать сотрудника ${empName}?`)) {
                    unblockEmployee.mutate(e.id)
                  }
                } else {
                  if (window.confirm(`Заблокировать сотрудника ${empName}?`)) {
                    blockEmployee.mutate(e.id)
                  }
                }
              }}
              isBlockPending={blockEmployee.isPending || unblockEmployee.isPending}
            />
          ))}
        </div>
      )}
```

- [ ] **Step 6: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/EmployeesPage.tsx
git commit -m "feat: add specialization filter and tile/table toggle to employees page"
```

---

## Verification

After both tasks complete, rebuild and smoke test:

```bash
cd /path/to/UK && docker compose build frontend && docker compose up -d frontend
```

Manual checks:
1. Open employees page — filter chips show 3 groups (Роль | Статус | Специализация) + toggle on the right
2. Click ⊞/☰ — view switches, selection persists on page reload
3. Click «⚡ Электрика» — list filters to electricians only, chip turns amber
4. Click «Электрика» again — resets to «Все спец.»
5. Table view shows all 6 columns with correct data and action buttons
