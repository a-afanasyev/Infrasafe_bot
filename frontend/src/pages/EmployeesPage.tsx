import { useEffect, useMemo, useState, useCallback } from 'react'
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
import ConfirmDialog from '../components/shared/ConfirmDialog'
import { usePageTitle } from '../hooks/usePageTitle'

const primaryBtnStyle: React.CSSProperties = {
  background: 'var(--accent)',
  border: 'none',
  borderRadius: 8,
  cursor: 'pointer',
  fontSize: '13px',
  color: '#fff',
  padding: '7px 14px',
  fontFamily: 'var(--font-display)',
  fontWeight: 600,
}

const secondaryBtnStyle: React.CSSProperties = {
  background: 'none',
  border: '1px solid var(--border)',
  borderRadius: 8,
  cursor: 'pointer',
  fontSize: '13px',
  color: 'var(--text-secondary)',
  padding: '7px 14px',
  fontFamily: 'var(--font-display)',
  fontWeight: 500,
}

function chipStyle(active: boolean): React.CSSProperties {
  return {
    background: active ? 'var(--accent)' : 'var(--bg-card)',
    border: `1px solid ${active ? 'var(--accent)' : 'var(--border)'}`,
    borderRadius: 20,
    cursor: 'pointer',
    fontSize: '12px',
    color: active ? '#fff' : 'var(--text-secondary)',
    padding: '5px 12px',
    fontFamily: 'var(--font-display)',
    fontWeight: active ? 600 : 400,
    transition: 'all 0.15s',
  }
}

