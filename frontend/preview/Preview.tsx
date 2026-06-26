import { useState } from 'react'
import { ShieldCheck, History, Database, Camera } from 'lucide-react'

import AccessTabBar from '@/components/access/AccessTabBar'
import ManualReviewQueue from '@/components/access/ManualReviewQueue'
import AccessEventsTable from '@/components/access/AccessEventsTable'
import AccessEventsFilters from '@/components/access/AccessEventsFilters'
import AccessPagination from '@/components/access/AccessPagination'
import VehiclesTable from '@/components/access/VehiclesTable'
import PassesTable from '@/components/access/PassesTable'
import RequestsTable from '@/components/access/RequestsTable'
import AccessPhotos from '@/components/access/AccessPhotos'
import type { AccessEventsFilters as Filters } from '@/types/access'

import LiveFeedPreview from './LiveFeedPreview'
import { liveEvents, historyEvents, vehicles, passes, requests, eventDetail } from './mockData'

/**
 * STANDALONE-превью трёх экранов контроля доступа на синтетических мок-данных.
 * Реальные презентационные компоненты переиспользуются как есть; ManualReviewQueue
 * (TanStack-Query) питается предзаполненным кэшем (см. main.tsx); live-лента —
 * тонкая копия (WS-хук) в LiveFeedPreview. Без сети, без auth, без бэкенда.
 */

function SectionHeader({
  icon,
  title,
  subtitle,
}: {
  icon: React.ReactNode
  title: string
  subtitle: string
}) {
  return (
    <div className="flex items-center gap-2.5">
      <span className="text-accent">{icon}</span>
      <div>
        <h1 className="text-xl font-semibold text-text-primary">{title}</h1>
        <p className="text-[13px] text-text-muted">{subtitle}</p>
      </div>
    </div>
  )
}

function SubLabel({ children }: { children: React.ReactNode }) {
  return (
    <p className="text-[11px] font-semibold uppercase tracking-wider text-text-muted">{children}</p>
  )
}

// ── (A) Пост охраны ──────────────────────────────────────────────────────────
function SecurityPostSection() {
  return (
    <section className="flex flex-col gap-5">
      <SectionHeader
        icon={<ShieldCheck size={22} />}
        title="Пост охраны"
        subtitle="Live-лента, очередь ручной проверки и история"
      />
      <div>
        <SubLabel>Live-лента</SubLabel>
        <div className="mt-2">
          <LiveFeedPreview events={liveEvents} />
        </div>
      </div>
      <div>
        <SubLabel>Очередь ручной проверки</SubLabel>
        <div className="mt-2">
          <ManualReviewQueue />
        </div>
      </div>
      <div>
        <SubLabel>Последние события</SubLabel>
        <div className="mt-2">
          <AccessEventsTable events={historyEvents.slice(0, 4)} />
        </div>
      </div>
    </section>
  )
}

// ── (B) История проездов ─────────────────────────────────────────────────────
function HistorySection() {
  const [filters, setFilters] = useState<Filters>({ limit: 10, offset: 0 })
  const patch = (p: Partial<Filters>) => setFilters((prev) => ({ ...prev, ...p, offset: 0 }))
  return (
    <section className="flex flex-col gap-5">
      <SectionHeader
        icon={<History size={22} />}
        title="История проездов"
        subtitle="События доступа с фильтрами и детализацией"
      />
      <AccessEventsFilters filters={filters} onChange={patch} extended />
      <AccessEventsTable events={historyEvents} />
      <AccessPagination total={128} limit={10} offset={0} onOffsetChange={() => {}} />
    </section>
  )
}

// ── (C) База доступа ─────────────────────────────────────────────────────────
function DatabaseSection() {
  const [tab, setTab] = useState('vehicles')
  const tabs = [
    { key: 'vehicles', label: 'Автомобили' },
    { key: 'passes', label: 'Пропуска' },
    { key: 'requests', label: 'Заявки' },
  ]
  return (
    <section className="flex flex-col gap-5">
      <SectionHeader
        icon={<Database size={22} />}
        title="База доступа"
        subtitle="Автомобили, пропуска и заявки жителей"
      />
      <AccessTabBar tabs={tabs} active={tab} onChange={setTab} />
      {/* Для скриншота показываем все три таба сразу, под подписями. */}
      <div className="flex flex-col gap-5">
        <div>
          <SubLabel>Автомобили</SubLabel>
          <div className="mt-2">
            <VehiclesTable vehicles={vehicles} />
          </div>
        </div>
        <div>
          <SubLabel>Пропуска</SubLabel>
          <div className="mt-2">
            <PassesTable passes={passes} />
          </div>
        </div>
        <div>
          <SubLabel>Заявки</SubLabel>
          <div className="mt-2">
            <RequestsTable requests={requests} />
          </div>
        </div>
      </div>
    </section>
  )
}

// ── (A2) Деталь события: крупные фото авто + номера рядом с контекстом ────────
function Ctx({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[10px] font-bold uppercase tracking-wider text-text-muted">{label}</span>
      <span className="text-[13px] text-text-primary">{value}</span>
    </div>
  )
}

function EventDetailSection() {
  const ev = eventDetail.camera_event
  return (
    <section className="flex flex-col gap-5">
      <SectionHeader
        icon={<Camera size={22} />}
        title="Деталь события"
        subtitle="Фото проезда (обзор + номер) и контекст камеры"
      />
      <div className="rounded-default border border-border-default bg-bg-card p-5 flex flex-col gap-5">
        <div>
          <SubLabel>Фото проезда</SubLabel>
          <div className="mt-2">
            <AccessPhotos
              size="full"
              overviewUrl={ev.overview_photo_url}
              plateUrl={ev.plate_photo_url}
            />
          </div>
        </div>
        <div>
          <SubLabel>Контекст камеры</SubLabel>
          <div className="mt-2 grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Ctx label="Номер" value={<span className="font-mono">{ev.plate_number_original}</span>} />
            <Ctx label="Достоверность" value={`${Math.round((ev.confidence ?? 0) * 100)}%`} />
            <Ctx label="Класс ТС" value={ev.vehicle_class ?? '—'} />
            <Ctx label="Цвет" value={ev.color ?? '—'} />
          </div>
        </div>
      </div>
    </section>
  )
}

export default function Preview() {
  return (
    <div className="min-h-screen bg-bg-root p-6">
      <div className="mx-auto flex max-w-[1200px] flex-col gap-12">
        <SecurityPostSection />
        <div className="h-px bg-border-default" />
        <EventDetailSection />
        <div className="h-px bg-border-default" />
        <HistorySection />
        <div className="h-px bg-border-default" />
        <DatabaseSection />
      </div>
    </div>
  )
}
