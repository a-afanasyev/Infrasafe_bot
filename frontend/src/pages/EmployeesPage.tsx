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
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'

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
    <div className="flex items-center gap-2">
      <Input
        type="text"
        placeholder="Поиск сотрудника..."
        value={search}
        onChange={e => setSearch(e.target.value)}
        className="w-[200px]"
      />
      <Button variant="outline" size="sm">Экспорт</Button>
      <Button size="sm">+ Добавить</Button>
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
    <div className="flex-1 flex items-center justify-center text-text-muted">
      Ошибка загрузки сотрудников
    </div>
  )

  return (
    <div className="p-5 px-6 flex flex-col gap-5">
      {/* Stats bar */}
      <div className="grid grid-cols-4 gap-3">
        {STATS.map(card => (
          <div
            key={card.label}
            className="bg-bg-card border border-border-default rounded-default p-4 flex items-center gap-3.5"
          >
            <div
              className="w-12 h-12 rounded-[12px] flex items-center justify-center text-[22px] shrink-0"
              style={{ background: card.iconBg + '22' }}
            >
              {card.icon}
            </div>
            <div>
              <div className="font-[var(--font-mono)] text-[22px] font-semibold text-text-primary">
                {card.value}
              </div>
              <div className="text-[11px] text-text-muted mt-0.5">
                {card.label}
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Pending approvals */}
      {pendingEmployees.length > 0 && (
        <div className="bg-bg-card border border-border-default rounded-default p-5">
          <div className="flex items-center gap-2 mb-4">
            <span className="font-[var(--font-display)] font-semibold text-sm text-text-primary">
              Ожидают одобрения
            </span>
            <span className="bg-amber/20 text-amber rounded-full px-2 py-0.5 text-[11px] font-semibold">
              {pendingEmployees.length}
            </span>
          </div>
          <div className="flex flex-col gap-2">
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
      <div className="grid grid-cols-[1fr_auto] gap-2 items-start">
        <div className="flex items-center gap-1.5 flex-wrap">
          {/* Role */}
          {[
            { key: 'all', label: 'Все' },
            { key: 'executor', label: 'Исполнители' },
            { key: 'manager', label: 'Менеджеры' },
          ].map(f => (
            <button
              key={f.key}
              onClick={() => setRoleFilter(f.key)}
              className={cn(
                'rounded-full cursor-pointer text-xs px-3 py-1.5 font-[var(--font-display)] transition-all duration-150 border',
                roleFilter === f.key
                  ? 'bg-accent border-accent text-white font-semibold'
                  : 'bg-bg-card border-border-default text-text-secondary font-normal'
              )}
            >
              {f.label}
            </button>
          ))}
          <div className="w-px h-6 bg-border-default mx-0.5" />
          {/* Status */}
          {[
            { key: 'all', label: 'Все статусы' },
            { key: 'on_shift', label: 'На смене' },
            { key: 'verified', label: 'Верифицированы' },
          ].map(f => (
            <button
              key={f.key}
              onClick={() => setStatusFilter(f.key)}
              className={cn(
                'rounded-full cursor-pointer text-xs px-3 py-1.5 font-[var(--font-display)] transition-all duration-150 border',
                statusFilter === f.key
                  ? 'bg-accent border-accent text-white font-semibold'
                  : 'bg-bg-card border-border-default text-text-secondary font-normal'
              )}
            >
              {f.label}
            </button>
          ))}
          <div className="w-px h-6 bg-border-default mx-0.5" />
          {/* Specialization -- single select */}
          <button
            onClick={() => setSpecFilter('all')}
            className={cn(
              'rounded-full cursor-pointer text-xs px-3 py-1.5 font-[var(--font-display)] transition-all duration-150 border',
              specFilter === 'all'
                ? 'bg-accent border-accent text-white font-semibold'
                : 'bg-bg-card border-border-default text-text-secondary font-normal'
            )}
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
                className={cn(
                  'rounded-full cursor-pointer text-xs px-3 py-1.5 font-[var(--font-display)] transition-all duration-150 border',
                  !isActive && 'bg-bg-card border-border-default text-text-secondary font-normal'
                )}
                style={isActive ? {
                  background: `color-mix(in srgb, ${color} 13%, transparent)`,
                  border: `1px solid color-mix(in srgb, ${color} 33%, transparent)`,
                  color,
                  fontWeight: 600,
                } : undefined}
              >
                {label}
              </button>
            )
          })}
        </div>
        {/* View toggle */}
        <div className="flex bg-bg-card border border-border-default rounded-sm overflow-hidden shrink-0">
          {(['tile', 'table'] as const).map((mode) => (
            <button
              key={mode}
              onClick={() => setViewMode(mode)}
              title={mode === 'tile' ? 'Плитки' : 'Таблица'}
              className={cn(
                'px-3 py-1.5 border-none cursor-pointer text-base flex items-center transition-all duration-150',
                viewMode === mode
                  ? 'bg-accent text-white'
                  : 'bg-transparent text-text-muted'
              )}
            >
              {mode === 'tile' ? '⊞' : '☰'}
            </button>
          ))}
        </div>
      </div>

      {/* Staff -- tile or table */}
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
        <div className="grid grid-cols-[repeat(auto-fill,minmax(340px,1fr))] gap-4">
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
