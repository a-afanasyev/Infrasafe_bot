import { useCallback, useEffect, useState, type ReactNode } from 'react'
import { Link } from 'react-router'
import { useTranslation } from 'react-i18next'
import { usePublicBoard } from '../hooks/usePublicBoard'
import { useBoardConfig } from '../hooks/useBoardConfig'
import { usePageTitle } from '../hooks/usePageTitle'
import { defaultBoardConfig } from '../types/boardConfig'
import type { BoardConfigData, HomeBlockId } from '../types/boardConfig'
import { brand } from '../brand/brand'
import { getDisplayTz, nowInDisplayTz, todayInDisplayTz } from '../utils/timezone'
import ContactCard from '../components/home/ContactCard'
import DetailDialog, { type DetailContent } from '../components/home/DetailDialog'
import ElevatorsCard from '../components/home/ElevatorsCard'
import HomeIcon from '../components/home/HomeIcon'
import NoticeCarousel from '../components/home/NoticeCarousel'
import RequestsCard from '../components/home/RequestsCard'
import WorkReportsCard from '../components/home/WorkReportsCard'
import WorksCard from '../components/home/WorksCard'
import { HOME_ROWS, localize, resolveHomeBlocks } from '../components/home/homeConfig'
import { MONTH_KEYS, type Lang } from '../components/home/homeFormat'
import './ResidentHomePage.css'

// Страница жителей «Ваш дом сегодня» — публичная главная по умолчанию.
// Табло для экрана в холле остаётся отдельной страницей (/resident-board).
// Всё, что на странице можно поменять, правится в «Редакторе витрины»
// (board_config: org/contacts/bot/часы/объявления/плановые работы + home —
// название комплекса, заголовки, видимость и заголовки блоков). Счётчики
// обращений, лифты и отчёты — живые данные системы, вручную не заполняются.

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
  const { data: fetchedConfig } = useBoardConfig()
  const config = configOverride ?? fetchedConfig ?? defaultBoardConfig
  const lang: Lang = (i18n.resolvedLanguage ?? i18n.language)?.startsWith('uz') ? 'uz' : 'ru'
  const home = config.home
  const pageTitle = localize(home?.title, lang) || t('home.pageTitle')
  usePageTitle(pageTitle, !configOverride)
  const { data: board } = usePublicBoard()

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

  const announcements = config.announcements.filter((a) => localize(a.title, lang))
  const orgName = localize(config.org.name, lang) || brand.displayName
  const complexName = localize(home?.complex_name, lang)
  const blocks = resolveHomeBlocks(config, lang)

  const BLOCKS: Record<HomeBlockId, () => ReactNode> = {
    announcements: () => (
      <NoticeCarousel announcements={announcements} title={blocks.announcements.title} lang={lang} onOpen={setDetail} />
    ),
    contacts: () => <ContactCard config={config} title={blocks.contacts.title} lang={lang} />,
    requests: () => <RequestsCard board={board} title={blocks.requests.title} month={wall.getMonth()} />,
    works: () => (
      <WorksCard
        works={config.planned_works ?? []}
        title={blocks.works.title}
        today={todayInDisplayTz()}
        lang={lang}
        onOpen={setDetail}
      />
    ),
    elevators: () => <ElevatorsCard title={blocks.elevators.title} lang={lang} />,
    workreports: () => <WorkReportsCard title={blocks.workreports.title} />,
  }

  // Ряд хранит свой номер в сетке (высота ряда зависит от него, а не от того,
  // сколько рядов выше скрыто).
  const rows = HOME_ROWS
    .map((pair, index) => ({ index: index + 1, visible: pair.filter((id) => blocks[id].visible) }))
    .filter((row) => row.visible.length > 0)

  return (
    <div className={configOverride ? 'rh rh--embedded' : 'rh'}>
      <a className="rh-skip" href="#rh-main">{t('home.skip')}</a>
      {/* rh-frame — контейнер адаптивности (@container rh): превью в редакторе
          раскладывается по своей ширине, а не по ширине окна. */}
      <div className="rh-frame">
      <div className="rh-shell">
        <header className="rh-header">
          <div className="rh-brand">
            <img src={`${import.meta.env.BASE_URL}${brand.logoMark}`} width={49} height={49} alt="" />
            <span className="rh-brand-type">
              <b>{orgName}<span className="rh-dot">.</span></b>
              <span>{localize(config.org.subtitle, lang) || t('home.management')}</span>
            </span>
          </div>
          {complexName && (
            <>
              <div className="rh-header-divider" />
              <div className="rh-complex">
                <HomeIcon name="building" />
                <span>
                  <span className="rh-complex-label">{t('home.complexLabel')}</span>
                  <b>{complexName}</b>
                </span>
              </div>
            </>
          )}
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
            <Link className="rh-icon-button rh-tv-link" to="/resident-board?mode=tv" title={t('home.tvViewHint')}>
              <HomeIcon name="monitor" />
              <span>{t('home.tvView')}</span>
            </Link>
          </div>
        </header>

        <main id="rh-main" tabIndex={-1}>
          <div className="rh-heading">
            <p className="rh-eyebrow">{localize(home?.eyebrow, lang) || t('home.eyebrow')}</p>
            <h1>{pageTitle}<span className="rh-dot">.</span></h1>
          </div>
          {rows.map(({ index, visible }) => (
            <div
              key={index}
              className={`rh-row rh-row--${index}${visible.length === 1 ? ' rh-row--single' : ''}`}
            >
              {visible.map((id) => <div key={id} className="rh-slot">{BLOCKS[id]()}</div>)}
            </div>
          ))}
        </main>

        <footer className="rh-footer">
          <span className="rh-footer-signature">
            <span className="rh-footer-leaf"><HomeIcon name="leaf" /></span>
            {orgName} · {localize(home?.tagline, lang) || t('home.footerTagline')}
          </span>
        </footer>
      </div>
      </div>
      <DetailDialog content={detail} onClose={closeDetail} />
    </div>
  )
}
