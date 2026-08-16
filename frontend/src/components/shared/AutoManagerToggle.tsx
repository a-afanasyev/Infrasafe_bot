import { useTranslation } from 'react-i18next'
import { useAutoManagerConfig, useUpdateAutoManagerConfig } from '../../hooks/useAutoManagerConfig'

// Строка-тумблер «автоматический менеджер включён/выключен». Вынесена из
// AutoManagerCard (раздел дежурств), чтобы тот же контрол стоял в топбаре
// канбана: выключать автораздачу заявок логично там, где на заявки и смотрят.
//
// Обе копии читают один queryKey ['auto-manager-config'], поэтому переключение
// в одном месте немедленно отражается в другом — отдельная синхронизация не
// нужна.
//
// При загрузке и при ошибке рендерим null: в шапке доски тумблер в неизвестном
// состоянии хуже отсутствующего — по нему нельзя понять, раздаются заявки или
// нет. Заодно это гасит 403 у роли без доступа к конфигу.
export default function AutoManagerToggle() {
  const { t } = useTranslation()
  const { data, isLoading, isError } = useAutoManagerConfig()
  const updateConfig = useUpdateAutoManagerConfig()

  if (isLoading || isError || !data) return null

  // Патч, не полный объект: мутация сама перезапрашивает актуальный конфиг
  // перед записью и мёржит патч поверх него (см. useAutoManagerConfig.ts) —
  // иначе полный объект из старого рендера затёр бы поля, изменённые ботом.
  const handleToggleEnabled = () => {
    updateConfig.mutate({ enabled: !data.enabled })
  }

  return (
    <label className="flex items-center gap-2 text-xs text-text-muted cursor-pointer">
      <span className={data.enabled ? 'text-emerald font-semibold' : 'text-text-muted'}>
        {data.enabled ? t('autoManager.enabledOn') : t('autoManager.enabledOff')}
      </span>
      <input
        type="checkbox"
        checked={data.enabled}
        onChange={handleToggleEnabled}
        disabled={updateConfig.isPending}
        aria-label={t('autoManager.toggleLabel')}
      />
    </label>
  )
}
