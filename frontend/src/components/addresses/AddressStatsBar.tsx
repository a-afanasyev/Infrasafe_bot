import { useTranslation } from 'react-i18next'
import type { AddressStats } from '../../types/api'

interface AddressStatsBarProps {
  stats: AddressStats | undefined
  onYardsClick: () => void
  onBuildingsClick: () => void
  onApartmentsClick: () => void
  onResidentsClick: () => void
}

// FE-09: верхняя плашка статистики (вынесена из AddressesPage без изменения
// поведения; форматы значений сохранены).
export default function AddressStatsBar({
  stats,
  onYardsClick,
  onBuildingsClick,
  onApartmentsClick,
  onResidentsClick,
}: AddressStatsBarProps) {
  const { t } = useTranslation()

  const cards = [
    {
      label: t('addresses.stats.yards'),
      value: stats ? `${stats.yards_active}/${stats.yards_total}` : '-',
      iconBg: 'var(--blue)',
      icon: '\u{1F3D8}',
      onClick: onYardsClick,
    },
    {
      label: t('addresses.stats.buildings'),
      // Display active/total to match the yards card and the building list,
      // which already filters by is_active. Soft-deleted rows would otherwise
      // make the header counter disagree with what the user sees below it.
      value: stats ? `${stats.buildings_active}/${stats.buildings_total}` : '-',
      iconBg: 'var(--emerald)',
      icon: '\u{1F3E2}',
      onClick: onBuildingsClick,
    },
    {
      label: t('addresses.stats.apartments'),
      value: stats ? `${stats.apartments_active}/${stats.apartments_total}` : '-',
      iconBg: 'var(--amber)',
      icon: '\u{1F3E0}',
      onClick: onApartmentsClick,
    },
    {
      label: t('addresses.stats.residents'),
      // FE-100: align with the active/total format of the other tiles
      // (approved residents out of approved+pending total).
      value: stats ? `${stats.residents_approved}/${stats.residents_approved + stats.residents_pending}` : '-',
      iconBg: 'var(--violet)',
      icon: '\u{1F465}',
      onClick: onResidentsClick,
    },
  ]

  return (
    <div className="grid grid-cols-4 gap-3">
      {cards.map(card => (
        <div
          key={card.label}
          onClick={card.onClick}
          className="bg-bg-card border border-border-default rounded-default p-4 flex items-center gap-3.5 cursor-pointer transition-colors hover:border-accent"
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
            <div className="text-[11px] text-text-muted mt-0.5">
              {card.label}
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}
