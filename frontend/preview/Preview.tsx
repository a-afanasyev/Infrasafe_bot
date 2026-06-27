import { useState } from 'react'
import {
  ShieldCheck,
  History,
  Database,
  Camera,
  Plus,
  Cpu,
  LayoutGrid,
  ListChecks,
  Users,
  Clock,
  Table2,
  MapPin,
  MonitorPlay,
  MessageSquare,
} from 'lucide-react'

import { Button } from '@/components/ui/button'
import AccessTabBar from '@/components/access/AccessTabBar'
import ManualReviewQueue from '@/components/access/ManualReviewQueue'
import AccessEventsTable from '@/components/access/AccessEventsTable'
import AccessEventsFilters from '@/components/access/AccessEventsFilters'
import AccessPagination from '@/components/access/AccessPagination'
import VehiclesTable from '@/components/access/VehiclesTable'
import PassesTable from '@/components/access/PassesTable'
import RequestsTable from '@/components/access/RequestsTable'
import AccessPhotos from '@/components/access/AccessPhotos'
import EquipmentTable, { type EquipmentColumn } from '@/components/access/EquipmentTable'
import { AccessStatusBadge, ParkingTypeBadge } from '@/components/access/AccessBadges'
import type {
  AccessEventsFilters as Filters,
  ZoneRow,
  GateRow,
  CameraRow,
  BarrierRow,
  ControllerRow,
  SpotRow,
  AssignmentRow,
} from '@/types/access'

import LiveFeedPreview from './LiveFeedPreview'
import {
  liveEvents,
  historyEvents,
  vehicles,
  passes,
  requests,
  eventDetail,
  zones,
  gates,
  cameras,
  barriers,
  controllers,
  spots,
  assignments,
} from './mockData'
import {
  VehicleStatusBlockPreview,
  TaxiPassFormPreview,
  RequestReviewApprovePreview,
  ControllerKeyPreview,
  ControllerTestPreview,
} from './DialogPreviews'

