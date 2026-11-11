import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { PRIMARY_BTN } from '../../simple/components/Ui'
import { residentApartments, searchResidents, type ResidentMatch } from './api'
import { isPhoneComplete, residentQuery, type Draft } from './model'
import { INPUT, TILE } from './tiles'
import { Hint, Title } from './ui'

type Stage = 'phone' | 'confirm' | 'name'

interface Props {
  draft: Draft
  /** Ответ на шаг: правка черновика и переход дальше. */
  onDone: (patch: Partial<Draft>) => void
}

/**
 * Шаг «Кто звонит»: телефон → система сама ищет жителя. Нашла — «Это он?»
 * (заявка пойдёт от его имени, адрес — его квартира в одно касание); не нашла —
 * необязательное имя, звонящий уйдёт в примечания.
 */
export default function PhoneStep({ draft, onDone }: Props) {
  const { t } = useTranslation()
  const [stage, setStage] = useState<Stage>('phone')
  const [phone, setPhone] = useState(draft.phone)
  const [name, setName] = useState(draft.callerName)
  const [matches, setMatches] = useState<ResidentMatch[]>([])
  const [busy, setBusy] = useState(false)

  const search = async () => {
    setBusy(true)
    try {
      const found = await searchResidents(residentQuery(phone))
      setMatches(found)
      setStage(found.length > 0 ? 'confirm' : 'name')
    } catch {
      // Поиск — удобство, а не условие: без него звонок принимается как от
      // незнакомого номера.
      setStage('name')
    } finally {
      setBusy(false)
    }
  }

  const pick = async (m: ResidentMatch) => {
    setBusy(true)
    const apartments = await residentApartments(m.id).catch(() => [])
    setBusy(false)
    onDone({
      phone,
      callerName: '',
      resident: { id: m.id, fullName: m.full_name?.trim() || phone },
      residentApartments: apartments,
    })
  }

  const asStranger = () => onDone({ phone, callerName: name.trim(), resident: null, residentApartments: [] })

  if (stage === 'confirm') {
    return (
      <div className="flex flex-col gap-3">
        <Title>{t(matches.length === 1 ? 'twa.dispatch.resident.isIt' : 'twa.dispatch.resident.pick')}</Title>
        {matches.map((m) => (
          <button key={m.id} type="button" disabled={busy} onClick={() => pick(m)} className={TILE}>
            {m.full_name?.trim() || m.phone}
          </button>
        ))}
        <button type="button" disabled={busy} onClick={() => setStage('name')} className={TILE}>
          {t('twa.dispatch.resident.no')}
        </button>
      </div>
    )
  }

  if (stage === 'name') {
    return (
      <div className="flex flex-col gap-3">
        <Title>{t('twa.dispatch.name.title')}</Title>
        <Hint>{t('twa.dispatch.name.hint')}</Hint>
        <input
          aria-label={t('twa.dispatch.name.title')}
          value={name}
          maxLength={100}
          onChange={(e) => setName(e.target.value)}
          className={`${INPUT} h-[64px]`}
        />
        <button type="button" onClick={asStranger} className={`${PRIMARY_BTN} bg-emerald-600 text-white`}>
          {t('twa.dispatch.next')}
        </button>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-3">
      <Title>{t('twa.dispatch.phone.title')}</Title>
      <Hint>{t('twa.dispatch.phone.hint')}</Hint>
      <input
        type="tel"
        inputMode="tel"
        autoComplete="off"
        aria-label={t('twa.dispatch.phone.title')}
        value={phone}
        maxLength={20}
        placeholder="90 123 45 67"
        onChange={(e) => setPhone(e.target.value)}
        className={`${INPUT} h-[72px] text-[28px] tracking-wide`}
      />
      <button
        type="button"
        disabled={!isPhoneComplete(phone) || busy}
        onClick={search}
        className={`${PRIMARY_BTN} bg-emerald-600 text-white`}
      >
        {t(busy ? 'twa.dispatch.phone.searching' : 'twa.dispatch.next')}
      </button>
    </div>
  )
}
