import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import ExecutorPicker, { type ExecutorChoice } from './ExecutorPicker'
import { tStatus } from '../../i18n/apiMaps'
import { needsReturnReasonModal } from './transitions'
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
  /** FEAT-группы: «Назначить дежурному» — назначить на группу-специализацию
   *  категории (спец резолвит сервер). Идёт со status="В работе". */
  assign_to_duty?: boolean
  notes?: string
  requested_materials?: string
  completion_report?: string
  /** Причина возврата. Имя поля транспортное — сервер переводит его в payload
   *  `reason` для MANAGER_RETURN_TO_WORK (api/requests/router.py). */
  return_reason?: string
}

interface Props {
  requestNumber: string
  targetStatus: string
  /** Колонка, из которой тащат. Нужна, чтобы отличить возврат в работу
   *  (спрашиваем причину) от взятия заявки (спрашиваем исполнителя). */
  sourceStatus?: string
  onConfirm: (data: TransitionData) => void
  onCancel: () => void
}

export default function TransitionModal({ targetStatus, sourceStatus, onConfirm, onCancel }: Props) {
  const { t } = useTranslation()
  const [executorId, setExecutorId] = useState<ExecutorChoice>('')
  const [text, setText] = useState('')
  const isReturnToWork = needsReturnReasonModal(sourceStatus, targetStatus)

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- намеренный сброс полей формы при смене целевого статуса
    setExecutorId('')
    setText('')
  }, [targetStatus, sourceStatus])

  const isValid = (): boolean => {
    // Причина обязательна: ядро отклонит пустую, и менеджер получил бы 422
    // вместо понятной подсказки.
    if (isReturnToWork) return text.trim().length > 0
    if (targetStatus === 'В работе') return executorId !== ''
    if (targetStatus === 'Закуп') return text.trim().length > 0
    if (targetStatus === 'Уточнение') return text.trim().length > 0
    if (targetStatus === 'Выполнена') return text.trim().length > 0
    return true
  }

  const handleConfirm = () => {
    const data: TransitionData = { status: targetStatus }
    if (isReturnToWork) {
      data.return_reason = text.trim()
      onConfirm(data)
      return
    }
    if (targetStatus === 'В работе' && executorId !== 'duty' && executorId !== '') {
      data.executor_id = executorId as number
    }
    // FEAT-группы: «Дежурный» → назначение на группу-специализацию (сервер
    // резолвит спец по категории), а не status-only переход без исполнителя.
    if (targetStatus === 'В работе' && executorId === 'duty') {
      data.assign_to_duty = true
    }
    if (targetStatus === 'Закуп') data.requested_materials = text.trim()
    if (targetStatus === 'Уточнение') data.notes = text.trim()
    if (targetStatus === 'Выполнена') data.completion_report = text.trim()
    onConfirm(data)
  }

  const TITLES: Record<string, string> = {
    'В работе': t('kanban.assignExecutor'),
    'Закуп': t('kanban.whatToBuy'),
    'Уточнение': t('kanban.questionToResident'),
    'Выполнена': t('kanban.completionReport'),
    'Исполнено': t('kanban.confirmCompletion'),
  }

  return (
    <Dialog open onOpenChange={(open) => { if (!open) onCancel() }}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>
            {isReturnToWork
              ? t('kanban.returnToWorkTitle')
              : TITLES[targetStatus] ?? t('kanban.transitionTo', { status: tStatus(targetStatus, t) })}
          </DialogTitle>
        </DialogHeader>

        {isReturnToWork && (
          <div className="space-y-1.5">
            <Label className="text-text-secondary">{t('kanban.returnReasonLabel')}</Label>
            <Textarea
              className="min-h-[100px]"
              placeholder={t('kanban.returnReasonPlaceholder')}
              value={text}
              onChange={e => setText(e.target.value)}
              autoFocus
            />
          </div>
        )}

        {!isReturnToWork && targetStatus === 'В работе' && (
          <ExecutorPicker value={executorId} onChange={setExecutorId} />
        )}

        {targetStatus === 'Закуп' && (
          <div className="space-y-1.5">
            <Label className="text-text-secondary">{t('kanban.describePurchase')}</Label>
            <Textarea
              className="min-h-[100px]"
              placeholder={t('kanban.purchasePlaceholder')}
              value={text}
              onChange={e => setText(e.target.value)}
              autoFocus
            />
          </div>
        )}

        {targetStatus === 'Уточнение' && (
          <div className="space-y-1.5">
            <Label className="text-text-secondary">{t('kanban.enterQuestion')}</Label>
            <Textarea
              className="min-h-[100px]"
              placeholder={t('kanban.questionPlaceholder')}
              value={text}
              onChange={e => setText(e.target.value)}
              autoFocus
            />
          </div>
        )}

        {targetStatus === 'Выполнена' && (
          <div className="space-y-1.5">
            <Label className="text-text-secondary">{t('kanban.describeWork')}</Label>
            <Textarea
              className="min-h-[120px]"
              placeholder={t('kanban.workPlaceholder')}
              value={text}
              onChange={e => setText(e.target.value)}
              autoFocus
            />
          </div>
        )}

        {targetStatus === 'Исполнено' && (
          <p className="text-sm text-text-secondary">
            {t('kanban.confirmExecutedMessage')}
          </p>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={onCancel}>
            {t('common.cancel')}
          </Button>
          <Button
            onClick={handleConfirm}
            disabled={!isValid()}
          >
            {t('common.confirm')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
