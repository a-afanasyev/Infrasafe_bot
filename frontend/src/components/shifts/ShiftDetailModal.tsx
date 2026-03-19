import { useState } from 'react'
import { useShift, useEndShift } from '../../hooks/useShifts'
import { formatTime, formatDateTime } from '../../utils/timezone'
import LoadingSpinner from '../shared/LoadingSpinner'
import ConfirmDialog from '../shared/ConfirmDialog'

interface Props {
  shiftId: number | null
  onClose: () => void
}

const SHIFT_TYPE_LABELS: Record<string, string> = {
  regular: 'Обычная',
  emergency: 'Экстренная',
  overtime: 'Сверхурочная',
  maintenance: 'Обслуживание',
}

const SHIFT_TYPE_COLORS: Record<string, string> = {
  regular: '#3b82f6',
  emergency: '#ef4444',
  overtime: '#f59e0b',
  maintenance: '#8b5cf6',
}

const STATUS_COLORS: Record<string, string> = {
  active: '#00d4aa',
  completed: '#6b7280',
  cancelled: '#ef4444',
  pending: '#f59e0b',
}

export default function ShiftDetailModal({ shiftId, onClose }: Props) {
  const { data: shift, isLoading } = useShift(shiftId)
  const endShift = useEndShift()
  const [confirmEndOpen, setConfirmEndOpen] = useState(false)

  if (shiftId === null) return null

  const handleEndShift = async () => {
    try {
      await endShift.mutateAsync(shiftId)
      onClose()
    } catch {
      // error visible via mutation state
    }
  }

  const typeColor = SHIFT_TYPE_COLORS[shift?.shift_type ?? 'regular'] ?? '#3b82f6'
  const statusColor = STATUS_COLORS[shift?.status ?? 'active'] ?? '#00d4aa'

  const overlayStyle: React.CSSProperties = {
    position: 'fixed',
    inset: 0,
    background: 'rgba(0,0,0,0.6)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 1000,
  }

  return (
    <div style={overlayStyle} onClick={e => { if (e.target === e.currentTarget) onClose() }}>
      <div
        style={{
          width: '480px',
          maxWidth: '100vw',
          background: 'var(--bg-card)',
          border: '1px solid var(--border)',
          borderRadius: '16px',
          padding: '28px',
          display: 'flex',
          flexDirection: 'column',
          gap: '20px',
          maxHeight: '90vh',
          overflowY: 'auto',
        }}
      >
        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <h2
            style={{
              margin: 0,
              fontFamily: 'var(--font-display)',
              fontSize: '18px',
              fontWeight: 700,
              color: 'var(--text-primary)',
            }}
          >
            Детали смены #{shiftId}
          </h2>
          <button
            onClick={onClose}
            style={{
              background: 'none',
              border: 'none',
              color: 'var(--text-muted)',
              cursor: 'pointer',
              fontSize: '20px',
              lineHeight: 1,
              padding: '4px',
            }}
          >
            ×
          </button>
        </div>

        {isLoading ? (
          <LoadingSpinner />
        ) : shift ? (
          <>
            {/* Executor + badges */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
                <span
                  style={{
                    fontFamily: 'var(--font-display)',
                    fontSize: '16px',
                    fontWeight: 600,
                    color: 'var(--text-primary)',
                  }}
                >
                  {shift.executor_name ?? `Исполнитель #${shift.user_id}`}
                </span>
                <span
                  style={{
                    background: `${typeColor}22`,
                    color: typeColor,
                    border: `1px solid ${typeColor}66`,
                    borderRadius: '20px',
                    padding: '3px 10px',
                    fontSize: '11px',
                    fontWeight: 700,
                  }}
                >
                  {SHIFT_TYPE_LABELS[shift.shift_type ?? 'regular'] ?? shift.shift_type}
                </span>
                <span
                  style={{
                    background: `${statusColor}22`,
                    color: statusColor,
                    border: `1px solid ${statusColor}66`,
                    borderRadius: '20px',
                    padding: '3px 10px',
                    fontSize: '11px',
                    fontWeight: 700,
                  }}
                >
                  {shift.status}
                </span>
              </div>

              {/* Time range */}
              <div
                style={{
                  fontSize: '14px',
                  color: 'var(--text-secondary)',
                  fontFamily: 'var(--font-mono)',
                }}
              >
                {formatDateTime(shift.start_time)}
                {shift.end_time ? ` — ${formatTime(shift.end_time)}` : ' — в процессе'}
              </div>
            </div>

            {/* Metrics grid */}
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: '1fr 1fr',
                gap: '12px',
              }}
            >
              {[
                {
                  label: 'Нагрузка',
                  value: `${shift.load_percentage}%`,
                  color: shift.load_percentage > 80 ? 'var(--red,#ef4444)' : 'var(--accent)',
                },
                {
                  label: 'Приоритет',
                  value: `${shift.priority_level} / 5`,
                  color: 'var(--amber,#f59e0b)',
                },
                {
                  label: 'Завершено заявок',
                  value: `${shift.completed_requests}`,
                  color: 'var(--blue,#3b82f6)',
                },
                {
                  label: 'Заявок (тек./макс.)',
                  value: `${shift.current_request_count} / ${shift.max_requests}`,
                  color: 'var(--text-secondary)',
                },
                {
                  label: 'Эффективность',
                  value:
                    shift.efficiency_score !== null
                      ? `${Math.round(shift.efficiency_score * 100) / 100}`
                      : '—',
                  color: 'var(--emerald,#10b981)',
                },
                {
                  label: 'Рейтинг качества',
                  value:
                    shift.quality_rating !== null
                      ? `${shift.quality_rating}`
                      : '—',
                  color: 'var(--violet,#8b5cf6)',
                },
              ].map(metric => (
                <div
                  key={metric.label}
                  style={{
                    background: 'var(--bg-surface)',
                    border: '1px solid var(--border)',
                    borderRadius: 'var(--radius-sm)',
                    padding: '12px',
                  }}
                >
                  <div
                    style={{
                      fontFamily: 'var(--font-mono)',
                      fontSize: '18px',
                      fontWeight: 700,
                      color: metric.color,
                      marginBottom: '4px',
                    }}
                  >
                    {metric.value}
                  </div>
                  <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                    {metric.label}
                  </div>
                </div>
              ))}
            </div>

            {/* Notes */}
            {shift.notes && (
              <div
                style={{
                  background: 'var(--bg-surface)',
                  border: '1px solid var(--border)',
                  borderRadius: 'var(--radius-sm)',
                  padding: '12px',
                }}
              >
                <div
                  style={{
                    fontSize: '11px',
                    fontWeight: 700,
                    color: 'var(--text-muted)',
                    textTransform: 'uppercase',
                    letterSpacing: '0.04em',
                    marginBottom: '6px',
                  }}
                >
                  Заметки
                </div>
                <p style={{ margin: 0, fontSize: '13px', color: 'var(--text-secondary)' }}>
                  {shift.notes}
                </p>
              </div>
            )}

            {/* Error from end shift */}
            {endShift.isError && (
              <div
                style={{
                  fontSize: '13px',
                  color: 'var(--red,#ef4444)',
                  background: 'rgba(239,68,68,0.1)',
                  border: '1px solid rgba(239,68,68,0.3)',
                  borderRadius: 'var(--radius-sm)',
                  padding: '10px 12px',
                }}
              >
                Ошибка при завершении смены
              </div>
            )}

            {/* Actions */}
            <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end' }}>
              {shift.status === 'active' && (
                <button
                  onClick={() => setConfirmEndOpen(true)}
                  disabled={endShift.isPending}
                  style={{
                    padding: '10px 20px',
                    borderRadius: 'var(--radius-sm)',
                    background: 'rgba(239,68,68,0.15)',
                    border: '1px solid rgba(239,68,68,0.4)',
                    color: '#ef4444',
                    fontSize: '14px',
                    fontWeight: 700,
                    cursor: endShift.isPending ? 'not-allowed' : 'pointer',
                    fontFamily: 'var(--font-body)',
                    opacity: endShift.isPending ? 0.7 : 1,
                  }}
                >
                  {endShift.isPending ? 'Завершение...' : 'Завершить смену'}
                </button>
              )}
              <button
                onClick={onClose}
                style={{
                  padding: '10px 20px',
                  borderRadius: 'var(--radius-sm)',
                  background: 'var(--bg-surface)',
                  border: '1px solid var(--border)',
                  color: 'var(--text-secondary)',
                  fontSize: '14px',
                  fontWeight: 600,
                  cursor: 'pointer',
                  fontFamily: 'var(--font-body)',
                }}
              >
                Закрыть
              </button>
            </div>
          </>
        ) : (
          <div style={{ fontSize: '14px', color: 'var(--text-muted)' }}>
            Смена не найдена
          </div>
        )}
      </div>

      <ConfirmDialog
        open={confirmEndOpen}
        onOpenChange={setConfirmEndOpen}
        title="Завершить смену"
        description="Завершить смену? Это действие нельзя отменить."
        confirmLabel="Завершить"
        onConfirm={handleEndShift}
        variant="warning"
        loading={endShift.isPending}
      />
    </div>
  )
}