export default function EmployeesPage() {
  usePageTitle('Сотрудники')
  const { setActions, clearActions } = useTopbar()
  const [roleFilter, setRoleFilter] = useState<string>('all')
  const [statusFilter, setStatusFilter] = useState<string>('all')
  const [specFilter, setSpecFilter] = useState<string>('all')
  const [search, setSearch] = useState<string>('')
  const [viewMode, setViewMode] = useState<'tile' | 'table'>(() => {
    try {
      const stored = localStorage.getItem('employees_view_mode')
      return (stored === 'tile' || stored === 'table') ? stored : 'tile'
    } catch { return 'tile' }
  })

  useEffect(() => {
    try { localStorage.setItem('employees_view_mode', viewMode) } catch {}
  }, [viewMode])

  const apiFilters: Record<string, string | boolean | undefined> = {
    ...(roleFilter !== 'all' ? { role: roleFilter } : {}),
    ...(statusFilter === 'on_shift' ? { has_active_shift: true } : {}),
    ...(statusFilter === 'verified' ? { verification_status: 'verified' } : {}),
    ...(specFilter !== 'all' ? { specialization: specFilter } : {}),
  }

  const { data: employees = [], isLoading, isError } = useEmployees(apiFilters, search || undefined)

  const [assignTarget, setAssignTarget] = useState<EmployeeBrief | null>(null)
  const [confirmState, setConfirmState] = useState<{
    open: boolean
    title: string
    description: string
    onConfirm: () => void
  }>({ open: false, title: '', description: '', onConfirm: () => {} })

  const approveEmployee = useApproveEmployee()
  const rejectEmployee = useRejectEmployee()
  const blockEmployee = useBlockEmployee()
  const unblockEmployee = useUnblockEmployee()

  const handleBlockToggle = useCallback((e: EmployeeBrief) => {
    const empName = [e.first_name, e.last_name].filter(Boolean).join(' ') || `#${e.id}`
    const isBlocked = e.status === 'blocked'
    setConfirmState({
      open: true,
      title: isBlocked ? 'Разблокировать сотрудника' : 'Заблокировать сотрудника',
      description: isBlocked
        ? `Разблокировать сотрудника ${empName}?`
        : `Заблокировать сотрудника ${empName}?`,
      onConfirm: () => {
        if (isBlocked) {
          unblockEmployee.mutate(e.id)
        } else {
          blockEmployee.mutate(e.id)
        }
      },
    })
  }, [blockEmployee, unblockEmployee])

  const total = employees.length
  const onShift = employees.filter(e => e.active_shift_id !== null).length
  const pending = employees.filter(
    e => e.verification_status !== 'verified' && e.verification_status !== 'rejected'
  ).length
  const verified = employees.filter(e => e.verification_status === 'verified').length

  const actionsNode = useMemo(() => (
    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
      <input
        type="text"
        placeholder="Поиск сотрудника..."
        value={search}
        onChange={e => setSearch(e.target.value)}
        style={{
          background: 'var(--bg-card)',
          border: '1px solid var(--border)',
          borderRadius: 8,
          padding: '6px 12px',
          fontSize: '13px',
          color: 'var(--text-primary)',
          fontFamily: 'var(--font-display)',
          outline: 'none',
          width: '200px',
        }}
      />
      <button style={secondaryBtnStyle}>Экспорт</button>
      <button style={primaryBtnStyle}>+ Добавить</button>
    </div>
  ), [search])

  useEffect(() => {
    setActions(actionsNode)
    return clearActions
  }, [setActions, clearActions, actionsNode])

  const STATS = [
    { label: 'Всего сотрудников', value: total, iconBg: 'var(--blue)', icon: '👥' },
    { label: 'На смене сейчас', value: onShift, iconBg: 'var(--emerald)', icon: '🟢' },
    { label: 'Ожидают одобрения', value: pending, iconBg: 'var(--amber)', icon: '⏳' },
    { label: 'Верифицированы', value: verified, iconBg: 'var(--violet)', icon: '✓' },
  ]

  const pendingEmployees = employees.filter(
    e => e.verification_status !== 'verified' && e.verification_status !== 'rejected'
  )

  if (isLoading) return <LoadingSpinner />

  if (isError) return (
    <div className="flex-1 flex items-center justify-center text-[var(--text-muted)]">
      Ошибка загрузки сотрудников
    </div>
  )

  return (
    <div style={{ padding: '20px 24px', display: 'flex', flexDirection: 'column', gap: '20px' }}>
      {/* Stats bar */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '12px' }}>
        {STATS.map(card => (
          <div
            key={card.label}
            style={{
              background: 'var(--bg-card)',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius)',
              padding: '16px',
              display: 'flex',
              alignItems: 'center',
              gap: '14px',
            }}
          >
            <div style={{
              width: 48,
              height: 48,
              borderRadius: 12,
              background: card.iconBg + '22',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: '22px',
              flexShrink: 0,
            }}>
              {card.icon}
            </div>
            <div>
              <div style={{
                fontFamily: 'var(--font-mono)',
                fontSize: '22px',
                fontWeight: 600,
                color: 'var(--text-primary)',
              }}>
                {card.value}
              </div>
              <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: 2 }}>
                {card.label}
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Pending approvals */}
      {pendingEmployees.length > 0 && (
        <div style={{
          background: 'var(--bg-card)',
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius)',
          padding: '20px',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '16px' }}>
            <span style={{
              fontFamily: 'var(--font-display)',
              fontWeight: 600,
              fontSize: '14px',
              color: 'var(--text-primary)',
            }}>
              Ожидают одобрения
            </span>
            <span style={{
              background: 'rgba(245,158,11,0.2)',
              color: 'var(--amber)',
              borderRadius: 20,
              padding: '2px 8px',
              fontSize: '11px',
              fontWeight: 600,
            }}>
              {pendingEmployees.length}
            </span>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {pendingEmployees.map(e => (
              <PendingApprovalCard
                key={e.id}
                employee={e}
                onApprove={(id) => approveEmployee.mutate(id)}
                onReject={(id) => rejectEmployee.mutate(id)}
                isPending={approveEmployee.isPending || rejectEmployee.isPending}
              />
            ))}
          </div>
        </div>
      )}

      {/* Filters + view toggle */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr auto', gap: '8px', alignItems: 'start' }}>
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
                  background: `color-mix(in srgb, ${color} 13%, transparent)`,
                  border: `1px solid color-mix(in srgb, ${color} 33%, transparent)`,
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

      {/* Staff — tile or table */}
      {viewMode === 'table' ? (
        <StaffTable
          employees={employees}
          onAssign={(e) => setAssignTarget(e)}
          onBlock={handleBlockToggle}
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
              onBlock={handleBlockToggle}
              isBlockPending={blockEmployee.isPending || unblockEmployee.isPending}
            />
          ))}
        </div>
      )}

      {assignTarget && (
        <AssignRequestModal
          employee={assignTarget}
          onClose={() => setAssignTarget(null)}
        />
      )}

      <ConfirmDialog
        open={confirmState.open}
        onOpenChange={(open) => setConfirmState(prev => ({ ...prev, open }))}
        title={confirmState.title}
        description={confirmState.description}
        confirmLabel="Подтвердить"
        onConfirm={confirmState.onConfirm}
        variant="warning"
        loading={blockEmployee.isPending || unblockEmployee.isPending}
      />
    </div>
  )
}