/**
 * STANDALONE-превью ВСЕХ экранов контроля доступа на синтетических мок-данных
 * (для скриншотов; §11 — номера/ключи вымышленные). Реальные презентационные
 * компоненты переиспользуются как есть; ManualReviewQueue (TanStack-Query)
 * питается предзаполненным кэшем (см. main.tsx); live-лента и диалоги (Radix-
 * портал во весь экран — не показать «рядом») отрисованы тонкими копиями.
 * Без сети, без auth, без бэкенда.
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

// Визуальные действия превью без сети/состояния — обработчики ничего не делают.
function noop() {}

function SubLabel({ children }: { children: React.ReactNode }) {
  return (
    <p className="text-[11px] font-semibold uppercase tracking-wider text-text-muted">{children}</p>
  )
}

function RolePill({ children }: { children: React.ReactNode }) {
  return (
    <span className="rounded-full bg-accent-dim px-1.5 py-0.5 text-[9px] font-medium text-accent">
      {children}
    </span>
  )
}

// ── (0) Интеграция в дашборд УК ───────────────────────────────────────────────
// Статическая вёрстка сайдбара дашборда (классы из DashboardLayout) с реальными
// пунктами УК + новыми пунктами доступа, чтобы показать: контроль доступа —
// это разделы того же дашборда, та же навигация и роли.
function SidebarNavRow({
  icon,
  label,
  active = false,
  roles,
}: {
  icon: React.ReactNode
  label: string
  active?: boolean
  roles?: string[]
}) {
  return (
    <div
      className={[
        'mb-0.5 flex items-center gap-2.5 rounded-sm border-l-[3px] px-3 py-[9px] text-sm transition-all',
        active
          ? 'border-accent bg-accent-dim font-semibold text-accent'
          : 'border-transparent text-text-secondary',
      ].join(' ')}
    >
      <span className="shrink-0">{icon}</span>
      <span className="flex-1">{label}</span>
      {roles && (
        <span className="flex flex-wrap justify-end gap-1">
          {roles.map((r) => (
            <RolePill key={r}>{r}</RolePill>
          ))}
        </span>
      )}
    </div>
  )
}

function IntegrationSection() {
  return (
    <section className="flex flex-col gap-5">
      <SectionHeader
        icon={<LayoutGrid size={22} />}
        title="Интеграция в дашборд УК"
        subtitle="Контроль доступа — разделы того же дашборда: общая навигация и роли"
      />
      <div className="grid gap-5 lg:grid-cols-[280px_1fr]">
        {/* Мок сайдбара дашборда */}
        <aside className="flex flex-col rounded-default border border-border-default bg-bg-sidebar">
          <div className="px-5 pt-5 pb-4">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-default bg-accent-dim text-accent font-bold">
                IS
              </div>
              <div>
                <div className="text-[15px] font-bold text-text-primary">InfraSafe</div>
                <div className="text-[11px] text-text-muted">Управление ЖК</div>
              </div>
            </div>
          </div>

          <nav className="flex-1 px-3 py-2">
            <div className="mb-1 px-2 py-1 text-[10px] font-semibold uppercase tracking-wider text-text-muted">
              Основное
            </div>
            <SidebarNavRow icon={<LayoutGrid size={16} />} label="Аналитика" />
            <SidebarNavRow icon={<ListChecks size={16} />} label="Заявки" />
            <SidebarNavRow icon={<Users size={16} />} label="Сотрудники" />
            <SidebarNavRow icon={<Clock size={16} />} label="Смены" />
            <SidebarNavRow icon={<Table2 size={16} />} label="Шаблоны" />
            <SidebarNavRow icon={<MapPin size={16} />} label="Адреса" />
            <SidebarNavRow icon={<MonitorPlay size={16} />} label="Редактор витрины" />
            <SidebarNavRow icon={<MessageSquare size={16} />} label="Обратная связь" />

            <div className="mt-3 mb-1 px-2 py-1 text-[10px] font-semibold uppercase tracking-wider text-accent">
              Контроль доступа · новое
            </div>
            <SidebarNavRow
              icon={<ShieldCheck size={16} />}
              label="Контроль доступа"
              active
              roles={['manager', 'security_operator', 'system_admin']}
            />
            <SidebarNavRow
              icon={<History size={16} />}
              label="История проездов"
              roles={['manager', 'system_admin']}
            />
            <SidebarNavRow
              icon={<Database size={16} />}
              label="База доступа"
              roles={['manager', 'system_admin']}
            />
            <SidebarNavRow
              icon={<Cpu size={16} />}
              label="Оборудование"
              roles={['manager', 'system_admin']}
            />
          </nav>
        </aside>

        {/* Контент-фрейм: один access-экран внутри дашборда */}
        <div className="flex flex-col gap-3 rounded-default border border-border-default bg-bg-card p-5">
          <SubLabel>Контент-фрейм дашборда — «Контроль доступа»</SubLabel>
          <LiveFeedPreview events={liveEvents.slice(0, 4)} />
        </div>
      </div>
    </section>
  )
}

