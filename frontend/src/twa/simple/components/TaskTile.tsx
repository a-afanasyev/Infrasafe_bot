import { useRef, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import {
  ArrowUpDown, Camera, Clock, Droplet, Flame, Hammer, HelpCircle, Hourglass, KeyRound, Shield, Sparkles,
  Trees, Undo2, Wifi, Wind, Zap, type LucideIcon,
} from 'lucide-react'
import { CATEGORY_MAP, type ApiCategory } from '../../../i18n/apiMaps'
import { isUrgent, urgencyStripClass, type TileState } from '../model'
import { AuthPhoto } from './Photo'
import { useResidentPhotoId } from '../hooks/useResidentPhoto'
import { useInView } from '../hooks/useLazyMedia'

const CATEGORY_ICON: Record<string, LucideIcon> = {
  'category.electrical': Zap,
  'category.plumbing': Droplet,
  'category.heating': Flame,
  'category.ventilation': Wind,
  'category.elevator': ArrowUpDown,
  'category.cleaning': Sparkles,
  'category.landscaping': Trees,
  'category.security': Shield,
  'category.internet_tv': Wifi,
  'category.repair': Hammer,
}

export function CategoryIcon({ category, size }: { category: string; size: number }) {
  const Icon = CATEGORY_ICON[CATEGORY_MAP[category as ApiCategory] ?? ''] ?? HelpCircle
  return <Icon size={size} aria-hidden />
}

const RED = 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300'
const GRAY = 'bg-gray-200 text-gray-700 dark:bg-gray-700 dark:text-gray-200'

const STATE_STYLE: Record<TileState, { icon: LucideIcon; className: string; key: string }> = {
  inWork: { icon: KeyRound, className: 'bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-300', key: 'twa.simple.status.inWork' },
  returned: { icon: Undo2, className: RED, key: 'twa.simple.status.returned' },
  retake: { icon: Camera, className: RED, key: 'twa.simple.status.retake' },
  waiting: { icon: Hourglass, className: GRAY, key: 'twa.simple.waitManager' },
  pending: { icon: Clock, className: GRAY, key: 'twa.simple.status.pending' },
}

/** Статус тремя каналами: цвет + иконка + слово. */
export function StateChip({ state }: { state: TileState }) {
  const { t } = useTranslation()
  const { icon: Icon, className, key } = STATE_STYLE[state]
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-[16px] font-semibold ${className}`}>
      <Icon size={18} aria-hidden /> {t(key)}
    </span>
  )
}

/** Срочная/критическая — огонь рядом со статусом (вдобавок к полосе). */
export function UrgentMark({ urgency }: { urgency?: string | null }) {
  const { t } = useTranslation()
  if (!isUrgent(urgency)) return null
  return (
    <span role="img" aria-label={t('twa.simple.urgent')} className="inline-flex text-red-600 dark:text-red-400">
      <Flame size={24} fill="currentColor" aria-hidden />
    </span>
  )
}

interface Props {
  requestNumber: string
  category: string
  address: string
  text: string
  urgency?: string | null
  state?: TileState
  reason?: string | null
  /** undefined — искать фото в медиа заявки; null — фото нет. */
  photoMediaId?: number | null
  onOpen?: () => void
  action?: ReactNode
}

/** Плитка заявки: фото/иконка, адрес крупно, одна строка текста, полоса срочности. */
export default function TaskTile({ requestNumber, category, address, text, urgency, state, reason, photoMediaId, onOpen, action }: Props) {
  const { t } = useTranslation()
  const ref = useRef<HTMLLIElement>(null)
  const visible = useInView(ref)
  const photoId = useResidentPhotoId(requestNumber, photoMediaId, visible)
  const strip = urgencyStripClass(urgency)
  const icon = (
    <div className="w-20 h-20 rounded-xl bg-gray-100 dark:bg-gray-700 text-gray-500 dark:text-gray-300 flex items-center justify-center shrink-0">
      <CategoryIcon category={category} size={40} />
    </div>
  )
  const body = (
    <div className="flex gap-3 items-start">
      {photoId != null ? (
        <AuthPhoto
          mediaId={photoId}
          enabled={visible}
          alt={t('twa.simple.task.photoAlt')}
          className="w-20 h-20 rounded-xl object-cover shrink-0"
          fallback={icon}
        />
      ) : icon}
      <div className="min-w-0 flex-1">
        {(state || isUrgent(urgency)) && (
          <div className="flex items-center gap-2 flex-wrap">
            {state && <StateChip state={state} />}
            <UrgentMark urgency={urgency} />
          </div>
        )}
        <p className="mt-1 text-[24px] font-bold leading-tight text-gray-900 dark:text-gray-50 break-words">{address}</p>
        {text && <p className="mt-1 text-[18px] text-gray-700 dark:text-gray-300 truncate">{text}</p>}
        {state === 'returned' && reason && (
          <p className="mt-1 text-[18px] font-semibold text-red-700 dark:text-red-400 break-words">{reason}</p>
        )}
      </div>
    </div>
  )
  return (
    <li
      ref={ref}
      data-testid={`tile-${requestNumber}`}
      className="relative list-none min-h-[120px] rounded-2xl bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 overflow-hidden"
    >
      {strip && <span aria-hidden className={`absolute left-0 top-0 bottom-0 w-2 ${strip}`} />}
      <div className="p-3 pl-5">
        {onOpen ? (
          <button type="button" onClick={onOpen} className="w-full text-left active:opacity-70">{body}</button>
        ) : body}
        {action && <div className="mt-3">{action}</div>}
      </div>
    </li>
  )
}
