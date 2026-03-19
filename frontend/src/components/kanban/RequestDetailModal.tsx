import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { apiClient } from '../../api/client'
import { cn } from '@/lib/utils'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'

const URGENCY: Record<string, { bg: string; text: string }> = {
  'Обычная':    { bg: 'bg-emerald/12',  text: 'text-emerald' },
  'Средняя':    { bg: 'bg-amber/12',    text: 'text-amber' },
  'Срочная':    { bg: 'bg-[#ea580c]/12', text: 'text-[#ea580c]' },
  'Критическая':{ bg: 'bg-red/12',      text: 'text-red' },
}

const STATUS: Record<string, { bg: string; text: string }> = {
  'Новая':     { bg: 'bg-blue/12',     text: 'text-blue' },
  'В работе':  { bg: 'bg-amber/12',    text: 'text-[#d97706]' },
  'Закуп':     { bg: 'bg-violet/12',   text: 'text-violet' },
  'Уточнение': { bg: 'bg-cyan/12',     text: 'text-cyan' },
  'Выполнена': { bg: 'bg-emerald/12',  text: 'text-emerald' },
  'Исполнено': { bg: 'bg-accent/12',   text: 'text-accent' },
  'Принято':   { bg: 'bg-green/12',    text: 'text-green' },
  'Отменена':  { bg: 'bg-red/12',      text: 'text-red' },
}

const SOURCE_ICON: Record<string, string> = {
  bot: '🤖', twa: '📱', web: '🌐', call_center: '📞',
}

interface Props {
  requestNumber: string | null
  onClose: () => void
}

