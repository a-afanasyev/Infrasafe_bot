import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { useCreateShift } from '../../hooks/useShifts'
import { useEmployees } from '../../hooks/useEmployees'
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

interface Props {
  isOpen: boolean
  onClose: () => void
}

import { SHIFT_TYPES, PRIORITIES } from '../../constants'

export default function CreateShiftModal({ isOpen, onClose }: Props) {
  const { t } = useTranslation()
  const createShift = useCreateShift()

  const [executorId, setExecutorId] = useState('')
  const [startTime, setStartTime] = useState('')
  const [endTime, setEndTime] = useState('')
  const [shiftType, setShiftType] = useState('regular')
  const [maxRequests, setMaxRequests] = useState('10')
  const [priority, setPriority] = useState('3')
  const [notes, setNotes] = useState('')
  const [specFocus, setSpecFocus] = useState<string[]>([])
  const [error, setError] = useState<string | null>(null)

  const { data: employees = [] } = useEmployees({}, undefined)

  useEffect(() => {
    if (isOpen) {
      setExecutorId('')
      setStartTime('')
      setEndTime('')
      setShiftType('regular')
      setMaxRequests('10')
      setPriority('3')
      setNotes('')
      setSpecFocus([])
      setError(null)
    }
  }, [isOpen])

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
    if (!endTime) {
      setError(t('errors.specifyEndTime'))
      return
    }
    if (new Date(endTime) <= new Date(startTime)) {
      setError(t('errors.endAfterStart'))
      return
    }

    try {
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
      onClose()
      // Reset form
      setExecutorId('')
      setStartTime('')
      setEndTime('')
      setShiftType('regular')
      setMaxRequests('10')
      setPriority('3')
      setNotes('')
      setSpecFocus([])
    } catch (err: unknown) {
      const msg =
        err instanceof Error ? err.message : t('errors.createShift')
      setError(msg)
    }
  }

  return (
    <Dialog open={isOpen} onOpenChange={(open) => { if (!open) onClose() }}>
      <DialogContent className="max-w-[520px] max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{t('shifts.createShift').replace('+ ', '')}</DialogTitle>
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
              {employees.map(emp => (
                <option key={emp.id} value={String(emp.id)}>
                  {[emp.first_name, emp.last_name].filter(Boolean).join(' ') || `ID ${emp.id}`}
                  {emp.phone ? ` \u00B7 ${emp.phone}` : ''}
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
            <Button
              type="button"
              variant="outline"
              onClick={onClose}
            >
              {t('common.cancel')}
            </Button>
            <Button
              type="submit"
              disabled={createShift.isPending}
            >
              {createShift.isPending ? t('common.creating') : t('common.create')}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