// ── (A) Пост охраны ──────────────────────────────────────────────────────────
function SecurityPostSection() {
  return (
    <section className="flex flex-col gap-5">
      <SectionHeader
        icon={<ShieldCheck size={22} />}
        title="Пост охраны"
        subtitle="Live-лента, очередь ручной проверки (с фото) и история"
      />
      <div>
        <SubLabel>Live-лента</SubLabel>
        <div className="mt-2">
          <LiveFeedPreview events={liveEvents} />
        </div>
      </div>
      <div>
        <SubLabel>Очередь ручной проверки (обзор + номер)</SubLabel>
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
        subtitle="Автомобили, пропуска и заявки жителей + действия менеджера"
      />
      <AccessTabBar tabs={tabs} active={tab} onChange={setTab} />
      {/* Для скриншота показываем все три таба сразу, под подписями. Действия
          менеджера — визуальные (no-op handlers): без бэкенда, только вид. */}
      <div className="flex flex-col gap-5">
        <div>
          <div className="flex items-center justify-between">
            <SubLabel>Автомобили</SubLabel>
            <Button size="sm" className="gap-1.5">
              <Plus size={16} />
              Добавить авто
            </Button>
          </div>
          <div className="mt-2">
            <VehiclesTable
              vehicles={vehicles}
              actions={{ onBlock: noop, onUnblock: noop, onArchive: noop }}
            />
          </div>
        </div>
        <div>
          <div className="flex items-center justify-between">
            <SubLabel>Пропуска</SubLabel>
            <Button size="sm" className="gap-1.5">
              <Plus size={16} />
              Создать taxi-пропуск
            </Button>
          </div>
          <div className="mt-2">
            <PassesTable passes={passes} />
          </div>
        </div>
        <div>
          <SubLabel>Заявки</SubLabel>
          <div className="mt-2">
            <RequestsTable requests={requests} actions={{ onApprove: noop, onReject: noop }} />
          </div>
        </div>
      </div>

      {/* Открытые диалоги действий менеджера (тонкие копии тела диалогов). */}
      <div>
        <SubLabel>Диалоги действий менеджера (открытое состояние)</SubLabel>
        <div className="mt-2 flex flex-wrap gap-5">
          <VehicleStatusBlockPreview />
          <TaxiPassFormPreview />
          <RequestReviewApprovePreview />
        </div>
      </div>
    </section>
  )
}

// ── (D) Оборудование ─────────────────────────────────────────────────────────
function dash(v: unknown): React.ReactNode {
  return v === null || v === undefined || v === '' ? '—' : String(v)
}

