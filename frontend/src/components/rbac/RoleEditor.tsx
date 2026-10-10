import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import {
  useDeleteRole,
  useResetRole,
  useUpdateRole,
  type RbacAction,
  type RbacRole,
} from '../../hooks/useRbac'

interface Props {
  role: RbacRole
  catalog: RbacAction[]
  canEdit: boolean
}

/**
 * Права одной роли по областям. Суперадмин отмечает действия и сохраняет;
 * остальные видят то же самое только для чтения. Действия «только
 * суперадмин» здесь не показываются — ролям они не выдаются.
 */
export default function RoleEditor({ role, catalog, canEdit }: Props) {
  const { t } = useTranslation()
  const update = useUpdateRole()
  const reset = useResetRole()
  const remove = useDeleteRole()
  const [chosen, setChosen] = useState<Set<string>>(() => new Set(role.actions))
  const [title, setTitle] = useState(role.title)
  const [confirmDelete, setConfirmDelete] = useState(false)

  const groups = useMemo(() => {
    const byArea = new Map<string, RbacAction[]>()
    for (const action of catalog) {
      if (action.superadmin_only) continue
      byArea.set(action.area, [...(byArea.get(action.area) ?? []), action])
    }
    return [...byArea.entries()]
  }, [catalog])

  const dirty =
    title.trim() !== role.title ||
    chosen.size !== role.actions.length ||
    role.actions.some((a) => !chosen.has(a))

  const toggle = (key: string) =>
    setChosen((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })

  const save = () =>
    update.mutate({ key: role.key, title: title.trim(), actions: [...chosen].sort() })

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-2">
        {canEdit ? (
          <input
            id={`rbac-title-${role.key}`}
            aria-label={t('rbac.roleTitle')}
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            maxLength={100}
            className="rounded-md border border-border-default bg-bg-surface px-3 py-2 text-[15px] font-semibold text-text-primary"
          />
        ) : (
          <h2 className="text-[15px] font-semibold text-text-primary">{role.title}</h2>
        )}
        <div className="text-[12px] text-text-muted">
          <code>{role.key}</code>
          {role.description ? ` · ${role.description}` : ''}
          {' · '}
          {t('rbac.actionsCount', { count: chosen.size })}
        </div>
      </div>

      {groups.map(([area, actions]) => (
        <fieldset key={area} className="rounded-md border border-border-default bg-bg-card">
          <legend className="px-2 ml-2 text-[12px] font-semibold text-text-secondary">{area}</legend>
          <div className="flex flex-col divide-y divide-border-default">
            {actions.map((action) => {
              const isDefault = action.default_roles.includes(role.key)
              const on = chosen.has(action.key)
              const changed = role.is_system && on !== isDefault
              return (
                <label
                  key={action.key}
                  className={cn(
                    'flex items-start gap-3 px-3 py-2 text-[13px]',
                    canEdit ? 'cursor-pointer hover:bg-bg-surface' : 'cursor-default',
                  )}
                >
                  <input
                    type="checkbox"
                    checked={on}
                    disabled={!canEdit}
                    onChange={() => toggle(action.key)}
                    className="mt-0.5 accent-[var(--accent)]"
                  />
                  <span className="min-w-0 flex-1">
                    <span className="text-text-primary">{action.title}</span>
                    <span className="block text-[11px] text-text-muted">
                      <code>{action.key}</code>
                      {action.approved_only && ` · ${t('rbac.approvedOnly')}`}
                      {changed && (
                        <span className="text-amber-700 dark:text-amber-300">
                          {' · '}
                          {isDefault ? t('rbac.removedFromDefault') : t('rbac.addedToDefault')}
                        </span>
                      )}
                    </span>
                  </span>
                </label>
              )
            })}
          </div>
        </fieldset>
      ))}

      {canEdit && (
        <div className="flex flex-wrap gap-2 sticky bottom-0 bg-bg-root py-3">
          <Button onClick={save} disabled={!dirty || !title.trim() || update.isPending}>
            {t('rbac.save')}
          </Button>
          {role.is_system && role.customized.length > 0 && (
            <Button variant="outline" onClick={() => reset.mutate(role.key)} disabled={reset.isPending}>
              {t('rbac.reset')}
            </Button>
          )}
          {!role.is_system && (
            <Button
              variant="outline"
              disabled={remove.isPending}
              onClick={() => (confirmDelete ? remove.mutate(role.key) : setConfirmDelete(true))}
              className={confirmDelete ? 'border-red-500 text-red-600' : undefined}
            >
              {confirmDelete ? t('rbac.deleteConfirm') : t('rbac.delete')}
            </Button>
          )}
        </div>
      )}
    </div>
  )
}
