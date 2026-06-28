import { useTranslation } from 'react-i18next'
import { Car, Ticket, PlusCircle, Copy } from 'lucide-react'

import {
  twaVehicles,
  twaVehicleRequests,
  twaPasses,
  twaGuestCode,
  type TwaVehicleMock,
  type TwaRequestMock,
  type TwaPassMock,
} from './mockData'

/**
 * Тонкие копии резидентского TWA-раздела «Доступ» (для скриншотов docs).
 *
 * Боевые экраны (src/twa/pages/access/*) ходят через twaClient/useQuery и
 * полагаются на Telegram-WebView + Tailwind `dark:`-варианты (в standalone-
 * превью OS-тема не гарантирована). Поэтому здесь — тонкие копии ТЕЛА вкладок с
 * жёстко зашитой тёмной Telegram-палитрой (как DialogPreviews/LiveFeedPreview):
 * та же разметка/иконки/i18n-ключи (twa.access.*), мобильная колонка ~390px.
 * Данные синтетические (mockData), без сети/состояния.
 */

// Telegram dark palette (фикс, не зависит от prefers-color-scheme).
const TG = {
  screen: '#0e1621',
  card: '#17212b',
  border: '#101a24',
  text: '#f5f6f7',
  textMuted: '#708499',
  emerald: '#22c55e',
}

// Бейдж статуса по нормализованному ключу (зеркало statusBadgeClass из TWA).
function statusPillStyle(status: string): { bg: string; fg: string } {
  switch (status) {
    case 'active':
    case 'approved':
      return { bg: 'rgba(16,185,129,0.18)', fg: '#34d399' }
    case 'pending':
      return { bg: 'rgba(245,158,11,0.18)', fg: '#fbbf24' }
    case 'rejected':
    case 'blocked':
      return { bg: 'rgba(239,68,68,0.18)', fg: '#f87171' }
    default: // revoked | expired | used | inactive
      return { bg: 'rgba(148,163,184,0.16)', fg: '#94a3b8' }
  }
}

function StatusPill({ status, label }: { status: string; label: string }) {
  const s = statusPillStyle(status)
  return (
    <span
      className="text-[11px] font-semibold px-2 py-0.5 rounded-full whitespace-nowrap"
      style={{ backgroundColor: s.bg, color: s.fg }}
    >
      {label}
    </span>
  )
}

