import { useTranslation } from 'react-i18next'
import { ChevronDown } from 'lucide-react'
import { cn } from '@/lib/utils'
import { tStatus } from '../../i18n/apiMaps'
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
} from '@/components/ui/dropdown-menu'
import { VALID_TRANSITIONS, FROZEN_STATUSES } from './transitions'
import { STATUS_DOT } from './statusStyles'

export default function StatusDropdown({
  status,
  statusStyle,
  onSelect,
}: {
  status: string
  statusStyle: { bg: string; text: string }
  onSelect: (targetStatus: string) => void
}) {
  const { t } = useTranslation()
  const frozen = FROZEN_STATUSES.has(status)
  const transitions = VALID_TRANSITIONS[status]
  const hasTransitions = transitions && transitions.size > 0

  // Frozen or no transitions — static badge
  if (frozen || !hasTransitions) {
    return (
      <span className={cn(
        'text-xs font-semibold px-2.5 py-1 rounded-full font-[family-name:var(--font-display)]',
        statusStyle.bg, statusStyle.text
      )}>
        {tStatus(status, t)}
      </span>
    )
  }

  const items = Array.from(transitions)
  const cancelIdx = items.indexOf('Отменена')

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button className={cn(
          'inline-flex items-center gap-1 text-xs font-semibold px-2.5 py-1 rounded-full font-[family-name:var(--font-display)] transition-colors cursor-pointer',
          'hover:ring-2 hover:ring-offset-1 hover:ring-offset-bg-card',
          statusStyle.bg, statusStyle.text,
          // ring color matches status
          status === 'Новая' && 'hover:ring-[#60a5fa]/40',
          status === 'В работе' && 'hover:ring-[#fbbf24]/40',
          status === 'Закуп' && 'hover:ring-[#a78bfa]/40',
          status === 'Уточнение' && 'hover:ring-[#22d3ee]/40',
          status === 'Выполнена' && 'hover:ring-[#34d399]/40',
          status === 'Исполнено' && 'hover:ring-accent/40',
        )}>
          {tStatus(status, t)}
          <ChevronDown className="w-3 h-3 opacity-60" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" sideOffset={6} className="min-w-[180px]">
        {items.map((targetStatus) => (
          <span key={targetStatus}>
            {/* Separator before Отменена */}
            {targetStatus === 'Отменена' && cancelIdx > 0 && <DropdownMenuSeparator />}
            <DropdownMenuItem
              onClick={() => onSelect(targetStatus)}
              variant={targetStatus === 'Отменена' ? 'destructive' : 'default'}
              className="gap-2.5 py-2 px-2.5"
            >
              <span className={cn(
                'w-2 h-2 rounded-full shrink-0',
                STATUS_DOT[targetStatus as keyof typeof STATUS_DOT] ?? 'bg-text-muted'
              )} />
              <span className="font-[family-name:var(--font-display)] font-semibold text-[13px]">
                {tStatus(targetStatus, t)}
              </span>
            </DropdownMenuItem>
          </span>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
