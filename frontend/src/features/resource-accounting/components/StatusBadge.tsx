import { useTranslation } from 'react-i18next';
import type { PeriodStatus, ReadingStatus } from '../api/types';

export function ReadingStatusBadge({ status }: { status: ReadingStatus | null | undefined }) {
  const { t } = useTranslation();
  if (!status)
    return (
      <span className="badge badge-missing">{t('resourceAccounting.status.reading.notEntered')}</span>
    );
  return (
    <span className={`badge badge-${status}`}>{t(`resourceAccounting.status.reading.${status}`)}</span>
  );
}

export function PeriodStatusBadge({ status }: { status: PeriodStatus }) {
  const { t } = useTranslation();
  return (
    <span className={`badge badge-period-${status}`}>
      {t(`resourceAccounting.status.period.${status}`)}
    </span>
  );
}

export function ActiveBadge({ active }: { active: boolean }) {
  const { t } = useTranslation();
  return active ? (
    <span className="badge badge-ok">{t('resourceAccounting.status.active')}</span>
  ) : (
    <span className="badge badge-missing">{t('resourceAccounting.status.archived')}</span>
  );
}