// Дата DD.MM HH:mm (как formatDateTime в TWA).
function fmt(value: string): string {
  return new Date(value).toLocaleString('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

// Мобильная рамка «телефон» (узкая колонка, тёмная Telegram-тема).
function MobileFrame({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div
      className="w-[390px] shrink-0 overflow-hidden rounded-[28px] border shadow-xl"
      style={{ backgroundColor: TG.screen, borderColor: '#000' }}
    >
      {/* Telegram header */}
      <div
        className="flex items-center gap-2 px-4 py-3"
        style={{ backgroundColor: '#17212b', borderBottom: `1px solid ${TG.border}` }}
      >
        <span className="text-[15px]" style={{ color: TG.textMuted }}>
          ←
        </span>
        <span className="text-[15px] font-semibold" style={{ color: TG.text }}>
          {title}
        </span>
      </div>
      <div className="p-4" style={{ minHeight: 560 }}>
        {children}
      </div>
    </div>
  )
}

function PrimaryButton({ icon, label }: { icon: React.ReactNode; label: string }) {
  return (
    <button
      type="button"
      className="w-full flex items-center justify-center gap-2 py-3 rounded-xl font-medium mb-4 text-white"
      style={{ backgroundColor: TG.emerald }}
    >
      {icon}
      {label}
    </button>
  )
}

// ── (1) Вкладка «Авто»: список авто + кнопка заявки + блок «Мои заявки» ────────
function TwaVehiclesView() {
  const { t } = useTranslation()
  const vehicleStatusLabel = (s: string) => t(`twa.access.vehicleStatus.${s}`, { defaultValue: s })
  const requestStatusLabel = (s: string) => t(`twa.access.requestStatus.${s}`, { defaultValue: s })

  return (
    <MobileFrame title={t('twa.access.title')}>
      <PrimaryButton icon={<PlusCircle size={18} />} label={t('twa.access.vehicles.requestButton')} />

      <div className="space-y-2">
        {twaVehicles.map((v: TwaVehicleMock) => (
          <div
            key={v.id}
            className="rounded-2xl p-4 border"
            style={{ backgroundColor: TG.card, borderColor: TG.border }}
          >
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2 min-w-0">
                <Car size={16} className="shrink-0" style={{ color: TG.emerald }} />
                <span className="font-semibold text-[14px] truncate" style={{ color: TG.text }}>
                  {v.plate_number_original}
                </span>
              </div>
              <StatusPill status={v.status} label={vehicleStatusLabel(v.status)} />
            </div>
            {(v.brand || v.model || v.color) && (
              <p className="text-[12px] mt-1" style={{ color: TG.textMuted }}>
                {[v.brand, v.model, v.color].filter(Boolean).join(' · ')}
              </p>
            )}
          </div>
        ))}
      </div>

      <h2 className="font-semibold text-[14px] mt-6 mb-2" style={{ color: TG.text }}>
        {t('twa.access.vehicles.myRequests')}
      </h2>
      <div className="space-y-2">
        {twaVehicleRequests.map((r: TwaRequestMock) => (
          <div
            key={r.id}
            className="rounded-2xl p-3 border"
            style={{ backgroundColor: TG.card, borderColor: TG.border }}
          >
            <div className="flex items-center justify-between gap-2">
              <span className="font-medium text-[13px] truncate" style={{ color: TG.text }}>
                {r.plate}
              </span>
              <StatusPill status={r.status} label={requestStatusLabel(r.status)} />
            </div>
            <p className="text-[11px] mt-1" style={{ color: TG.textMuted }}>
              {fmt(r.created_at)}
            </p>
            {r.review_comment && (
              <p className="text-[12px] mt-1" style={{ color: TG.textMuted }}>
                {r.review_comment}
              </p>
            )}
          </div>
        ))}
      </div>
    </MobileFrame>
  )
}

// ── (2) Вкладка «Пропуска»: список пропусков + кнопка «Заказать пропуск» ───────
function TwaPassesView() {
  const { t } = useTranslation()
  const passTypeLabel = (s: string) => t(`twa.access.passType.${s}`, { defaultValue: s })
  const passStatusLabel = (s: string) => t(`twa.access.passStatus.${s}`, { defaultValue: s })

  return (
    <MobileFrame title={t('twa.access.title')}>
      <PrimaryButton icon={<PlusCircle size={18} />} label={t('twa.access.passes.newButton')} />

      <div className="space-y-2">
        {twaPasses.map((p: TwaPassMock) => (
          <div
            key={p.id}
            className="rounded-2xl p-4 border"
            style={{ backgroundColor: TG.card, borderColor: TG.border }}
          >
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2 min-w-0">
                <Ticket size={16} className="shrink-0" style={{ color: TG.emerald }} />
                <span className="font-semibold text-[14px] truncate" style={{ color: TG.text }}>
                  {passTypeLabel(p.pass_type)}
                </span>
              </div>
              <StatusPill status={p.status} label={passStatusLabel(p.status)} />
            </div>
            {p.plate && (
              <p className="text-[12px] mt-1" style={{ color: TG.text }}>
                {p.plate}
              </p>
            )}
            <p className="text-[12px] mt-1" style={{ color: TG.textMuted }}>
              {t('twa.access.passes.validUntil')}: {fmt(p.valid_until)}
            </p>
            <p className="text-[12px]" style={{ color: TG.textMuted }}>
              {t('twa.access.passes.entries')}: {p.used_entries}/{p.max_entries}
            </p>
            {p.status === 'active' && (
              <button
                type="button"
                className="mt-3 w-full text-[13px] font-medium rounded-xl py-2 border"
                style={{ color: '#f87171', borderColor: 'rgba(248,113,113,0.4)' }}
              >
                {t('twa.access.passes.cancel')}
              </button>
            )}
          </div>
        ))}
      </div>
    </MobileFrame>
  )
}

// ── (3) Экран успеха гостевого пропуска с ОДНОРАЗОВЫМ КОДОМ (§9.3) ─────────────
function TwaGuestCodeView() {
  const { t } = useTranslation()
  return (
    <MobileFrame title={t('twa.access.title')}>
      <h1 className="text-lg font-bold mb-4" style={{ color: TG.text }}>
        {t('twa.access.passNew.code.title')}
      </h1>

      <div
        className="rounded-2xl border p-6 text-center"
        style={{ backgroundColor: TG.card, borderColor: TG.border }}
      >
        <p className="text-[13px] mb-3" style={{ color: TG.textMuted }}>
          {t('twa.access.passNew.code.label')}
        </p>
        <div
          className="font-mono text-3xl font-bold tracking-[0.3em] mb-5"
          style={{ color: TG.text }}
        >
          {twaGuestCode}
        </div>
        <button
          type="button"
          className="w-full flex items-center justify-center gap-2 py-3 rounded-xl font-semibold text-white"
          style={{ backgroundColor: TG.emerald }}
        >
          <Copy size={16} />
          {t('twa.access.passNew.code.copy')}
        </button>
      </div>

      <p className="mt-4 text-[13px] text-center px-2" style={{ color: '#fbbf24' }}>
        {t('twa.access.passNew.code.hint')}
      </p>
    </MobileFrame>
  )
}

export { TwaVehiclesView, TwaPassesView, TwaGuestCodeView }
