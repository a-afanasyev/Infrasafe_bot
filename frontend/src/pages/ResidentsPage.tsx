import { useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useTopbar } from '../contexts/topbar'
import { useResidents, useResidentStats, useResidentsWebSocket } from '../hooks/useResidents'
import type { ResidentFilters } from '../hooks/useResidents'
import { useYards, useAllBuildings, useAllApartments } from '../hooks/useAddresses'
import ResidentCard from '../components/residents/ResidentCard'
import ResidentTable from '../components/residents/ResidentTable'
import EmptyState from '../components/shared/EmptyState'
import LoadingSpinner from '../components/shared/LoadingSpinner'
import { usePageTitle } from '../hooks/usePageTitle'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import { cn } from '@/lib/utils'

const PAGE_SIZE = 25

export default function ResidentsPage() {
  const { t } = useTranslation()
  usePageTitle(t('nav.residents'))
  const { setActions, clearActions } = useTopbar()
  useResidentsWebSocket()

  const [statusFilter, setStatusFilter] = useState<string>('all')
  const [verificationFilter, setVerificationFilter] = useState<string>('all')
  const [yardId, setYardId] = useState<number | null>(null)
  const [buildingId, setBuildingId] = useState<number | null>(null)
  const [apartmentId, setApartmentId] = useState<number | null>(null)
  const [search, setSearch] = useState<string>('')
  const [offset, setOffset] = useState(0)
  const [viewMode, setViewMode] = useState<'tile' | 'table'>(() => {
    try {
      const stored = localStorage.getItem('residents_view_mode')
      return (stored === 'tile' || stored === 'table') ? stored : 'tile'
    } catch { return 'tile' }
  })

  useEffect(() => {
    try { localStorage.setItem('residents_view_mode', viewMode) } catch { /* localStorage недоступен — режим отображения не персистим */ }
  }, [viewMode])

  // Любая смена фильтра возвращает на первую страницу: иначе offset от прошлой
  // выдачи попадает в новую и пользователь видит пустой экран при непустом
  // результате. Сброс делается в обработчиках, а не в эффекте: setState внутри
  // эффекта даёт каскадный ререндер (и запрещён линтером).
  const withPageReset = <T,>(set: (v: T) => void) => (v: T) => {
    set(v)
    setOffset(0)
  }

  const onStatusChange = withPageReset(setStatusFilter)
  const onVerificationChange = withPageReset(setVerificationFilter)

  const onYardChange = (v: number | null) => {
    setYardId(v)
    setBuildingId(null)
    setApartmentId(null)
    setOffset(0)
  }
  const onBuildingChange = (v: number | null) => {
    setBuildingId(v)
    setApartmentId(null)
    setOffset(0)
  }
  const onApartmentChange = withPageReset(setApartmentId)

  const filters: ResidentFilters = {
    ...(statusFilter !== 'all' ? { status: statusFilter } : {}),
    ...(verificationFilter !== 'all' ? { verification_status: verificationFilter } : {}),
    ...(apartmentId !== null ? { apartment_id: apartmentId } : {}),
    ...(apartmentId === null && buildingId !== null ? { building_id: buildingId } : {}),
    ...(apartmentId === null && buildingId === null && yardId !== null ? { yard_id: yardId } : {}),
  }

  const { data, isLoading, isError } = useResidents(
    filters,
    search || undefined,
    { limit: PAGE_SIZE, offset },
  )
  const { data: stats } = useResidentStats()

  // Каскад: дома фильтруются двором, квартиры — домом; выбор верхнего уровня
  // сбрасывает нижние (как AddressBreadcrumb).
  const { data: yards = [] } = useYards()
  const { data: buildings = [] } = useAllBuildings(yardId)
  const { data: apartments = [] } = useAllApartments(yardId, buildingId)

  // Поле поиска НЕконтролируемое (defaultValue + debounce), и узел мемоизирован
  // БЕЗ зависимости от `search` — иначе набранный символ стирается.
  //
  // Почему: топбар получает узел не напрямую, а через состояние контекста,
  // которое обновляется в useEffect — то есть ВТОРЫМ коммитом. У контролируемого
  // поля React в фазе обработки события сверяет DOM-значение с последним
  // отрендеренным `value` (всё ещё старым) и откатывает DOM. Замерено на живом
  // profk: после `input` значение в DOM = "", и только через тик появляется
  // набранный символ — при обычной скорости печати символы теряются
  // («админ» → «амн»). Дефект общий для всех страниц с поиском в топбаре
  // (воспроизведён на «Сотрудниках»), здесь лечится локально.
  //
  // Debounce 300мс заодно убирает запрос на каждое нажатие.
  const searchTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  useEffect(() => () => clearTimeout(searchTimer.current), [])

  const actionsNode = useMemo(() => (
    <Input
      type="text"
      placeholder={t('residents.searchPlaceholder')}
      defaultValue=""
      onChange={e => {
        const value = e.target.value
        clearTimeout(searchTimer.current)
        searchTimer.current = setTimeout(() => {
          setSearch(value)
          setOffset(0)
        }, 300)
      }}
      className="w-[220px]"
    />
  ), [t])

  useEffect(() => {
    setActions(actionsNode)
    return clearActions
  }, [setActions, clearActions, actionsNode])

  const STATS = [
    { label: t('residents.statsTotal'), value: stats?.total ?? '-', iconBg: 'var(--blue)', icon: '👥' },
    { label: t('residents.statsPending'), value: stats?.pending ?? '-', iconBg: 'var(--amber)', icon: '⏳' },
    { label: t('residents.statsVerificationRequested'), value: stats?.verification_requested ?? '-', iconBg: 'var(--violet)', icon: '📄' },
    { label: t('residents.statsBlocked'), value: stats?.blocked ?? '-', iconBg: 'var(--red)', icon: '⛔' },
  ]

  const items = data?.items ?? []
  const total = data?.total ?? 0

  return (
    <div className="p-5 px-6 flex flex-col gap-5">
      {/* Stats bar */}
      <div className="grid grid-cols-4 gap-3">
        {STATS.map(card => (
          <div
            key={card.label}
            className="bg-bg-card border border-border-default rounded-default p-4 flex items-center gap-3.5"
          >
            <div
              className="w-12 h-12 rounded-xl flex items-center justify-center text-[22px] shrink-0"
              style={{ background: card.iconBg + '22' }}
            >
              {card.icon}
            </div>
            <div>
              <div className="font-[family-name:var(--font-mono)] text-[22px] font-semibold text-text-primary">
                {card.value}
              </div>
              <div className="text-[11px] text-text-muted mt-0.5">{card.label}</div>
            </div>
          </div>
        ))}
      </div>

      {/* Filters */}
      <div className="flex flex-col gap-2">
        <div className="flex items-center gap-1.5 flex-wrap">
          {[
            { key: 'all', label: t('residents.filterStatus') },
            { key: 'pending', label: t('residents.accountStatus.pending') },
            { key: 'approved', label: t('residents.accountStatus.approved') },
            { key: 'blocked', label: t('residents.accountStatus.blocked') },
          ].map(f => (
            <button
              key={f.key}
              onClick={() => onStatusChange(f.key)}
              className={cn(
                'rounded-full cursor-pointer text-xs px-3 py-1.5 font-[family-name:var(--font-display)] transition-all duration-150 border',
                statusFilter === f.key
                  ? 'bg-accent border-accent text-white font-semibold'
                  : 'bg-bg-card border-border-default text-text-secondary font-normal',
              )}
            >
              {f.label}
            </button>
          ))}
          <div className="w-px h-6 bg-border-default mx-0.5" />
          {[
            { key: 'all', label: t('residents.filterVerification') },
            { key: 'pending', label: t('residents.verification.pending') },
            { key: 'requested', label: t('residents.verification.requested') },
            { key: 'verified', label: t('residents.verification.verified') },
            { key: 'rejected', label: t('residents.verification.rejected') },
          ].map(f => (
            <button
              key={f.key}
              onClick={() => onVerificationChange(f.key)}
              className={cn(
                'rounded-full cursor-pointer text-xs px-3 py-1.5 font-[family-name:var(--font-display)] transition-all duration-150 border',
                verificationFilter === f.key
                  ? 'bg-accent border-accent text-white font-semibold'
                  : 'bg-bg-card border-border-default text-text-secondary font-normal',
              )}
            >
              {f.label}
            </button>
          ))}
          <div className="flex-1" />
          <div className="flex bg-bg-card border border-border-default rounded-sm overflow-hidden shrink-0">
            {(['tile', 'table'] as const).map(mode => (
              <button
                key={mode}
                onClick={() => setViewMode(mode)}
                title={mode === 'tile' ? t('residents.viewTile') : t('residents.viewTable')}
                className={cn(
                  'px-3 py-1.5 border-none cursor-pointer text-base flex items-center transition-all duration-150',
                  viewMode === mode ? 'bg-accent text-white' : 'bg-transparent text-text-muted',
                )}
              >
                {mode === 'tile' ? '⊞' : '☰'}
              </button>
            ))}
          </div>
        </div>

        {/* Address cascade */}
        <div className="flex items-center gap-2 flex-wrap">
          <Select
            value={yardId ?? ''}
            onChange={e => onYardChange(e.target.value ? Number(e.target.value) : null)}
            className="w-[220px] text-xs"
          >
            <option value="">{t('residents.allYards')}</option>
            {yards.map(y => <option key={y.id} value={y.id}>{y.name}</option>)}
          </Select>
          <Select
            value={buildingId ?? ''}
            onChange={e => onBuildingChange(e.target.value ? Number(e.target.value) : null)}
            className="w-[220px] text-xs"
          >
            <option value="">{t('residents.allBuildings')}</option>
            {buildings.map(b => <option key={b.id} value={b.id}>{b.address}</option>)}
          </Select>
          <Select
            value={apartmentId ?? ''}
            onChange={e => onApartmentChange(e.target.value ? Number(e.target.value) : null)}
            className="w-[180px] text-xs"
          >
            <option value="">{t('residents.allApartments')}</option>
            {apartments.map(a => (
              <option key={a.id} value={a.id}>{a.apartment_number}</option>
            ))}
          </Select>
        </div>
      </div>

      {/* List */}
      {isLoading ? (
        <LoadingSpinner />
      ) : isError ? (
        <div className="flex-1 flex items-center justify-center text-text-muted">
          {t('common.error')}
        </div>
      ) : viewMode === 'table' ? (
        <ResidentTable residents={items} />
      ) : items.length === 0 ? (
        // offset > 0 при пустой выдаче = страница уехала за конец списка
        // (polling сократил total, пока менеджер стоял на дальней странице).
        // Показываем не «ничего не найдено», а способ вернуться.
        <EmptyState
          icon="👥"
          title={offset > 0 ? t('residents.pageOutOfRange') : t('residents.notFound')}
          subtitle={offset > 0 ? t('residents.pageOutOfRangeDesc') : t('residents.notFoundDesc')}
          action={offset > 0 ? (
            <Button variant="outline" size="sm" onClick={() => setOffset(0)}>
              {t('residents.toFirstPage')}
            </Button>
          ) : undefined}
        />
      ) : (
        <div className="grid grid-cols-[repeat(auto-fill,minmax(320px,1fr))] gap-4">
          {items.map(r => <ResidentCard key={r.id} resident={r} />)}
        </div>
      )}

      {/* Pagination */}
      {total > PAGE_SIZE && (
        <div className="flex items-center justify-center gap-3">
          <Button
            variant="outline"
            size="sm"
            disabled={offset === 0}
            onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
          >
            {t('common.back')}
          </Button>
          <span className="text-xs text-text-muted font-[family-name:var(--font-mono)]">
            {offset + 1}–{Math.min(offset + PAGE_SIZE, total)} / {total}
          </span>
          <Button
            variant="outline"
            size="sm"
            disabled={offset + PAGE_SIZE >= total}
            onClick={() => setOffset(offset + PAGE_SIZE)}
          >
            {t('common.next')}
          </Button>
        </div>
      )}
    </div>
  )
}
