import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'
import type { RbacRole } from '../../hooks/useRbac'

interface Props {
  roles: RbacRole[]
  selected: string | null
  onSelect: (key: string) => void
}

/** Список ролей: системные сверху, у каждой — число сотрудников и метка правок. */
export default function RoleList({ roles, selected, onSelect }: Props) {
  const { t } = useTranslation()
  return (
    <ul className="flex flex-col gap-1" aria-label={t('rbac.rolesList')}>
      {roles.map((role) => (
        <li key={role.key}>
          <button
            type="button"
            onClick={() => onSelect(role.key)}
            aria-current={selected === role.key ? 'true' : undefined}
            className={cn(
              'w-full text-left rounded-md border px-3 py-2 transition-colors',
              'focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent',
              selected === role.key
                ? 'border-accent bg-accent/10'
                : 'border-border-default bg-bg-card hover:bg-bg-surface',
            )}
          >
            <div className="flex items-center justify-between gap-2">
              <span className="text-[13px] font-semibold text-text-primary truncate">{role.title}</span>
              <span className="text-[11px] text-text-muted shrink-0 tabular-nums">
                {t('rbac.usersCount', { count: role.users_count })}
              </span>
            </div>
            <div className="flex items-center gap-1.5 mt-1">
              <code className="text-[11px] text-text-muted">{role.key}</code>
              <span
                className={cn(
                  'text-[10px] px-1.5 py-px rounded-full border',
                  role.is_system
                    ? 'border-border-default text-text-muted'
                    : 'border-accent/40 text-accent',
                )}
              >
                {role.is_system ? t('rbac.system') : t('rbac.custom')}
              </span>
              {role.customized.length > 0 && (
                <span className="text-[10px] px-1.5 py-px rounded-full bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300">
                  {t('rbac.changedCount', { count: role.customized.length })}
                </span>
              )}
            </div>
          </button>
        </li>
      ))}
    </ul>
  )
}
