import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { usePersonName } from '../../hooks/usePersonName'
import { ChevronDown, TriangleAlert, X as XIcon } from 'lucide-react'
import { tUrgency, tCategory } from '../../i18n/apiMaps'
import { useHasRole } from '../../hooks/useHasRole'
import { useSeenRequests } from '../../hooks/useSeenRequests'
import { useRequest, useRequestComments } from '../../hooks/useRequestDetail'
import { categoryChangeWarning, useRequestMutations, type CategoryWarning } from '../../hooks/useRequestMutations'
import { CATEGORIES, MAX_REQUEST_TEXT_LENGTH, URGENCIES, normalizeUrgency } from '../../constants'
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
} from '@/components/ui/dropdown-menu'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import TransitionModal, { type TransitionData } from './TransitionModal'
import ReassignExecutorModal from './ReassignExecutorModal'
import { REASSIGNABLE_STATUSES } from './transitions'
import RequestMaterialsBlock from '../materials/RequestMaterialsBlock'
import RequestMedia from './RequestMedia'
import RequestAlertContext from './RequestAlertContext'
import StatusDropdown from './StatusDropdown'
import { MODAL_STATUSES, FROZEN_STATUSES, inProgressNeedsExecutorModal, needsReturnReasonModal } from './transitions'
import { STATUS_BADGE } from './statusStyles'
import ElevatorStatusPromptDialog from '../elevators/ElevatorStatusPromptDialog'
import { isElevatorsEnabled } from '../../utils/featureFlags'
import { getUrgencyStyle } from './urgencyStyle'

