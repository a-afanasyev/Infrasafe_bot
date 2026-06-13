import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { ChevronDown, ImageOff, X as XIcon } from 'lucide-react'
import { apiClient } from '../../api/client'
import { safeErrorMessage } from '@/utils/errorMessage'
import { tStatus, tUrgency, tCategory } from '../../i18n/apiMaps'
import { useHasRole } from '../../hooks/useHasRole'
import { URGENCIES, normalizeUrgency } from '../../constants'
import { formatDate } from '../../i18n/formatters'
import { cn } from '@/lib/utils'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
} from '@/components/ui/dropdown-menu'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import TransitionModal, { type TransitionData } from './TransitionModal'
import { VALID_TRANSITIONS, MODAL_STATUSES, FROZEN_STATUSES } from './KanbanBoard'

// TASK 17: канон-ключи + legacy-рус (dual-read, снять рус в Фазе 2).
const URGENCY: Record<string, { bg: string; text: string }> = {
  low:          { bg: 'bg-emerald/12',  text: 'text-emerald' },
  medium:       { bg: 'bg-amber/12',    text: 'text-amber' },
  high:         { bg: 'bg-[#ea580c]/12', text: 'text-[#ea580c]' },
  critical:     { bg: 'bg-red/12',      text: 'text-red' },
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

const STATUS_DOT: Record<string, string> = {
  'Новая':     'bg-[#60a5fa]',
  'В работе':  'bg-[#fbbf24]',
  'Закуп':     'bg-[#a78bfa]',
  'Уточнение': 'bg-[#22d3ee]',
  'Выполнена': 'bg-[#34d399]',
  'Исполнено': 'bg-accent',
  'Принято':   'bg-[#4ade80]',
  'Отменена':  'bg-[#f87171]',
}

const SOURCE_ICON: Record<string, string> = {
  bot: '🤖', twa: '📱', web: '🌐', call_center: '📞', inspector: '🚶',
}

// FE-119: format the InfraSafe working-range band. One-sided when only min OR
// max is present (e.g. heating ≥40 °C, transformer load ≤80 %).
function formatWorkingRange(
  min?: number | null,
  max?: number | null,
  unit?: string | null,
): string | null {
  const u = unit ? ` ${unit}` : ''
  if (min != null && max != null) return `${min}–${max}${u}`
  if (min != null) return `≥ ${min}${u}`
  if (max != null) return `≤ ${max}${u}`
  return null
}

interface Props {
  requestNumber: string | null
  onClose: () => void
  /**
   * INT-120 #4 — handler for opening a different request from inside this modal
   * (clicking the «Связанная заявка» link on the reopen-block). When omitted,
   * the link renders as plain text — callers can opt in to navigation.
   */
  onOpenRelated?: (relatedRequestNumber: string) => void
}

export default function RequestDetailModal({ requestNumber, onClose, onOpenRelated }: Props) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [comment, setComment] = useState('')
  const [confirmNote, setConfirmNote] = useState('')
  const [showConfirmSection, setShowConfirmSection] = useState(false)
  const [showReturnSection, setShowReturnSection] = useState(false)
  const [returnReason, setReturnReason] = useState('')
  const [showForceAcceptSection, setShowForceAcceptSection] = useState(false)
  const [forceAcceptNote, setForceAcceptNote] = useState('')
  const [remindStatus, setRemindStatus] = useState<'idle' | 'sending' | 'sent' | 'error'>('idle')
  const [pendingTargetStatus, setPendingTargetStatus] = useState<string | null>(null)

  // FE-07: reset per-request form state when a *different* request opens.
  // Done at render time («adjust state when input changes») rather than in an
  // effect — avoids the set-state-in-effect cascade. We deliberately do NOT use
  // `key={requestNumber}` to force a remount: that would unmount the Radix
  // Dialog on close (requestNumber→null) and kill its exit animation.
  const [shownRequest, setShownRequest] = useState(requestNumber)
  if (requestNumber !== shownRequest) {
    setShownRequest(requestNumber)
    setComment('')
    setConfirmNote('')
    setShowConfirmSection(false)
    setShowReturnSection(false)
    setReturnReason('')
    setShowForceAcceptSection(false)
    setForceAcceptNote('')
    setRemindStatus('idle')
    setPendingTargetStatus(null)
  }

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

  const isManager = useHasRole('manager')

  const updateRequest = useMutation({
    mutationFn: (data: Record<string, unknown>) =>
      apiClient.patch(`/api/v2/requests/${requestNumber}`, data).then(r => r.data),
    onSuccess: () => {
      toast.success(t('toast.requestUpdated'))
      queryClient.invalidateQueries({ queryKey: ['request', requestNumber] })
      queryClient.invalidateQueries({ queryKey: ['kanban'] })
      setShowConfirmSection(false)
      setConfirmNote('')
    },
    onError: (error: unknown) => {
      toast.error(t('toast.requestUpdateFailed'), { description: safeErrorMessage(error, 'An error occurred') })
    },
  })

  const forceAccept = useMutation({
    mutationFn: (note: string) =>
      apiClient.patch(`/api/v2/requests/${requestNumber}`, {
        status: 'Принято',
        manager_confirmation_notes: note,
      }).then(r => r.data),
    onSuccess: () => {
      toast.success(t('toast.requestForceAccepted'))
      queryClient.invalidateQueries({ queryKey: ['request', requestNumber] })
      queryClient.invalidateQueries({ queryKey: ['kanban'] })
      setShowForceAcceptSection(false)
      setForceAcceptNote('')
    },
    onError: (error: unknown) => {
      toast.error(t('toast.requestForceAcceptFailed'), { description: safeErrorMessage(error, 'An error occurred') })
    },
  })

  const sendReminder = async () => {
    setRemindStatus('sending')
    try {
      await apiClient.post(`/api/v2/requests/${requestNumber}/remind-applicant`)
      toast.success(t('toast.reminderSent'))
      setRemindStatus('sent')
      setTimeout(() => setRemindStatus('idle'), 3000)
    } catch {
      toast.error(t('toast.reminderFailed'))
      setRemindStatus('error')
      setTimeout(() => setRemindStatus('idle'), 3000)
    }
  }

  const postComment = useMutation({
    mutationFn: (text: string) =>
      apiClient.post(`/api/v2/requests/${requestNumber}/comments`, { text, is_internal: true }).then(r => r.data),
    onSuccess: () => {
      toast.success(t('toast.noteAdded'))
      queryClient.invalidateQueries({ queryKey: ['comments', requestNumber] })
      setComment('')
    },
    onError: (error: unknown) => {
      toast.error(t('toast.noteAddFailed'), { description: safeErrorMessage(error, 'An error occurred') })
    },
  })

  const handleTransitionConfirm = (data: TransitionData) => {
    updateRequest.mutate(data as unknown as Record<string, unknown>)
    setPendingTargetStatus(null)
  }

  if (!requestNumber) return null

  const statusStyle = STATUS[request?.status ?? ''] ?? { bg: 'bg-bg-surface', text: 'text-text-muted' }
  const urgencyStyle = request?.urgency ? URGENCY[request.urgency] : null

  return (
    <>
    <Dialog open onOpenChange={(open) => { if (!open) onClose() }}>
      <DialogContent
        className="max-w-[520px] max-h-[88vh] p-0 gap-0 flex flex-col"
        onPointerDownOutside={(e) => {
          // Prevent dialog close when clicking dropdown menu items (rendered in portal)
          const target = e.target as HTMLElement
          if (target.closest('[data-slot="dropdown-menu-content"]')) {
            e.preventDefault()
          }
        }}
      >
        {!request ? (
          <div className="p-6 text-center text-text-muted font-[family-name:var(--font-body)]">
            {t('common.loading')}
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
                {tCategory(request.category, t)}
              </DialogTitle>
            </DialogHeader>

            {/* Body */}
            <div className="px-[18px] py-4 overflow-y-auto flex-1 flex flex-col gap-3.5">

              {/* Badges */}
              <div className="flex gap-1.5 flex-wrap items-center">
                <StatusDropdown
                  status={request.status}
                  statusStyle={statusStyle}
                  onSelect={(targetStatus) => {
                    if (MODAL_STATUSES.has(targetStatus)) {
                      // For 'В работе': skip modal if already has executor
                      if (targetStatus === 'В работе' && request.executor_id) {
                        updateRequest.mutate({ status: targetStatus })
                        return
                      }
                      setPendingTargetStatus(targetStatus)
                    } else {
                      updateRequest.mutate({ status: targetStatus })
                    }
                  }}
                />
                {request.urgency && (
                  isManager && !FROZEN_STATUSES.has(request.status) ? (
                    // TASK 17: менеджер меняет критичность (терминальные статусы заморожены backend-guard'ом).
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <button
                          type="button"
                          disabled={updateRequest.isPending}
                          className={cn(
                            'text-xs font-semibold px-2.5 py-1 rounded-full inline-flex items-center gap-1 font-[family-name:var(--font-display)]',
                            urgencyStyle?.bg, urgencyStyle?.text
                          )}
                        >
                          {tUrgency(request.urgency, t)}
                          <ChevronDown className="w-3 h-3" />
                        </button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent>
                        {URGENCIES.map((u) => (
                          <DropdownMenuItem
                            key={u}
                            onSelect={() => {
                              // Сравниваем по канон-ключу: legacy-рус значение (Phase 1)
                              // не должно вызывать лишний PATCH при выборе эквивалента.
                              if (u !== normalizeUrgency(request.urgency)) updateRequest.mutate({ urgency: u })
                            }}
                          >
                            {tUrgency(u, t)}
                          </DropdownMenuItem>
                        ))}
                      </DropdownMenuContent>
                    </DropdownMenu>
                  ) : urgencyStyle ? (
                    <span className={cn(
                      'text-xs font-semibold px-2.5 py-1 rounded-full font-[family-name:var(--font-display)]',
                      urgencyStyle.bg, urgencyStyle.text
                    )}>{tUrgency(request.urgency, t)}</span>
                  ) : null
                )}
                {request.manager_confirmed && (
                  <span className="text-xs font-semibold px-2.5 py-1 rounded-full bg-emerald/12 text-emerald font-[family-name:var(--font-display)]">
                    ✓ {t('kanban.confirmed')}
                  </span>
                )}
              </div>

              {/* INT-120 #4 — Sprint 10 reopen-chain context.
                  Backend surfaces these from webhook_inbox.payload.alert when
                  the request was created via inbound InfraSafe alert (sub-task
                  #3). reopen_sequence is null for first-time alerts and
                  manual requests; engineer_required_reason is non-null only
                  on alert.engineer_required chain-end transitions. */}
              {(request.reopen_sequence || request.engineer_required_reason) && (
                <div className="bg-amber/8 border border-amber/25 rounded-[10px] px-3 py-2.5 text-[13px] flex flex-col gap-1.5">
                  {request.reopen_sequence && (
                    <div className="flex items-center gap-1.5 flex-wrap">
                      <span className="font-semibold text-[#d97706]">
                        🔁 {t('kanban.reopenBadge', { n: request.reopen_sequence })}
                      </span>
                      {request.related_request_number && (
                        <>
                          <span className="text-text-muted">·</span>
                          <span className="text-text-secondary">
                            {t('kanban.relatedRequest')}{' '}
                          </span>
                          {onOpenRelated ? (
                            <button
                              type="button"
                              onClick={() => onOpenRelated(request.related_request_number)}
                              className="font-[family-name:var(--font-mono)] text-blue hover:underline cursor-pointer"
                            >
                              {request.related_request_number}
                            </button>
                          ) : (
                            <span className="font-[family-name:var(--font-mono)] text-text-primary">
                              {request.related_request_number}
                            </span>
                          )}
                        </>
                      )}
                    </div>
                  )}
                  {request.engineer_required_reason && (
                    <div className="flex items-center gap-1.5 flex-wrap pt-1 border-t border-amber/15">
                      <span className="font-semibold text-red">
                        ⚠ {t('kanban.engineerEscalation')}
                      </span>
                      <span className="text-text-secondary">
                        {t('kanban.engineerReason')}{' '}
                      </span>
                      <span className="font-[family-name:var(--font-mono)] text-text-primary text-[12px]">
                        {request.engineer_required_reason}
                      </span>
                    </div>
                  )}
                </div>
              )}

              {/* FE-119 — InfraSafe alert context (metric + infrastructure).
                  Rendered only for requests created from an inbound alert.
                  metric_value absent → label-only (e.g. LEAK_DETECTED). */}
              {(request.metric_label || request.infrastructure_label) && (
                <div className="bg-blue/8 border border-blue/25 rounded-[10px] px-3 py-2.5 text-[13px] flex flex-col gap-1">
                  <span className="font-semibold text-blue text-[11px] uppercase tracking-wide font-[family-name:var(--font-display)]">
                    📡 {t('kanban.alertSource')}
                  </span>
                  {request.infrastructure_label && (
                    <div className="text-text-secondary">{request.infrastructure_label}</div>
                  )}
                  {request.metric_label && (
                    <div className="text-text-primary">
                      {request.metric_label}
                      {request.metric_value != null && (
                        <>
                          {': '}
                          <span className="font-[family-name:var(--font-mono)] font-semibold">
                            {request.metric_value}{request.metric_unit ? ` ${request.metric_unit}` : ''}
                          </span>
                          {formatWorkingRange(request.metric_normal_min, request.metric_normal_max, request.metric_unit) && (
                            <span className="text-text-muted">
                              {' '}({t('kanban.workingRange')} {formatWorkingRange(request.metric_normal_min, request.metric_normal_max, request.metric_unit)})
                            </span>
                          )}
                        </>
                      )}
                    </div>
                  )}
                </div>
              )}

              {/* Description */}
              {request.description && (
                <p className="text-sm text-text-primary leading-relaxed m-0">
                  {request.description}
                </p>
              )}

              {/* Media (фото/видео заявки). Раздел скрывается, если медиа нет. */}
              <RequestMedia requestNumber={request.request_number} />

              {/* Meta */}
              <div className="flex flex-col gap-1">
                <div className="text-xs text-text-secondary">
                  {t('kanban.createdAt')} {formatDate(request.created_at)}
                </div>
                {request.executor_name && (
                  <div className="text-xs text-text-secondary">
                    {t('kanban.executor')} <span className="font-semibold text-text-primary">{request.executor_name}</span>
                  </div>
                )}
                {request.address && (
                  <div className="text-xs text-text-secondary">
                    {t('kanban.address')} {request.address}
                  </div>
                )}
              </div>

              {/* Contextual blocks */}
              {request.requested_materials && (
                <div className="bg-amber/8 border border-amber/20 rounded-[10px] px-3 py-2.5 text-[13px]">
                  <span className="font-semibold text-[#d97706]">{t('kanban.purchase')} </span>
                  <span className="text-text-primary">{request.requested_materials}</span>
                </div>
              )}
              {request.notes && (
                <div className="bg-blue/8 border border-blue/20 rounded-[10px] px-3 py-2.5 text-[13px]">
                  <span className="font-semibold text-blue">{t('kanban.clarification')} </span>
                  <span className="text-text-primary">{request.notes}</span>
                </div>
              )}
              {request.completion_report && (
                <div className="bg-emerald/8 border border-emerald/20 rounded-[10px] px-3 py-2.5 text-[13px]">
                  <span className="font-semibold text-emerald">{t('kanban.report')} </span>
                  <span className="text-text-primary">{request.completion_report}</span>
                </div>
              )}
              {request.return_reason && (
                <div className="bg-red/8 border border-red/20 rounded-[10px] px-3 py-2.5 text-[13px]">
                  <span className="font-semibold text-red">{t('kanban.returnReason')} </span>
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
                      >✓ {t('kanban.confirmAction')}</Button>
                      <Button
                        variant="outline"
                        onClick={() => setShowReturnSection(true)}
                        className="flex-1 border-[#ea580c] text-[#ea580c] hover:bg-[#ea580c]/10"
                      >↩ {t('kanban.returnToWork')}</Button>
                    </div>
                  )}
                  {showConfirmSection && (
                    <div className="flex flex-col gap-2">
                      <Label className="text-text-secondary text-xs">{t('kanban.commentOptional')}</Label>
                      <Textarea
                        className="min-h-[60px] resize-y"
                        placeholder={t('kanban.commentPlaceholder')}
                        value={confirmNote}
                        onChange={e => setConfirmNote(e.target.value)}
                      />
                      <div className="flex gap-2">
                        <Button variant="outline" className="flex-1" onClick={() => setShowConfirmSection(false)}>
                          {t('common.cancel')}
                        </Button>
                        <Button
                          onClick={() => updateRequest.mutate({ status: 'Исполнено', manager_confirmed: true, ...(confirmNote ? { manager_confirmation_notes: confirmNote } : {}) })}
                          disabled={updateRequest.isPending}
                          className="flex-1 bg-emerald hover:bg-emerald/90 text-white"
                        >
                          {updateRequest.isPending ? t('common.saving') : t('common.confirm')}
                        </Button>
                      </div>
                    </div>
                  )}
                  {showReturnSection && (
                    <div className="flex flex-col gap-2">
                      <Label className="text-text-secondary text-xs">{t('kanban.returnReasonLabel')}</Label>
                      <Textarea
                        className="min-h-[60px] resize-y"
                        placeholder={t('kanban.returnPlaceholder')}
                        value={returnReason}
                        onChange={e => setReturnReason(e.target.value)}
                        autoFocus
                      />
                      <div className="flex gap-2">
                        <Button variant="outline" className="flex-1" onClick={() => setShowReturnSection(false)}>
                          {t('common.cancel')}
                        </Button>
                        <Button
                          onClick={() => updateRequest.mutate({ status: 'В работе', return_reason: returnReason.trim() })}
                          disabled={updateRequest.isPending || !returnReason.trim()}
                          className="flex-1 bg-[#ea580c] hover:bg-[#ea580c]/90 text-white"
                        >
                          {updateRequest.isPending ? t('common.saving') : t('kanban.returnAction')}
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
                    {t('kanban.awaitingAcceptance')}
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
                        {remindStatus === 'sending' ? t('kanban.reminding') : remindStatus === 'sent' ? `✓ ${t('kanban.reminded')}` : remindStatus === 'error' ? `✗ ${t('kanban.remindError')}` : `🔔 ${t('kanban.remindResident')}`}
                      </Button>

                      {/* Force accept button */}
                      <Button
                        variant="outline"
                        onClick={() => setShowForceAcceptSection(true)}
                        className="flex-1 bg-amber/10 text-[#d97706] border-amber/30 font-semibold font-[family-name:var(--font-display)]"
                      >
                        ✓ {t('kanban.forceAccept')}
                      </Button>
                    </div>
                  )}

                  {showForceAcceptSection && (
                    <div className="flex flex-col gap-2">
                      <Label className="text-text-secondary text-xs">
                        {t('kanban.forceAcceptReason')} <span className="text-red">*</span>
                      </Label>
                      <Textarea
                        className="min-h-[72px] resize-y"
                        placeholder={t('kanban.forceAcceptPlaceholder')}
                        value={forceAcceptNote}
                        onChange={e => setForceAcceptNote(e.target.value)}
                        autoFocus
                      />
                      {forceAcceptNote.length > 0 && forceAcceptNote.length < 10 && (
                        <div className="text-[11px] text-red">{t('errors.minChars', { min: 10, current: forceAcceptNote.length })}</div>
                      )}
                      <div className="flex gap-2">
                        <Button
                          variant="outline"
                          className="flex-1"
                          onClick={() => { setShowForceAcceptSection(false); setForceAcceptNote('') }}
                        >{t('common.cancel')}</Button>
                        <Button
                          onClick={() => forceAccept.mutate(forceAcceptNote)}
                          disabled={forceAccept.isPending || forceAcceptNote.trim().length < 10}
                          className="flex-1 bg-[#d97706] hover:bg-[#d97706]/90 text-white font-[family-name:var(--font-display)]"
                        >
                          {forceAccept.isPending ? t('common.saving') : t('kanban.forceAccept')}
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
                    {t('kanban.history')}
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
                        <span className="text-[11px] text-text-muted">{formatDate(c.created_at)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Add comment */}
              <div className="flex flex-col gap-1.5">
                <div className="text-[11px] font-bold text-text-muted uppercase tracking-wide font-[family-name:var(--font-display)]">
                  {t('kanban.managerNote')}
                </div>
                <div className="flex gap-2">
                  <Input
                    className="flex-1"
                    placeholder={t('kanban.addNote')}
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

    {pendingTargetStatus && (
      <TransitionModal
        requestNumber={requestNumber}
        targetStatus={pendingTargetStatus}
        onConfirm={handleTransitionConfirm}
        onCancel={() => setPendingTargetStatus(null)}
      />
    )}
    </>
  )
}

interface MediaItem {
  id: number
  file_type: string
  mime_type: string
  category?: string | null
}

// Site-wide CSP (infrasafe-nginx) запрещает blob: в img-src → грузим байты
// через apiClient (Bearer) и конвертируем в data: URL (как FeedbackDetailModal /
// twa/MediaGallery). Без этого фото к заявке не отображались на канбане вовсе —
// раздела медиа в модалке просто не было.
async function fetchMediaDataUrl(mediaId: number): Promise<string> {
  const r = await apiClient.get(`/api/v2/media/${mediaId}/file`, { responseType: 'blob' })
  return await new Promise<string>((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => (typeof reader.result === 'string' ? resolve(reader.result) : reject(new Error('bad')))
    reader.onerror = () => reject(reader.error)
    reader.readAsDataURL(r.data as Blob)
  })
}

function RequestMedia({ requestNumber }: { requestNumber: string }) {
  const { t } = useTranslation()
  const [lightboxId, setLightboxId] = useState<number | null>(null)

  const { data: items = [] } = useQuery<MediaItem[]>({
    queryKey: ['request-media', requestNumber],
    queryFn: () => apiClient.get(`/api/v2/media/request/${requestNumber}`).then(r => r.data),
    enabled: !!requestNumber,
    staleTime: 60_000,
  })

  if (items.length === 0) return null

  return (
    <div>
      <div className="text-[11px] font-bold text-text-muted uppercase tracking-wide font-[family-name:var(--font-display)] mb-2">
        {t('kanban.photos')}
      </div>
      <div className="flex flex-wrap gap-2">
        {items.map((m) => (
          <MediaThumb key={m.id} id={m.id} isVideo={m.file_type === 'video'} onOpen={() => setLightboxId(m.id)} />
        ))}
      </div>
      {lightboxId !== null && (
        <MediaLightbox key={lightboxId} id={lightboxId} onClose={() => setLightboxId(null)} />
      )}
    </div>
  )
}

function MediaThumb({ id, isVideo, onOpen }: { id: number; isVideo: boolean; onOpen: () => void }) {
  const { t } = useTranslation()
  // FE-11: cache the blob data-URL by media id (shared queryKey with the
  // lightbox) so re-opening the modal or the viewer doesn't re-download.
  const { data: url, isError: errored } = useQuery({
    queryKey: ['media-blob', id],
    queryFn: () => fetchMediaDataUrl(id),
    staleTime: 5 * 60_000,
    retry: false,
  })

  if (errored) {
    return (
      <div className="w-20 h-20 rounded-lg border border-border-default bg-bg-surface flex items-center justify-center text-text-secondary" title={t('kanban.mediaError')}>
        <ImageOff size={18} />
      </div>
    )
  }
  return (
    <button
      type="button"
      onClick={onOpen}
      className="relative w-20 h-20 rounded-lg overflow-hidden border border-border-default bg-bg-surface"
    >
      {url ? (
        isVideo ? (
          <video src={url} className="w-full h-full object-cover" muted />
        ) : (
          <img src={url} alt="" className="w-full h-full object-cover" />
        )
      ) : (
        <div className="w-full h-full animate-pulse bg-bg-surface" />
      )}
      {isVideo && (
        <span className="absolute inset-0 flex items-center justify-center text-white text-lg drop-shadow">▶</span>
      )}
    </button>
  )
}

function MediaLightbox({ id, onClose }: { id: number; onClose: () => void }) {
  // FE-11: reuse the cached blob (shared ['media-blob', id]) — opening the
  // viewer for a thumb that already loaded is instant, no re-download.
  const { data: url, isError } = useQuery({
    queryKey: ['media-blob', id],
    queryFn: () => fetchMediaDataUrl(id),
    staleTime: 5 * 60_000,
    retry: false,
  })
  const isVideo = url?.startsWith('data:video') ?? false

  useEffect(() => {
    if (isError) onClose()
  }, [isError, onClose])

  return (
    <div
      className="fixed inset-0 z-[60] bg-black/85 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <button
        type="button"
        onClick={onClose}
        className="absolute top-4 right-4 w-9 h-9 rounded-full bg-white/15 text-white flex items-center justify-center"
      >
        <XIcon size={18} />
      </button>
      {url && (
        isVideo ? (
          <video src={url} controls autoPlay className="max-w-full max-h-[85vh] rounded-lg" onClick={(e) => e.stopPropagation()} />
        ) : (
          <img src={url} alt="" className="max-w-full max-h-[85vh] rounded-lg object-contain" onClick={(e) => e.stopPropagation()} />
        )
      )}
    </div>
  )
}

function StatusDropdown({
  status,
  statusStyle,
  onSelect,
}: {
  status: string
  statusStyle: { bg: string; text: string }
  onSelect: (targetStatus: string) => void
}) {
  const { t } = useTranslation()
  const frozen = FROZEN_STATUSES.has(status)
  const transitions = VALID_TRANSITIONS[status]
  const hasTransitions = transitions && transitions.size > 0

  // Frozen or no transitions — static badge
  if (frozen || !hasTransitions) {
    return (
      <span className={cn(
        'text-xs font-semibold px-2.5 py-1 rounded-full font-[family-name:var(--font-display)]',
        statusStyle.bg, statusStyle.text
      )}>
        {tStatus(status, t)}
      </span>
    )
  }

  const items = Array.from(transitions)
  const cancelIdx = items.indexOf('Отменена')

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button className={cn(
          'inline-flex items-center gap-1 text-xs font-semibold px-2.5 py-1 rounded-full font-[family-name:var(--font-display)] transition-colors cursor-pointer',
          'hover:ring-2 hover:ring-offset-1 hover:ring-offset-bg-card',
          statusStyle.bg, statusStyle.text,
          // ring color matches status
          status === 'Новая' && 'hover:ring-[#60a5fa]/40',
          status === 'В работе' && 'hover:ring-[#fbbf24]/40',
          status === 'Закуп' && 'hover:ring-[#a78bfa]/40',
          status === 'Уточнение' && 'hover:ring-[#22d3ee]/40',
          status === 'Выполнена' && 'hover:ring-[#34d399]/40',
          status === 'Исполнено' && 'hover:ring-accent/40',
        )}>
          {tStatus(status, t)}
          <ChevronDown className="w-3 h-3 opacity-60" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" sideOffset={6} className="min-w-[180px]">
        {items.map((targetStatus) => (
          <span key={targetStatus}>
            {/* Separator before Отменена */}
            {targetStatus === 'Отменена' && cancelIdx > 0 && <DropdownMenuSeparator />}
            <DropdownMenuItem
              onClick={() => onSelect(targetStatus)}
              variant={targetStatus === 'Отменена' ? 'destructive' : 'default'}
              className="gap-2.5 py-2 px-2.5"
            >
              <span className={cn(
                'w-2 h-2 rounded-full shrink-0',
                STATUS_DOT[targetStatus] ?? 'bg-text-muted'
              )} />
              <span className="font-[family-name:var(--font-display)] font-semibold text-[13px]">
                {tStatus(targetStatus, t)}
              </span>
            </DropdownMenuItem>
          </span>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
