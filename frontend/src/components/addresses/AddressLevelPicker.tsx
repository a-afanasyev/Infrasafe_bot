import { useTranslation } from 'react-i18next'
import { Label } from '@/components/ui/label'
import { Select } from '@/components/ui/select'
import { useApartments, useBuildings, useYards } from '../../hooks/useAddresses'

import type { AddressLevelValue } from './addressLevel'

/**
 * Адрес заявки из справочника: двор (обязателен) → дом → квартира. Уровень
 * заявки — самый глубокий выбранный: «весь двор», «весь дом» или квартира.
 * Значение и тело для API — `addressLevel.ts`.
 */
interface Props {
  value: AddressLevelValue
  onChange: (next: AddressLevelValue) => void
  /** Префикс id полей — на странице может быть две формы адреса. */
  idPrefix?: string
}

const parseId = (raw: string): number | null => (raw ? Number(raw) : null)

export default function AddressLevelPicker({ value, onChange, idPrefix = 'addr' }: Props) {
  const { t } = useTranslation()
  const yards = useYards()
  const buildings = useBuildings(value.yardId)
  const apartments = useApartments(value.buildingId)

  return (
    <>
      <div className="space-y-1.5">
        <Label htmlFor={`${idPrefix}-yard`}>{t('addressPicker.yard')}</Label>
        <Select
          id={`${idPrefix}-yard`}
          value={value.yardId ?? ''}
          onChange={(e) => onChange({ yardId: parseId(e.target.value), buildingId: null, apartmentId: null })}
        >
          <option value="">{t('addressPicker.yardPlaceholder')}</option>
          {(yards.data ?? []).map((y) => (
            <option key={y.id} value={y.id}>{y.name}</option>
          ))}
        </Select>
      </div>

      <div className="space-y-1.5">
        <Label htmlFor={`${idPrefix}-building`}>{t('addressPicker.building')}</Label>
        <Select
          id={`${idPrefix}-building`}
          value={value.buildingId ?? ''}
          disabled={value.yardId === null}
          onChange={(e) => onChange({ ...value, buildingId: parseId(e.target.value), apartmentId: null })}
        >
          <option value="">{t('addressPicker.wholeYard')}</option>
          {(buildings.data ?? []).map((b) => (
            <option key={b.id} value={b.id}>{b.address}</option>
          ))}
        </Select>
      </div>

      <div className="space-y-1.5">
        <Label htmlFor={`${idPrefix}-apartment`}>{t('addressPicker.apartment')}</Label>
        <Select
          id={`${idPrefix}-apartment`}
          value={value.apartmentId ?? ''}
          disabled={value.buildingId === null}
          onChange={(e) => onChange({ ...value, apartmentId: parseId(e.target.value) })}
        >
          <option value="">{t('addressPicker.wholeBuilding')}</option>
          {(apartments.data ?? []).map((a) => (
            <option key={a.id} value={a.id}>{a.apartment_number}</option>
          ))}
        </Select>
      </div>
    </>
  )
}
