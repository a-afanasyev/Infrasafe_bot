import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router'
import { useTranslation } from 'react-i18next'
import { useBoardConfig } from '../hooks/useBoardConfig'
import { usePageTitle } from '../hooks/usePageTitle'
import {
  publicCleaningPhotoUrl,
  usePublicCleaningToday,
  type PublicCleaningHouse,
} from '../hooks/usePublicCleaning'
import { defaultBoardConfig } from '../types/boardConfig'
import { formatTime } from '../utils/timezone'
import { botHandle } from '../components/home/homeFormat'
import HomeIcon from '../components/home/HomeIcon'
import './ResidentHomePage.css'

/**
 * «Уборка домов» — открытый обзор по всем домам (/cleaning): статус дома и
 * каждого подъезда за сегодня и миниатюры фото, которые открываются по нажатию.
 * Сюда ведёт блок «Уборка» со страницы жителей. Данные — та же открытая сводка
 * (GET /api/v2/public/cleaning/today): только дома, показанные жителям, «убрано»
 * только у принятого задания, фото — только там, где менеджер включил их показ.
 */

interface Shot {
  id: number
  label: string
}

function PhotoViewer({ shot, onClose }: { shot: Shot | null; onClose: () => void }) {
  const { t } = useTranslation()
  const closeRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    if (!shot) return
    const returnTo = document.activeElement as HTMLElement | null
    closeRef.current?.focus()
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('keydown', onKey)
      returnTo?.focus?.()
    }
  }, [shot, onClose])

  if (!shot) return null
  return (
    <div className="rh-dialog-backdrop" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div className="rh-dialog rh-clean-viewer" role="dialog" aria-modal="true" aria-label={shot.label}>
        <div className="rh-dialog-top">
          <span className="rh-dialog-kicker">{shot.label}</span>
          <button ref={closeRef} type="button" className="rh-icon-button rh-dialog-close" aria-label={t('home.close')} onClick={onClose}>
            <HomeIcon name="close" />
          </button>
        </div>
        {/* Оригинал не пришёл (медиа-сервис занят) — показываем уже загруженное превью. */}
        <img
          src={publicCleaningPhotoUrl(shot.id, true)} alt={shot.label}
          onError={(e) => {
            const preview = publicCleaningPhotoUrl(shot.id)
            if (!e.currentTarget.src.endsWith(preview)) e.currentTarget.src = preview
          }}
        />
      </div>
    </div>
  )
}

function HouseCard({ house, onOpen }: { house: PublicCleaningHouse; onOpen: (shot: Shot) => void }) {
  const { t } = useTranslation()
  // Подъезд — одна строка; фото грузятся, только когда его раскрыли.
  const [open, setOpen] = useState<number | null>(null)
  return (
    <article className={`rh-card rh-clean-house rh-clean-house--${house.state}`}>
      <header>
        <h2>{house.address}</h2>
        <span className="rh-clean-state">
          {t(`home.cleaning.state.${house.state}`)}{house.done_at ? ` · ${formatTime(house.done_at)}` : ''}
        </span>
      </header>
      <ul>
        {house.entrances.map((entrance) => (
          <li key={entrance.entrance} className={`rh-clean-entrance rh-clean-entrance--${entrance.state}`}>
            <div className="rh-clean-entrance-line">
              <strong>{t('home.cleaning.entrance', { n: entrance.entrance })}</strong>
              <span>
                {entrance.state === 'done' && entrance.done_at
                  ? t('home.cleaning.doneAt', { time: formatTime(entrance.done_at) })
                  : t(`home.cleaning.entranceState.${entrance.state}`)}
              </span>
              {entrance.photo_ids.length > 0 && (
                <button
                  type="button" className="rh-small-action" aria-expanded={open === entrance.entrance}
                  onClick={() => setOpen(open === entrance.entrance ? null : entrance.entrance)}
                >
                  {t(open === entrance.entrance ? 'home.cleaning.less' : 'home.cleaning.more', { count: entrance.photo_ids.length })}
                </button>
              )}
            </div>
            {open === entrance.entrance && entrance.photo_ids.length > 0 && (
              <div className="rh-clean-thumbs">
                {entrance.photo_ids.map((id, index) => {
                  const label = t('home.cleaning.photoAlt', { address: house.address, n: entrance.entrance, i: index + 1 })
                  return (
                    <button key={id} type="button" className="rh-clean-thumb" aria-label={label} onClick={() => onOpen({ id, label })}>
                      <img
                        src={publicCleaningPhotoUrl(id)} alt="" loading="lazy"
                        onError={(e) => { e.currentTarget.style.visibility = 'hidden' }}
                      />
                    </button>
                  )
                })}
              </div>
            )}
          </li>
        ))}
      </ul>
    </article>
  )
}

export default function ResidentCleaningPage() {
  const { t } = useTranslation()
  usePageTitle(t('home.cleaning.title'))
  const { data, isLoading, isError } = usePublicCleaningToday()
  const { data: config } = useBoardConfig()
  const [shot, setShot] = useState<Shot | null>(null)
  const closeShot = useCallback(() => setShot(null), [])
  const bot = botHandle(config?.bot?.username ?? defaultBoardConfig.bot.username)

  const houses = data?.enabled ? data.buildings : []
  const total = data?.buildings_total ?? 0
  const done = data?.buildings_done ?? 0

  return (
    <div className="rh">
      <div className="rh-frame">
        <div className="rh-shell rh-clean-shell">
          <header className="rh-header rh-clean-header">
            <Link className="rh-small-action" to="/home">← {t('home.cleaning.back')}</Link>
            <div className="rh-heading">
              <h1>{t('home.cleaning.title')}<span className="rh-dot">.</span></h1>
              <p className="rh-clean-sub">{t('home.cleaning.sub')}</p>
            </div>
          </header>

          <main className="rh-clean-main">
            {isLoading && <p className="rh-empty">{t('common.loading')}</p>}
            {isError && <p className="rh-empty" role="alert">{t('home.cleaning.loadError')}</p>}
            {data && houses.length === 0 && <p className="rh-empty">{t('home.cleaning.noHouses')}</p>}

            {houses.length > 0 && (
              <>
                <section className="rh-card rh-clean-summary" aria-label={t('home.cleaning.done')}>
                  <div>
                    <span className="rh-metric-number rh-cleaning-number">{done}<span> / {total}</span></span>
                    <span className="rh-metric-caption">{t('home.cleaning.done')}</span>
                  </div>
                  <div className="rh-clean-progress-wrap">
                    <div className="rh-clean-progress" role="progressbar" aria-valuemin={0} aria-valuemax={total} aria-valuenow={done}>
                      <span style={{ width: `${total > 0 ? (done / total) * 100 : 0}%` }} />
                    </div>
                    <p className="rh-metric-caption">{t('home.cleaning.rule')}</p>
                  </div>
                </section>

                <div className="rh-clean-grid">
                  {houses.map((house) => <HouseCard key={house.building_id} house={house} onOpen={setShot} />)}
                </div>

                <section className="rh-clean-complain">
                  <p>{t('home.cleaning.complainQuestion')}</p>
                  <a className="rh-clean-complain-button" href={`https://t.me/${bot}`} target="_blank" rel="noopener noreferrer">
                    {t('home.cleaning.complainBot')}
                  </a>
                </section>
              </>
            )}
          </main>
        </div>
      </div>
      <PhotoViewer shot={shot} onClose={closeShot} />
    </div>
  )
}
