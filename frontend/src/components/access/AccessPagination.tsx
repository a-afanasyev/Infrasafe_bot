import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'

/**
 * Пагинация по конверту `{total, limit, offset}` access-API.
 * Стрелки prev/next + «N–M из T». Кнопки гасятся на краях диапазона.
 */
interface Props {
  total: number
  limit: number
  offset: number
  onOffsetChange: (offset: number) => void
}

export default function AccessPagination({ total, limit, offset, onOffsetChange }: Props) {
  const { t } = useTranslation()
  if (total === 0) return null

  const from = offset + 1
  const to = Math.min(offset + limit, total)
  const canPrev = offset > 0
  const canNext = to < total

  return (
    <div className="flex items-center justify-end gap-3 text-[13px] text-text-muted">
      <span>{t('accessControl.pagination.range', { from, to, total })}</span>
      <div className="flex items-center gap-1.5">
        <Button
          variant="outline"
          size="sm"
          disabled={!canPrev}
          onClick={() => onOffsetChange(Math.max(0, offset - limit))}
        >
          ←
        </Button>
        <Button
          variant="outline"
          size="sm"
          disabled={!canNext}
          onClick={() => onOffsetChange(offset + limit)}
        >
          →
        </Button>
      </div>
    </div>
  )
}
