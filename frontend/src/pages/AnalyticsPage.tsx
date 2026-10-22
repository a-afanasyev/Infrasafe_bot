import { useState } from 'react'
import { useSearchParams } from 'react-router'
import { useTranslation } from 'react-i18next'
import { usePageTitle } from '../hooks/usePageTitle'
import { useCan } from '../hooks/useCan'
import {
  useAddressStats,
  useBacklog,
  useChannelStats,
  useCostStats,
  useExecutorStats,
  useQualityStats,
  useRequestStats,
  useShiftStats,
} from '../hooks/useAnalytics'
import AccessTabBar from '../components/access/AccessTabBar'
import LoadingSpinner from '../components/shared/LoadingSpinner'
import PeriodBar from '../components/analytics/PeriodBar'
import OverviewTab from '../components/analytics/OverviewTab'
import ExecutorsTab from '../components/analytics/ExecutorsTab'
import QualityTab from '../components/analytics/QualityTab'
import BacklogTab from '../components/analytics/BacklogTab'
import ChannelsTab from '../components/analytics/ChannelsTab'
import OfficialReportDialog from '../components/analytics/OfficialReportDialog'
import { todayInDisplayTz } from '../utils/timezone'
import {
  autoGranularity,
  daysInRange,
  isValidRange,
  presetRange,
  type DateRange,
  type Granularity,
  type PresetId,
} from '../utils/analyticsPeriod'

const TABS = ['overview', 'executors', 'quality', 'backlog', 'channels'] as const
type Tab = (typeof TABS)[number]
/** Дневной срез длиннее года не предлагается (см. PeriodBar). */
const DAY_SLICE_MAX_DAYS = 366

function ErrorBanner({ text }: { text: string }) {
  return (
    <div className="p-3 px-4 rounded-sm bg-red/10 border border-red/30 text-red text-[13px]">{text}</div>
  )
}

export default function AnalyticsPage() {
  const { t } = useTranslation()
  const canReport = useCan('requests.stats')
  usePageTitle(t('nav.analytics'))
  const [searchParams, setSearchParams] = useSearchParams()
  const tabParam = searchParams.get('tab')
  const tab: Tab = (TABS as readonly string[]).includes(tabParam ?? '') ? (tabParam as Tab) : 'overview'

  const [preset, setPreset] = useState<PresetId>('thisMonth')
  const [range, setRange] = useState<DateRange>(() => presetRange('thisMonth', todayInDisplayTz()))
  const [granularity, setGranularity] = useState<Granularity | null>(null)

  const valid = isValidRange(range)
  const activeRange = valid ? range : null
  const autoGran = valid ? autoGranularity(range) : 'day'
  // Ручной дневной срез сбрасывается на авто, если период вырос больше года.
  const gran = granularity === 'day' && valid && daysInRange(range) > DAY_SLICE_MAX_DAYS ? null : granularity
  const effectiveGran = gran ?? autoGran

  const onTab = (key: string) => {
    const next = new URLSearchParams(searchParams)
    if (key === 'overview') next.delete('tab')
    else next.set('tab', key)
    setSearchParams(next, { replace: true })
  }

  // Запросы только для открытой вкладки: остальные не грузят сервер зря.
  const overview = useRequestStats(tab === 'overview' ? activeRange : null, gran)
  const shifts = useShiftStats()
  const executors = useExecutorStats(tab === 'executors' ? activeRange : null)
  const quality = useQualityStats(tab === 'quality' ? activeRange : null)
  const addresses = useAddressStats(tab === 'backlog' ? activeRange : null)
  const backlog = useBacklog(tab === 'backlog')
  const channels = useChannelStats(tab === 'channels' ? activeRange : null, gran)
  const costs = useCostStats(tab === 'channels' ? activeRange : null)

  const current = {
    overview: [overview],
    executors: [executors],
    quality: [quality],
    backlog: [backlog, addresses],
    channels: [channels, costs],
  }[tab]
  const loading = valid && current.some(q => q.isLoading)
  const failed = current.some(q => q.isError)

  return (
    <div className="p-4 md:p-5 md:px-6 flex flex-col gap-4 min-w-0">
      <div className="flex flex-wrap items-start gap-2">
        <div className="flex-1 min-w-0 basis-[28rem]">
          <PeriodBar
            preset={preset}
            range={range}
            granularity={gran}
            effectiveGranularity={effectiveGran}
            showGranularity={tab === 'overview' || tab === 'channels'}
            onPreset={id => {
              setPreset(id)
              setRange(presetRange(id, todayInDisplayTz()))
            }}
            onCustom={next => {
              setPreset('custom')
              setRange(next)
            }}
            onGranularity={setGranularity}
          />
        </div>
        {canReport && <OfficialReportDialog range={activeRange} />}
      </div>

      <AccessTabBar
        tabs={TABS.map(key => ({ key, label: t(`analytics.tabs.${key}`) }))}
        active={tab}
        onChange={onTab}
      />

      {failed && <ErrorBanner text={t('analytics.loadError')} />}

      {loading ? (
        <LoadingSpinner />
      ) : (
        <>
          {tab === 'overview' && overview.data && (
            <OverviewTab stats={overview.data} onShiftNow={shifts.data?.active_executors ?? null} />
          )}
          {tab === 'executors' && executors.data && activeRange && (
            <ExecutorsTab rows={executors.data} range={activeRange} />
          )}
          {tab === 'quality' && quality.data && <QualityTab data={quality.data} />}
          {tab === 'backlog' && <BacklogTab backlog={backlog.data} addresses={addresses.data} />}
          {tab === 'channels' && <ChannelsTab channels={channels.data} costs={costs.data} />}
        </>
      )}
    </div>
  )
}
