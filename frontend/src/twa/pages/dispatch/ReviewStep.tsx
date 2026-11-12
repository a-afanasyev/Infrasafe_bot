import { useTranslation } from 'react-i18next'
import type { TFunction } from 'i18next'
import { AlertTriangle, Pencil } from 'lucide-react'
import { tCategory } from '../../../i18n/apiMaps'
import { PRIMARY_BTN, SECONDARY_BTN } from '../../simple/components/Ui'
import type { AddressOption, CheckIssue } from './api'
import type { Draft, Step } from './model'
import { TILE, tile } from './tiles'
import { Title } from './ui'

export type Phase = 'idle' | 'checking' | 'sending'

interface Props {
  draft: Draft
  issues: CheckIssue[]
  phase: Phase
  error: string | null
  onEdit: (step: Step) => void
  onFix: (issue: CheckIssue, option?: AddressOption) => void
  onKeep: (issue: CheckIssue) => void
  onSubmit: () => void
}

const urgencyLabel = (t: TFunction, urgency: string) => t(`twa.create.urgency.${urgency}`)

/** Текст замечания по коду сервера; незнакомый код — общий текст. */
function issueText(t: TFunction, issue: CheckIssue): string {
  const value =
    issue.field === 'category' && issue.suggestion
      ? tCategory(issue.suggestion, t)
      : issue.field === 'urgency' && issue.suggestion
        ? urgencyLabel(t, issue.suggestion)
        : undefined
  return t(`twa.dispatch.issue.${issue.code}`, { value, defaultValue: t('twa.dispatch.issue.generic') })
}

/** Сводка заявки: каждое поле можно поправить; замечания ИИ — совет у своего поля. */
export default function ReviewStep({ draft, issues, phase, error, onEdit, onFix, onKeep, onSubmit }: Props) {
  const { t } = useTranslation()
  const busy = phase !== 'idle'
  const flagged = new Set(issues.map((i) => i.field))
  const caller = draft.resident?.fullName ?? draft.callerName

  const rows: { step: Step; field?: CheckIssue['field']; label: string; value: string }[] = [
    { step: 'phone', label: t('twa.dispatch.review.caller'), value: [draft.phone, caller].filter(Boolean).join(' · ') },
    { step: 'address', field: 'address', label: t('twa.dispatch.review.address'), value: draft.address?.label ?? '' },
    { step: 'category', field: 'category', label: t('twa.dispatch.review.category'), value: tCategory(draft.category, t) },
    { step: 'description', field: 'description', label: t('twa.dispatch.review.description'), value: draft.description.trim() },
    { step: 'urgency', field: 'urgency', label: t('twa.dispatch.review.urgency'), value: urgencyLabel(t, draft.urgency) },
  ]

  return (
    <div className="flex flex-col gap-3">
      <Title>{t('twa.dispatch.review.title')}</Title>

      {/* Замечания — сразу под заголовком: после «Отправить» их видно без прокрутки. */}
      {issues.map((issue) => (
        <div
          key={issue.code}
          role="alert"
          className="rounded-2xl border-2 border-amber-500 bg-amber-50 dark:bg-amber-900/30 p-4 flex flex-col gap-3"
        >
          <p className="flex gap-3 text-[20px] font-semibold text-gray-900 dark:text-gray-50">
            <AlertTriangle size={28} className="shrink-0 text-amber-600" aria-hidden />
            {issueText(t, issue)}
          </p>
          {issue.options.map((o) => (
            <button key={`${o.type}-${o.id}`} type="button" disabled={busy} className={TILE} onClick={() => onFix(issue, o)}>
              {o.label}
            </button>
          ))}
          <div className="grid grid-cols-2 gap-2">
            {issue.options.length === 0 && (
              <button
                type="button"
                disabled={busy}
                className={`${SECONDARY_BTN} bg-emerald-600 text-white`}
                onClick={() => onFix(issue)}
              >
                {t('twa.dispatch.issue.fix')}
              </button>
            )}
            <button
              type="button"
              disabled={busy}
              className={`${SECONDARY_BTN} bg-gray-200 dark:bg-gray-700 text-gray-900 dark:text-gray-50 ${issue.options.length ? 'col-span-2' : ''}`}
              onClick={() => onKeep(issue)}
            >
              {t('twa.dispatch.issue.keep')}
            </button>
          </div>
        </div>
      ))}

      {rows.map((row) => (
        <button
          key={row.step}
          type="button"
          disabled={busy}
          onClick={() => onEdit(row.step)}
          aria-label={`${t('twa.dispatch.review.edit')}: ${row.label}`}
          className={`${tile(row.field && flagged.has(row.field) ? 'flagged' : 'plain')} flex items-center gap-3`}
        >
          <span className="flex-1 min-w-0">
            <span className="block text-[16px] font-normal text-gray-500 dark:text-gray-400">{row.label}</span>
            <span className="block break-words">{row.value}</span>
          </span>
          <Pencil size={24} className="shrink-0 text-gray-400" aria-hidden />
        </button>
      ))}

      {error && (
        <p role="alert" className="text-[18px] font-semibold text-red-600 dark:text-red-400">
          {error}
        </p>
      )}

      <button type="button" disabled={busy} onClick={onSubmit} className={`${PRIMARY_BTN} bg-emerald-600 text-white`}>
        {phase === 'checking'
          ? t('twa.dispatch.review.checking')
          : phase === 'sending'
            ? t('twa.dispatch.review.sending')
            : t(issues.length > 0 ? 'twa.dispatch.review.sendAnyway' : 'twa.dispatch.review.send')}
      </button>
    </div>
  )
}
