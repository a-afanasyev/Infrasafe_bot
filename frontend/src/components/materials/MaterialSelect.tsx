import { useTranslation } from 'react-i18next'
import { Select } from '@/components/ui/select'
import { useMaterials } from '../../hooks/useMaterials'
import { useUnitLabel } from '../../hooks/useUnitLabel'

interface Props {
  value: number | ''
  onChange: (id: number | '') => void
  disabled?: boolean
}

/** Селект активной номенклатуры (общий для форм прихода/расхода/корректировки). */
export default function MaterialSelect({ value, onChange, disabled }: Props) {
  const { t } = useTranslation()
  const unitLabel = useUnitLabel()
  const { data: materials } = useMaterials({ is_active: true, limit: 200 })

  return (
    <Select
      value={value}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value ? Number(e.target.value) : '')}
    >
      <option value="">{t('materials.form.selectMaterial')}</option>
      {(materials ?? []).map((m) => (
        <option key={m.id} value={m.id}>
          {m.name} ({unitLabel(m.unit)})
        </option>
      ))}
    </Select>
  )
}