const SOURCE_ICON: Record<string, string> = {
  bot: '🤖', twa: '📱', web: '🌐', call_center: '📞', inspector: '🚶',
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
  const { name: personName } = usePersonName()
  const [comment, setComment] = useState('')
  const [confirmNote, setConfirmNote] = useState('')
  const [showConfirmSection, setShowConfirmSection] = useState(false)
  const [showReturnSection, setShowReturnSection] = useState(false)
  const [returnReason, setReturnReason] = useState('')
  const [showForceAcceptSection, setShowForceAcceptSection] = useState(false)
  const [forceAcceptNote, setForceAcceptNote] = useState('')
  const [remindStatus, setRemindStatus] = useState<'idle' | 'sending' | 'sent' | 'error'>('idle')
  const [pendingTargetStatus, setPendingTargetStatus] = useState<string | null>(null)
  const [reassignOpen, setReassignOpen] = useState(false)
  // Итог смены категории (см. CategoryWarning). Кнопка назначения — только
  // там, где канон пускает MANAGER_ASSIGN (флаг с сервера). Баннер гаснет при
  // успешном (пере)назначении и при no_op (live-QA 2026-09-03).
  const [categoryWarning, setCategoryWarning] = useState<CategoryWarning | null>(null)
  // Модуль «Лифты»: после подтверждения заявки с elevator_id — подсказка
  // «Лифт работает?» (смена статуса лифта одним касанием, Ф4a-3).
  const [elevatorPromptOpen, setElevatorPromptOpen] = useState(false)

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
    setCategoryWarning(null)
    setElevatorPromptOpen(false)
  }

  const { data: request } = useRequest(requestNumber)
  const { data: comments } = useRequestComments(requestNumber)

  // Открытая карточка считается прочитанной на своей текущей версии. Эффект
  // по `updated_at` покрывает оба пути входа — клик по карточке на доске и
  // deep-link `?request=` — и до-гасит точку, если заявка обновилась, пока
  // модалка открыта.
  const { markSeen } = useSeenRequests()
  const requestUpdatedAt: string | null = request?.updated_at ?? request?.created_at ?? null
  useEffect(() => {
    if (!requestNumber || !requestUpdatedAt) return
    markSeen(requestNumber, requestUpdatedAt)
  }, [requestNumber, requestUpdatedAt, markSeen])

  const isManager = useHasRole('manager')

  // Канон MANAGER_ASSIGN пускает смену исполнителя только из этих статусов —
  // список берётся из общего места, а не объявляется здесь второй раз.
  const canReassign = isManager && REASSIGNABLE_STATUSES.has(request?.status ?? '')

  const { updateRequest, changeCategory, forceAccept, remindApplicant, postComment } = useRequestMutations(
    requestNumber,
    {
      onUpdated: () => {
        setShowConfirmSection(false)
        setConfirmNote('')
      },
      onCategoryChanged: (data) => setCategoryWarning(categoryChangeWarning(data)),
      onForceAccepted: () => {
        setShowForceAcceptSection(false)
        setForceAcceptNote('')
      },
      onCommentPosted: () => setComment(''),
    },
  )

  const resetRemindStatusLater = () => setTimeout(() => setRemindStatus('idle'), 3000)
  const sendReminder = () => {
    setRemindStatus('sending')
    remindApplicant.mutate(undefined, {
      onSuccess: () => {
        setRemindStatus('sent')
        resetRemindStatusLater()
      },
      onError: () => {
        setRemindStatus('error')
        resetRemindStatusLater()
      },
    })
  }

  const handleTransitionConfirm = (data: TransitionData) => {
    updateRequest.mutate(data as unknown as Record<string, unknown>)
    setPendingTargetStatus(null)
  }

  // У заявки по лифту после успешной приёмки менеджером спрашиваем, работает
  // ли лифт (только при включённом модуле). Общий хвост для обоих путей:
  // подтверждение «Выполнена» → «Исполнено» и приёмка за жителя → «Принято».
  const openElevatorPromptIfNeeded = () => {
    if (isElevatorsEnabled() && request?.elevator_id) setElevatorPromptOpen(true)
  }

  const confirmCompletion = () =>
    updateRequest.mutate(
      { status: 'Исполнено', manager_confirmed: true, ...(confirmNote ? { manager_confirmation_notes: confirmNote } : {}) },
      { onSuccess: openElevatorPromptIfNeeded },
    )

  const forceAcceptWithNote = () =>
    forceAccept.mutate(forceAcceptNote, { onSuccess: openElevatorPromptIfNeeded })

  if (!requestNumber) return null

  const statusStyle = STATUS_BADGE[request?.status as keyof typeof STATUS_BADGE]
    ?? { bg: 'bg-bg-surface', text: 'text-text-muted' }
  const urgencyStyle = getUrgencyStyle(request?.urgency)

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
                {isManager && !FROZEN_STATUSES.has(request.status) ? (
                  // Менеджер меняет категорию прямо из заголовка (терминальные
                  // статусы заморожены каноном — там заголовок статичен).
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <button
                        type="button"
                        disabled={changeCategory.isPending}
                        title={t('kanban.changeCategory')}
                        className="inline-flex items-center gap-1 hover:text-accent transition-colors"
                      >
                        {tCategory(request.category, t)}
                        <ChevronDown className="w-4 h-4 text-text-muted" />
                      </button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent>
                      {CATEGORIES.map((c) => (
                        <DropdownMenuItem
                          key={c}
                          onSelect={() => {
                            // Сравниваем по локализованной подписи: в БД может
                            // лежать legacy-рус лейбл того же ключа — сервер
                            // и так ответил бы no_op, но запрос не нужен.
                            if (tCategory(c, t) !== tCategory(request.category, t)) changeCategory.mutate(c)
                          }}
                        >
                          {tCategory(c, t)}
                        </DropdownMenuItem>
                      ))}
                    </DropdownMenuContent>
                  </DropdownMenu>
                ) : tCategory(request.category, t)}
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
                      // 'В работе': модалка выбора исполнителя нужна только при
                      // назначении из «Новая» без исполнителя (canon MANAGER_ASSIGN).
                      // Из resume/return-источников (Закуп/Уточнение/Выполнена/
                      // Исполнено/Возвращена) executor_id НЕ принимается backend'ом
                      // (→ 422 «unexpected field 'executor_id'»), поэтому коммитим
                      // переход напрямую. Зеркалит фикс в KanbanBoard.handleDragEnd.
                      // Возврат в работу обязан нести причину (ядро иначе даёт
                      // 422) — открываем модалку, а не коммитим напрямую.
                      if (
                        targetStatus === 'В работе' &&
                        !needsReturnReasonModal(request.status, targetStatus) &&
                        !inProgressNeedsExecutorModal(request.status, Boolean(request.executor_id))
                      ) {
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

              <RequestAlertContext request={request} onOpenRelated={onOpenRelated} />

              {/* Description */}
              {request.description && (
                <p className="text-sm text-text-primary leading-relaxed m-0">
                  {request.description}
                </p>
              )}

              {/* Media: фото заявки + фотоотчёт (менеджер может дозагрузить).
                  Раздел скрывается, если медиа нет и грузить некому. */}
              <RequestMedia requestNumber={request.request_number} />

              {/* Meta */}
              <div className="flex flex-col gap-1">
                <div className="text-xs text-text-secondary">
                  {t('kanban.createdAt')} {formatDate(request.created_at)}
                </div>
                {categoryWarning && (
                  <div
                    role="alert"
                    className="flex items-center gap-2 flex-wrap rounded-sm border border-amber/40 bg-amber/10 px-2.5 py-1.5 text-xs text-text-primary"
                  >
                    <TriangleAlert className="w-3.5 h-3.5 text-amber shrink-0" />
                    <span>
                      {categoryWarning.kind === 'mismatch'
                        ? t('kanban.categorySpecMismatch')
                        : t('kanban.categoryLeftUnassigned')}
                    </span>
                    {categoryWarning.canReassign && (
                      <button
                        type="button"
                        onClick={() => setReassignOpen(true)}
                        className="text-accent hover:underline font-medium"
                      >
                        {categoryWarning.kind === 'mismatch'
                          ? t('kanban.reassignConfirm')
                          : t('kanban.assignConfirm')}
                      </button>
                    )}
                    <button
                      type="button"
                      onClick={() => setCategoryWarning(null)}
                      aria-label={t('common.close')}
                      className="ml-auto text-text-muted hover:text-text-primary"
                    >
                      <XIcon className="w-3 h-3" />
                    </button>
                  </div>
                )}
                {(request.executor_name || canReassign) && (
                  <div className="text-xs text-text-secondary flex items-center gap-2 flex-wrap">
                    {request.executor_name ? (
                      <span>
                        {t('kanban.executor')}{' '}
                        <span className="font-semibold text-text-primary">{personName(request.executor_name)}</span>
                      </span>
                    ) : (
                      <span>{t('kanban.executorNotAssigned')}</span>
                    )}
                    {/* Смена исполнителя из САМОЙ заявки. Раньше это было
                        возможно только «от сотрудника» (Сотрудники →
                        «Назначить заявку»), то есть менеджеру приходилось
                        уходить из карточки в другой раздел. Статусы — те же,
                        что пускает канон MANAGER_ASSIGN. */}
                    {canReassign && (
                      <button
                        type="button"
                        onClick={() => setReassignOpen(true)}
                        className="text-accent hover:underline font-medium"
                      >
                        {request.executor_id
                          ? t('kanban.reassignExecutorShort')
                          : t('kanban.assignExecutorShort')}
                      </button>
                    )}
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
              {/* Складской учёт: списанные материалы + себестоимость
                  (рендерится только MATERIALS_MODULE_ROLES и при наличии списаний) */}
              <div className="bg-bg-surface border border-border-default rounded-[10px] px-3 py-2.5 text-[13px] empty:hidden">
                <RequestMaterialsBlock requestNumber={request.request_number} />
              </div>
              {request.return_reason && (
                <div className="bg-red/8 border border-red/20 rounded-[10px] px-3 py-2.5 text-[13px]">
                  <span className="font-semibold text-red">{t('kanban.returnReason')} </span>
                  <span className="text-text-primary">{request.return_reason}</span>
                </div>
              )}
              {/* Причина менеджера — отдельным блоком и своей подписью: это
                  ответная реплика на возврат жителя, слипшись они бы
                  дезинформировали исполнителя. */}
              {request.manager_return_reason && (
                <div className="bg-[#ea580c]/8 border border-[#ea580c]/20 rounded-[10px] px-3 py-2.5 text-[13px]">
                  <span className="font-semibold text-[#ea580c]">{t('kanban.managerReturnReason')} </span>
                  <span className="text-text-primary">{request.manager_return_reason}</span>
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
                        maxLength={MAX_REQUEST_TEXT_LENGTH}
                      />
                      <div className="flex gap-2">
                        <Button variant="outline" className="flex-1" onClick={() => setShowConfirmSection(false)}>
                          {t('common.cancel')}
                        </Button>
                        <Button
                          onClick={confirmCompletion}
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
                        maxLength={MAX_REQUEST_TEXT_LENGTH}
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
                        maxLength={MAX_REQUEST_TEXT_LENGTH}
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
                          onClick={forceAcceptWithNote}
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
                    maxLength={MAX_REQUEST_TEXT_LENGTH}
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
        sourceStatus={request?.status}
        category={request?.category ?? null}
        onConfirm={handleTransitionConfirm}
        onCancel={() => setPendingTargetStatus(null)}
      />
    )}

    {reassignOpen && request && (
      <ReassignExecutorModal
        requestNumber={requestNumber}
        category={request.category ?? null}
        currentExecutorId={request.executor_id ?? null}
        currentExecutorName={request.executor_name ?? null}
        onClose={() => setReassignOpen(false)}
        onReassigned={() => setCategoryWarning(null)}
      />
    )}

    {elevatorPromptOpen && request?.elevator_id && (
      <ElevatorStatusPromptDialog
        open
        elevatorId={request.elevator_id}
        elevatorLabel={request.elevator_label ?? `#${request.elevator_id}`}
        currentStatus={request.elevator_status ?? null}
        requestNumbers={[requestNumber]}
        onClose={() => setElevatorPromptOpen(false)}
      />
    )}
    </>
  )
}
