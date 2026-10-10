import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import { useCreateRole, type RbacRole } from '../../hooks/useRbac'

const KEY_PATTERN = /^[a-z][a-z0-9_]{2,31}$/

interface Props {
  roles: RbacRole[]
  onCreated: (key: string) => void
  onCancel: () => void
}

/** Новая роль: ключ, название и права «как у» выбранной роли (или пустые). */
export default function CreateRoleForm({ roles, onCreated, onCancel }: Props) {
  const { t } = useTranslation()
  const create = useCreateRole()
  const [key, setKey] = useState('')
  const [title, setTitle] = useState('')
  const [copyFrom, setCopyFrom] = useState('')

  const keyValid = KEY_PATTERN.test(key)
  const taken = roles.some((r) => r.key === key)
  const canSubmit = keyValid && !taken && title.trim() !== '' && !create.isPending

  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!canSubmit) return
    const actions = roles.find((r) => r.key === copyFrom)?.actions ?? []
    create.mutate({ key, title: title.trim(), actions }, { onSuccess: () => onCreated(key) })
  }

  return (
    <form onSubmit={submit} className="rounded-md border border-border-default bg-bg-card p-4 flex flex-col gap-3">
      <div className="text-[14px] font-semibold text-text-primary">{t('rbac.newRole')}</div>
      <label className="flex flex-col gap-1 text-[12px] text-text-secondary">
        {t('rbac.roleTitle')}
        <input
          id="rbac-new-title"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          maxLength={100}
          placeholder={t('rbac.roleTitlePlaceholder')}
          className="rounded-md border border-border-default bg-bg-surface px-3 py-2 text-[13px] text-text-primary"
        />
      </label>
      <label className="flex flex-col gap-1 text-[12px] text-text-secondary">
        {t('rbac.roleKey')}
        <input
          id="rbac-new-key"
          value={key}
          onChange={(e) => setKey(e.target.value.toLowerCase())}
          placeholder="senior_executor"
          className="rounded-md border border-border-default bg-bg-surface px-3 py-2 text-[13px] font-mono text-text-primary"
        />
        <span className={key && (!keyValid || taken) ? 'text-red-600' : 'text-text-muted'}>
          {taken ? t('rbac.keyTaken') : t('rbac.keyHint')}
        </span>
      </label>
      <label className="flex flex-col gap-1 text-[12px] text-text-secondary">
        {t('rbac.copyFrom')}
        <select
          id="rbac-new-copy"
          value={copyFrom}
          onChange={(e) => setCopyFrom(e.target.value)}
          className="rounded-md border border-border-default bg-bg-surface px-3 py-2 text-[13px] text-text-primary"
        >
          <option value="">{t('rbac.copyNone')}</option>
          {roles.map((r) => (
            <option key={r.key} value={r.key}>
              {r.title}
            </option>
          ))}
        </select>
      </label>
      <div className="flex gap-2">
        <Button type="submit" disabled={!canSubmit}>
          {t('rbac.create')}
        </Button>
        <Button type="button" variant="outline" onClick={onCancel}>
          {t('common.cancel')}
        </Button>
      </div>
    </form>
  )
}
