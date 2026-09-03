import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Button } from '../../components/ui/button'
import { Input } from '../../components/ui/input'
import type {
  RegistrationApartment,
  RegistrationBuilding,
  RegistrationYard,
} from '../../hooks/useRegistration'

export interface AddressLabels {
  yard: string
  building: string
}

export interface CascadeApi {
  yards: (ticket: string) => Promise<RegistrationYard[]>
  buildings: (ticket: string, yardId: number) => Promise<RegistrationBuilding[]>
  apartments: (ticket: string, buildingId: number) => Promise<RegistrationApartment[]>
}

interface Props {
  ticket: string
  api: CascadeApi
  onSelect: (apartment: RegistrationApartment, labels: AddressLabels) => void
}

type Step = 'yard' | 'building' | 'apartment'

const itemBtn =
  'w-full bg-bg-card border border-[color:var(--auth-card-border)] rounded-xl p-3 text-[14px] text-left active:scale-[0.97] transition-transform'

/**
 * Двор → дом → квартира, как в боте (спека 2026-09-03 §5.1): списки
 * крупными кнопками, крошки выбранного, «Назад», фильтр квартир по номеру.
 */
export function AddressCascade({ ticket, api, onSelect }: Props) {
  const { t } = useTranslation()
  const [step, setStep] = useState<Step>('yard')
  const [yard, setYard] = useState<RegistrationYard | null>(null)
  const [building, setBuilding] = useState<RegistrationBuilding | null>(null)
  const [yards, setYards] = useState<RegistrationYard[] | null>(null)
  const [buildings, setBuildings] = useState<RegistrationBuilding[] | null>(null)
  const [apartments, setApartments] = useState<RegistrationApartment[] | null>(null)
  const [filter, setFilter] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    let alive = true
    setError('')
    const load = async () => {
      try {
        if (step === 'yard') setYards(await api.yards(ticket))
        else if (step === 'building' && yard) setBuildings(await api.buildings(ticket, yard.id))
        else if (step === 'apartment' && building) setApartments(await api.apartments(ticket, building.id))
      } catch {
        if (alive) setError(t('register.error_generic'))
      }
    }
    void load()
    return () => { alive = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step, yard?.id, building?.id, ticket])

  function back() {
    if (step === 'apartment') { setStep('building'); setApartments(null); setFilter('') }
    else if (step === 'building') { setStep('yard'); setBuildings(null); setYard(null) }
  }

  const titleKey = step === 'yard' ? 'register.select_yard'
    : step === 'building' ? 'register.select_building' : 'register.select_apartment'
  const list = step === 'yard' ? yards : step === 'building' ? buildings : apartments
  const muted = 'text-[13px] text-text-secondary font-[family-name:var(--font-body)]'

  const visibleApartments = (apartments ?? []).filter((a) =>
    a.apartment_number.toLowerCase().includes(filter.trim().toLowerCase()),
  )

  return (
    <div className="flex flex-col gap-3">
      {(yard || building) && (
        <div className={muted}>
          {yard && <span>{yard.name}</span>}
          {building && <span> › {building.address}</span>}
        </div>
      )}
      <div className="font-[family-name:var(--font-display)] font-bold text-text-primary">
        {t(titleKey)}
      </div>
      {error && <div className="text-[13px] text-red">{error}</div>}
      {list === null && !error && <div className={muted}>{t('common.loading')}</div>}
      {list !== null && list.length === 0 && <div className={muted}>{t('register.no_items')}</div>}

      {step === 'yard' && yards?.map((y) => (
        <button key={y.id} type="button" className={itemBtn}
          onClick={() => { setYard(y); setStep('building') }}>
          🏘️ {y.name}
        </button>
      ))}

      {step === 'building' && buildings?.map((b) => (
        <button key={b.id} type="button" className={itemBtn}
          onClick={() => { setBuilding(b); setStep('apartment') }}>
          🏢 {b.address}
        </button>
      ))}

      {step === 'apartment' && apartments && apartments.length > 0 && (
        <>
          <Input
            type="text"
            inputMode="numeric"
            placeholder={t('register.filter_apartment')}
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          />
          <div className="grid grid-cols-4 gap-2">
            {visibleApartments.map((a) => (
              <button key={a.id} type="button"
                className="bg-bg-card border border-[color:var(--auth-card-border)] rounded-xl py-3 text-[14px] text-center active:scale-[0.97] transition-transform"
                onClick={() => yard && building && onSelect(a, { yard: yard.name, building: building.address })}>
                {a.apartment_number}
              </button>
            ))}
          </div>
        </>
      )}

      {step !== 'yard' && (
        <Button type="button" variant="outline" className="w-full" onClick={back}>
          {t('register.back')}
        </Button>
      )}
    </div>
  )
}
