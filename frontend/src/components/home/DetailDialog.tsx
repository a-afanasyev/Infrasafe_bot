import { useEffect, useId, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import HomeIcon from './HomeIcon'

export interface DetailContent {
  kicker: string
  title: string
  date: string
  body: string
}

interface DetailDialogProps {
  content: DetailContent | null
  onClose: () => void
}

// Модалка подробностей (объявление / плановая работа). Свой оверлей, а не
// shadcn Dialog: публичная страница всегда светлая, а Dialog тянет тему
// дашборда (тёмную у InfraSafe). Esc и клик по фону закрывают; фокус — на
// «Закрыть», после закрытия возвращается туда, где был.
export default function DetailDialog({ content, onClose }: DetailDialogProps) {
  const { t } = useTranslation()
  const titleId = useId()
  const closeRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    if (!content) return
    const returnTo = document.activeElement as HTMLElement | null
    closeRef.current?.focus()
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('keydown', onKey)
      returnTo?.focus?.()
    }
  }, [content, onClose])

  if (!content) return null

  return (
    <div className="rh-dialog-backdrop" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div className="rh-dialog" role="dialog" aria-modal="true" aria-labelledby={titleId}>
        <div className="rh-dialog-top">
          <span className="rh-dialog-kicker">{content.kicker}</span>
          <button ref={closeRef} type="button" className="rh-icon-button rh-dialog-close" aria-label={t('home.close')} onClick={onClose}>
            <HomeIcon name="close" />
          </button>
        </div>
        <h2 id={titleId}>{content.title}</h2>
        {content.date && (
          <div className="rh-dialog-date">
            <HomeIcon name="calendar" />
            {content.date}
          </div>
        )}
        {content.body && (
          <div className="rh-dialog-body">
            {content.body.split(/\n{2,}|\n/).filter(Boolean).map((p, i) => <p key={i}>{p}</p>)}
          </div>
        )}
        <button type="button" className="rh-dialog-confirm" onClick={onClose}>{t('home.understood')}</button>
      </div>
    </div>
  )
}
