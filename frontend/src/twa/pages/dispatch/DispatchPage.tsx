import { useCallback, useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { ArrowLeft } from 'lucide-react'
import ElevatorStep from '../../components/ElevatorStep'
import { useTelegramSDK } from '../../hooks/useTelegramSDK'
import { ResultScreen, PRIMARY_BTN } from '../../simple/components/Ui'
import { getErrorMessage } from '../../utils/errors'
import AddressStep from './AddressStep'
import PhoneStep from './PhoneStep'
import { CategoryStep, DescriptionStep, UrgencyStep } from './ProblemSteps'
import ReviewStep, { type Phase } from './ReviewStep'
import { aiCheckEnabled, checkRequest, createRequest, type AddressOption, type CheckIssue } from './api'
import {
  EMPTY_DRAFT,
  applyIssueFix,
  buildCheckBody,
  buildCreateBody,
  elevatorMissing,
  stepAfter,
  stepBefore,
  withAddress,
  type Draft,
  type Step,
} from './model'

const DRAFT_KEY = 'twa.dispatch.draft'
/** Замечание, оставленное «как есть»: тот же совет не повторяем, другой — покажем. */
const issueKey = (i: CheckIssue): string => `${i.code}:${i.suggestion ?? ''}`
const ISSUE_STEP: Record<CheckIssue['field'], Step> = {
  description: 'description',
  category: 'category',
  urgency: 'urgency',
  address: 'address',
}

function loadDraft(): Draft {
  try {
    const raw = sessionStorage.getItem(DRAFT_KEY)
    return raw ? { ...EMPTY_DRAFT, ...(JSON.parse(raw) as Partial<Draft>) } : EMPTY_DRAFT
  } catch {
    return EMPTY_DRAFT
  }
}

/**
 * Экран диспетчера: заявка по телефонному звонку. Один вопрос на экран,
 * адрес только из справочника; перед отправкой ИИ проверяет заявку и
 * подсказывает, что поправить — совет, а не запрет.
 */
export default function DispatchPage() {
  const { t } = useTranslation()
  const { haptic, notify, showBackButton } = useTelegramSDK()
  const [draft, setDraft] = useState<Draft>(loadDraft)
  const [issues, setIssues] = useState<CheckIssue[]>([])
  // Что уже проверено и какие замечания человек оставил как есть: повторное
  // «Отправить» без правок не зовёт ИИ снова и не повторяет тот же совет.
  const [checkedKey, setCheckedKey] = useState<string | null>(null)
  const [kept, setKept] = useState<string[]>([])
  const [phase, setPhase] = useState<Phase>('idle')
  const [error, setError] = useState<string | null>(null)
  const [doneNumber, setDoneNumber] = useState<string | null>(null)

  const ai = useQuery({ queryKey: ['twa', 'dispatch', 'ai'], queryFn: aiCheckEnabled, staleTime: 5 * 60_000 })

  useEffect(() => {
    try {
      sessionStorage.setItem(DRAFT_KEY, JSON.stringify(draft))
    } catch { /* sessionStorage недоступен (private mode) — работаем без черновика */ }
  }, [draft])

  const advance = useCallback((patch: Partial<Draft> = {}) => {
    haptic('selection')
    setDraft((d) => {
      const next = { ...d, ...patch }
      const step = stepAfter(d.step, next)
      return { ...next, step, editing: step === 'review' ? false : next.editing }
    })
  }, [haptic])

  const goBack = useCallback(() => {
    setDraft((d) => ({ ...d, step: stepBefore(d.step, d), editing: false }))
  }, [])
  useEffect(() => {
    if (draft.step !== 'phone' && !doneNumber) return showBackButton(goBack)
  }, [draft.step, doneNumber, showBackButton, goBack])

  const edit = (step: Step) => setDraft((d) => ({ ...d, step, editing: true }))

  const reset = () => {
    setDraft(EMPTY_DRAFT)
    setIssues([])
    setCheckedKey(null)
    setKept([])
    setError(null)
    setDoneNumber(null)
  }

  const contentKey = JSON.stringify(buildCheckBody(draft))
  const visibleIssues = checkedKey === contentKey ? issues : []

  const fix = (issue: CheckIssue, option?: AddressOption) => {
    const fixed = applyIssueFix(draft, issue, option)
    if (fixed === draft) {
      edit(ISSUE_STEP[issue.field]) // подставить нечего — открываем сам вопрос
      return
    }
    // Правка в одно касание закрывает своё замечание; остальные остаются на
    // экране, повторно ИИ не зовём.
    // Стала нужна категория «Лифт» или сменился дом — сначала выбрать лифт.
    setDraft(elevatorMissing(fixed) ? { ...fixed, step: 'elevator', editing: true } : fixed)
    setCheckedKey(JSON.stringify(buildCheckBody(fixed)))
    setIssues((list) => list.filter((i) => i.code !== issue.code))
  }

  const keep = (issue: CheckIssue) => {
    setKept((k) => [...k, issueKey(issue)])
    setIssues((list) => list.filter((i) => i.code !== issue.code))
  }

  const submit = async () => {
    setError(null)
    if (ai.data && checkedKey !== contentKey) {
      setPhase('checking')
      // Сбой проверки не должен останавливать приём звонка.
      const result = await checkRequest(buildCheckBody(draft)).catch(() => null)
      const fresh = (result?.issues ?? []).filter((i) => !kept.includes(issueKey(i)))
      setCheckedKey(contentKey)
      setIssues(fresh)
      if (fresh.length > 0) {
        notify('warning')
        // Замечания стоят над сводкой, а кнопка «Отправить» — под ней.
        document.querySelector('main')?.scrollIntoView?.({ block: 'start' })
        setPhase('idle')
        return
      }
    }
    setPhase('sending')
    try {
      const created = await createRequest(buildCreateBody(draft))
      notify('success')
      setDoneNumber(created.request_number)
      // Телефон и имя звонящего не должны оставаться в черновике WebView.
      setDraft(EMPTY_DRAFT)
    } catch (err: unknown) {
      notify('error')
      setError(getErrorMessage(err, t('twa.create.submitFailed')))
    } finally {
      setPhase('idle')
    }
  }

  if (doneNumber) {
    return (
      <ResultScreen ok title={t('twa.dispatch.done.title', { number: doneNumber })}>
        <button type="button" onClick={reset} className={`${PRIMARY_BTN} bg-white text-emerald-700`}>
          {t('twa.dispatch.done.next')}
        </button>
      </ResultScreen>
    )
  }

  return (
    <main className="max-w-md mx-auto p-4 pb-[calc(24px+env(safe-area-inset-bottom))] flex flex-col gap-4">
      {draft.step !== 'phone' && (
        <button
          type="button"
          onClick={goBack}
          className="self-start h-[48px] px-2 flex items-center gap-2 text-[18px] font-semibold text-gray-700 dark:text-gray-200"
        >
          <ArrowLeft size={24} aria-hidden /> {t('twa.dispatch.back')}
        </button>
      )}

      {draft.step === 'phone' && <PhoneStep draft={draft} onDone={advance} />}
      {draft.step === 'address' && <AddressStep draft={draft} onPick={(address) => advance(withAddress(draft, address))} />}
      {draft.step === 'category' && <CategoryStep value={draft.category} onPick={(category) => advance({ category })} />}
      {draft.step === 'elevator' && (
        <ElevatorStep
          buildingId={draft.address?.buildingId ?? null}
          value={draft.elevator}
          onChange={(elevator) => setDraft((d) => ({ ...d, elevator }))}
          onNext={() => advance()}
          onBackToCategory={() => setDraft((d) => ({ ...d, step: 'category' }))}
          onBackToAddress={() => setDraft((d) => ({ ...d, step: 'address' }))}
        />
      )}
      {draft.step === 'description' && (
        <DescriptionStep value={draft.description} onDone={(description) => advance({ description })} />
      )}
      {draft.step === 'urgency' && <UrgencyStep value={draft.urgency} onPick={(urgency) => advance({ urgency })} />}
      {draft.step === 'review' && (
        <ReviewStep
          draft={draft}
          issues={visibleIssues}
          phase={phase}
          error={error}
          onEdit={edit}
          onFix={fix}
          onKeep={keep}
          onSubmit={submit}
        />
      )}
    </main>
  )
}
