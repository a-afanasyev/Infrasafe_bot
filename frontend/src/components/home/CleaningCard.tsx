import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { usePublicCleaningToday, type PublicCleaningHouse } from '../../hooks/usePublicCleaning'
import { formatTime } from '../../utils/timezone'

interface CleaningCardProps {
  title: string
}

interface YardGroup {
  key: number
  name: string
  houses: PublicCleaningHouse[]
}

/** «10G» после «9G», «Phase 10» после «Phase 2». */
const natural = (a: string, b: string): number => a.localeCompare(b, undefined, { numeric: true })

/** Общее начало адресов до последней «, » («Yangi Olmazor, ») — уходит в заголовок, на плитке остаётся номер дома. */
function commonPrefix(addresses: string[]): string {
  if (addresses.length < 2) return ''
  let prefix = addresses[0]
  for (const address of addresses) {
    while (!address.startsWith(prefix)) prefix = prefix.slice(0, -1)
  }
  const cut = prefix.lastIndexOf(', ')
  return cut < 0 ? '' : prefix.slice(0, cut + 2)
}

/** Дома по дворам (фазам комплекса); без двора в ответе — одна безымянная группа. */
function groupByYard(buildings: PublicCleaningHouse[]): YardGroup[] {
  const groups = new Map<number, YardGroup>()
  for (const house of buildings) {
    const key = house.yard_id ?? 0
    const group = groups.get(key) ?? { key, name: house.yard_name ?? '', houses: [] }
    groups.set(key, { ...group, houses: [...group.houses, house] })
  }
  return [...groups.values()]
    .map((group) => ({ ...group, houses: [...group.houses].sort((a, b) => natural(a.address, b.address)) }))
    .sort((a, b) => natural(a.name, b.name))
}

// «Уборка» на странице жителей: «убрано N из M домов», полоса хода и плитка на
// каждый дом, сгруппированные по дворам (фазам). Счёт по домам, не по подъездам:
// дом убран, когда приняты все его задания дня. Подъезды и фото — на
// странице-обзоре /cleaning. Данные — открытая сводка модуля «Уборка»; имён
// сотрудников и причин проверки в ней нет.
export default function CleaningCard({ title }: CleaningCardProps) {
  const { t } = useTranslation()
  const { data } = usePublicCleaningToday()
  // Пока менеджер не включил показ ни одного дома, жителям блок не виден вовсе.
  if (data && (!data.enabled || data.buildings.length === 0)) return null
  const total = data?.buildings_total ?? 0
  const done = data?.buildings_done ?? 0
  const groups = groupByYard(data?.buildings ?? [])
  const prefix = commonPrefix((data?.buildings ?? []).map((b) => b.address))
  const heading = `${title || t('home.cleaning.title')}${prefix ? ` · ${prefix.slice(0, -2)}` : ''}`

  return (
    <section className="rh-card rh-cleaning" aria-labelledby="rh-cleaning-heading">
      <div className="rh-section-heading">
        <div>
          <h2 id="rh-cleaning-heading">{heading}</h2>
          <p>{t('home.cleaning.sub')}</p>
        </div>
        {data && <Link className="rh-small-action" to="/cleaning">{t('home.cleaning.all')} →</Link>}
      </div>
      {!data ? (
        <p className="rh-empty">—</p>
      ) : (
        <>
          {total === 0 ? (
            <span className="rh-metric-caption">{t('home.cleaning.empty')}</span>
          ) : (
            <div className="rh-cleaning-top">
              <span className="rh-metric-number rh-cleaning-number">
                {done}<span> / {total}</span>
              </span>
              <div className="rh-cleaning-progress">
                <div className="rh-clean-progress" role="progressbar" aria-valuemin={0} aria-valuemax={total} aria-valuenow={done}>
                  <span style={{ width: `${(done / total) * 100}%` }} />
                </div>
                <span className="rh-metric-caption">{t('home.cleaning.done')}</span>
              </div>
            </div>
          )}
          <div className="rh-cleaning-groups">
            {groups.map((group) => {
              const scheduled = group.houses.filter((h) => h.state !== 'none')
              const cleaned = scheduled.filter((h) => h.state === 'done').length
              const allDone = scheduled.length > 0 && cleaned === scheduled.length
              return (
                <section key={group.key} className="rh-cleaning-group">
                  {groups.length > 1 && (
                    <h3 className="rh-cleaning-group-head">
                      {group.name}
                      {scheduled.length > 0 && (
                        <span className={allDone ? 'rh-cleaning-group-all' : undefined}>
                          {allDone
                            ? t('home.cleaning.groupAll', { count: cleaned })
                            : t('home.cleaning.groupCount', { done: cleaned, total: scheduled.length })}
                        </span>
                      )}
                    </h3>
                  )}
                  <ul className={`rh-cleaning-tiles${prefix ? '' : ' rh-cleaning-tiles--wide'}`}>
                    {group.houses.map((house) => {
                      const time = house.done_at ? formatTime(house.done_at) : ''
                      return (
                        <li
                          key={house.building_id}
                          className={`rh-cleaning-tile rh-cleaning-tile--${house.state}`}
                          title={`${house.address} — ${t(`home.cleaning.state.${house.state}`)}${time ? ` · ${time}` : ''}`}
                        >
                          <strong>{house.address.slice(prefix.length)}</strong>
                          <span>{time ? `✓ ${time}` : t(`home.cleaning.tile.${house.state}`)}</span>
                        </li>
                      )
                    })}
                  </ul>
                </section>
              )
            })}
          </div>
          <span className="rh-metric-caption">{t('home.cleaning.rule')}</span>
        </>
      )}
    </section>
  )
}
