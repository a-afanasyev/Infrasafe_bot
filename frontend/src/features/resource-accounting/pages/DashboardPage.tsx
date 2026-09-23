import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';
import { api, apiPaged } from '../api/client';
import type { ExportItem, Meter, Period, ValidationSummary } from '../api/types';
import { EXPORT_STATUS_KEYS } from '../api/types';
import { Empty, ErrorState, Loading } from '../components/DataState';
import { PeriodStatusBadge } from '../components/StatusBadge';
import { useResourceFormat } from '../utils/useResourceFormat';
import { useResourceAuth } from '../auth/ResourceAuthContext';
import { useResourceLink } from '../paths';

function latestPeriod(periods: Period[]): Period | null {
  if (!periods.length) return null;
  return [...periods].sort((a, b) => b.month.localeCompare(a.month))[0];
}

export function DashboardPage() {
  const { t } = useTranslation();
  const { formatDateTime, formatMonth } = useResourceFormat();
  const { role } = useResourceAuth();
  const link = useResourceLink();
  const isViewer = role === 'resource_viewer';

  const periodsQuery = useQuery({
    queryKey: ['periods'],
    queryFn: () => api<Period[]>('/v1/periods'),
  });

  const period = periodsQuery.data ? latestPeriod(periodsQuery.data) : null;

  const activeMetersQuery = useQuery({
    queryKey: ['meters', 'active-total'],
    queryFn: async () => {
      const { meta } = await apiPaged<Meter>('/v1/meters', {
        params: { status: 'active', per_page: 1, page: 1 },
      });
      return meta.total;
    },
  });

  const validationQuery = useQuery({
    queryKey: ['validate', period?.month],
    queryFn: () =>
      api<ValidationSummary>(`/v1/periods/${period!.month}/validate`, { method: 'POST' }),
    enabled: Boolean(period) && !isViewer,
  });

  const exportsQuery = useQuery({
    queryKey: ['exports', 'recent'],
    queryFn: () => api<ExportItem[]>('/v1/exports'),
  });

  if (periodsQuery.isLoading) return <Loading />;
  if (periodsQuery.isError)
    return <ErrorState error={periodsQuery.error} onRetry={() => periodsQuery.refetch()} />;

  const v = validationQuery.data;
  const recentExports = (exportsQuery.data ?? []).slice(0, 5);

  return (
    <div>
      <div className="page-header">
        <h1>{t('resourceAccounting.nav.summary')}</h1>
        {period && (
          <div className="page-header-side">
            {t('resourceAccounting.dashboard.lastPeriod')} <strong>{formatMonth(period.month)}</strong>{' '}
            <PeriodStatusBadge status={period.status} />
          </div>
        )}
      </div>

      <div className="cards">
        <div className="card">
          <div className="card-label">{t('resourceAccounting.dashboard.activeMeters')}</div>
          <div className="card-value">
            {activeMetersQuery.isLoading ? '…' : (activeMetersQuery.data ?? '—')}
          </div>
        </div>
        <div className="card">
          <div className="card-label">{t('resourceAccounting.dashboard.enteredInPeriod')}</div>
          <div className="card-value">
            {isViewer ? '—' : validationQuery.isLoading ? '…' : (v?.entered ?? '—')}
          </div>
        </div>
        <div className="card">
          <div className="card-label">{t('resourceAccounting.dashboard.notEntered')}</div>
          <div className="card-value card-value-warn">
            {isViewer ? '—' : validationQuery.isLoading ? '…' : (v?.not_entered ?? '—')}
          </div>
        </div>
        <div className="card">
          <div className="card-label">{t('resourceAccounting.dashboard.warningsErrors')}</div>
          <div className="card-value">
            {isViewer || !v ? (
              '—'
            ) : (
              <>
                <span className="text-warning">{v.by_status?.warning ?? 0}</span>
                {' / '}
                {/* AUD7-CODE-08: сервер отдаёт массив ошибок — объект как child ронял страницу. */}
                <span className="text-error">{v.errors.length}</span>
              </>
            )}
          </div>
        </div>
      </div>

      {!period && (
        <Empty text={t('resourceAccounting.dashboard.noPeriods')} />
      )}

      <section className="panel">
        <div className="panel-header">
          <h2>{t('resourceAccounting.dashboard.recentExports')}</h2>
          <Link to={link('/exports')} className="link">
            {t('resourceAccounting.dashboard.allExports')}
          </Link>
        </div>
        {exportsQuery.isLoading ? (
          <Loading />
        ) : exportsQuery.isError ? (
          <ErrorState error={exportsQuery.error} onRetry={() => exportsQuery.refetch()} />
        ) : recentExports.length === 0 ? (
          <Empty text={t('resourceAccounting.exports.empty')} />
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>{t('resourceAccounting.exports.period')}</th>
                <th>{t('resourceAccounting.exports.format')}</th>
                <th>{t('resourceAccounting.exports.colStatus')}</th>
                <th>{t('resourceAccounting.exports.colCreated')}</th>
              </tr>
            </thead>
            <tbody>
              {recentExports.map((exp) => (
                <tr key={exp.id}>
                  <td>{exp.period_month ? formatMonth(exp.period_month) : '—'}</td>
                  <td className="mono">{exp.format.toUpperCase()}</td>
                  <td>{EXPORT_STATUS_KEYS[exp.status] ? t(EXPORT_STATUS_KEYS[exp.status]) : exp.status}</td>
                  <td>{formatDateTime(exp.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
