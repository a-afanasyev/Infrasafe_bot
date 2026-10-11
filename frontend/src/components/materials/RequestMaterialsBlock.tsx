import { useTranslation } from 'react-i18next'
import { useRequestMaterials } from '../../hooks/useMaterials'
import { fmtMoney, fmtQty } from '../../utils/materialsFormat'
import { useUnitLabel } from '../../hooks/useUnitLabel'
import { useCan } from '../../hooks/useCan'

/**
 * Блок «Материалы» в карточке заявки (RequestDetailModal): списанные материалы
 * + суммарная себестоимость. Рендерится только при действии materials.manage;
 * при отсутствии списаний не показывается вовсе.
 */
export default function RequestMaterialsBlock({ requestNumber }: { requestNumber: string }) {
  const { t } = useTranslation()
  const unitLabel = useUnitLabel()
  const allowed = useCan('materials.manage')
  const { data } = useRequestMaterials(allowed ? requestNumber : null)

  if (!allowed || !data || data.items.length === 0) return null

  return (
    <div className="flex flex-col gap-1">
      <span className="font-semibold text-text-primary">
        {t('materials.requestBlock.title')}
      </span>
      <ul className="flex flex-col gap-0.5">
        {data.items.map((item) => (
          <li
            key={item.id}
            className={
              item.is_reversed
                ? 'text-text-muted line-through text-[13px]'
                : 'text-text-primary text-[13px]'
            }
          >
            {item.material_name} — {fmtQty(item.qty)} {unitLabel(item.unit)}
            <span className="text-text-muted"> · {fmtMoney(item.total_cost)}</span>
            {item.is_reversed && (
              <span className="no-underline text-text-muted">
                {' '}({t('materials.requestBlock.reversed')})
              </span>
            )}
          </li>
        ))}
      </ul>
      <span className="text-[13px] text-text-secondary">
        {t('materials.requestBlock.total', { total: fmtMoney(data.total_cost) })}
      </span>
    </div>
  )
}
