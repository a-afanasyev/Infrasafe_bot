import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { AnnouncementCfg } from '../../types/boardConfig'
import CourtyardArt from './CourtyardArt'
import type { DetailContent } from './DetailDialog'
import HomeIcon from './HomeIcon'
import { announcementWall, wallDateTimeLabel, type Lang } from './homeFormat'

// Смена слайда раз в 8 секунд: успеть прочитать заголовок и подзаголовок.
export const SLIDE_INTERVAL_MS = 8000

interface NoticeCarouselProps {
  announcements: AnnouncementCfg[]
  // Надпись-кикер из редактора витрины; '' → «Важное для вас».
  title?: string
  lang: Lang
  onOpen: (content: DetailContent) => void
  // Интервал автосмены; ТВ-режим табло ставит длиннее (читают с расстояния).
  intervalMs?: number
}

function prefersReducedMotion(): boolean {
  return typeof window !== 'undefined' && !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
}

export default function NoticeCarousel({ announcements, title: heading = '', lang, onOpen, intervalMs = SLIDE_INTERVAL_MS }: NoticeCarouselProps) {
  const { t } = useTranslation()
  const [index, setIndex] = useState(0)
  // Без автосмены при «уменьшить движение» — пользователь листает сам.
  const [paused, setPaused] = useState(prefersReducedMotion)
  const count = announcements.length
  const current = count ? announcements[Math.min(index, count - 1)] : null

  useEffect(() => {
    if (paused || count < 2) return
    const id = setInterval(() => setIndex((i) => (i + 1) % count), intervalMs)
    return () => clearInterval(id)
  }, [paused, count, intervalMs])

  const go = (delta: number) => setIndex((i) => (i + delta + count) % count)
  const loc = (v: { ru: string; uz: string }) => v[lang] || v.ru

  if (!current) {
    return (
      <section className="rh-notice" aria-label={t('home.carousel.label')}>
        <div className="rh-notice-top">
          <div className="rh-kicker"><HomeIcon name="notice" />{heading || t('home.important')}</div>
        </div>
        <div className="rh-notice-content">
          <h2>{t('home.noAnnouncementsTitle')}</h2>
          <p>{t('home.noAnnouncementsText')}</p>
        </div>
        <CourtyardArt />
      </section>
    )
  }

  const wall = announcementWall(current.published_at)
  const date = wall ? wallDateTimeLabel(wall, t, lang) : ''
  const kicker = current.important ? t('home.importantTag') : t('home.announcement')
  const title = loc(current.title)
  const text = loc(current.text)

  return (
    <section className="rh-notice" aria-roledescription="carousel" aria-label={t('home.carousel.label')}>
      <div className="rh-notice-top">
        <div className="rh-kicker"><HomeIcon name="notice" />{heading || t('home.important')}</div>
        <span className={current.important ? 'rh-notice-tag rh-notice-tag--important' : 'rh-notice-tag'}>{kicker}</span>
      </div>
      <div className="rh-notice-content" aria-live={paused ? 'polite' : 'off'}>
        {date && <div className="rh-notice-date"><HomeIcon name="calendar" />{date}</div>}
        <h2>{title}</h2>
        {text && <p>{text}</p>}
        {text && (
          <button
            type="button"
            className="rh-details-button"
            onClick={() => onOpen({ kicker, title, date, body: text })}
          >
            {t('home.readMore')}
            <HomeIcon name="arrow" />
          </button>
        )}
      </div>
      <CourtyardArt />
      {count > 1 && (
        <div className="rh-notice-bottom">
          <div className="rh-dots" role="group" aria-label={t('home.carousel.choose')}>
            {announcements.map((a, i) => (
              <button
                key={a.id}
                type="button"
                aria-label={t('home.carousel.goTo', { n: i + 1 })}
                aria-pressed={i === index}
                onClick={() => setIndex(i)}
              />
            ))}
          </div>
          <div className="rh-carousel-controls">
            <span className="rh-slide-count">
              {String(index + 1).padStart(2, '0')} <span>/ {String(count).padStart(2, '0')}</span>
            </span>
            <button type="button" className="rh-round-button" aria-label={t('home.carousel.prev')} onClick={() => go(-1)}>
              <HomeIcon name="chevron" className="rh-backwards" />
            </button>
            <button
              type="button"
              className="rh-round-button"
              aria-label={paused ? t('home.carousel.play') : t('home.carousel.pause')}
              aria-pressed={paused}
              onClick={() => setPaused((p) => !p)}
            >
              <HomeIcon name={paused ? 'play' : 'pause'} />
            </button>
            <button type="button" className="rh-round-button" aria-label={t('home.carousel.next')} onClick={() => go(1)}>
              <HomeIcon name="chevron" />
            </button>
          </div>
        </div>
      )}
    </section>
  )
}
