import { useCallback, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import LoadingSpinner from '../components/shared/LoadingSpinner'
import RoleList from '../components/rbac/RoleList'
import RoleEditor from '../components/rbac/RoleEditor'
import CreateRoleForm from '../components/rbac/CreateRoleForm'
import { usePageTitle } from '../hooks/usePageTitle'
import { useRbacCatalog, useRbacRoles } from '../hooks/useRbac'

/**
 * «Роли и права». Суперадмин (ADMIN_USER_IDS) создаёт роли и меняет их права;
 * менеджер и другие с правом rbac.view видят всё только для чтения. Решает
 * сервер: can_edit приходит из API, а не из догадок интерфейса.
 */
export default function RolesPage() {
  const { t } = useTranslation()
  usePageTitle(t('rbac.title'))
  const roles = useRbacRoles()
  const catalog = useRbacCatalog()
  const [selected, setSelected] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  const [dirty, setDirty] = useState(false)
  // Выбрана другая роль, пока в текущей есть несохранённые правки.
  const [pending, setPending] = useState<string | null>(null)
  const onDirtyChange = useCallback((value: boolean) => setDirty(value), [])

  if (roles.isLoading || catalog.isLoading) return <LoadingSpinner />
  if (roles.isError || catalog.isError || !roles.data || !catalog.data) {
    return <div className="py-10 px-6 text-text-muted text-center">{t('rbac.loadFailed')}</div>
  }

  const { roles: list, can_edit: canEdit } = roles.data
  const current = list.find((r) => r.key === selected) ?? list[0]

  const select = (key: string) => {
    if (key === current?.key) return
    if (dirty) setPending(key)
    else setSelected(key)
  }
  const leave = (key: string) => {
    setPending(null)
    setDirty(false)
    setSelected(key)
  }

  return (
    <div className="p-5 px-6 flex flex-col gap-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-[18px] font-semibold text-text-primary">{t('rbac.title')}</h1>
          <p className="text-[12px] text-text-muted max-w-[640px]">{t('rbac.subtitle')}</p>
          <p className="text-[11px] text-text-muted max-w-[640px] mt-1">{t('rbac.scopeNote')}</p>
        </div>
        {canEdit && !creating && <Button onClick={() => setCreating(true)}>{t('rbac.newRole')}</Button>}
      </div>

      {!canEdit && (
        <div role="note" className="rounded-md border border-border-default bg-bg-surface px-3 py-2 text-[12px] text-text-secondary">
          {t('rbac.readOnly')}
        </div>
      )}

      <div className="grid gap-4 md:grid-cols-[280px_1fr] items-start">
        <div className="flex flex-col gap-3 md:sticky md:top-4">
          {creating && (
            <CreateRoleForm
              roles={list}
              onCancel={() => setCreating(false)}
              onCreated={(key) => {
                setCreating(false)
                leave(key)
              }}
            />
          )}
          <RoleList roles={list} selected={current?.key ?? null} onSelect={select} />
        </div>
        {current && (
          <div className="flex flex-col gap-3 min-w-0">
            {pending && (
              <div
                role="alert"
                className="flex flex-wrap items-center gap-2 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-[12px] text-amber-800 dark:border-amber-700 dark:bg-amber-900/30 dark:text-amber-200"
              >
                <span className="flex-1 min-w-[200px]">{t('rbac.unsavedSwitch', { role: current.title })}</span>
                <Button size="sm" variant="outline" onClick={() => leave(pending)}>
                  {t('rbac.discardAndGo')}
                </Button>
                <Button size="sm" onClick={() => setPending(null)}>
                  {t('rbac.stay')}
                </Button>
              </div>
            )}
            {/* key: при выборе другой роли состояние редактора начинается заново. */}
            <RoleEditor
              key={`${current.key}:${current.actions.join(',')}:${current.title}`}
              role={current}
              catalog={catalog.data}
              canEdit={canEdit}
              onDirtyChange={onDirtyChange}
            />
          </div>
        )}
      </div>
    </div>
  )
}
