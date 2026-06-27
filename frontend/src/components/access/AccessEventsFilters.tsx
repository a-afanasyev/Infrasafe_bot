import { useTranslation } from 'react-i18next'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import { Button } from '@/components/ui/button'
import type { AccessEventsFilters as Filters } from '../../types/access'

/**
 * Панель фильтров истории событий (номер, решение, период, и опц. зона/источник
 * для менеджера). Меняет родительский объект фильтров — родитель обнуляет offset
 * и перезапрашивает.
 */
interface Props {
  filters: Filters
  onChange: (patch: Partial<Filters>) => void
  /** Показать расширенные фильтры менеджера (зона, источник). */
  extended?: boolean
}

// Канонические решения движка (DATA_MODEL_PILOT) — фолбэк-перевод в badge.
const DECISIONS = ['allow', 'deny', 'manual_review'] as const

export default function AccessEventsFilters({ filters, onChange, extended }: Props) {
  const { t } = useTranslation()

  return (
    <div className="flex flex-wrap items-end gap-2">
      <label className="flex flex-col gap-1 text-[11px] text-text-muted">
        {t('accessControl.columns.plate')}
        <Input
          type="text"
          value={filters.plate ?? ''}
          onChange={(e) => onChange({ plate: e.target.value || undefined })}
          placeholder={t('accessControl.filters.platePlaceholder')}
          className="w-[160px]"
        />
      </label>

      <label className="flex flex-col gap-1 text-[11px] text-text-muted">
        {t('accessControl.columns.decision')}
        <Select
          value={filters.decision ?? ''}
          onChange={(e) => onChange({ decision: e.target.value || undefined })}
          className="w-[150px]"
        >
          <option value="">{t('accessControl.filters.allDecisions')}</option>
          {DECISIONS.map((d) => (
            <option key={d} value={d}>
              {t(`accessControl.decision.${d}`, { defaultValue: d })}
            </option>
          ))}
        </Select>
      </label>

      <label className="flex flex-col gap-1 text-[11px] text-text-muted">
        {t('accessControl.filters.dateFrom')}
        <Input
          type="date"
          value={filters.date_from ?? ''}
          onChange={(e) => onChange({ date_from: e.target.value || undefined })}
          className="w-[150px]"
        />
      </label>

      <label className="flex flex-col gap-1 text-[11px] text-text-muted">
        {t('accessControl.filters.dateTo')}
        <Input
          type="date"
          value={filters.date_to ?? ''}
          onChange={(e) => onChange({ date_to: e.target.value || undefined })}
          className="w-[150px]"
        />
      </label>

      {extended && (
        <>
          <label className="flex flex-col gap-1 text-[11px] text-text-muted">
            {t('accessControl.zone')}
            <Input
              type="number"
              value={filters.zone_id ?? ''}
              onChange={(e) =>
                onChange({ zone_id: e.target.value ? Number(e.target.value) : undefined })
              }
              className="w-[100px]"
            />
          </label>
          <label className="flex flex-col gap-1 text-[11px] text-text-muted">
            {t('accessControl.columns.source')}
            <Input
              type="text"
              value={filters.source ?? ''}
              onChange={(e) => onChange({ source: e.target.value || undefined })}
              className="w-[130px]"
            />
          </label>
        </>
      )}

      <Button
        variant="outline"
        size="sm"
        onClick={() =>
          onChange({
            plate: undefined,
            decision: undefined,
            date_from: undefined,
            date_to: undefined,
            zone_id: undefined,
            source: undefined,
          })
        }
      >
        {t('accessControl.filters.reset')}
      </Button>
    </div>
  )
}
