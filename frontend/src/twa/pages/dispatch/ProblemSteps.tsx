import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { CATEGORIES, MAX_REQUEST_TEXT_LENGTH, URGENCIES } from '../../../constants'
import { tCategory } from '../../../i18n/apiMaps'
import { PRIMARY_BTN } from '../../simple/components/Ui'
import { INPUT, tile } from './tiles'
import { Hint, Title } from './ui'

// Короче трёх букв — не описание («да», «ок»).
const DESCRIPTION_MIN = 3

export function CategoryStep({ value, onPick }: { value: string; onPick: (category: string) => void }) {
  const { t } = useTranslation()
  return (
    <div className="flex flex-col gap-3">
      <Title>{t('twa.dispatch.category.title')}</Title>
      <div className="grid grid-cols-2 gap-2">
        {CATEGORIES.map((c) => (
          <button
            key={c}
            type="button"
            aria-pressed={c === value}
            onClick={() => onPick(c)}
            className={tile(c === value ? 'selected' : 'plain')}
          >
            {tCategory(c, t)}
          </button>
        ))}
      </div>
    </div>
  )
}

export function DescriptionStep({ value, onDone }: { value: string; onDone: (description: string) => void }) {
  const { t } = useTranslation()
  const [text, setText] = useState(value)
  return (
    <div className="flex flex-col gap-3">
      <Title>{t('twa.dispatch.description.title')}</Title>
      <Hint>{t('twa.dispatch.description.hint')}</Hint>
      <textarea
        aria-label={t('twa.dispatch.description.title')}
        value={text}
        maxLength={MAX_REQUEST_TEXT_LENGTH}
        onChange={(e) => setText(e.target.value)}
        className={`${INPUT} min-h-[160px] py-3 resize-none`}
      />
      <button
        type="button"
        disabled={text.trim().length < DESCRIPTION_MIN}
        onClick={() => onDone(text)}
        className={`${PRIMARY_BTN} bg-emerald-600 text-white`}
      >
        {t('twa.dispatch.next')}
      </button>
    </div>
  )
}

export function UrgencyStep({ value, onPick }: { value: string; onPick: (urgency: string) => void }) {
  const { t } = useTranslation()
  return (
    <div className="flex flex-col gap-3">
      <Title>{t('twa.dispatch.urgency.title')}</Title>
      {URGENCIES.map((u) => (
        <button
          key={u}
          type="button"
          aria-pressed={u === value}
          onClick={() => onPick(u)}
          className={tile(u === value ? 'selected' : u === 'critical' ? 'danger' : 'plain')}
        >
          {t(`twa.create.urgency.${u}`)}
        </button>
      ))}
    </div>
  )
}