function EquipmentSection() {
  const [tab, setTab] = useState('zones')
  const tabs = [
    { key: 'zones', label: 'Зоны' },
    { key: 'spots', label: 'Места' },
    { key: 'assignments', label: 'Закрепления' },
    { key: 'gates', label: 'Въезды' },
    { key: 'cameras', label: 'Камеры' },
    { key: 'barriers', label: 'Шлагбаумы' },
    { key: 'controllers', label: 'Контроллеры' },
  ]

  const offline = (m: string) =>
    m === 'fail_closed' ? 'Закрыто при сбое' : 'Кэш постоянных'
  const dir = (d: string) => (d === 'entry' ? 'Въезд' : 'Выезд')
  const gateCode = (id: number) => gates.find((g) => g.id === id)?.code ?? `#${id}`
  const zoneLabel = (id: number) => {
    const z = zones.find((z) => z.id === id)
    return z ? `${z.code} — ${z.name}` : `#${id}`
  }
  const zoneCode = (id: number) => zones.find((z) => z.id === id)?.code ?? `#${id}`
  const spotCell = (id: number) => {
    const s = spots.find((s) => s.id === id)
    return s ? `${zoneCode(s.zone_id)} · ${s.code}` : `#${id}`
  }
  const ownership = (o: string) => (o === 'owned' ? 'Собственное' : 'Аренда')
  // Мок-занятость для shared-зон (в боевом UI подтягивается с occupancy-эндпоинта).
  const occupancyMock: Record<number, string> = { 2: '57 / 80' }

  const zoneCols: EquipmentColumn<ZoneRow>[] = [
    { key: 'code', label: 'Код', render: (z) => <span className="font-mono font-semibold">{z.code}</span> },
    { key: 'name', label: 'Название', render: (z) => z.name },
    { key: 'parking_type', label: 'Тип парковки', render: (z) => <ParkingTypeBadge type={z.parking_type ?? 'assigned'} /> },
    { key: 'occupancy', label: 'Занятость', render: (z) => (z.parking_type === 'shared' ? <span className="font-mono">{occupancyMock[z.id] ?? '—'}</span> : <span className="text-text-muted">—</span>) },
    { key: 'offline', label: 'Offline-режим', render: (z) => offline(z.offline_mode) },
    { key: 'max', label: 'Лимит постоянных', render: (z) => dash(z.max_permanent_per_apartment) },
    { key: 'status', label: 'Статус', render: (z) => <AccessStatusBadge status={z.is_active ? 'active' : 'archived'} /> },
  ]

  const fmtDate = (v: string | null) => (v ? new Date(v).toLocaleString() : '—')
  const spotCols: EquipmentColumn<SpotRow>[] = [
    { key: 'code', label: 'Код', render: (s) => <span className="font-mono font-semibold">{s.code}</span> },
    { key: 'zone', label: 'Зона', render: (s) => zoneLabel(s.zone_id) },
    { key: 'status', label: 'Статус', render: (s) => <AccessStatusBadge status={s.status} /> },
  ]
  const assignmentCols: EquipmentColumn<AssignmentRow>[] = [
    { key: 'spot', label: 'Место', render: (a) => <span className="font-mono">{spotCell(a.spot_id)}</span> },
    { key: 'apartment', label: 'ID квартиры', render: (a) => `#${a.apartment_id}` },
    { key: 'ownership', label: 'Тип владения', render: (a) => ownership(a.ownership_type) },
    { key: 'from', label: 'Действует с', render: (a) => fmtDate(a.valid_from) },
    { key: 'until', label: 'Действует до', render: (a) => fmtDate(a.valid_until) },
    { key: 'status', label: 'Статус', render: (a) => <AccessStatusBadge status={a.status} /> },
  ]
  const gateCols: EquipmentColumn<GateRow>[] = [
    { key: 'code', label: 'Код', render: (g) => <span className="font-mono font-semibold">{g.code}</span> },
    { key: 'zone', label: 'Зона', render: (g) => zoneLabel(g.zone_id) },
    { key: 'direction', label: 'Направление', render: (g) => dir(g.direction) },
    { key: 'name', label: 'Название', render: (g) => dash(g.name) },
    { key: 'status', label: 'Статус', render: (g) => <AccessStatusBadge status={g.is_active ? 'active' : 'archived'} /> },
  ]
  const cameraCols: EquipmentColumn<CameraRow>[] = [
    { key: 'code', label: 'Код', render: (c) => <span className="font-mono font-semibold">{c.code}</span> },
    { key: 'gate', label: 'Въезд', render: (c) => gateCode(c.gate_id) },
    { key: 'direction', label: 'Направление', render: (c) => dir(c.direction) },
    { key: 'vendor', label: 'Производитель', render: (c) => dash([c.vendor, c.model].filter(Boolean).join(' ')) },
    { key: 'status', label: 'Статус', render: (c) => <AccessStatusBadge status={c.is_active ? 'active' : 'archived'} /> },
  ]
  const barrierCols: EquipmentColumn<BarrierRow>[] = [
    { key: 'code', label: 'Код', render: (b) => <span className="font-mono font-semibold">{b.code}</span> },
    { key: 'gate', label: 'Въезд', render: (b) => gateCode(b.gate_id) },
    { key: 'relay', label: 'Реле', render: (b) => dash([b.relay_type, b.relay_channel != null ? `#${b.relay_channel}` : ''].filter(Boolean).join(' ')) },
    { key: 'status', label: 'Статус', render: (b) => <AccessStatusBadge status={b.is_active ? 'active' : 'archived'} /> },
  ]
  const controllerCols: EquipmentColumn<ControllerRow>[] = [
    { key: 'uid', label: 'UID', render: (c) => <span className="font-mono font-semibold">{c.controller_uid}</span> },
    { key: 'name', label: 'Название', render: (c) => dash(c.name) },
    { key: 'status', label: 'Статус', render: (c) => <AccessStatusBadge status={c.is_active ? (c.status ?? 'active') : 'archived'} /> },
    { key: 'ip', label: 'IP allowlist', render: (c) => (c.ip_allowlist && c.ip_allowlist.length ? c.ip_allowlist.join(', ') : '—') },
  ]

  return (
    <section className="flex flex-col gap-5">
      <SectionHeader
        icon={<Cpu size={22} />}
        title="Оборудование"
        subtitle="Зоны, въезды, камеры, шлагбаумы и контроллеры точек проезда"
      />
      <AccessTabBar tabs={tabs} active={tab} onChange={setTab} />
      {/* Для скриншота показываем все табы сразу, под подписями. */}
      <div className="flex flex-col gap-5">
        <div>
          <SubLabel>Зоны</SubLabel>
          <div className="mt-2">
            <EquipmentTable rows={zones} columns={zoneCols} emptyText="" onEdit={noop} onDeactivate={noop} />
          </div>
        </div>
        <div>
          <div className="flex items-center justify-between">
            <SubLabel>Места</SubLabel>
            <Button size="sm" className="gap-1.5">
              <Plus size={16} />
              Добавить место
            </Button>
          </div>
          <div className="mt-2">
            <EquipmentTable rows={spots} columns={spotCols} emptyText="" onEdit={noop} onDeactivate={noop} />
          </div>
        </div>
        <div>
          <div className="flex items-center justify-between">
            <SubLabel>Закрепления</SubLabel>
            <Button size="sm" className="gap-1.5">
              <Plus size={16} />
              Закрепить место
            </Button>
          </div>
          <div className="mt-2">
            <EquipmentTable
              rows={assignments}
              columns={assignmentCols}
              emptyText=""
              extraActions={() => (
                <>
                  <Button size="sm" variant="outline">Продлить</Button>
                  <Button size="sm" variant="destructive">Отозвать</Button>
                </>
              )}
            />
          </div>
        </div>
        <div>
          <SubLabel>Въезды</SubLabel>
          <div className="mt-2">
            <EquipmentTable rows={gates} columns={gateCols} emptyText="" onEdit={noop} onDeactivate={noop} />
          </div>
        </div>
        <div>
          <SubLabel>Камеры</SubLabel>
          <div className="mt-2">
            <EquipmentTable rows={cameras} columns={cameraCols} emptyText="" onEdit={noop} onDeactivate={noop} />
          </div>
        </div>
        <div>
          <SubLabel>Шлагбаумы</SubLabel>
          <div className="mt-2">
            <EquipmentTable rows={barriers} columns={barrierCols} emptyText="" onEdit={noop} onDeactivate={noop} />
          </div>
        </div>
        <div>
          <SubLabel>Контроллеры</SubLabel>
          <div className="mt-2">
            <EquipmentTable
              rows={controllers}
              columns={controllerCols}
              emptyText=""
              onEdit={noop}
              onDeactivate={noop}
              extraActions={() => (
                <>
                  <Button size="sm" variant="outline">Тест</Button>
                  <Button size="sm" variant="outline">Ротировать ключ</Button>
                </>
              )}
            />
          </div>
        </div>
      </div>

      {/* Открытые диалоги оборудования (тонкие копии тела диалогов). */}
      <div>
        <SubLabel>Диалоги оборудования (открытое состояние)</SubLabel>
        <div className="mt-2 flex flex-wrap gap-5">
          <ControllerKeyPreview />
          <ControllerTestPreview />
        </div>
      </div>
    </section>
  )
}

export default function Preview() {
  return (
    <div className="min-h-screen bg-bg-root p-6">
      <div className="mx-auto flex max-w-[1200px] flex-col gap-12">
        <IntegrationSection />
        <div className="h-px bg-border-default" />
        <SecurityPostSection />
        <div className="h-px bg-border-default" />
        <EventDetailSection />
        <div className="h-px bg-border-default" />
        <HistorySection />
        <div className="h-px bg-border-default" />
        <DatabaseSection />
        <div className="h-px bg-border-default" />
        <EquipmentSection />
      </div>
    </div>
  )
}
