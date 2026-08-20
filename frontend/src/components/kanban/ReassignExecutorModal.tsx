import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { apiClient } from '../../api/client'
import { safeErrorMessage } from '@/utils/errorMessage'
import ExecutorPicker, { type ExecutorChoice } from './ExecutorPicker'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'

interface Props {
  requestNumber: string
  /** Текущий исполнитель — исключается из списка и определяет заголовок. */
  currentExecutorId: number | null
  currentExecutorName: string | null
  onClose: () => void
}

/**
 * Смена исполнителя заявки прямо из её карточки.
 *
 * До этого сменить исполнителя на вебе можно было только «от сотрудника»
 * (Сотрудники → «Назначить заявку»): менеджер, глядя на заявку в работе,
 * должен был уйти в другой раздел и искать там нужного человека. Бот такую
 * кнопку получил, дашборд — нет; здесь паритет.
 *
 * Пишет тем же каноном, что и бот: PATCH `{executor_id}` без `status`
 * транслируется роутером в `MANAGER_ASSIGN` (Новая/В работе → В работе) с
 * отменой прошлого назначения, audit/outbox и уведомлениями. Вариант
 * «дежурному» идёт как `{status: "В работе", assign_to_duty: true}` — спец
 * резолвит сервер по категории.
 */
export default function ReassignExecutorModal({
  requestNumber,
  currentExecutorId,
  currentExecutorName,
  onClose,
}: Props) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [choice, setChoice] = useState<ExecutorChoice>('')
  const [error, setError] = useState<string | null>(null)

  const mutation = useMutation({
    mutationFn: (value: ExecutorChoice) => {
      const body =
        value === 'duty'
          ? { status: 'В работе', assign_to_duty: true }
          : { executor_id: value as number }
      return apiClient.patch(`/api/v2/requests/${requestNumber}`, body).then(r => r.data)
    },
    onSuccess: () => {
      toast.success(t('toast.requestUpdated'))
      queryClient.invalidateQueries({ queryKey: ['kanban'] })
      queryClient.invalidateQueries({ queryKey: ['request', requestNumber] })
      queryClient.invalidateQueries({ queryKey: ['employees'] })
      onClose()
    },
    onError: (err: unknown) => {
      // Текст сервера важнее общего «не удалось сохранить»: 409 «нет дежурного
      // на смене» говорит менеджеру, что делать дальше, а подмена скрыла бы
      // причину отказа. Канонный хелпер проекта (axios.isAxiosError + лимит
      // длины), а не свой instanceof: тот врёт при разных инстансах axios.
      const message = safeErrorMessage(err, t('errors.saveFailed'))
      toast.error(message)
      setError(message)
    },
  })

  const isReassign = currentExecutorId !== null

  return (
    <Dialog open onOpenChange={open => { if (!open) onClose() }}>
      <DialogContent className="max-w-[460px]">
        <DialogHeader>
          <DialogTitle>
            {isReassign ? t('kanban.reassignExecutor') : t('kanban.assignExecutor')}
          </DialogTitle>
          {isReassign && currentExecutorName && (
            <p className="text-[13px] text-text-muted mt-0.5">
              {t('kanban.currentExecutor', { name: currentExecutorName })}
            </p>
          )}
        </DialogHeader>

        <ExecutorPicker
          value={choice}
          onChange={value => { setChoice(value); setError(null) }}
          excludeId={currentExecutorId}
          emptyText={t('kanban.noOtherExecutors')}
        />

        {error && <p className="text-xs text-red m-0">{error}</p>}

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            {t('common.cancel')}
          </Button>
          <Button
            onClick={() => mutation.mutate(choice)}
            disabled={choice === '' || mutation.isPending}
          >
            {isReassign ? t('kanban.reassignConfirm') : t('kanban.assignConfirm')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
