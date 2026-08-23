import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Trash2 } from 'lucide-react'
import { cn } from '@/lib/utils'
import { usePageTitle } from '../hooks/usePageTitle'
import {
  useMonitoredGroups,
  useCreateMonitoredGroup,
  useUpdateMonitoredGroup,
  useDeleteMonitoredGroup,
  type MonitoredGroup,
  type MonitoredGroupKind,
} from '../hooks/useMonitoredGroups'

const KINDS: MonitoredGroupKind[] = ['residents', 'staff']

function AddGroupForm() {
  const { t } = useTranslation()
  const create = useCreateMonitoredGroup()
  const [chatId, setChatId] = useState('')
  const [title, setTitle] = useState('')
  const [kind, setKind] = useState<MonitoredGroupKind>('residents')
  const [requireTag, setRequireTag] = useState(false)

  // Telegram supergroup id — отрицательное число вида -100XXXXXXXXXX
  const parsed = Number.parseInt(chatId.trim(), 10)
  const chatIdValid = chatId.trim() !== '' && Number.isSafeInteger(parsed)

  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!chatIdValid || create.isPending) return
    create.mutate(
      {
        chat_id: parsed,
        ...(title.trim() ? { title: title.trim() } : {}),
        kind,
        ...(requireTag ? { require_tag: true } : {}),
      },
      {
        onSuccess: () => {
          setChatId('')
          setTitle('')
          setKind('residents')
          setRequireTag(false)
        },
      },
    )
  }

  return (
    <form
      onSubmit={submit}
      className="rounded-lg border border-border-default bg-bg-card p-4 mb-4 flex flex-col gap-3"
    >
      <div className="text-[14px] font-semibold text-text-primary">{t('groups.addTitle')}</div>
      <div className="flex flex-col md:flex-row gap-3 md:items-end">
        <label className="flex flex-col gap-1 text-[13px] text-text-secondary">
          {t('groups.chatId')}
          <input
            value={chatId}
            onChange={(e) => setChatId(e.target.value)}
            placeholder="-1001234567890"
            inputMode="numeric"
            className="rounded-md border border-border-default bg-bg-surface px-3 py-2 text-[13px] text-text-primary w-full md:w-56"
          />
        </label>
        <label className="flex flex-col gap-1 text-[13px] text-text-secondary flex-1">
          {t('groups.groupTitle')}
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder={t('groups.groupTitlePlaceholder')}
            className="rounded-md border border-border-default bg-bg-surface px-3 py-2 text-[13px] text-text-primary w-full"
          />
        </label>
        <label className="flex flex-col gap-1 text-[13px] text-text-secondary">
          {t('groups.kind')}
          <select
            value={kind}
            onChange={(e) => setKind(e.target.value as MonitoredGroupKind)}
            className="rounded-md border border-border-default bg-bg-surface px-3 py-2 text-[13px] text-text-primary"
          >
            {KINDS.map((k) => (
              <option key={k} value={k}>
                {t(`groups.kind_${k}`)}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-2 text-[13px] text-text-secondary whitespace-nowrap pb-2">
          <input
            type="checkbox"
            checked={requireTag}
            onChange={(e) => setRequireTag(e.target.checked)}
            className="accent-[var(--accent)]"
          />
          {t('groups.requireTag')}
        </label>
        <button
          type="submit"
          disabled={!chatIdValid || create.isPending}
          className={cn(
            'rounded-md px-4 py-2 text-[13px] font-medium transition-colors',
            chatIdValid && !create.isPending
              ? 'bg-accent text-white hover:opacity-90'
              : 'bg-bg-surface text-text-secondary cursor-not-allowed',
          )}
        >
          {t('groups.add')}
        </button>
      </div>
      <div className="text-[12px] text-text-secondary">{t('groups.chatIdHint')}</div>
    </form>
  )
}

function GroupRow({ group }: { group: MonitoredGroup }) {
  const { t } = useTranslation()
  const update = useUpdateMonitoredGroup()
  const remove = useDeleteMonitoredGroup()
  // Удаление в два клика (без window.confirm): первый клик переводит кнопку в
  // состояние подтверждения, второй — удаляет.
  const [confirmDelete, setConfirmDelete] = useState(false)

  return (
    <tr className="border-t border-border-default">
      <td className="px-3 py-2 whitespace-nowrap font-mono text-text-primary">{group.chat_id}</td>
      <td className="px-3 py-2 max-w-[280px] truncate text-text-primary">{group.title || '—'}</td>
      <td className="px-3 py-2 whitespace-nowrap text-text-secondary">
        {t(`groups.kind_${group.kind}`)}
      </td>
      <td className="px-3 py-2">
        <button
          onClick={() =>
            update.mutate({ id: group.id, body: { require_tag: !group.require_tag } })
          }
          disabled={update.isPending}
          aria-label={t('groups.requireTagToggle')}
          className={cn(
            'px-2.5 py-1 rounded-full text-[11px] font-medium border transition-colors',
            group.require_tag
              ? 'bg-sky-100 text-sky-700 border-sky-200 dark:bg-sky-900/30 dark:text-sky-300 dark:border-sky-800'
              : 'bg-bg-surface text-text-secondary border-border-default',
          )}
        >
          {t(group.require_tag ? 'groups.requireTagOn' : 'groups.requireTagOff')}
        </button>
      </td>
      <td className="px-3 py-2">
        <button
          onClick={() =>
            update.mutate({ id: group.id, body: { is_active: !group.is_active } })
          }
          disabled={update.isPending}
          aria-label={t(group.is_active ? 'groups.deactivate' : 'groups.activate')}
          className={cn(
            'px-2.5 py-1 rounded-full text-[11px] font-medium border transition-colors',
            group.is_active
              ? 'bg-emerald-100 text-emerald-700 border-emerald-200 dark:bg-emerald-900/30 dark:text-emerald-300 dark:border-emerald-800'
              : 'bg-bg-surface text-text-secondary border-border-default',
          )}
        >
          {t(group.is_active ? 'groups.active' : 'groups.inactive')}
        </button>
      </td>
      <td className="px-3 py-2 text-right whitespace-nowrap">
        {confirmDelete ? (
          <span className="inline-flex items-center gap-2">
            <button
              onClick={() => remove.mutate(group.id)}
              disabled={remove.isPending}
              className="text-[12px] font-medium text-red-600 dark:text-red-400 hover:underline"
            >
              {t('groups.confirmDelete')}
            </button>
            <button
              onClick={() => setConfirmDelete(false)}
              className="text-[12px] text-text-secondary hover:underline"
            >
              {t('common.cancel')}
            </button>
          </span>
        ) : (
          <button
            onClick={() => setConfirmDelete(true)}
            aria-label={t('groups.delete')}
            className="text-text-secondary hover:text-red-600 dark:hover:text-red-400 transition-colors"
          >
            <Trash2 size={15} />
          </button>
        )}
      </td>
    </tr>
  )
}

export default function GroupsPage() {
  const { t } = useTranslation()
  usePageTitle(t('groups.title'))
  const { data, isLoading } = useMonitoredGroups()
  const items = data?.items ?? []

  return (
    <div className="p-4 md:p-6">
      <h1 className="text-xl font-bold text-text-primary mb-1">{t('groups.title')}</h1>
      <p className="text-[13px] text-text-secondary mb-4">{t('groups.subtitle')}</p>

      <AddGroupForm />

      {isLoading ? (
        <div className="text-text-secondary text-sm py-8 text-center">{t('common.loading')}</div>
      ) : items.length === 0 ? (
        <div className="text-text-secondary text-sm py-8 text-center">{t('groups.empty')}</div>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border-default">
          <table className="w-full text-[13px]">
            <thead className="bg-bg-surface text-text-secondary">
              <tr>
                <th className="text-left font-medium px-3 py-2">{t('groups.chatId')}</th>
                <th className="text-left font-medium px-3 py-2">{t('groups.groupTitle')}</th>
                <th className="text-left font-medium px-3 py-2">{t('groups.kind')}</th>
                <th className="text-left font-medium px-3 py-2">{t('groups.requireTagLabel')}</th>
                <th className="text-left font-medium px-3 py-2">{t('groups.statusLabel')}</th>
                <th className="px-3 py-2" />
              </tr>
            </thead>
            <tbody>
              {items.map((g) => (
                <GroupRow key={g.id} group={g} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
