import { useState } from 'react'
import { useShift, useEndShift } from '../../hooks/useShifts'
import { formatTime, formatDateTime } from '../../utils/timezone'
import LoadingSpinner from '../shared/LoadingSpinner'
import ConfirmDialog from '../shared/ConfirmDialog'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'

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

  return (
    <>
      <Dialog open={shiftId !== null} onOpenChange={(open) => { if (!open) onClose() }}>
        <DialogContent className="max-w-[480px] max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Детали смены #{shiftId}</DialogTitle>
          </DialogHeader>

          {isLoading ? (
            <LoadingSpinner />
          ) : shift ? (
            <div className="flex flex-col gap-5">
              {/* Executor + badges */}
              <div className="flex flex-col gap-3">
                <div className="flex items-center gap-2.5 flex-wrap">
                  <span className="font-[var(--font-display)] text-base font-semibold text-text-primary">
                    {shift.executor_name ?? `Исполнитель #${shift.user_id}`}
                  </span>
                  <span
                    className="rounded-full px-2.5 py-0.5 text-[11px] font-bold"
                    style={{
                      background: `${typeColor}22`,
                      color: typeColor,
                      border: `1px solid ${typeColor}66`,
                    }}
                  >
                    {SHIFT_TYPE_LABELS[shift.shift_type ?? 'regular'] ?? shift.shift_type}
                  </span>
                  <span
                    className="rounded-full px-2.5 py-0.5 text-[11px] font-bold"
                    style={{
                      background: `${statusColor}22`,
                      color: statusColor,
                      border: `1px solid ${statusColor}66`,
                    }}
                  >
                    {shift.status}
                  </span>
                </div>

                {/* Time range */}
                <div className="text-sm text-text-secondary font-[var(--font-mono)]">
                  {formatDateTime(shift.start_time)}
                  {shift.end_time ? ` — ${formatTime(shift.end_time)}` : ' — в процессе'}
                </div>
              </div>

              {/* Metrics grid */}
              <div className="grid grid-cols-2 gap-3">
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
                    className="bg-bg-surface border border-border-default rounded-sm p-3"
                  >
                    <div
                      className="font-[var(--font-mono)] text-lg font-bold mb-1"
                      style={{ color: metric.color }}
                    >
                      {metric.value}
                    </div>
                    <div className="text-[11px] text-text-muted">
                      {metric.label}
                    </div>
                  </div>
                ))}
              </div>

              {/* Notes */}
              {shift.notes && (
                <div className="bg-bg-surface border border-border-default rounded-sm p-3">
                  <div className="text-[11px] font-bold text-text-muted uppercase tracking-wider mb-1.5">
                    Заметки
                  </div>
                  <p className="m-0 text-[13px] text-text-secondary">
                    {shift.notes}
                  </p>
                </div>
              )}

              {/* Error from end shift */}
              {endShift.isError && (
                <div className="text-[13px] text-red bg-red/10 border border-red/30 rounded-sm px-3 py-2.5">
                  Ошибка при завершении смены
                </div>
              )}

              {/* Actions */}
              <DialogFooter>
                {shift.status === 'active' && (
                  <Button
                    variant="destructive"
                    onClick={() => setConfirmEndOpen(true)}
                    disabled={endShift.isPending}
                  >
                    {endShift.isPending ? 'Завершение...' : 'Завершить смену'}
                  </Button>
                )}
                <Button
                  variant="outline"
                  onClick={onClose}
                >
                  Закрыть
                </Button>
              </DialogFooter>
            </div>
          ) : (
            <div className="text-sm text-text-muted">
              Смена не найдена
            </div>
          )}
        </DialogContent>
      </Dialog>

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
    </>
  )
}
