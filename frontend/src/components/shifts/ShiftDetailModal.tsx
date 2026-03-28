import { useState } from 'react'
import { useTranslation } from 'react-i18next'
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
  const { t } = useTranslation()
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
            <DialogTitle>{t('shifts.shiftDetail', { id: shiftId })}</DialogTitle>
          </DialogHeader>

          {isLoading ? (
            <LoadingSpinner />
          ) : shift ? (
            <div className="flex flex-col gap-5">
              {/* Executor + badges */}
              <div className="flex flex-col gap-3">
                <div className="flex items-center gap-2.5 flex-wrap">
                  <span className="font-[var(--font-display)] text-base font-semibold text-text-primary">
                    {shift.executor_name ?? t('shifts.executorFallback', { id: shift.user_id })}
                  </span>
                  <span
                    className="rounded-full px-2.5 py-0.5 text-[11px] font-bold"
                    style={{
                      background: `${typeColor}22`,
                      color: typeColor,
                      border: `1px solid ${typeColor}66`,
                    }}
                  >
                    {t(`shiftType.${shift.shift_type ?? 'regular'}`)}
                  </span>
                  <span
                    className="rounded-full px-2.5 py-0.5 text-[11px] font-bold"
                    style={{
                      background: `${statusColor}22`,
                      color: statusColor,
                      border: `1px solid ${statusColor}66`,
                    }}
                  >
                    {t(`shiftStatus.${shift.status}`, shift.status)}
                  </span>
                </div>

                {/* Time range */}
                <div className="text-sm text-text-secondary font-[var(--font-mono)]">
                  {formatDateTime(shift.start_time)}
                  {shift.end_time ? ` — ${formatTime(shift.end_time)}` : ` ${t('shifts.inProgress')}`}
                </div>
              </div>

              {/* Metrics grid */}
              <div className="grid grid-cols-2 gap-3">
                {[
                  {
                    label: t('shifts.loadPercent'),
                    value: `${shift.load_percentage}%`,
                    color: shift.load_percentage > 80 ? 'var(--red,#ef4444)' : 'var(--accent)',
                  },
                  {
                    label: t('shifts.priorityOf5'),
                    value: `${shift.priority_level} / 5`,
                    color: 'var(--amber,#f59e0b)',
                  },
                  {
                    label: t('shifts.completedRequestsLabel'),
                    value: `${shift.completed_requests}`,
                    color: 'var(--blue,#3b82f6)',
                  },
                  {
                    label: t('shifts.currentMax'),
                    value: `${shift.current_request_count} / ${shift.max_requests}`,
                    color: 'var(--text-secondary)',
                  },
                  {
                    label: t('shifts.efficiencyLabel'),
                    value:
                      shift.efficiency_score !== null
                        ? `${Math.round(shift.efficiency_score * 100) / 100}`
                        : '—',
                    color: 'var(--emerald,#10b981)',
                  },
                  {
                    label: t('shifts.qualityRating'),
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
                    {t('shifts.notes')}
                  </div>
                  <p className="m-0 text-[13px] text-text-secondary">
                    {shift.notes}
                  </p>
                </div>
              )}

              {/* Error from end shift */}
              {endShift.isError && (
                <div className="text-[13px] text-red bg-red/10 border border-red/30 rounded-sm px-3 py-2.5">
                  {t('errors.endShift')}
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
                    {endShift.isPending ? t('shifts.endingShift') : t('shifts.endShift')}
                  </Button>
                )}
                <Button
                  variant="outline"
                  onClick={onClose}
                >
                  {t('common.close')}
                </Button>
              </DialogFooter>
            </div>
          ) : (
            <div className="text-sm text-text-muted">
              {t('errors.shiftNotFound')}
            </div>
          )}
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={confirmEndOpen}
        onOpenChange={setConfirmEndOpen}
        title={t('shifts.confirmEndShift')}
        description={t('shifts.confirmEndShiftDesc')}
        confirmLabel={t('shifts.confirmEnd')}
        onConfirm={handleEndShift}
        variant="warning"
        loading={endShift.isPending}
      />
    </>
  )
}
