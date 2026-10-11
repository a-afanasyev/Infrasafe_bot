import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  PRESETS,
  daysInRange,
  formatRange,
  isValidRange,
  type DateRange,
  type Granularity,
  type PresetId,
} from '../../utils/analyticsPeriod'

const GRANULARITIES: readonly Granularity[] = ['day', 'month', 'year']
/** Дневной срез длиннее года — сотни столбиков, график нечитаем. */
const DAY_SLICE_MAX_DAYS = 366

interface Props {
  preset: PresetId
  range: DateRange
  granularity: Granularity | null
  effectiveGranularity: Granularity
  onPreset: (preset: Exclude<PresetId, 'custom'>) => void
  onCustom: (range: DateRange) => void
  onGranularity: (granularity: Granularity | null) => void
  showGranularity: boolean
}

export default function PeriodBar({
  preset, range, granularity, effectiveGranularity, onPreset, onCustom, onGranularity, showGranularity,
}: Props) {
  const { t } = useTranslation()
  const valid = isValidRange(range)
  const days = valid ? daysInRange(range) : 0

  return (
    <div className="flex flex-col gap-2.5">
      <div className="flex flex-wrap items-center gap-2">
        {PRESETS.map(id => (
          <Button
            key={id}
            size="sm"
            variant={preset === id ? 'default' : 'outline'}
            className="rounded-full"
            onClick={() => onPreset(id)}
          >
            {t(`analytics.preset.${id}`)}
          </Button>
        ))}
        <div className="flex items-center gap-1.5">
          <Input
            type="date"
            aria-label={t('analytics.dateFrom')}
            value={range.from}
            max={range.to || undefined}
            onChange={e => onCustom({ from: e.target.value, to: range.to })}
            className="h-8 w-[150px]"
          />
          <span className="text-text-muted">—</span>
          <Input
            type="date"
            aria-label={t('analytics.dateTo')}
            value={range.to}
            min={range.from || undefined}
            onChange={e => onCustom({ from: range.from, to: e.target.value })}
            className="h-8 w-[150px]"
          />
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2 text-xs text-text-muted">
        {valid ? (
          <span className="font-[family-name:var(--font-mono)]">{formatRange(range)}</span>
        ) : (
          <span className="text-red">{t('analytics.invalidRange')}</span>
        )}
        {showGranularity && (
          <div className="flex items-center gap-1 ml-auto" role="group" aria-label={t('analytics.granularity')}>
            <span>{t('analytics.granularity')}:</span>
            <Button
              size="sm"
              variant={granularity === null ? 'default' : 'ghost'}
              className="h-7 px-2"
              onClick={() => onGranularity(null)}
            >
              {t('analytics.auto')} ({t(`analytics.gran.${effectiveGranularity}`)})
            </Button>
            {GRANULARITIES.map(g => (
              <Button
                key={g}
                size="sm"
                variant={granularity === g ? 'default' : 'ghost'}
                className="h-7 px-2"
                disabled={g === 'day' && days > DAY_SLICE_MAX_DAYS}
                onClick={() => onGranularity(g)}
              >
                {t(`analytics.gran.${g}`)}
              </Button>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
