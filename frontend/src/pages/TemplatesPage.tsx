import { useEffect, useMemo, useState, useCallback } from 'react'
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
import { SPEC_COLORS, SPEC_DISPLAY } from '../utils/employeeUtils'
import ConfirmDialog from '../components/shared/ConfirmDialog'

// Map English spec keys → colors from SPEC_COLORS (keyed by Russian name)
const SPEC_KEY_TO_COLOR: Record<string, string> = {
  electrician: SPEC_COLORS['Электрика'] ?? 'var(--text-secondary)',
  plumber: SPEC_COLORS['Сантехника'] ?? 'var(--text-secondary)',
  heating: SPEC_COLORS['Отопление'] ?? 'var(--text-secondary)',
  cleaning: SPEC_COLORS['Уборка'] ?? 'var(--text-secondary)',
  security: SPEC_COLORS['Безопасность'] ?? 'var(--text-secondary)',
  elevator: SPEC_COLORS['Лифт'] ?? 'var(--text-secondary)',
  landscaping: SPEC_COLORS['Благоустройство'] ?? 'var(--text-secondary)',
  ventilation: SPEC_COLORS['Вентиляция'] ?? 'var(--text-secondary)',
}

const SHIFT_TYPE_COLOR: Record<string, string> = {
  regular: 'var(--blue)',
  emergency: 'var(--red)',
  overtime: 'var(--amber)',
  maintenance: 'var(--violet)',
}

const SHIFT_TYPE_LABEL: Record<string, string> = {
  regular: 'Обычная',
  emergency: 'Экстренная',
  overtime: 'Сверхурочная',
  maintenance: 'Тех. обслуживание',
}

const DAY_LABELS = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']

const primaryBtnStyle: React.CSSProperties = {
  padding: '8px 14px',
  borderRadius: 'var(--radius-sm)',
  fontSize: '13px',
  fontWeight: 600,
  cursor: 'pointer',
  fontFamily: 'var(--font-body)',
  background: 'var(--accent)',
  color: '#000',
  border: 'none',
}

function formatTime(hour: number, minute: number): string {
  return `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`
}

function computeEndTime(hour: number, minute: number, duration: number): string {
  const totalMinutes = hour * 60 + minute + duration * 60
  const endHour = Math.floor(totalMinutes / 60) % 24
  const endMinute = totalMinutes % 60
  return formatTime(endHour, endMinute)
}

// Subcomponent to isolate hover state for delete button
function DeleteButton({ onDelete }: { onDelete: () => void }) {
  const [hovered, setHovered] = useState(false)
  return (
    <button
      onClick={onDelete}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        padding: '5px 10px',
        borderRadius: 6,
        fontSize: '12px',
        fontWeight: 600,
        cursor: 'pointer',
        fontFamily: 'var(--font-body)',
        background: hovered ? 'rgba(239,68,68,0.1)' : 'var(--bg-surface)',
        color: hovered ? 'var(--red, #ef4444)' : 'var(--text-secondary)',
        border: `1px solid ${hovered ? 'rgba(239,68,68,0.4)' : 'var(--border)'}`,
        whiteSpace: 'nowrap',
        transition: 'all 0.15s',
      }}
    >
      Удал.
    </button>
  )
}

