import { useTranslation } from 'react-i18next'
import { Label } from '@/components/ui/label'
import { Select } from '@/components/ui/select'
import { useBuildings, useYards } from '../../hooks/useAddresses'
import { useElevatorsForBuilding } from '../../hooks/useElevators'
import type { CallCenterElevatorValue } from './callCenterElevator'

/**
 * Поля формы колл-центра для категории «Лифт»: каскад двор → дом из
 * справочника (адрес уровня дома → `building_id`, без него лифт не
 * привязать), лифт этого дома (`GET /elevators/for-building/{id}`),
 * «работает?». Дом/лифт/работает обязательны — иначе сервер отвечает 422
 * (Р11). Значение и проверка — `callCenterElevator.ts`.
 */
interface Props {
  value: CallCenterElevatorValue
  onChange: (next: CallCenterElevatorValue) => void
}

const parseId = (raw: string): number | null => (raw ? Number(raw) : null)

export default function CallCenterElevatorFields({ value, onChange }: Props) {
  const { t } = useTranslation()
  const yards = useYards()
  const buildings = useBuildings(value.yardId)
  const elevators = useElevatorsForBuilding(value.buildingId)
  const elevatorList = elevators.data ?? []
  const noElevators = value.buildingId !== null && elevators.isSuccess && elevatorList.length === 0

  return (
    <>
      <div className="space-y-1.5">
        <Label htmlFor="cc-yard">{t('callcenter.elevator.yard')}</Label>
        <Select
          id="cc-yard"
          value={value.yardId ?? ''}
          onChange={(e) => onChange({ ...value, yardId: parseId(e.target.value), buildingId: null, elevatorId: null })}
        >
          <option value="">{t('callcenter.elevator.yardPlaceholder')}</option>
          {(yards.data ?? []).map((y) => (
            <option key={y.id} value={y.id}>{y.name}</option>
          ))}
        </Select>
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="cc-building">{t('callcenter.elevator.building')}</Label>
        <Select
          id="cc-building"
          value={value.buildingId ?? ''}
          disabled={value.yardId === null}
          onChange={(e) => onChange({ ...value, buildingId: parseId(e.target.value), elevatorId: null })}
        >
          <option value="">{t('callcenter.elevator.buildingPlaceholder')}</option>
          {(buildings.data ?? []).map((b) => (
            <option key={b.id} value={b.id}>{b.address}</option>
          ))}
        </Select>
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="cc-elevator">{t('callcenter.elevator.elevator')}</Label>
        <Select
          id="cc-elevator"
          value={value.elevatorId ?? ''}
          disabled={value.buildingId === null || elevatorList.length === 0}
          onChange={(e) => onChange({ ...value, elevatorId: parseId(e.target.value) })}
        >
          <option value="">{t('callcenter.elevator.elevatorPlaceholder')}</option>
          {elevatorList.map((el) => (
            <option key={el.id} value={el.id}>
              {el.label} — {t(el.current_status ? `elevators.status.${el.current_status}` : 'elevators.status.none')}
            </option>
          ))}
        </Select>
        {noElevators && <p className="text-text-muted text-xs">{t('callcenter.elevator.noElevators')}</p>}
      </div>

      <fieldset className="space-y-1.5">
        <legend className="text-sm font-medium">{t('callcenter.elevator.operational')}</legend>
        <div className="flex gap-4 text-sm">
          <label className="flex items-center gap-1.5">
            <input
              type="radio"
              name="cc-elevator-operational"
              checked={value.operational === true}
              onChange={() => onChange({ ...value, operational: true })}
            />
            {t('callcenter.elevator.yes')}
          </label>
          <label className="flex items-center gap-1.5">
            <input
              type="radio"
              name="cc-elevator-operational"
              checked={value.operational === false}
              onChange={() => onChange({ ...value, operational: false })}
            />
            {t('callcenter.elevator.no')}
          </label>
        </div>
      </fieldset>
    </>
  )
}
