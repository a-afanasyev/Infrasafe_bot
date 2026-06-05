import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { useCreateShift, useUpdateShift, useDeleteShift } from '../../hooks/useShifts'
import { useEmployees } from '../../hooks/useEmployees'
import { isoToDatetimeLocal } from '../../utils/timezone'
import type { ShiftDetail } from '../../types/api'
import ConfirmDialog from '../shared/ConfirmDialog'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { cn } from '@/lib/utils'
import { SHIFT_TYPES, PRIORITIES } from '../../constants'

interface Props {
  isOpen: boolean
  onClose: () => void
  /** When provided, the modal works in edit mode (pre-filled + PATCH). */
  shift?: ShiftDetail | null
}

export default function CreateShiftModal({ isOpen, onClose, shift = null }: Props) {
  const { t } = useTranslation()
  const createShift = useCreateShift()
  const updateShift = useUpdateShift()
  const deleteShift = useDeleteShift()
  const isEdit = shift !== null
  const isPending = isEdit ? updateShift.isPending : createShift.isPending

  const [executorId, setExecutorId] = useState('')
  const [startTime, setStartTime] = useState('')
  const [endTime, setEndTime] = useState('')
  const [shiftType, setShiftType] = useState('regular')
  const [maxRequests, setMaxRequests] = useState('10')
  const [priority, setPriority] = useState('3')
  const [notes, setNotes] = useState('')
  const [specFocus, setSpecFocus] = useState<string[]>([])
  const [error, setError] = useState<string | null>(null)
  const [confirmDeleteOpen, setConfirmDeleteOpen] = useState(false)

  const { data: employees = [] } = useEmployees({}, undefined)

  // When editing a shift whose executor isn't in the (verified) employees list
  // — e.g. assigned before verification — surface them as a selectable option so
  // the dropdown shows the real executor instead of the empty placeholder.
  const showCurrentExecutor =
    isEdit && shift?.user_id != null && !employees.some(e => e.id === shift.user_id)

  useEffect(() => {
    if (!isOpen) return
    // eslint-disable-next-line react-hooks/set-state-in-effect -- intentional form (re)init on open; React batches these setState calls into one commit
    setError(null)
    if (shift) {
      setExecutorId(shift.user_id != null ? String(shift.user_id) : '')
      setStartTime(shift.start_time ? isoToDatetimeLocal(shift.start_time) : '')
      setEndTime(shift.end_time ? isoToDatetimeLocal(shift.end_time) : '')
      setShiftType(shift.shift_type ?? 'regular')
      setMaxRequests(String(shift.max_requests))
      setPriority(String(shift.priority_level))
      setNotes(shift.notes ?? '')
      setSpecFocus(shift.specialization_focus ?? [])
    } else {
      setExecutorId('')
      setStartTime('')
      setEndTime('')
      setShiftType('regular')
      setMaxRequests('10')
      setPriority('3')
      setNotes('')
      setSpecFocus([])
    }
  }, [isOpen, shift])

  const toggleSpec = (spec: string) => {
    setSpecFocus(prev => prev.includes(spec) ? prev.filter(s => s !== spec) : [...prev, spec])
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    if (!executorId) { setError(t('errors.selectExecutor')); return }
    if (!startTime) {
      setError(t('errors.specifyStartTime'))
      return
    }
    // End time is required when creating, optional when editing (an active
    // shift may still be open-ended).
    if (!isEdit && !endTime) {
      setError(t('errors.specifyEndTime'))
      return
    }
    if (endTime && new Date(endTime) <= new Date(startTime)) {
      setError(t('errors.endAfterStart'))
      return
    }

    try {
      if (isEdit && shift) {
        await updateShift.mutateAsync({
          id: shift.id,
          user_id: Number(executorId),
          start_time: new Date(startTime).toISOString(),
          end_time: endTime ? new Date(endTime).toISOString() : undefined,
          shift_type: shiftType,
          max_requests: Number(maxRequests),
          priority_level: Number(priority),
          notes: notes || undefined,
          specialization_focus: specFocus,
        })
      } else {
        await createShift.mutateAsync({
          user_id: Number(executorId),
          start_time: new Date(startTime).toISOString(),
          end_time: endTime ? new Date(endTime).toISOString() : undefined,
          shift_type: shiftType,
          max_requests: Number(maxRequests),
          priority_level: Number(priority),
          notes: notes || undefined,
          specialization_focus: specFocus,
        })
      }
      onClose()
    } catch (err: unknown) {
      const msg =
        err instanceof Error ? err.message : t(isEdit ? 'errors.updateShift' : 'errors.createShift')
      setError(msg)
    }
  }

  const handleDelete = async () => {
    if (!shift) return
    try {
      await deleteShift.mutateAsync(shift.id)
      onClose()
    } catch {
      // error surfaced via toast
    }
  }

  const canDelete = isEdit && shift?.status === 'planned'

  return (
    <>
      <Dialog open={isOpen} onOpenChange={(open) => { if (!open) onClose() }}>
        <DialogContent className="max-w-[520px] max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>
              {isEdit ? t('shifts.editShiftTitle') : t('shifts.createShift').replace('+ ', '')}
            </DialogTitle>
          </DialogHeader>

          <form
            onSubmit={handleSubmit}
            className="flex flex-col gap-4"
          >
            {/* Executor */}
            <div className="space-y-1.5">
              <Label className="text-xs uppercase tracking-wider text-text-secondary">{t('shifts.executorLabel')}</Label>
              <Select
                value={executorId}
                onChange={e => setExecutorId(e.target.value)}
              >
                <option value="">{t('shifts.selectExecutor')}</option>
                {showCurrentExecutor && shift && (
                  <option value={String(shift.user_id)}>
                    {shift.executor_name ?? `ID ${shift.user_id}`}
                  </option>
                )}
                {employees.map(emp => (
                  <option key={emp.id} value={String(emp.id)}>
                    {[emp.first_name, emp.last_name].filter(Boolean).join(' ') || `ID ${emp.id}`}
                    {emp.phone ? ` · ${emp.phone}` : ''}
                  </option>
                ))}
              </Select>
            </div>

            {/* Start time */}
            <div className="space-y-1.5">
              <Label className="text-xs uppercase tracking-wider text-text-secondary">{t('shifts.shiftStart')}</Label>
              <Input
                type="datetime-local"
                value={startTime}
                onChange={e => setStartTime(e.target.value)}
              />
            </div>

            {/* End time */}
            <div className="space-y-1.5">
              <Label className="text-xs uppercase tracking-wider text-text-secondary">{t('shifts.shiftEnd')}</Label>
              <Input
                type="datetime-local"
                value={endTime}
                onChange={e => setEndTime(e.target.value)}
              />
            </div>

            {/* Shift type */}
            <div className="space-y-1.5">
              <Label className="text-xs uppercase tracking-wider text-text-secondary">{t('shifts.shiftType')}</Label>
              <Select
                value={shiftType}
                onChange={e => setShiftType(e.target.value)}
              >
                {SHIFT_TYPES.map(st => (
                  <option key={st.value} value={st.value}>{t(`shiftType.${st.value}`)}</option>
                ))}
              </Select>
            </div>

            {/* Specializations */}
            <div className="space-y-1.5">
              <Label className="text-xs uppercase tracking-wider text-text-secondary">{t('shifts.specializationsLabel')}</Label>
              <div className="flex flex-wrap gap-1.5">
                {(['electrician', 'plumber', 'heating', 'cleaning', 'security', 'elevator', 'landscaping', 'ventilation'] as const).map(key => (
                  <button
                    key={key}
                    type="button"
                    onClick={() => toggleSpec(key)}
                    className={cn(
                      'px-2.5 py-1 rounded-full text-xs cursor-pointer border transition-colors',
                      specFocus.includes(key)
                        ? 'bg-accent-dim text-accent border-border-active'
                        : 'bg-bg-surface text-text-secondary border-border-default'
                    )}
                  >{t(`specialization.${key}`)}</button>
                ))}
              </div>
            </div>

            {/* Max requests */}
            <div className="space-y-1.5">
              <Label className="text-xs uppercase tracking-wider text-text-secondary">{t('shifts.maxRequests')}</Label>
              <Input
                type="number"
                min={1}
                value={maxRequests}
                onChange={e => setMaxRequests(e.target.value)}
              />
            </div>

            {/* Priority */}
            <div className="space-y-1.5">
              <Label className="text-xs uppercase tracking-wider text-text-secondary">{t('shifts.priorityLabel')}</Label>
              <Select
                value={priority}
                onChange={e => setPriority(e.target.value)}
              >
                {PRIORITIES.map(p => (
                  <option key={p.value} value={p.value}>{t(`priority.${p.value}`)}</option>
                ))}
              </Select>
            </div>

            {/* Notes */}
            <div className="space-y-1.5">
              <Label className="text-xs uppercase tracking-wider text-text-secondary">{t('shifts.notesLabel')}</Label>
              <Textarea
                value={notes}
                onChange={e => setNotes(e.target.value)}
                rows={3}
                placeholder={t('shifts.notesPlaceholder')}
                className="resize-y"
              />
            </div>

            {/* Error */}
            {error && (
              <div className="text-[13px] text-red bg-red/10 border border-red/30 rounded-sm px-3 py-2.5">
                {error}
              </div>
            )}

            {/* Actions */}
            <DialogFooter>
              {canDelete && (
                <Button
                  type="button"
                  variant="destructive"
                  className="mr-auto"
                  onClick={() => setConfirmDeleteOpen(true)}
                  disabled={deleteShift.isPending}
                >
                  {deleteShift.isPending ? t('shifts.deletingShift') : t('shifts.deleteShift')}
                </Button>
              )}
              <Button
                type="button"
                variant="outline"
                onClick={onClose}
              >
                {t('common.cancel')}
              </Button>
              <Button
                type="submit"
                disabled={isPending}
              >
                {isEdit
                  ? (isPending ? t('common.saving') : t('common.save'))
                  : (isPending ? t('common.creating') : t('common.create'))}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={confirmDeleteOpen}
        onOpenChange={setConfirmDeleteOpen}
        title={t('shifts.confirmDeleteShift')}
        description={t('shifts.confirmDeleteShiftDesc')}
        confirmLabel={t('shifts.deleteShift')}
        onConfirm={handleDelete}
        variant="warning"
        loading={deleteShift.isPending}
      />
    </>
  )
}
