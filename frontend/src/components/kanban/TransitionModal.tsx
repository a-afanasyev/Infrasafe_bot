import { useState, useEffect } from 'react'
import { useEmployees } from '../../hooks/useEmployees'
import { cn } from '@/lib/utils'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'

export interface TransitionData {
  status: string
  executor_id?: number
  notes?: string
  requested_materials?: string
  completion_report?: string
}

interface Props {
  requestNumber: string
  targetStatus: string
  onConfirm: (data: TransitionData) => void
  onCancel: () => void
}

export default function TransitionModal({ requestNumber: _requestNumber, targetStatus, onConfirm, onCancel }: Props) {
  const [executorId, setExecutorId] = useState<number | 'duty' | ''>('')
  const [text, setText] = useState('')
  const { data: employees = [] } = useEmployees({ verification_status: 'verified' })

  useEffect(() => {
    setExecutorId('')
    setText('')
  }, [targetStatus])

  const isValid = (): boolean => {
    if (targetStatus === 'В работе') return executorId !== ''
    if (targetStatus === 'Закуп') return text.trim().length > 0
    if (targetStatus === 'Уточнение') return text.trim().length > 0
    if (targetStatus === 'Выполнена') return text.trim().length > 0
    return true
  }

  const handleConfirm = () => {
    const data: TransitionData = { status: targetStatus }
    if (targetStatus === 'В работе' && executorId !== 'duty' && executorId !== '') {
      data.executor_id = executorId as number
    }
    if (targetStatus === 'Закуп') data.requested_materials = text.trim()
    if (targetStatus === 'Уточнение') data.notes = text.trim()
    if (targetStatus === 'Выполнена') data.completion_report = text.trim()
    onConfirm(data)
  }

  const TITLES: Record<string, string> = {
    'В работе': 'Назначить исполнителя',
    'Закуп': 'Что необходимо купить?',
    'Уточнение': 'Вопрос к жителю',
    'Выполнена': 'Отчёт о выполнении',
    'Исполнено': 'Подтвердить выполнение',
  }

  return (
    <Dialog open onOpenChange={(open) => { if (!open) onCancel() }}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>
            {TITLES[targetStatus] ?? `Перевод в "${targetStatus}"`}
          </DialogTitle>
        </DialogHeader>

        {targetStatus === 'В работе' && (
          <div className="space-y-2">
            <Label className="text-text-secondary">Выберите исполнителя:</Label>
            <button
              onClick={() => setExecutorId('duty')}
              className={cn(
                'w-full text-left border rounded-default p-3 text-sm transition-colors',
                executorId === 'duty'
                  ? 'border-accent bg-accent-dim text-accent'
                  : 'border-border-default hover:bg-bg-surface text-text-primary'
              )}
            >
              <span className="font-medium">Дежурный</span>
              <span className="text-text-muted text-xs ml-2">— назначить дежурному</span>
            </button>
            <div className="text-xs text-text-muted text-center py-1">или конкретный специалист:</div>
            <div className="max-h-48 overflow-y-auto space-y-1">
              {employees.map(emp => {
                const name = [emp.first_name, emp.last_name].filter(Boolean).join(' ') || `#${emp.id}`
                return (
                  <button
                    key={emp.id}
                    onClick={() => setExecutorId(emp.id)}
                    className={cn(
                      'w-full text-left border rounded-default p-3 text-sm transition-colors',
                      executorId === emp.id
                        ? 'border-accent bg-accent-dim text-accent'
                        : 'border-border-default hover:bg-bg-surface text-text-primary'
                    )}
                  >
                    <span className="font-medium">{name}</span>
                    {emp.active_shift_id !== null && (
                      <span className="ml-2 text-xs text-emerald">● На смене</span>
                    )}
                  </button>
                )
              })}
            </div>
          </div>
        )}

        {targetStatus === 'Закуп' && (
          <div className="space-y-1.5">
            <Label className="text-text-secondary">Опишите что нужно купить:</Label>
            <Textarea
              className="min-h-[100px]"
              placeholder="Например: труба ПВХ 50мм, 2 шт; кран шаровый ½"
              value={text}
              onChange={e => setText(e.target.value)}
              autoFocus
            />
          </div>
        )}

        {targetStatus === 'Уточнение' && (
          <div className="space-y-1.5">
            <Label className="text-text-secondary">Введите вопрос для жителя:</Label>
            <Textarea
              className="min-h-[100px]"
              placeholder="Например: Укажите точный адрес и этаж"
              value={text}
              onChange={e => setText(e.target.value)}
              autoFocus
            />
          </div>
        )}

        {targetStatus === 'Выполнена' && (
          <div className="space-y-1.5">
            <Label className="text-text-secondary">Опишите что было сделано:</Label>
            <Textarea
              className="min-h-[120px]"
              placeholder="Например: Заменён смеситель на кухне, протечка устранена"
              value={text}
              onChange={e => setText(e.target.value)}
              autoFocus
            />
          </div>
        )}

        {targetStatus === 'Исполнено' && (
          <p className="text-sm text-text-secondary">
            Подтвердить перевод заявки в статус "Исполнено"? Житель получит уведомление для приёмки.
          </p>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={onCancel}>
            Отмена
          </Button>
          <Button
            onClick={handleConfirm}
            disabled={!isValid()}
          >
            Подтвердить
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
