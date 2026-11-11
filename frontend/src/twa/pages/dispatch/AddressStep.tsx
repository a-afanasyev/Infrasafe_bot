import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { ErrorBlock, Loading, SECONDARY_BTN } from '../../simple/components/Ui'
import { listApartments, listBuildings, listYards, type Building, type Yard } from './api'
import type { Address, Draft } from './model'
import { INPUT, TILE, TILE_WHOLE } from './tiles'
import { Hint, Title } from './ui'

// Поле «номер квартиры» появляется, когда плиток больше, чем видно без прокрутки.
const APARTMENT_FILTER_FROM = 12

interface Props {
  draft: Draft
  onPick: (address: Address) => void
}

/**
 * Шаг «Где проблема»: адрес только из справочника. У найденного жителя —
 * его квартиры в одно касание; иначе двор → дом → квартира, на каждом уровне
 * можно остановиться («Весь двор», «Весь дом»).
 */
export default function AddressStep({ draft, onPick }: Props) {
  const { t } = useTranslation()
  const [own, setOwn] = useState(draft.residentApartments.length > 0)
  const [yard, setYard] = useState<Yard | null>(null)
  const [building, setBuilding] = useState<Building | null>(null)
  const [filter, setFilter] = useState('')

  const yards = useQuery({ queryKey: ['twa', 'dispatch', 'yards'], queryFn: listYards, enabled: !own })
  const buildings = useQuery({
    queryKey: ['twa', 'dispatch', 'buildings', yard?.id],
    queryFn: () => listBuildings((yard as Yard).id),
    enabled: yard !== null,
  })
  const apartments = useQuery({
    queryKey: ['twa', 'dispatch', 'apartments', building?.id],
    queryFn: () => listApartments((building as Building).id),
    enabled: building !== null,
  })

  if (own) {
    return (
      <div className="flex flex-col gap-3">
        <Title>{t('twa.dispatch.address.title')}</Title>
        <Hint>{t('twa.dispatch.address.residentApartments', { name: draft.resident?.fullName })}</Hint>
        {draft.residentApartments.map((a) => (
          <button
            key={a.id}
            type="button"
            className={TILE}
            onClick={() => onPick({ level: 'apartment', id: a.id, label: a.label, buildingId: a.building_id })}
          >
            {a.label}
          </button>
        ))}
        <button type="button" className={TILE_WHOLE} onClick={() => setOwn(false)}>
          {t('twa.dispatch.address.other')}
        </button>
      </div>
    )
  }

  if (yard === null) {
    return (
      <div className="flex flex-col gap-3">
        <Title>{t('twa.dispatch.address.yard')}</Title>
        {yards.isLoading && <Loading />}
        {yards.isError && <ErrorBlock onRetry={() => yards.refetch()} />}
        {yards.data?.length === 0 && <Hint>{t('twa.inspector.noYards')}</Hint>}
        {yards.data?.map((y) => (
          <button key={y.id} type="button" className={TILE} onClick={() => setYard(y)}>
            {y.name}
          </button>
        ))}
      </div>
    )
  }

  if (building === null) {
    return (
      <div className="flex flex-col gap-3">
        <Title>{t('twa.dispatch.address.building')}</Title>
        <Hint>{yard.name}</Hint>
        <button
          type="button"
          className={TILE_WHOLE}
          onClick={() => onPick({ level: 'yard', id: yard.id, label: yard.name, buildingId: null })}
        >
          {t('twa.dispatch.address.wholeYard')}
        </button>
        {buildings.isLoading && <Loading />}
        {buildings.isError && <ErrorBlock onRetry={() => buildings.refetch()} />}
        {buildings.data?.map((b) => (
          <button key={b.id} type="button" className={TILE} onClick={() => setBuilding(b)}>
            {b.address}
          </button>
        ))}
        <button type="button" className={`${SECONDARY_BTN} text-gray-700 dark:text-gray-200`} onClick={() => setYard(null)}>
          {t('twa.dispatch.address.otherYard')}
        </button>
      </div>
    )
  }

  const all = apartments.data ?? []
  const shown = filter ? all.filter((a) => a.number.startsWith(filter)) : all
  return (
    <div className="flex flex-col gap-3">
      <Title>{t('twa.dispatch.address.apartment')}</Title>
      <Hint>{building.address}</Hint>
      <button
        type="button"
        className={TILE_WHOLE}
        onClick={() => onPick({ level: 'building', id: building.id, label: building.address, buildingId: building.id })}
      >
        {t('twa.dispatch.address.wholeBuilding')}
      </button>
      {all.length > APARTMENT_FILTER_FROM && (
        <input
          inputMode="numeric"
          aria-label={t('twa.dispatch.address.apartment')}
          placeholder={t('twa.dispatch.address.apartmentFilter')}
          value={filter}
          onChange={(e) => setFilter(e.target.value.trim())}
          className={`${INPUT} h-[64px]`}
        />
      )}
      {apartments.isLoading && <Loading />}
      {apartments.isError && <ErrorBlock onRetry={() => apartments.refetch()} />}
      <div className="grid grid-cols-4 gap-2">
        {shown.map((a) => (
          <button
            key={a.id}
            type="button"
            aria-label={t('twa.dispatch.address.apartmentN', { number: a.number })}
            className={`${TILE} px-1 text-center`}
            onClick={() =>
              onPick({
                level: 'apartment',
                id: a.id,
                label: `${building.address}, ${t('twa.dispatch.address.apartmentN', { number: a.number })}`,
                buildingId: building.id,
              })
            }
          >
            {a.number}
          </button>
        ))}
      </div>
      <button type="button" className={`${SECONDARY_BTN} text-gray-700 dark:text-gray-200`} onClick={() => setBuilding(null)}>
        {t('twa.dispatch.address.otherBuilding')}
      </button>
    </div>
  )
}
