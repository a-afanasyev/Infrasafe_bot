import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import { useRbacRoles, useSetUserRoles, useUserRoles } from '../../hooks/useRbac'

interface Props {
  employeeId: number
}

/**
 * Роли сотрудника. Менять может только суперадмин (can_edit от сервера);
 * менеджер видит набор без кнопок. Роль суперадмина здесь не выдаётся —
 * она задаётся в ADMIN_USER_IDS.
 */
export default function RolesSection({ employeeId }: Props) {
  const { t } = useTranslation()
  const userRoles = useUserRoles(employeeId)
  const roles = useRbacRoles()
  const setRoles = useSetUserRoles(employeeId)
  const [draft, setDraft] = useState<Set<string> | null>(null)

  if (userRoles.isLoading || roles.isLoading) return null
  if (!userRoles.data || !roles.data) return null

  const current = new Set(userRoles.data.roles)
  const chosen = draft ?? current
  const canEdit = userRoles.data.can_edit
  const dirty = draft !== null && (draft.size !== current.size || [...draft].some((r) => !current.has(r)))

  const toggle = (key: string) => {
    const next = new Set(chosen)
    if (next.has(key)) next.delete(key)
    else next.add(key)
    setDraft(next)
  }

  return (
    <section
      aria-labelledby="employee-roles-title"
      className="bg-bg-card border border-border-default rounded-default p-5 flex flex-col gap-3"
    >
      <div className="flex items-center justify-between gap-3">
        <div>
          <div id="employee-roles-title" className="text-[13px] font-semibold text-text-primary">
            {t('rbac.employeeRoles')}
          </div>
          <div className="text-[11px] text-text-muted mt-0.5">
            {canEdit ? t('rbac.employeeRolesHint') : t('rbac.employeeRolesReadOnly')}
          </div>
        </div>
        {userRoles.data.is_superadmin && (
          <span className="text-[11px] px-2 py-0.5 rounded-full border border-accent/40 text-accent">
            {t('rbac.superadmin')}
          </span>
        )}
      </div>
      <div className="flex flex-wrap gap-2">
        {roles.data.roles.map((role) => {
          const on = chosen.has(role.key)
          return (
            <label
              key={role.key}
              className={`flex items-center gap-2 rounded-md border px-2.5 py-1.5 text-[12px] ${
                on ? 'border-accent bg-accent/10 text-text-primary' : 'border-border-default text-text-secondary'
              } ${canEdit ? 'cursor-pointer' : 'cursor-default'}`}
            >
              <input
                type="checkbox"
                checked={on}
                disabled={!canEdit}
                onChange={() => toggle(role.key)}
                className="accent-[var(--accent)]"
              />
              {role.title}
            </label>
          )
        })}
      </div>
      {canEdit && (
        <div className="flex gap-2">
          <Button
            size="sm"
            disabled={!dirty || chosen.size === 0 || setRoles.isPending}
            onClick={() => setRoles.mutate([...chosen], { onSuccess: () => setDraft(null) })}
          >
            {t('rbac.save')}
          </Button>
          {dirty && (
            <Button size="sm" variant="outline" onClick={() => setDraft(null)}>
              {t('common.cancel')}
            </Button>
          )}
        </div>
      )}
    </section>
  )
}