export default function TemplatesPage() {
  const { setActions, clearActions } = useTopbar()
  const [createOpen, setCreateOpen] = useState(false)
  const [pendingCreateId, setPendingCreateId] = useState<number | null>(null)

  const { data: templates = [], isLoading, isError } = useTemplates()
  const updateTemplate = useUpdateTemplate()
  const deleteTemplate = useDeleteTemplate()
  const createFromTemplate = useCreateShiftFromTemplate()

  const actionsNode = useMemo(
    () => (
      <button onClick={() => setCreateOpen(true)} style={primaryBtnStyle}>
        + Создать шаблон
      </button>
    ),
    [setCreateOpen],
  )

  useEffect(() => {
    setActions(actionsNode)
    return clearActions
  }, [setActions, clearActions, actionsNode])

  const totalCount = templates.length
  const autoCreateCount = templates.filter(t => t.auto_create).length
  const activeCount = templates.filter(t => t.is_active).length

  const STATS = [
    {
      emoji: '📋',
      value: totalCount,
      label: 'Всего шаблонов',
      color: 'var(--blue)',
      bgGrad:
        'linear-gradient(135deg, rgba(59,130,246,0.25), rgba(37,99,235,0.1))',
    },
    {
      emoji: '🔄',
      value: autoCreateCount,
      label: 'Авто-создание',
      color: 'var(--emerald)',
      bgGrad:
        'linear-gradient(135deg, rgba(16,185,129,0.25), rgba(5,150,105,0.1))',
    },
    {
      emoji: '📅',
      value: activeCount,
      label: 'Активных шаблонов',
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
      <div
        style={{
          padding: '20px 24px',
          color: 'var(--red, #ef4444)',
          fontSize: '14px',
        }}
      >
        Ошибка загрузки шаблонов. Проверьте соединение и попробуйте снова.
      </div>
    )
  }

  const thStyle: React.CSSProperties = {
    padding: '10px 14px',
    textAlign: 'left',
    fontSize: '0.65rem',
    fontWeight: 600,
    color: 'var(--text-muted)',
    textTransform: 'uppercase',
    letterSpacing: '0.06em',
    whiteSpace: 'nowrap',
  }

  const tdStyle: React.CSSProperties = {
    padding: '12px 14px',
    verticalAlign: 'middle',
    borderTop: '1px solid var(--border)',
  }

  return (
    <div
      style={{
        padding: '20px 24px',
        display: 'flex',
        flexDirection: 'column',
        gap: '20px',
      }}
    >
      {/* Stats bar */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(3, 1fr)',
          gap: '16px',
        }}
      >
        {STATS.map(card => (
          <div
            key={card.label}
            style={{
              background: 'var(--bg-card)',
              border: '1px solid var(--border)',
              borderRadius: '12px',
              padding: '20px',
              display: 'flex',
              alignItems: 'center',
              gap: '16px',
            }}
          >
            <div
              style={{
                width: 48,
                height: 48,
                borderRadius: 12,
                background: card.bgGrad,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: '22px',
                flexShrink: 0,
              }}
            >
              {card.emoji}
            </div>
            <div>
              <div
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: '1.5rem',
                  fontWeight: 600,
                  color: card.color,
                  lineHeight: 1,
                }}
              >
                {card.value}
              </div>
              <div
                style={{
                  fontSize: '11px',
                  color: 'var(--text-muted)',
                  marginTop: '4px',
                }}
              >
                {card.label}
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Data table */}
      <div
        style={{
          background: 'var(--bg-card)',
          border: '1px solid var(--border)',
          borderRadius: '12px',
          overflow: 'hidden',
        }}
      >
        {templates.length === 0 ? (
          <EmptyState
            icon="📋"
            title="Нет шаблонов"
            subtitle="Создайте первый шаблон смены"
          />
        ) : (
          <table
            style={{
              width: '100%',
              borderCollapse: 'separate',
              borderSpacing: 0,
            }}
          >
            <thead>
              <tr style={{ background: 'var(--bg-surface)' }}>
                <th style={thStyle}>Название</th>
                <th style={thStyle}>Время</th>
                <th style={thStyle}>Тип</th>
                <th style={thStyle}>Дни недели</th>
                <th style={thStyle}>Специализации</th>
                <th style={thStyle}>Исполнители</th>
                <th style={thStyle}>Авто</th>
                <th style={thStyle}>Действия</th>
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
                const typeLabel =
                  SHIFT_TYPE_LABEL[tmpl.default_shift_type] ??
                  tmpl.default_shift_type
                const executorProgress =
                  tmpl.max_executors > 0
                    ? Math.round(
                        (tmpl.min_executors / tmpl.max_executors) * 100,
                      )
                    : 0

                return (
                  <TemplateRow
                    key={tmpl.id}
                    tdStyle={tdStyle}
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
        title="Удалить шаблон"
        description="Удалить шаблон? Это действие нельзя отменить."
        confirmLabel="Удалить"
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
  tdStyle: React.CSSProperties
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
  tdStyle,
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
  const [rowHovered, setRowHovered] = useState(false)

  return (
    <tr
      style={{
        opacity: tmpl.is_active ? 1 : 0.5,
        background: rowHovered
          ? 'var(--bg-card-hover, rgba(255,255,255,0.03))'
          : 'transparent',
      }}
      onMouseEnter={() => setRowHovered(true)}
      onMouseLeave={() => setRowHovered(false)}
    >
      {/* Название */}
      <td style={tdStyle}>
        <strong
          style={{
            fontSize: '13px',
            color: 'var(--text-primary)',
            display: 'block',
          }}
        >
          {tmpl.name}
        </strong>
        {tmpl.description && (
          <small style={{ color: 'var(--text-muted)', fontSize: '11px' }}>
            {tmpl.description}
          </small>
        )}
      </td>

      {/* Время */}
      <td style={tdStyle}>
        <div
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: '13px',
            color: 'var(--text-primary)',
            whiteSpace: 'nowrap',
          }}
        >
          {startStr} — {endStr}
        </div>
        <div
          style={{
            fontSize: '11px',
            color: 'var(--text-muted)',
            marginTop: '2px',
          }}
        >
          {tmpl.duration_hours} часов
        </div>
      </td>

      {/* Тип */}
      <td style={tdStyle}>
        <span
          style={{
            display: 'inline-block',
            padding: '3px 8px',
            borderRadius: 20,
            fontSize: '11px',
            fontWeight: 600,
            color: typeColor,
            background: typeColor + '22',
            whiteSpace: 'nowrap',
          }}
        >
          {typeLabel}
        </span>
      </td>

      {/* Дни недели */}
      <td style={tdStyle}>
        <div style={{ display: 'flex', gap: '3px' }}>
          {DAY_LABELS.map((label, dayIdx) => {
            const active = tmpl.days_of_week?.includes(dayIdx) ?? false
            return (
              <div
                key={dayIdx}
                style={{
                  width: 28,
                  height: 28,
                  borderRadius: 6,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: '11px',
                  fontWeight: 600,
                  flexShrink: 0,
                  background: active ? 'var(--accent-dim)' : 'var(--bg-surface)',
                  color: active ? 'var(--accent)' : 'var(--text-muted)',
                  border: `1px solid ${active ? 'var(--border-active)' : 'var(--border)'}`,
                }}
              >
                {label}
              </div>
            )
          })}
        </div>
      </td>

      {/* Специализации */}
      <td style={tdStyle}>
        {tmpl.required_specializations && tmpl.required_specializations.length > 0 ? (
          <div
            style={{
              display: 'flex',
              flexWrap: 'wrap',
              gap: '4px',
              maxWidth: '160px',
            }}
          >
            {tmpl.required_specializations.map(spec => {
              const color = SPEC_KEY_TO_COLOR[spec] ?? 'var(--text-secondary)'
              const label = SPEC_DISPLAY[spec] ?? spec
              return (
                <span
                  key={spec}
                  style={{
                    display: 'inline-block',
                    padding: '2px 6px',
                    borderRadius: 20,
                    fontSize: '10px',
                    fontWeight: 600,
                    color,
                    background: color + '22',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {label}
                </span>
              )
            })}
          </div>
        ) : (
          <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>—</span>
        )}
      </td>

      {/* Исполнители */}
      <td style={tdStyle}>
        <div
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: '13px',
            color: 'var(--text-primary)',
            whiteSpace: 'nowrap',
          }}
        >
          {tmpl.min_executors}—{tmpl.max_executors}
        </div>
        <div
          style={{
            marginTop: '4px',
            width: 60,
            height: 4,
            borderRadius: 2,
            background: 'var(--border)',
            overflow: 'hidden',
          }}
        >
          <div
            style={{
              height: '100%',
              width: `${executorProgress}%`,
              background: 'var(--accent)',
              borderRadius: 2,
            }}
          />
        </div>
      </td>

      {/* Авто toggle */}
      <td style={tdStyle}>
        <div
          onClick={() => onToggleAutoCreate(tmpl.id, !tmpl.auto_create)}
          title={
            tmpl.auto_create ? 'Авто-создание включено' : 'Авто-создание выключено'
          }
          style={{
            width: 40,
            height: 22,
            borderRadius: 11,
            background: tmpl.auto_create ? 'var(--accent)' : 'var(--bg-surface)',
            border: '1px solid var(--border)',
            position: 'relative',
            cursor: 'pointer',
            transition: 'background 0.2s',
            flexShrink: 0,
          }}
        >
          <div
            style={{
              position: 'absolute',
              top: 2,
              left: tmpl.auto_create ? 20 : 2,
              width: 16,
              height: 16,
              borderRadius: '50%',
              background: '#fff',
              transition: 'left 0.2s',
              boxShadow: '0 1px 3px rgba(0,0,0,0.3)',
            }}
          />
        </div>
      </td>

      {/* Действия */}
      <td style={tdStyle}>
        <div style={{ display: 'flex', gap: '6px', flexWrap: 'nowrap' }}>
          {tmpl.is_active && (
            <button
              onClick={() => onCreateFromToday(tmpl.id)}
              disabled={createPending}
              style={{
                padding: '5px 10px',
                borderRadius: 6,
                fontSize: '12px',
                fontWeight: 600,
                cursor: createPending ? 'not-allowed' : 'pointer',
                fontFamily: 'var(--font-body)',
                background: 'var(--accent)',
                color: '#000',
                border: 'none',
                whiteSpace: 'nowrap',
                opacity: createPending ? 0.7 : 1,
              }}
            >
              Создать
            </button>
          )}
          <button
            disabled
            title="Редактирование в разработке"
            style={{
              padding: '5px 10px',
              borderRadius: 6,
              fontSize: '12px',
              fontWeight: 600,
              cursor: 'not-allowed',
              fontFamily: 'var(--font-body)',
              background: 'var(--bg-surface)',
              color: 'var(--text-muted)',
              border: '1px solid var(--border)',
              whiteSpace: 'nowrap',
              opacity: 0.6,
            }}
          >
            Ред.
          </button>
          <DeleteButton onDelete={() => onDelete(tmpl.id)} />
        </div>
      </td>
    </tr>
  )
}
