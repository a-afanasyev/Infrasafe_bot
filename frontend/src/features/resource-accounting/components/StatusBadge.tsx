import type { PeriodStatus, ReadingStatus } from '../api/types';

const READING_LABELS: Record<ReadingStatus, string> = {
  ok: 'ОК',
  warning: 'Предупреждение',
  error: 'Ошибка',
  missing: 'Нет данных',
};

export function ReadingStatusBadge({ status }: { status: ReadingStatus | null | undefined }) {
  if (!status) return <span className="badge badge-missing">Не введено</span>;
  return <span className={`badge badge-${status}`}>{READING_LABELS[status]}</span>;
}

// eslint-disable-next-line react-refresh/only-export-components -- ported module: badge labels co-located with badge components
export const PERIOD_STATUS_LABELS: Record<PeriodStatus, string> = {
  open: 'Открыт',
  review: 'На проверке',
  submitted: 'Передан',
  closed: 'Закрыт',
};

export function PeriodStatusBadge({ status }: { status: PeriodStatus }) {
  return <span className={`badge badge-period-${status}`}>{PERIOD_STATUS_LABELS[status]}</span>;
}

export function ActiveBadge({ active }: { active: boolean }) {
  return active ? (
    <span className="badge badge-ok">Активен</span>
  ) : (
    <span className="badge badge-missing">Архив</span>
  );
}