export default function RequestDetailModal({ requestNumber, onClose }: Props) {
  const queryClient = useQueryClient()
  const [comment, setComment] = useState('')
  const [confirmNote, setConfirmNote] = useState('')
  const [showConfirmSection, setShowConfirmSection] = useState(false)
  const [showReturnSection, setShowReturnSection] = useState(false)
  const [returnReason, setReturnReason] = useState('')
  const [showForceAcceptSection, setShowForceAcceptSection] = useState(false)
  const [forceAcceptNote, setForceAcceptNote] = useState('')
  const [remindStatus, setRemindStatus] = useState<'idle' | 'sending' | 'sent' | 'error'>('idle')

  useEffect(() => {
    setComment('')
    setConfirmNote('')
    setShowConfirmSection(false)
    setShowReturnSection(false)
    setReturnReason('')
    setShowForceAcceptSection(false)
    setForceAcceptNote('')
    setRemindStatus('idle')
  }, [requestNumber])

  const { data: request } = useQuery({
    queryKey: ['request', requestNumber],
    queryFn: () => apiClient.get(`/api/v2/requests/${requestNumber}`).then(r => r.data),
    enabled: !!requestNumber,
  })

  const { data: comments } = useQuery({
    queryKey: ['comments', requestNumber],
    queryFn: () => apiClient.get(`/api/v2/requests/${requestNumber}/comments`).then(r => r.data),
    enabled: !!requestNumber,
  })

  const updateRequest = useMutation({
    mutationFn: (data: Record<string, unknown>) =>
      apiClient.patch(`/api/v2/requests/${requestNumber}`, data).then(r => r.data),
    onSuccess: () => {
      toast.success('Заявка обновлена')
      queryClient.invalidateQueries({ queryKey: ['request', requestNumber] })
      queryClient.invalidateQueries({ queryKey: ['kanban'] })
      setShowConfirmSection(false)
      setConfirmNote('')
    },
    onError: (error: Error) => {
      toast.error('Не удалось обновить заявку', { description: error.message })
    },
  })

  const forceAccept = useMutation({
    mutationFn: (note: string) =>
      apiClient.patch(`/api/v2/requests/${requestNumber}`, {
        status: 'Принято',
        manager_confirmation_notes: note,
      }).then(r => r.data),
    onSuccess: () => {
      toast.success('Заявка принята за жителя')
      queryClient.invalidateQueries({ queryKey: ['request', requestNumber] })
      queryClient.invalidateQueries({ queryKey: ['kanban'] })
      setShowForceAcceptSection(false)
      setForceAcceptNote('')
    },
    onError: (error: Error) => {
      toast.error('Не удалось принять заявку', { description: error.message })
    },
  })

  const sendReminder = async () => {
    setRemindStatus('sending')
    try {
      await apiClient.post(`/api/v2/requests/${requestNumber}/remind-applicant`)
      toast.success('Напоминание отправлено жителю')
      setRemindStatus('sent')
      setTimeout(() => setRemindStatus('idle'), 3000)
    } catch {
      toast.error('Не удалось отправить напоминание')
      setRemindStatus('error')
      setTimeout(() => setRemindStatus('idle'), 3000)
    }
  }

  const postComment = useMutation({
    mutationFn: (text: string) =>
      apiClient.post(`/api/v2/requests/${requestNumber}/comments`, { text, is_internal: true }).then(r => r.data),
    onSuccess: () => {
      toast.success('Заметка добавлена')
      queryClient.invalidateQueries({ queryKey: ['comments', requestNumber] })
      setComment('')
    },
    onError: (error: Error) => {
      toast.error('Не удалось добавить заметку', { description: error.message })
    },
  })

  if (!requestNumber) return null

  const statusStyle = STATUS[request?.status ?? ''] ?? { bg: 'bg-bg-surface', text: 'text-text-muted' }
  const urgencyStyle = request?.urgency ? URGENCY[request.urgency] : null

  return (
    <Dialog open onOpenChange={(open) => { if (!open) onClose() }}>
      <DialogContent className="max-w-[520px] max-h-[88vh] p-0 gap-0 flex flex-col">
        {!request ? (
          <div className="p-6 text-center text-text-muted font-[family-name:var(--font-body)]">
            Загрузка...
          </div>
        ) : (
          <>
            {/* Header */}
            <DialogHeader className="px-[18px] pt-4 pb-3.5 border-b border-border-default shrink-0 space-y-1">
              <div className="flex items-center gap-2">
                <span className="font-[family-name:var(--font-mono)] text-[11px] text-text-muted">
                  {request.request_number}
                </span>
                <span className="text-[13px]">{SOURCE_ICON[request.source ?? ''] ?? ''}</span>
              </div>
              <DialogTitle className="font-[family-name:var(--font-display)] text-lg">
                {request.category}
              </DialogTitle>
            </DialogHeader>

            {/* Body */}
            <div className="px-[18px] py-4 overflow-y-auto flex-1 flex flex-col gap-3.5">

              {/* Badges */}
              <div className="flex gap-1.5 flex-wrap">
                <span className={cn(
                  'text-xs font-semibold px-2.5 py-1 rounded-full font-[family-name:var(--font-display)]',
                  statusStyle.bg, statusStyle.text
                )}>{request.status}</span>
                {urgencyStyle && (
                  <span className={cn(
                    'text-xs font-semibold px-2.5 py-1 rounded-full font-[family-name:var(--font-display)]',
                    urgencyStyle.bg, urgencyStyle.text
                  )}>{request.urgency}</span>
                )}
                {request.manager_confirmed && (
                  <span className="text-xs font-semibold px-2.5 py-1 rounded-full bg-emerald/12 text-emerald font-[family-name:var(--font-display)]">
                    ✓ Подтверждено
                  </span>
                )}
              </div>

              {/* Description */}
              {request.description && (
                <p className="text-sm text-text-primary leading-relaxed m-0">
                  {request.description}
                </p>
              )}

              {/* Meta */}
              <div className="flex flex-col gap-1">
                <div className="text-xs text-text-secondary">
                  Создана: {new Date(request.created_at).toLocaleString('ru')}
                </div>
                {request.executor_name && (
                  <div className="text-xs text-text-secondary">
                    Исполнитель: <span className="font-semibold text-text-primary">{request.executor_name}</span>
                  </div>
                )}
                {request.address && (
                  <div className="text-xs text-text-secondary">
                    Адрес: {request.address}
                  </div>
                )}
              </div>

              {/* Contextual blocks */}
              {request.requested_materials && (
                <div className="bg-amber/8 border border-amber/20 rounded-[10px] px-3 py-2.5 text-[13px]">
                  <span className="font-semibold text-[#d97706]">Закуп: </span>
                  <span className="text-text-primary">{request.requested_materials}</span>
                </div>
              )}
              {request.notes && (
                <div className="bg-blue/8 border border-blue/20 rounded-[10px] px-3 py-2.5 text-[13px]">
                  <span className="font-semibold text-blue">Уточнение: </span>
                  <span className="text-text-primary">{request.notes}</span>
                </div>
              )}
              {request.completion_report && (
                <div className="bg-emerald/8 border border-emerald/20 rounded-[10px] px-3 py-2.5 text-[13px]">
                  <span className="font-semibold text-emerald">Отчёт: </span>
                  <span className="text-text-primary">{request.completion_report}</span>
                </div>
              )}
              {request.return_reason && (
                <div className="bg-red/8 border border-red/20 rounded-[10px] px-3 py-2.5 text-[13px]">
                  <span className="font-semibold text-red">Возврат: </span>
                  <span className="text-text-primary">{request.return_reason}</span>
                </div>
              )}

              {/* Manager actions — status: Выполнена */}
              {request.status === 'Выполнена' && (
                <div className="border border-border-default rounded-default p-3 bg-bg-surface flex flex-col gap-2">
                  {!showConfirmSection && !showReturnSection && (
                    <div className="flex gap-2">
                      <Button
                        onClick={() => setShowConfirmSection(true)}
                        className="flex-1 bg-emerald hover:bg-emerald/90 text-white"
                      >✓ Подтвердить</Button>
                      <Button
                        variant="outline"
                        onClick={() => setShowReturnSection(true)}
                        className="flex-1 border-[#ea580c] text-[#ea580c] hover:bg-[#ea580c]/10"
                      >↩ Вернуть в работу</Button>
                    </div>
                  )}
                  {showConfirmSection && (
                    <div className="flex flex-col gap-2">
                      <Label className="text-text-secondary text-xs">Комментарий (необязательно):</Label>
                      <Textarea
                        className="min-h-[60px] resize-y"
                        placeholder="Всё выполнено качественно"
                        value={confirmNote}
                        onChange={e => setConfirmNote(e.target.value)}
                      />
                      <div className="flex gap-2">
                        <Button variant="outline" className="flex-1" onClick={() => setShowConfirmSection(false)}>
                          Отмена
                        </Button>
                        <Button
                          onClick={() => updateRequest.mutate({ status: 'Исполнено', manager_confirmed: true, ...(confirmNote ? { manager_confirmation_notes: confirmNote } : {}) })}
                          disabled={updateRequest.isPending}
                          className="flex-1 bg-emerald hover:bg-emerald/90 text-white"
                        >
                          {updateRequest.isPending ? 'Сохраняю...' : 'Подтвердить'}
                        </Button>
                      </div>
                    </div>
                  )}
                  {showReturnSection && (
                    <div className="flex flex-col gap-2">
                      <Label className="text-text-secondary text-xs">Причина возврата:</Label>
                      <Textarea
                        className="min-h-[60px] resize-y"
                        placeholder="Опишите что нужно доделать"
                        value={returnReason}
                        onChange={e => setReturnReason(e.target.value)}
                        autoFocus
                      />
                      <div className="flex gap-2">
                        <Button variant="outline" className="flex-1" onClick={() => setShowReturnSection(false)}>
                          Отмена
                        </Button>
                        <Button
                          onClick={() => updateRequest.mutate({ status: 'В работе', return_reason: returnReason.trim() })}
                          disabled={updateRequest.isPending || !returnReason.trim()}
                          className="flex-1 bg-[#ea580c] hover:bg-[#ea580c]/90 text-white"
                        >
                          {updateRequest.isPending ? 'Сохраняю...' : 'Вернуть'}
                        </Button>
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* Manager actions — status: Исполнено (remind applicant or force-accept) */}
              {request.status === 'Исполнено' && (
                <div className="border border-border-default rounded-default p-3 bg-bg-surface flex flex-col gap-2">
                  <div className="text-xs text-text-secondary font-[family-name:var(--font-body)]">
                    Заявка выполнена. Ожидается приёмка жителем.
                  </div>

                  {!showForceAcceptSection && (
                    <div className="flex gap-2">
                      {/* Remind button */}
                      <Button
                        variant="outline"
                        onClick={sendReminder}
                        disabled={remindStatus === 'sending' || remindStatus === 'sent'}
                        className={cn(
                          'flex-1 font-semibold font-[family-name:var(--font-display)]',
                          remindStatus === 'sent'
                            ? 'bg-emerald/12 text-emerald border-emerald/30'
                            : remindStatus === 'error'
                            ? 'text-red'
                            : 'bg-blue/10 text-blue border-blue/30'
                        )}
                      >
                        {remindStatus === 'sending' ? 'Отправка...' : remindStatus === 'sent' ? '✓ Напомнено' : remindStatus === 'error' ? '✗ Ошибка' : '🔔 Напомнить жителю'}
                      </Button>

                      {/* Force accept button */}
                      <Button
                        variant="outline"
                        onClick={() => setShowForceAcceptSection(true)}
                        className="flex-1 bg-amber/10 text-[#d97706] border-amber/30 font-semibold font-[family-name:var(--font-display)]"
                      >
                        ✓ Принять за жителя
                      </Button>
                    </div>
                  )}

                  {showForceAcceptSection && (
                    <div className="flex flex-col gap-2">
                      <Label className="text-text-secondary text-xs">
                        Причина приёмки без жителя <span className="text-red">*</span>
                      </Label>
                      <Textarea
                        className="min-h-[72px] resize-y"
                        placeholder="Минимум 10 символов — например: житель недоступен 3 дня, работы приняты визуально"
                        value={forceAcceptNote}
                        onChange={e => setForceAcceptNote(e.target.value)}
                        autoFocus
                      />
                      {forceAcceptNote.length > 0 && forceAcceptNote.length < 10 && (
                        <div className="text-[11px] text-red">Минимум 10 символов ({forceAcceptNote.length}/10)</div>
                      )}
                      <div className="flex gap-2">
                        <Button
                          variant="outline"
                          className="flex-1"
                          onClick={() => { setShowForceAcceptSection(false); setForceAcceptNote('') }}
                        >Отмена</Button>
                        <Button
                          onClick={() => forceAccept.mutate(forceAcceptNote)}
                          disabled={forceAccept.isPending || forceAcceptNote.trim().length < 10}
                          className="flex-1 bg-[#d97706] hover:bg-[#d97706]/90 text-white font-[family-name:var(--font-display)]"
                        >
                          {forceAccept.isPending ? 'Сохраняю...' : 'Принять за жителя'}
                        </Button>
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* Comments history */}
              {comments && comments.length > 0 && (
                <div>
                  <div className="text-[11px] font-bold text-text-muted uppercase tracking-wide font-[family-name:var(--font-display)] mb-2">
                    История
                  </div>
                  <div className="flex flex-col gap-1.5">
                    {comments.map((c: { id: number; comment_text: string; is_internal: boolean; created_at: string }) => (
                      <div key={c.id} className={cn(
                        'rounded-[10px] px-3 py-2.5 text-[13px] border',
                        c.is_internal
                          ? 'bg-amber/[0.07] border-amber/15'
                          : 'bg-bg-surface border-border-default'
                      )}>
                        <p className="m-0 mb-1 text-text-primary">{c.comment_text}</p>
                        <span className="text-[11px] text-text-muted">{new Date(c.created_at).toLocaleString('ru')}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Add comment */}
              <div className="flex flex-col gap-1.5">
                <div className="text-[11px] font-bold text-text-muted uppercase tracking-wide font-[family-name:var(--font-display)]">
                  Заметка менеджера
                </div>
                <div className="flex gap-2">
                  <Input
                    className="flex-1"
                    placeholder="Добавить заметку..."
                    value={comment}
                    onChange={e => setComment(e.target.value)}
                    onKeyDown={e => e.key === 'Enter' && comment.trim() && postComment.mutate(comment)}
                  />
                  <Button
                    size="icon"
                    onClick={() => postComment.mutate(comment)}
                    disabled={!comment.trim() || postComment.isPending}
                    className="shrink-0"
                  >↑</Button>
                </div>
              </div>

            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}
