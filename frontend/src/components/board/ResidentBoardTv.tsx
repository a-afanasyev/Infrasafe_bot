import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { brand } from '../../brand/brand'
import { useDisplayTz } from '../../contexts/displayTz'
import { tCategory } from '../../i18n/apiMaps'
import type { PublicBoardData } from '../../hooks/usePublicBoard'
import type { BoardConfigData, LocalizedText } from '../../types/boardConfig'
import ContactCard from '../home/ContactCard'
import DetailDialog, { type DetailContent } from '../home/DetailDialog'
import HomeIcon from '../home/HomeIcon'
import NoticeCarousel from '../home/NoticeCarousel'
import { localize, resolveHomeBlocks } from '../home/homeConfig'
import { BOARD_STATUSES, boardClock, boardDate } from './boardDisplay'
import '../../pages/ResidentHomePage.css'
import './residentBoardTv.css'

// ТВ-режим табло: те же блоки и стиль, что у главной жителей (/home), но в один
// экран 16:9 без прокрутки. Объявления крутит NoticeCarousel (автосмена, точки,
// пауза), контакты и QR — ContactCard; своё здесь только сводка и шесть статусов.
const TV_SLIDE_INTERVAL_MS = 15_000
const STALE_AFTER_MS = 120_000

interface Props {
  board?: PublicBoardData
  config?: BoardConfigData
  now: Date
  updatedAt: number
  isError: boolean
  configError: boolean
}

function useOnline() {
  const [online, setOnline] = useState(() => navigator.onLine)
  useEffect(() => {
    const off = () => setOnline(false)
    const on = () => setOnline(true)
    window.addEventListener('offline', off)
    window.addEventListener('online', on)
    return () => {
      window.removeEventListener('offline', off)
      window.removeEventListener('online', on)
    }
  }, [])
  return online
}

