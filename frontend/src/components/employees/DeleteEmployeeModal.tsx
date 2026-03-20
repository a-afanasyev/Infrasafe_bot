import { useState, useEffect } from 'react'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogFooter,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import {
  useActiveRequestsCount,
  useDeleteEmployee,
  useEmployees,
} from '../../hooks/useEmployees'
import type { EmployeeBrief } from '../../hooks/useEmployees'
import { AVATAR_GRADIENTS, getInitials } from '../../utils/employeeUtils'
import { cn } from '@/lib/utils'

interface Props {
  employee: EmployeeBrief
  onClose: () => void
}

type Step = 'confirm' | 'reassign'

export default function DeleteEmployeeModal({ employee, onClose }: Props) {
  const [step, setStep] = useState<Step>('confirm')
  const [reason, setReason] = useState('')
  const [selectedTarget, setSelectedTarget] = useState<number | null>(null)

  const name =
    [employee.first_name, employee.last_name].filter(Boolean).join(' ') ||
    'Без имени'

  const { data: activeRequestsData } = useActiveRequestsCount(employee.id)
  const activeCount = activeRequestsData?.count ?? 0

  const { data: employees = [] } = useEmployees()
  const availableTargets = employees.filter(
    (e) => e.id !== employee.id && e.status !== 'blocked',
  )

  const deleteEmployee = useDeleteEmployee()

  // Close on success
  useEffect(() => {
    if (deleteEmployee.isSuccess) onClose()
  }, [deleteEmployee.isSuccess, onClose])

  const handleConfirmStep = () => {
    if (activeCount > 0) {
      setStep('reassign')
    } else {
      deleteEmployee.mutate({ id: employee.id, reason })
    }
  }

  const handleReassignAndDelete = () => {
    if (selectedTarget === null) return
    deleteEmployee.mutate({
      id: employee.id,
      reason,
      reassign_to: selectedTarget,
    })
  }

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-md">
        {step === 'confirm' && (
          <>
            <DialogHeader>
              <DialogTitle>Удаление сотрудника</DialogTitle>
              <DialogDescription>
                Вы уверены, что хотите удалить {name}?
              </DialogDescription>
            </DialogHeader>

            <div className="flex flex-col gap-2">
              <Label htmlFor="delete-reason">Причина удаления</Label>
              <Textarea
                id="delete-reason"
                placeholder="Укажите причину..."
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                rows={3}
              />
            </div>

            <DialogFooter>
              <Button variant="outline" onClick={onClose}>
                Отмена
              </Button>
              <Button
                variant="destructive"
                disabled={!reason.trim() || deleteEmployee.isPending}
                onClick={handleConfirmStep}
              >
                {deleteEmployee.isPending ? 'Удаление...' : 'Удалить'}
              </Button>
            </DialogFooter>
          </>
        )}

        {step === 'reassign' && (
          <>
            <DialogHeader>
              <DialogTitle>Передача заявок</DialogTitle>
              <DialogDescription>
                У сотрудника {activeCount} активных заявок. Выберите кому их
                передать.
              </DialogDescription>
            </DialogHeader>

            <div className="flex flex-col gap-1.5 max-h-[300px] overflow-y-auto">
              {availableTargets.map((e) => {
                const gradient =
                  AVATAR_GRADIENTS[e.id % AVATAR_GRADIENTS.length]
                const initials = getInitials(e.first_name, e.last_name)
                const targetName =
                  [e.first_name, e.last_name].filter(Boolean).join(' ') ||
                  'Без имени'
                const isSelected = selectedTarget === e.id

                return (
                  <button
                    key={e.id}
                    type="button"
                    onClick={() => setSelectedTarget(e.id)}
                    className={cn(
                      'flex items-center gap-3 p-2.5 rounded-lg border cursor-pointer transition-colors text-left w-full',
                      isSelected
                        ? 'border-accent bg-accent/10'
                        : 'border-border-default hover:bg-bg-surface',
                    )}
                  >
                    <div
                      className="w-8 h-8 rounded-full flex items-center justify-center text-white text-[11px] font-bold font-[var(--font-display)] shrink-0"
                      style={{ background: gradient }}
                    >
                      {initials}
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="font-[var(--font-display)] font-semibold text-xs text-text-primary truncate">
                        {targetName}
                      </div>
                      {e.phone && (
                        <div className="text-[10px] text-text-muted font-[var(--font-mono)]">
                          {e.phone}
                        </div>
                      )}
                    </div>
                    {e.active_shift_id !== null && (
                      <span className="text-[10px] font-semibold text-emerald bg-emerald/15 px-1.5 py-0.5 rounded-[10px] shrink-0">
                        На смене
                      </span>
                    )}
                  </button>
                )
              })}
              {availableTargets.length === 0 && (
                <div className="text-sm text-text-muted text-center py-4">
                  Нет доступных сотрудников для передачи
                </div>
              )}
            </div>

            <DialogFooter>
              <Button variant="outline" onClick={() => setStep('confirm')}>
                Назад
              </Button>
              <Button
                variant="destructive"
                disabled={
                  selectedTarget === null || deleteEmployee.isPending
                }
                onClick={handleReassignAndDelete}
              >
                {deleteEmployee.isPending
                  ? 'Удаление...'
                  : 'Передать и удалить'}
              </Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}
