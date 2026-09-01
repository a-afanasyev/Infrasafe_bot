import { useTranslation } from 'react-i18next'

/** Две НЕЗАВИСИМЫЕ оси статуса жителя, поэтому два разных бейджа:
 *  аккаунт (`users.status`) решает, пустят ли в бота, верификация
 *  (`users.verification_status`) — подтверждена ли личность. Житель может быть
 *  approved и при этом непроверенным, и наоборот. */

const ACCOUNT_COLORS: Record<string, string> = {
  pending: 'var(--amber)',
  approved: 'var(--emerald)',
  blocked: 'var(--red)',
}

const VERIFICATION_COLORS: Record<string, string> = {
  pending: 'var(--text-muted)',
  requested: 'var(--amber)',
  verified: 'var(--emerald)',
  rejected: 'var(--red)',
}

function Badge({ color, children }: { color: string; children: React.ReactNode }) {
  return (
    <span
      className="text-[11px] font-semibold px-2.5 py-0.5 rounded-full whitespace-nowrap"
      style={{
        background: `color-mix(in srgb, ${color} 13%, transparent)`,
        color,
      }}
    >
      {children}
    </span>
  )
}

export function ResidentAccountBadge({ status }: { status: string }) {
  const { t } = useTranslation()
  return (
    <Badge color={ACCOUNT_COLORS[status] ?? 'var(--text-muted)'}>
      {t(`residents.accountStatus.${status}`, status)}
    </Badge>
  )
}

/** Пользователь заблокировал бота: доставка ему невозможна, пока сам не
 *  разблокирует. Для карточек жителей; StaffCard рендерит свой инлайн в
 *  стиле остальных своих бейджей. */
export function BotBlockedBadge() {
  const { t } = useTranslation()
  return <Badge color="var(--red)">{`🚫 ${t('residents.botBlocked')}`}</Badge>
}

export function ResidentVerificationBadge({ status }: { status: string }) {
  const { t } = useTranslation()
  return (
    <Badge color={VERIFICATION_COLORS[status] ?? 'var(--text-muted)'}>
      {t(`residents.verification.${status}`, status)}
    </Badge>
  )
}
