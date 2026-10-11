import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router'
import { useTranslation } from 'react-i18next'
import { usePublicBoard } from '../hooks/usePublicBoard'
import { useBoardConfig } from '../hooks/useBoardConfig'
import { usePageTitle } from '../hooks/usePageTitle'
import { defaultBoardConfig } from '../types/boardConfig'
import type { BoardConfigData } from '../types/boardConfig'
import { brand } from '../brand/brand'
import { getDisplayTz, nowInDisplayTz, todayInDisplayTz } from '../utils/timezone'
import ContactCard from '../components/home/ContactCard'
import DetailDialog, { type DetailContent } from '../components/home/DetailDialog'
import HomeIcon from '../components/home/HomeIcon'
import NoticeCarousel from '../components/home/NoticeCarousel'
import RequestsCard from '../components/home/RequestsCard'
import WorksCard from '../components/home/WorksCard'
import { MONTH_KEYS, type Lang } from '../components/home/homeFormat'
import './ResidentHomePage.css'

// Страница жителей «Ваш дом сегодня» — публичная главная по умолчанию.
// Табло для экрана в холле остаётся отдельной страницей (/resident-board).
// Данные те же: конфиг витрины (редактор витрины) + анонимные агрегаты табло.

// Часы показывают минуты — тик раз в 5 с, а не каждую секунду.
const CLOCK_TICK_MS = 5000

const TZ_CITY: Record<string, Record<Lang, string>> = {
  'Asia/Tashkent': { ru: 'Ташкент', uz: 'Toshkent' },
}

function tzLabel(tz: string, lang: Lang): string {
  const city = TZ_CITY[tz]?.[lang] ?? tz.split('/').pop()?.replace(/_/g, ' ') ?? tz
  let offset = ''
  try {
    offset = new Intl.DateTimeFormat('en-US', { timeZone: tz, timeZoneName: 'shortOffset' })
      .formatToParts(new Date())
      .find((p) => p.type === 'timeZoneName')?.value.replace('GMT', 'UTC') ?? ''
  } catch {
    offset = ''
  }
  return offset ? `${city} · ${offset}` : city
}

interface ResidentHomePageProps {
  // Превью в редакторе витрины — с несохранённым черновиком.
  configOverride?: BoardConfigData
}

export default function ResidentHomePage({ configOverride }: ResidentHomePageProps) {
  const { t, i18n } = useTranslation()
  usePageTitle(t('home.pageTitle'), !configOverride)
  const { data: board } = usePublicBoard()
  const { data: fetchedConfig } = useBoardConfig()
  const config = configOverride ?? fetchedConfig ?? defaultBoardConfig
  const lang: Lang = (i18n.resolvedLanguage ?? i18n.language)?.startsWith('uz') ? 'uz' : 'ru'
  const loc = (v: { ru: string; uz: string }) => (v[lang] || v.ru).trim()

  const [wall, setWall] = useState(nowInDisplayTz)
  useEffect(() => {
    const id = setInterval(() => setWall(nowInDisplayTz()), CLOCK_TICK_MS)
    return () => clearInterval(id)
  }, [])

  const [detail, setDetail] = useState<DetailContent | null>(null)
  const closeDetail = useCallback(() => setDetail(null), [])

  const hh = String(wall.getHours()).padStart(2, '0')
  const mm = String(wall.getMinutes()).padStart(2, '0')
  const dayKey = ['sun', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat'][wall.getDay()]
  const month = t(`months.${MONTH_KEYS[wall.getMonth()]}`)
  const dateLine = lang === 'uz'
    ? `${wall.getDate()}-${month}, ${t(`days.short.${dayKey}`)}`
    : `${wall.getDate()} ${month}, ${t(`days.short.${dayKey}`).toLowerCase()}`

  const announcements = config.announcements.filter((a) => loc(a.title))
  const orgName = loc(config.org.name) || brand.displayName

  return (
    <div className={configOverride ? 'rh rh--embedded' : 'rh'}>
      <a className="rh-skip" href="#rh-main">{t('home.skip')}</a>
      <div className="rh-shell">
        <header className="rh-header">
          <div className="rh-brand">
            <img src={`${import.meta.env.BASE_URL}${brand.logoMark}`} width={49} height={49} alt="" />
            <span className="rh-brand-type">
              <b>{orgName}<span className="rh-dot">.</span></b>
              <span>{loc(config.org.subtitle) || t('home.management')}</span>
            </span>
          </div>
          <div className="rh-header-end">
            <div className="rh-clock">
              <time dateTime={`${hh}:${mm}`}>{hh}:{mm}</time>
              <div>
                <span>{dateLine}</span>
                <span className="rh-clock-city">{tzLabel(getDisplayTz(), lang)}</span>
              </div>
            </div>
            <div className="rh-lang" role="group" aria-label="RU / UZ">
              {(['ru', 'uz'] as const).map((l) => (
                <button key={l} type="button" aria-pressed={lang === l} onClick={() => i18n.changeLanguage(l)}>
                  {l.toUpperCase()}
                </button>
              ))}
            </div>
            <Link className="rh-icon-button rh-tv-link" to="/resident-board" title={t('home.tvViewHint')}>
              <HomeIcon name="monitor" />
              <span>{t('home.tvView')}</span>
            </Link>
          </div>
        </header>

        <main id="rh-main" tabIndex={-1}>
          <div className="rh-heading">
            <p className="rh-eyebrow">{t('home.eyebrow')}</p>
            <h1>{t('home.pageTitle')}<span className="rh-dot">.</span></h1>
          </div>
          <div className="rh-primary">
            <NoticeCarousel announcements={announcements} lang={lang} onOpen={setDetail} />
            <ContactCard config={config} lang={lang} />
          </div>
          <div className="rh-secondary">
            <RequestsCard board={board} month={wall.getMonth()} />
            <WorksCard works={config.planned_works ?? []} today={todayInDisplayTz()} lang={lang} onOpen={setDetail} />
          </div>
        </main>

        <footer className="rh-footer">
          <span className="rh-footer-signature">
            <span className="rh-footer-leaf"><HomeIcon name="leaf" /></span>
            {orgName} · {t('home.footerTagline')}
          </span>
        </footer>
      </div>
      <DetailDialog content={detail} onClose={closeDetail} />
    </div>
  )
}
