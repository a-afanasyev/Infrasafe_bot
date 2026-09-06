import { useTranslation } from 'react-i18next'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select } from '@/components/ui/select'
import FormSection from './FormSection'
import { useBuildings, useYards } from '../../hooks/useAddresses'
import { ELEVATOR_FIELD_MAX, type ElevatorFormState, type ElevatorFormTextKey } from '../../utils/elevatorForm'

/**
 * Поля формы лифта по секциям: обязательные (каскад двор→дом, подъезд, номер,
 * паспорт, производитель, серийник), паспорт, договор, освидетельствование,
 * простой/публикация. Состояние — у страницы (`ElevatorFormState`).
 * `maxLength` = ширины колонок бэка, `min={1}` у положительных чисел.
 */
interface Props {
  form: ElevatorFormState
  onChange: (patch: Partial<ElevatorFormState>) => void
}

interface TextFieldProps {
  form: ElevatorFormState
  onChange: Props['onChange']
  name: ElevatorFormTextKey
  labelKey: string
  type?: 'text' | 'number' | 'date' | 'url' | 'tel'
  required?: boolean
  min?: number
}

function TextField({ form, onChange, name, labelKey, type = 'text', required = false, min }: TextFieldProps) {
  const { t } = useTranslation()
  const id = `elevator-${name}`
  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor={id}>
        {t(labelKey)}{required && <span className="text-red"> *</span>}
      </Label>
      <Input
        id={id}
        type={type}
        value={form[name]}
        min={min}
        maxLength={ELEVATOR_FIELD_MAX[name]}
        onChange={(e) => onChange({ [name]: e.target.value } as Partial<ElevatorFormState>)}
      />
    </div>
  )
}

export default function ElevatorFormFields({ form, onChange }: Props) {
  const { t } = useTranslation()
  const yards = useYards()
  const yardId = form.yard_id ? Number(form.yard_id) : null
  const buildings = useBuildings(yardId)
  const f = { form, onChange }

  return (
    <div className="flex flex-col gap-4">
      <FormSection title={t('elevators.form.sectionRequired')}>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="elevator-yard_id">{t('elevators.form.yard')} <span className="text-red">*</span></Label>
          <Select
            id="elevator-yard_id"
            value={form.yard_id}
            onChange={(e) => onChange({ yard_id: e.target.value, building_id: '' })}
          >
            <option value="">{t('elevators.form.selectYard')}</option>
            {(yards.data ?? []).map((y) => (
              <option key={y.id} value={y.id}>{y.name}</option>
            ))}
          </Select>
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="elevator-building_id">{t('elevators.form.building')} <span className="text-red">*</span></Label>
          <Select
            id="elevator-building_id"
            value={form.building_id}
            disabled={yardId === null}
            onChange={(e) => onChange({ building_id: e.target.value })}
          >
            <option value="">{t('elevators.form.selectBuilding')}</option>
            {(buildings.data ?? []).map((b) => (
              <option key={b.id} value={b.id}>{b.address}</option>
            ))}
          </Select>
        </div>
        <TextField {...f} name="entrance_number" labelKey="elevators.form.entrance" type="number" min={1} required />
        <TextField {...f} name="elevator_number" labelKey="elevators.form.elevatorNumber" type="number" min={1} required />
        <TextField {...f} name="passport_number" labelKey="elevators.form.passportNumber" required />
        <TextField {...f} name="manufacturer" labelKey="elevators.form.manufacturer" required />
        <TextField {...f} name="serial_number" labelKey="elevators.form.serialNumber" required />
      </FormSection>

      <FormSection title={t('elevators.form.sectionPassport')}>
        <TextField {...f} name="factory_number" labelKey="elevators.form.factoryNumber" />
        <TextField {...f} name="model" labelKey="elevators.form.model" />
        <TextField {...f} name="production_year" labelKey="elevators.form.productionYear" type="number" min={1} />
        <TextField {...f} name="capacity_kg" labelKey="elevators.form.capacityKg" type="number" min={1} />
        <TextField {...f} name="floors_served" labelKey="elevators.form.floorsServed" />
      </FormSection>

      <FormSection title={t('elevators.form.sectionContract')}>
        <TextField {...f} name="service_org_name" labelKey="elevators.form.serviceOrgName" />
        <TextField {...f} name="service_org_phone" labelKey="elevators.form.serviceOrgPhone" type="tel" />
        <TextField {...f} name="contract_number" labelKey="elevators.form.contractNumber" />
        <TextField {...f} name="contract_until" labelKey="elevators.form.contractUntil" type="date" />
      </FormSection>

      <FormSection title={t('elevators.form.sectionCert')}>
        <TextField {...f} name="cert_number" labelKey="elevators.form.certNumber" />
        <TextField {...f} name="cert_valid_until" labelKey="elevators.form.certValidUntil" type="date" />
        <TextField {...f} name="cert_act_url" labelKey="elevators.form.certActUrl" type="url" />
      </FormSection>

      <FormSection title={t('elevators.form.sectionDowntime')}>
        <TextField {...f} name="downtime_reason" labelKey="elevators.form.downtimeReason" />
        <TextField {...f} name="spare_part_expected_on" labelKey="elevators.form.sparePartExpectedOn" type="date" />
        <div className="flex flex-col gap-2 justify-end">
          <label className="flex items-center gap-2 text-[13px] text-text-primary">
            <input
              type="checkbox"
              checked={form.publish_downtime_details}
              onChange={(e) => onChange({ publish_downtime_details: e.target.checked })}
            />
            {t('elevators.form.publishDowntimeDetails')}
          </label>
          <label className="flex items-center gap-2 text-[13px] text-text-primary">
            <input
              type="checkbox"
              checked={form.is_public}
              onChange={(e) => onChange({ is_public: e.target.checked })}
            />
            {t('elevators.form.isPublic')}
          </label>
        </div>
      </FormSection>
    </div>
  )
}
