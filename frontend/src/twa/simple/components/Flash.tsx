/* eslint-disable react-refresh/only-export-components -- экран и его хук живут вместе */
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Check, RotateCcw } from 'lucide-react'
import { PRIMARY_BTN, ResultScreen, SECONDARY_BTN } from './Ui'

/** Исход действия на весь экран (взять, смена, язык). */
export interface Flash {
  ok: boolean
  title: string
  /** Для ошибки: «Ещё раз» повторяет действие. */
  retry?: () => void
}

const OK_HOLD_MS = 1200

/** Успех гаснет сам; ошибка — по кнопке. */
export function useFlash(): [Flash | null, (flash: Flash | null) => void] {
  const [flash, setFlash] = useState<Flash | null>(null)
  useEffect(() => {
    if (!flash?.ok) return
    const id = window.setTimeout(() => setFlash(null), OK_HOLD_MS)
    return () => window.clearTimeout(id)
  }, [flash])
  return [flash, setFlash]
}

export function FlashScreen({ flash, onClose }: { flash: Flash | null; onClose: () => void }) {
  const { t } = useTranslation()
  if (!flash) return null
  if (flash.ok) {
    return (
      <div onClick={onClose}>
        <ResultScreen ok title={flash.title} />
      </div>
    )
  }
  return (
    <ResultScreen ok={false} title={flash.title}>
      {flash.retry && (
        <button
          type="button"
          onClick={() => {
            onClose()
            flash.retry?.()
          }}
          className={`${PRIMARY_BTN} bg-white text-red-700`}
        >
          <RotateCcw size={30} aria-hidden /> {t('twa.simple.error.retry')}
        </button>
      )}
      <button type="button" onClick={onClose} className={`${SECONDARY_BTN} border-2 border-white text-white`}>
        <Check size={26} aria-hidden /> {t('twa.simple.ok')}
      </button>
    </ResultScreen>
  )
}
