import { useEffect, useMemo, useState, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { useTopbar } from '../contexts/TopbarContext'
import {
  useTemplates,
  useUpdateTemplate,
  useDeleteTemplate,
  useCreateShiftFromTemplate,
} from '../hooks/useTemplates'
import CreateTemplateModal from '../components/templates/CreateTemplateModal'
import EmptyState from '../components/shared/EmptyState'
import LoadingSpinner from '../components/shared/LoadingSpinner'
import { SPEC_COLORS, getSpecDisplay } from '../utils/employeeUtils'
import ConfirmDialog from '../components/shared/ConfirmDialog'
import { usePageTitle } from '../hooks/usePageTitle'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

const SHIFT_TYPE_COLOR: Record<string, string> = {
  regular: 'var(--blue)',
  emergency: 'var(--red)',
  overtime: 'var(--amber)',
  maintenance: 'var(--violet)',
}

const DAY_KEYS = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'] as const

function formatTime(hour: number, minute: number): string {
  return `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`
}

function computeEndTime(hour: number, minute: number, duration: number): string {
  const totalMinutes = hour * 60 + minute + duration * 60
  const endHour = Math.floor(totalMinutes / 60) % 24
  const endMinute = totalMinutes % 60
  return formatTime(endHour, endMinute)
}

// Format an ISO 'YYYY-MM-DD' anchor date as 'DD.MM'
function formatAnchor(iso: string): string {
  const [, month, day] = iso.split('-')
  return `${day}.${month}`
}

// Subcomponent to isolate hover state for delete button
function DeleteButton({ label, onDelete }: { label: string; onDelete: () => void }) {
  return (
    <Button
      variant="outline"
      size="sm"
      onClick={onDelete}
      className="text-xs hover:bg-red/10 hover:text-red hover:border-red/40"
    >
      {label}
    </Button>
  )
}

export default function TemplatesPage() {
  const { t } = useTranslation()
  usePageTitle(t('nav.templates'))
  const { setActions, clearActions } = useTopbar()
  const [createOpen, setCreateOpen] = useState(false)
  const [pendingCreateId, setPendingCreateId] = useState<number | null>(null)

  const { data: templates = [], isLoading, isError } = useTemplates()
  const updateTemplate = useUpdateTemplate()
  const deleteTemplate = useDeleteTemplate()
  const createFromTemplate = useCreateShiftFromTemplate()

  const actionsNode = useMemo(
    () => (
      <Button onClick={() => setCreateOpen(true)} size="sm">
        {t('templates.createTemplate')}
      </Button>
    ),
    [setCreateOpen, t],
  )

  useEffect(() => {
    setActions(actionsNode)
    return clearActions
  }, [setActions, clearActions, actionsNode])

  const totalCount = templates.length
  const autoCreateCount = templates.filter(tpl => tpl.auto_create).length
  const activeCount = templates.filter(tpl => tpl.is_active).length

  const STATS = [
    {
      emoji: '\u{1F4CB}',
      value: totalCount,
      label: t('templates.totalTemplates'),
      color: 'var(--blue)',
      bgGrad:
        'linear-gradient(135deg, rgba(59,130,246,0.25), rgba(37,99,235,0.1))',
    },
    {
      emoji: '\u{1F504}',
      value: autoCreateCount,
      label: t('templates.autoCreate'),
      color: 'var(--emerald)',
      bgGrad:
        'linear-gradient(135deg, rgba(16,185,129,0.25), rgba(5,150,105,0.1))',
    },
    {
      emoji: '\u{1F4C5}',
      value: activeCount,
      label: t('templates.activeTemplates'),
      color: 'var(--amber)',
      bgGrad:
        'linear-gradient(135deg, rgba(245,158,11,0.25), rgba(217,119,6,0.1))',
    },
  ]

  const [confirmState, setConfirmState] = useState<{
    open: boolean
    templateId: number | null
  }>({ open: false, templateId: null })

  const handleToggleAutoCreate = (id: number, newValue: boolean) => {
    updateTemplate.mutate({ id, auto_create: newValue })
  }

  const handleDelete = useCallback((id: number) => {
    setConfirmState({ open: true, templateId: id })
  }, [])

  const handleCreateFromToday = (id: number) => {
    setPendingCreateId(id)
    createFromTemplate.mutate(
      { template_id: id, date: new Date().toISOString().split('T')[0] },
      { onSettled: () => setPendingCreateId(null) },
    )
  }

  if (isLoading) return <LoadingSpinner />

  if (isError) {
    return (
      <div className="p-5 px-6 text-red text-sm">
        {t('errors.loadTemplates')}
      </div>
    )
  }

  const TABLE_HEADERS = [
    t('templates.headers.name'),
    t('templates.headers.time'),
    t('templates.headers.type'),
    t('templates.headers.daysOfWeek'),
    t('templates.headers.specializations'),
    t('templates.headers.executors'),
    t('templates.headers.auto'),
    t('templates.headers.actions'),
  ]

  return (
    <div className="p-5 px-6 flex flex-col gap-5">
      {/* Stats bar */}
      <div className="grid grid-cols-3 gap-4">
        {STATS.map(card => (
          <div
            key={card.label}
            className="bg-bg-card border border-border-default rounded-[12px] p-5 flex items-center gap-4"
          >
            <div
              className="w-12 h-12 rounded-[12px] flex items-center justify-center text-[22px] shrink-0"
              style={{ background: card.bgGrad }}
            >
              {card.emoji}
            </div>
            <div>
              <div
                className="font-[var(--font-mono)] text-2xl font-semibold leading-none"
                style={{ color: card.color }}
              >
                {card.value}
              </div>
              <div className="text-[11px] text-text-muted mt-1">
                {card.label}
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Data table */}
      <div className="bg-bg-card border border-border-default rounded-[12px] overflow-hidden">
        {templates.length === 0 ? (
          <EmptyState
            icon={'\u{1F4CB}'}
            title={t('templates.noTemplates')}
            subtitle={t('templates.noTemplatesDesc')}
          />
        ) : (
          <table className="w-full border-collapse border-spacing-0">
            <thead>
              <tr className="bg-bg-surface">
                {TABLE_HEADERS.map(h => (
                  <th
                    key={h}
                    className="px-3.5 py-2.5 text-left text-[0.65rem] font-semibold text-text-muted uppercase tracking-wider whitespace-nowrap"
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {templates.map(tmpl => {
                const startStr = formatTime(tmpl.start_hour, tmpl.start_minute)
                const endStr = computeEndTime(
                  tmpl.start_hour,
                  tmpl.start_minute,
                  tmpl.duration_hours,
                )
                const typeColor =
                  SHIFT_TYPE_COLOR[tmpl.default_shift_type] ??
                  'var(--text-secondary)'
                const typeLabel = t(`shiftType.${tmpl.default_shift_type}`)
                const executorProgress =
                  tmpl.max_executors > 0
                    ? Math.round(
                        (tmpl.min_executors / tmpl.max_executors) * 100,
                      )
                    : 0

                return (
                  <TemplateRow
                    key={tmpl.id}
                    tmpl={tmpl}
                    startStr={startStr}
                    endStr={endStr}
                    typeColor={typeColor}
                    typeLabel={typeLabel}
                    executorProgress={executorProgress}
                    onToggleAutoCreate={handleToggleAutoCreate}
                    onDelete={handleDelete}
                    onCreateFromToday={handleCreateFromToday}
                    createPending={pendingCreateId === tmpl.id}
                  />
                )
              })}
            </tbody>
          </table>
        )}
      </div>

      {/* Create modal */}
      <CreateTemplateModal
        isOpen={createOpen}
        onClose={() => setCreateOpen(false)}
      />

      <ConfirmDialog
        open={confirmState.open}
        onOpenChange={(open) => setConfirmState(prev => ({ ...prev, open }))}
        title={t('templates.confirmDeleteTitle')}
        description={t('templates.confirmDeleteDesc')}
        confirmLabel={t('common.delete')}
        onConfirm={() => {
          if (confirmState.templateId !== null) {
            deleteTemplate.mutate(confirmState.templateId)
          }
        }}
        variant="danger"
        loading={deleteTemplate.isPending}
      />
    </div>
  )
}

interface TemplateRowProps {
  tmpl: import('../hooks/useTemplates').TemplateBrief
  startStr: string
  endStr: string
  typeColor: string
  typeLabel: string
  executorProgress: number
  onToggleAutoCreate: (id: number, newValue: boolean) => void
  onDelete: (id: number) => void
  onCreateFromToday: (id: number) => void
  createPending: boolean
}

function TemplateRow({
  tmpl,
  startStr,
  endStr,
  typeColor,
  typeLabel,
  executorProgress,
  onToggleAutoCreate,
  onDelete,
  onCreateFromToday,
  createPending,
}: TemplateRowProps) {
  const { t } = useTranslation()
  const [rowHovered, setRowHovered] = useState(false)

  return (
    <tr
      className={cn(
        'transition-colors',
        !tmpl.is_active && 'opacity-50',
        rowHovered ? 'bg-bg-card-hover' : 'bg-transparent'
      )}
      onMouseEnter={() => setRowHovered(true)}
      onMouseLeave={() => setRowHovered(false)}
    >
      {/* Name */}
      <td className="px-3.5 py-3 align-middle border-t border-border-default">
        <strong className="text-[13px] text-text-primary block">
          {tmpl.name}
        </strong>
        {tmpl.description && (
          <small className="text-text-muted text-[11px]">
            {tmpl.description}
          </small>
        )}
      </td>

      {/* Time */}
      <td className="px-3.5 py-3 align-middle border-t border-border-default">
        <div className="font-[var(--font-mono)] text-[13px] text-text-primary whitespace-nowrap">
          {startStr} — {endStr}
        </div>
        <div className="text-[11px] text-text-muted mt-0.5">
          {tmpl.duration_hours} {t('common.hours')}
        </div>
      </td>

      {/* Type */}
      <td className="px-3.5 py-3 align-middle border-t border-border-default">
        <span
          className="inline-block px-2 py-0.5 rounded-full text-[11px] font-semibold whitespace-nowrap"
          style={{
            color: typeColor,
            background: typeColor + '22',
          }}
        >
          {typeLabel}
        </span>
      </td>

      {/* Days of week */}
      <td className="px-3.5 py-3 align-middle border-t border-border-default">
        {tmpl.recurrence_mode === 'cycle' &&
        tmpl.cycle_days_on != null &&
        tmpl.cycle_days_off != null ? (
          <span className="inline-block px-2 py-0.5 rounded-full text-[11px] font-semibold whitespace-nowrap bg-accent-dim text-accent border border-border-active">
            {tmpl.cycle_anchor_date
              ? t('templates.cycleBadge', {
                  on: tmpl.cycle_days_on,
                  off: tmpl.cycle_days_off,
                  anchor: formatAnchor(tmpl.cycle_anchor_date),
                })
              : t('templates.cycleBadgeNoAnchor', {
                  on: tmpl.cycle_days_on,
                  off: tmpl.cycle_days_off,
                })}
          </span>
        ) : (
          <div className="flex gap-[3px]">
            {DAY_KEYS.map((dayKey, dayIdx) => {
              const active = tmpl.days_of_week?.includes(dayIdx) ?? false
              return (
                <div
                  key={dayIdx}
                  className={cn(
                    'w-7 h-7 rounded-[6px] flex items-center justify-center text-[11px] font-semibold shrink-0 border',
                    active
                      ? 'bg-accent-dim text-accent border-border-active'
                      : 'bg-bg-surface text-text-muted border-border-default'
                  )}
                >
                  {t(`days.short.${dayKey}`)}
                </div>
              )
            })}
          </div>
        )}
      </td>

      {/* Specializations */}
      <td className="px-3.5 py-3 align-middle border-t border-border-default">
        {tmpl.required_specializations && tmpl.required_specializations.length > 0 ? (
          <div className="flex flex-wrap gap-1 max-w-[160px]">
            {tmpl.required_specializations.map(spec => {
              const color = SPEC_COLORS[spec] ?? 'var(--text-secondary)'
              const label = getSpecDisplay(spec, t)
              return (
                <span
                  key={spec}
                  className="inline-block px-1.5 py-0.5 rounded-full text-[10px] font-semibold whitespace-nowrap"
                  style={{
                    color,
                    background: color + '22',
                  }}
                >
                  {label}
                </span>
              )
            })}
          </div>
        ) : (
          <span className="text-xs text-text-muted">{'—'}</span>
        )}
      </td>

      {/* Executors */}
      <td className="px-3.5 py-3 align-middle border-t border-border-default">
        <div className="font-[var(--font-mono)] text-[13px] text-text-primary whitespace-nowrap">
          {tmpl.min_executors}{'—'}{tmpl.max_executors}
        </div>
        <div className="mt-1 w-[60px] h-1 rounded-sm bg-border-default overflow-hidden">
          <div
            className="h-full bg-accent rounded-sm"
            style={{ width: `${executorProgress}%` }}
          />
        </div>
      </td>

      {/* Auto toggle */}
      <td className="px-3.5 py-3 align-middle border-t border-border-default">
        <div
          onClick={() => onToggleAutoCreate(tmpl.id, !tmpl.auto_create)}
          title={
            tmpl.auto_create ? t('templates.autoCreateOn') : t('templates.autoCreateOff')
          }
          className={cn(
            'w-10 h-[22px] rounded-full border border-border-default relative cursor-pointer transition-colors duration-200 shrink-0',
            tmpl.auto_create ? 'bg-accent' : 'bg-bg-surface'
          )}
        >
          <div
            className="absolute top-0.5 w-4 h-4 rounded-full bg-white shadow-[0_1px_3px_rgba(0,0,0,0.3)] transition-[left] duration-200"
            style={{ left: tmpl.auto_create ? 20 : 2 }}
          />
        </div>
      </td>

      {/* Actions */}
      <td className="px-3.5 py-3 align-middle border-t border-border-default">
        <div className="flex gap-1.5 flex-nowrap">
          {tmpl.is_active && (
            <Button
              size="sm"
              onClick={() => onCreateFromToday(tmpl.id)}
              disabled={createPending}
              className="text-xs"
            >
              {t('templates.createFromTemplate')}
            </Button>
          )}
          <Button
            variant="outline"
            size="sm"
            disabled
            title={t('employees.editInDev')}
            className="text-xs opacity-60"
          >
            {t('templates.editBtn')}
          </Button>
          <DeleteButton label={t('templates.deleteBtn')} onDelete={() => onDelete(tmpl.id)} />
        </div>
      </td>
    </tr>
  )
}
