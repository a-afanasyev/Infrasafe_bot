import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  useFeedbackList,
  type FeedbackFilters,
  type FeedbackStatus,
  type FeedbackType,
} from '../hooks/useFeedback'
import FeedbackDetailModal from '../components/feedback/FeedbackDetailModal'
import { cn } from '@/lib/utils'
import { Paperclip } from 'lucide-react'
import { usePageTitle } from '../hooks/usePageTitle'

const TYPE_FILTERS: (FeedbackType | 'all')[] = ['all', 'complaint', 'wish']
const STATUS_FILTERS: (FeedbackStatus | 'all')[] = ['all', 'new', 'in_review', 'resolved']

const STATUS_CLASS: Record<FeedbackStatus, string> = {
  new: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300',
  in_review: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300',
  resolved: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300',
}

function FilterRow<T extends string>({
  label, options, value, onChange, render,
}: {
  label: string
  options: T[]
  value: T
  onChange: (v: T) => void
  render: (v: T) => string
}) {
  return (
    <div className="flex items-center gap-2 flex-wrap">
      <span className="text-[13px] text-text-secondary">{label}:</span>
      {options.map((o) => (
        <button
          key={o}
          onClick={() => onChange(o)}
          className={cn(
            'px-3 py-1 rounded-full text-[12px] font-medium border transition-colors',
            value === o
              ? 'bg-accent text-white border-accent'
              : 'bg-bg-card border-border-default text-text-secondary hover:bg-bg-surface',
          )}
        >
          {render(o)}
        </button>
      ))}
    </div>
  )
}

export default function FeedbackPage() {
  const { t } = useTranslation()
  usePageTitle(t('feedback.title')) // QA-03: иначе document.title оставался от предыдущей страницы
  const [typeFilter, setTypeFilter] = useState<FeedbackType | 'all'>('all')
  const [statusFilter, setStatusFilter] = useState<FeedbackStatus | 'all'>('all')
  const [openId, setOpenId] = useState<number | null>(null)

  const filters: FeedbackFilters = {
    ...(typeFilter !== 'all' ? { type: typeFilter } : {}),
    ...(statusFilter !== 'all' ? { status: statusFilter } : {}),
  }
  const { data, isLoading } = useFeedbackList(filters)
  const items = data?.items ?? []

  return (
    <div className="p-4 md:p-6">
      <h1 className="text-xl font-bold text-text-primary mb-4">{t('feedback.title')}</h1>

      <div className="flex flex-col gap-2 mb-4">
        <FilterRow
          label={t('feedback.filterType')}
          options={TYPE_FILTERS}
          value={typeFilter}
          onChange={setTypeFilter}
          render={(o) => (o === 'all' ? t('feedback.all') : t(`feedback.${o}`))}
        />
        <FilterRow
          label={t('feedback.filterStatus')}
          options={STATUS_FILTERS}
          value={statusFilter}
          onChange={setStatusFilter}
          render={(o) => (o === 'all' ? t('feedback.all') : t(`feedback.${o}`))}
        />
      </div>

      {isLoading ? (
        <div className="text-text-secondary text-sm py-8 text-center">{t('common.loading')}</div>
      ) : items.length === 0 ? (
        <div className="text-text-secondary text-sm py-8 text-center">{t('feedback.empty')}</div>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border-default">
          <table className="w-full text-[13px]">
            <thead className="bg-bg-surface text-text-secondary">
              <tr>
                <th className="text-left font-medium px-3 py-2">{t('feedback.type')}</th>
                <th className="text-left font-medium px-3 py-2">{t('feedback.statusLabel')}</th>
                <th className="text-left font-medium px-3 py-2">{t('feedback.message')}</th>
                <th className="text-left font-medium px-3 py-2">{t('feedback.author')}</th>
              </tr>
            </thead>
            <tbody>
              {items.map((it) => (
                <tr
                  key={it.id}
                  role="button"
                  tabIndex={0}
                  onClick={() => setOpenId(it.id)}
                  onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setOpenId(it.id) } }}
                  className="border-t border-border-default hover:bg-bg-surface cursor-pointer focus:outline-none focus:bg-bg-surface"
                >
                  <td className="px-3 py-2 whitespace-nowrap">{t(`feedback.${it.type}`)}</td>
                  <td className="px-3 py-2">
                    <span className={cn('px-2 py-0.5 rounded-full text-[11px] font-medium', STATUS_CLASS[it.status])}>
                      {t(`feedback.${it.status}`)}
                    </span>
                  </td>
                  <td className="px-3 py-2 max-w-[320px]">
                    <span className="flex items-center gap-1.5">
                      {it.has_media && <Paperclip size={12} className="text-text-secondary shrink-0" />}
                      <span className="truncate text-text-primary">{it.text}</span>
                    </span>
                  </td>
                  <td className="px-3 py-2 whitespace-nowrap text-text-secondary">{it.author_name || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {openId != null && <FeedbackDetailModal feedbackId={openId} onClose={() => setOpenId(null)} />}
    </div>
  )
}