export default function ResidentBoardTv({ board, config, now, updatedAt, isError, configError }: Props) {
  const { t, i18n } = useTranslation()
  const tz = useDisplayTz()
  const online = useOnline()
  const [detail, setDetail] = useState<DetailContent | null>(null)
  const closeDetail = useCallback(() => setDetail(null), [])
  const lang = i18n.language.startsWith('uz') ? 'uz' : 'ru'
  const loc = (text?: LocalizedText) => text?.[lang] || text?.ru || ''
  const visible = (id: string) => !!config?.layout.some(item => item.id === id && item.visible)
  const blocks = config ? resolveHomeBlocks(config, lang) : null

  const counts = board?.status_counts
  const totalActive = counts ? BOARD_STATUSES.slice(0, 4).reduce((sum, s) => sum + (counts[s.status] ?? 0), 0) : null
  // Та же цифра, что на главной жителей: решённые за бизнес-месяц (бэк фильтрует по completed_at).
  const totalDone = board ? board.completed_month ?? 0 : null
  const noData = t('board.tv.noData')
  const stale = !!updatedAt && now.getTime() - updatedAt > STALE_AFTER_MS
  const interrupted = !online || isError || stale
  const updated = updatedAt ? t('board.tv.updated', { time: boardClock(new Date(updatedAt), tz, true) }) : t('board.tv.loading')
  const metrics = [
    { key: 'active', label: t('board.stats.activeRequests'), value: totalActive },
    { key: 'done', label: t('board.stats.completedMonth'), value: totalDone },
    { key: 'avg', label: t('board.stats.avgResolution'), value: board?.avg_resolution_hours == null ? null : `${board.avg_resolution_hours.toFixed(1)} ${t('analytics.h')}` },
    { key: 'shift', label: t('board.stats.specialistsOnShift'), value: board?.active_executors },
  ]
  const age = (createdAt: string) => {
    const minutes = Math.floor((now.getTime() - new Date(createdAt).getTime()) / 60_000)
    if (!Number.isFinite(minutes)) return noData
    if (minutes < 60) return t('board.elapsed.min', { count: Math.max(0, minutes) })
    if (minutes < 1440) return t('board.elapsed.hours', { count: Math.floor(minutes / 60) })
    return t('board.elapsed.days', { count: Math.floor(minutes / 1440) })
  }
  const orgName = loc(config?.org.name) || brand.displayName
  const complexName = localize(config?.home?.complex_name, lang)
  const announcements = (config?.announcements ?? []).filter(a => loc(a.title))

  return (
    <div className="rh rb-tv" data-testid="resident-board-tv">
      <div className="rh-frame rb-tv-frame">
        <div className="rh-shell rb-tv-shell">
          <header className="rh-header">
            <div className="rh-brand">
              <img src={`${import.meta.env.BASE_URL}${brand.logoMark}`} width={49} height={49} alt="" />
              <span className="rh-brand-type">
                <b>{orgName}<span className="rh-dot">.</span></b>
                <span>{loc(config?.org.subtitle) || (config ? t('home.management') : t(configError ? 'board.tv.configUnavailable' : 'board.tv.loading'))}</span>
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
                <time>{boardClock(now, tz)}</time>
                <div><span>{boardDate(now, tz, t)}</span></div>
              </div>
            </div>
          </header>

          <main>
            {(visible('announcements') || !config) && (
              <div className="rh-row rb-tv-row rb-tv-row--1">
                <div className="rh-slot">
                  <NoticeCarousel announcements={announcements} title={blocks?.announcements.title} lang={lang} onOpen={setDetail} intervalMs={TV_SLIDE_INTERVAL_MS} />
                </div>
                {config && <div className="rh-slot"><ContactCard config={config} title={blocks?.contacts.title ?? ''} lang={lang} /></div>}
              </div>
            )}
            {!config && <p className="rh-card rb-tv-empty">{t(configError ? 'board.tv.configUnavailable' : 'board.tv.loading')}</p>}
            {(visible('stats') || visible('requests')) && (
              <div className={`rh-row rb-tv-row rb-tv-row--2${visible('stats') && visible('requests') ? '' : ' rh-row--single'}`}>
                {visible('stats') && (
                  <section className="rh-card rh-requests rb-tv-kpi" aria-label={t('board.tv.summary')}>
                    <div className="rh-section-heading"><div><h2>{t('board.tv.summary')}</h2><p>{t('home.requestsSub')}</p></div></div>
                    <div className="rb-tv-kpi-grid">
                      {metrics.map(m => (
                        <div className={`rh-metric rb-tv-metric rb-tv-metric--${m.key}`} key={m.key}>
                          <span className="rh-metric-label"><span className="rh-status-dot" />{m.label}</span>
                          <span className={m.value == null ? 'rh-metric-number rb-tv-empty-value' : 'rh-metric-number'}>{m.value ?? noData}</span>
                        </div>
                      ))}
                    </div>
                  </section>
                )}
                {visible('requests') && (
                  <section className="rh-card rh-requests rb-tv-requests" aria-label={t('board.sections.currentRequests')}>
                    <div className="rh-section-heading">
                      <div><h2>{t('board.sections.currentRequests')}</h2><p>{t('board.tv.requestsNote')}</p></div>
                      <span className="rh-small-action rh-small-action--active">{totalActive == null ? noData : t('board.sections.activeCount', { count: totalActive })}</span>
                    </div>
                    <div className="rb-tv-pipeline">
                      {BOARD_STATUSES.map(step => {
                        const rows = (board?.active_requests ?? []).filter(r => r.status === step.status)
                        const count = counts?.[step.status]
                        const first = rows[0]
                        const caption = step.key === 'executed' ? t('board.tv.awaitingAcceptance') : step.key === 'approved' ? t('board.tv.accepted')
                          : first ? `${tCategory(first.category, t)} · ${age(first.created_at)}` : count === 0 ? t('board.tv.none') : ''
                        return (
                          <div className="rh-metric rb-tv-metric rb-tv-stage" key={step.status} style={{ '--stage-color': step.color } as React.CSSProperties}>
                            <span className="rh-metric-label"><span className="rh-status-dot" />{t(`board.pipeline.${step.key}`)}</span>
                            <span className={count == null ? 'rh-metric-number rb-tv-empty-value' : 'rh-metric-number'}>{count ?? noData}</span>
                            <span className="rh-metric-caption">{caption}</span>
                          </div>
                        )
                      })}
                    </div>
                  </section>
                )}
              </div>
            )}
          </main>

          <footer className={interrupted || configError ? 'rh-footer rb-tv-footer rb-tv-warning' : 'rh-footer rb-tv-footer'}>
            <span className="rh-footer-signature">
              <span className="rh-footer-leaf"><HomeIcon name="leaf" /></span>
              {orgName} · {localize(config?.home?.tagline, lang) || t('home.footerTagline')}
            </span>
            <span className="rb-tv-status">
              {interrupted ? t(updatedAt ? 'board.tv.interrupted' : 'board.tv.unavailable') : updated}{interrupted && updatedAt > 0 && ` · ${updated}`}{configError && ` · ${t('board.tv.configUnavailable')}`}
            </span>
            <Link to="/resident-board">{t('board.tv.pageMode')}</Link>
          </footer>
        </div>
      </div>
      <DetailDialog content={detail} onClose={closeDetail} />
    </div>
  )
}
