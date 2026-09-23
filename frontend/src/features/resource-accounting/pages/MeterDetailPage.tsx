import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router';
import {
  Bar,
  CartesianGrid,
  Cell,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { api, ApiError } from '../api/client';
import type { Meter, MeterAnalytics, MeterCreatePayload, Provider } from '../api/types';
import { METER_STATUS_KEYS, RESOURCE_TYPE_KEYS } from '../api/types';
import { Empty, ErrorState, Loading } from '../components/DataState';
import { Modal } from '../components/Modal';
import { MeterForm } from '../components/MeterForm';
import { formatNumber } from '../utils/format';
import { useResourceFormat } from '../utils/useResourceFormat';
import { canEnterReadings } from '../auth/roles';
import { useResourceAuth } from '../auth/ResourceAuthContext';
import { useResourceLink } from '../paths';
// Акцент графика — из scoped CSS-токена .ra-root { --accent }, чтобы модуль
// подхватывал бренд хоста автоматически (без VITE_BRAND-слоя).
const accentColor = 'var(--accent)';

type Range = '6m' | '12m' | '24m' | 'all';
type Tab = 'details' | 'chart';

const STATUS_COLORS: Record<string, string> = {
  ok: accentColor,
  warning: '#d97706',
  error: '#dc2626',
  missing: '#9ca3af',
};

export function MeterDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { t } = useTranslation();
  const { formatDate } = useResourceFormat();
  const navigate = useNavigate();
  const link = useResourceLink();
  const { role } = useResourceAuth();
  const queryClient = useQueryClient();
  const canEdit = canEnterReadings(role);

  const [tab, setTab] = useState<Tab>('details');
  const [range, setRange] = useState<Range>('12m');
  const [modal, setModal] = useState<'edit' | 'correct' | 'replace' | 'archive' | null>(null);
  const [modalError, setModalError] = useState<string | null>(null);
  const [newNumber, setNewNumber] = useState('');
  const [reason, setReason] = useState('');
  const [removedAt, setRemovedAt] = useState('');

  const meterQuery = useQuery({
    queryKey: ['meter', id],
    queryFn: () => api<Meter>(`/v1/meters/${id}`),
    enabled: Boolean(id),
  });

  const providersQuery = useQuery({
    queryKey: ['providers'],
    queryFn: () => api<Provider[]>('/v1/providers'),
  });

  const analyticsQuery = useQuery({
    queryKey: ['meter-analytics', id, range],
    queryFn: () => api<MeterAnalytics>(`/v1/analytics/meters/${id}`, { params: { range } }),
    enabled: Boolean(id) && tab === 'chart',
  });

  const closeModal = () => {
    setModal(null);
    setModalError(null);
    setNewNumber('');
    setReason('');
    setRemovedAt('');
  };

  const onMutationError = (e: unknown) =>
    setModalError(e instanceof ApiError ? e.message : t('resourceAccounting.common.operationError'));

  const refetchMeter = () => {
    void queryClient.invalidateQueries({ queryKey: ['meter', id] });
    void queryClient.invalidateQueries({ queryKey: ['meters'] });
  };

  const patchMeter = useMutation({
    mutationFn: (payload: Partial<MeterCreatePayload>) =>
      api<Meter>(`/v1/meters/${id}`, { method: 'PATCH', body: payload }),
    onSuccess: () => {
      refetchMeter();
      closeModal();
    },
    onError: onMutationError,
  });

  const correctNumber = useMutation({
    mutationFn: () =>
      api(`/v1/meters/${id}/correct-number`, {
        method: 'POST',
        body: { new_number: newNumber.trim(), reason: reason.trim() },
      }),
    onSuccess: () => {
      refetchMeter();
      closeModal();
    },
    onError: onMutationError,
  });

  const replaceMeter = useMutation({
    mutationFn: (newMeter: MeterCreatePayload) =>
      api<Meter>(`/v1/meters/${id}/replace`, {
        method: 'POST',
        body: { removed_at: removedAt, reason: reason.trim(), new_meter: newMeter },
      }),
    onSuccess: (created) => {
      refetchMeter();
      closeModal();
      navigate(link(`/meters/${created.id}`));
    },
    onError: onMutationError,
  });

  const archiveMeter = useMutation({
    mutationFn: () => api(`/v1/meters/${id}/archive`, { method: 'POST' }),
    onSuccess: () => {
      refetchMeter();
      closeModal();
    },
    onError: onMutationError,
  });

  if (meterQuery.isLoading) return <Loading />;
  if (meterQuery.isError)
    return <ErrorState error={meterQuery.error} onRetry={() => meterQuery.refetch()} />;
  const meter = meterQuery.data!;
  const provider = providersQuery.data?.find((p) => p.id === meter.provider_id);

  const analytics = analyticsQuery.data;
  const chartData = (analytics?.points ?? []).map((p) => ({
    month: p.month,
    reading: p.reading !== null ? Number(p.reading) : null,
    consumption: p.consumption !== null ? Number(p.consumption) : null,
    status: p.status ?? 'missing',
  }));

  return (
    <div>
      <div className="page-header">
        <div>
          <button className="btn btn-sm btn-ghost" onClick={() => navigate(link('/meters'))}>
            {t('resourceAccounting.meterDetail.backToList')}
          </button>
          <h1>
            <span className="mono">{meter.meter_number}</span> — {meter.name}
          </h1>
          <div className="muted">
            {t(RESOURCE_TYPE_KEYS[meter.resource_type])}, {meter.unit} ·{' '}
            {METER_STATUS_KEYS[meter.status] ? t(METER_STATUS_KEYS[meter.status]) : meter.status}
          </div>
        </div>
        {canEdit && meter.status === 'active' && (
          <div className="btn-group">
            <button className="btn" onClick={() => setModal('edit')}>
              {t('resourceAccounting.meterDetail.edit')}
            </button>
            <button className="btn" onClick={() => setModal('correct')}>
              {t('resourceAccounting.meterDetail.correctNumber')}
            </button>
            <button className="btn" onClick={() => setModal('replace')}>
              {t('resourceAccounting.meterDetail.replace')}
            </button>
            <button className="btn btn-danger" onClick={() => setModal('archive')}>
              {t('resourceAccounting.meterDetail.toArchive')}
            </button>
          </div>
        )}
      </div>

      <div className="tabs">
        <button className={`tab${tab === 'details' ? ' active' : ''}`} onClick={() => setTab('details')}>
          {t('resourceAccounting.meterDetail.tabDetails')}
        </button>
        <button className={`tab${tab === 'chart' ? ' active' : ''}`} onClick={() => setTab('chart')}>
          {t('resourceAccounting.meterDetail.tabChart')}
        </button>
      </div>

      {tab === 'details' && (
        <div className="detail-grid">
          <section className="panel">
            <h2>{t('resourceAccounting.meterDetail.tabDetails')}</h2>
            <dl className="props">
              <dt>{t('resourceAccounting.meterDetail.description')}</dt>
              <dd>{meter.description}</dd>
              <dt>{t('resourceAccounting.meterDetail.installLocation')}</dt>
              <dd>{meter.install_location}</dd>
              <dt>{t('resourceAccounting.meterDetail.primaryObject')}</dt>
              <dd>{meter.primary_object_name ?? '—'}</dd>
              <dt>{t('resourceAccounting.meterDetail.provider')}</dt>
              <dd>{provider?.name ?? '—'}</dd>
              <dt>{t('resourceAccounting.meterDetail.providerAccount')}</dt>
              <dd>{meter.provider_account ?? '—'}</dd>
              <dt>{t('resourceAccounting.meterDetail.serialNumber')}</dt>
              <dd>{meter.serial_number ?? '—'}</dd>
              <dt>{t('resourceAccounting.meterDetail.coefficient')}</dt>
              <dd>{formatNumber(meter.coefficient)}</dd>
              <dt>{t('resourceAccounting.meterDetail.maxDigits')}</dt>
              <dd>{meter.max_digits ?? '—'}</dd>
              <dt>{t('resourceAccounting.meterDetail.installedAt')}</dt>
              <dd>{formatDate(meter.installed_at)}</dd>
              {meter.removed_at && (
                <>
                  <dt>{t('resourceAccounting.meterDetail.removedAt')}</dt>
                  <dd>{formatDate(meter.removed_at)}</dd>
                </>
              )}
              <dt>{t('resourceAccounting.meterDetail.note')}</dt>
              <dd>{meter.note ?? '—'}</dd>
              <dt>{t('resourceAccounting.meterDetail.tags')}</dt>
              <dd>{meter.tags.length ? meter.tags.map((tag) => tag.name).join(', ') : '—'}</dd>
            </dl>
          </section>
          <section className="panel">
            <h2>{t('resourceAccounting.meterDetail.consumers')}</h2>
            {meter.consumers.length === 0 ? (
              <Empty text={t('resourceAccounting.meterDetail.noConsumers')} />
            ) : (
              <table className="table">
                <thead>
                  <tr>
                    <th>{t('resourceAccounting.meterDetail.colObject')}</th>
                    <th>{t('resourceAccounting.meterDetail.description')}</th>
                  </tr>
                </thead>
                <tbody>
                  {meter.consumers.map((c, i) => (
                    <tr key={c.id ?? i}>
                      <td>{c.object_name ?? c.object_id}</td>
                      <td>{c.description ?? '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>
        </div>
      )}

      {tab === 'chart' && (
        <section className="panel">
          <div className="panel-header">
            <h2>{t('resourceAccounting.meterDetail.chartTitle')}</h2>
            <div className="btn-group">
              {(['6m', '12m', '24m', 'all'] as Range[]).map((r) => (
                <button
                  key={r}
                  className={`btn btn-sm${range === r ? ' btn-primary' : ''}`}
                  onClick={() => setRange(r)}
                >
                  {r === 'all' ? t('resourceAccounting.meterDetail.rangeAll') : t('resourceAccounting.meterDetail.rangeMonths', { n: parseInt(r, 10) })}
                </button>
              ))}
            </div>
          </div>
          {analyticsQuery.isLoading ? (
            <Loading />
          ) : analyticsQuery.isError ? (
            <ErrorState error={analyticsQuery.error} onRetry={() => analyticsQuery.refetch()} />
          ) : chartData.length === 0 ? (
            <Empty text={t('resourceAccounting.meterDetail.noChartData')} />
          ) : (
            <>
              <div className="chart-box">
                <ResponsiveContainer width="100%" height={340}>
                  <ComposedChart data={chartData} margin={{ top: 8, right: 16, bottom: 4, left: 8 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                    <XAxis dataKey="month" tick={{ fontSize: 12 }} />
                    <YAxis
                      yAxisId="consumption"
                      tick={{ fontSize: 12 }}
                      label={{ value: t('resourceAccounting.meterDetail.consumptionAxis', { unit: meter.unit }), angle: -90, position: 'insideLeft', fontSize: 12 }}
                    />
                    <YAxis
                      yAxisId="reading"
                      orientation="right"
                      tick={{ fontSize: 12 }}
                      label={{ value: t('resourceAccounting.meterDetail.reading'), angle: 90, position: 'insideRight', fontSize: 12 }}
                    />
                    <Tooltip
                      formatter={(value, name) => [
                        value !== null && value !== undefined ? formatNumber(Number(value)) : '—',
                        name === 'consumption' ? t('resourceAccounting.meterDetail.consumption') : t('resourceAccounting.meterDetail.reading'),
                      ]}
                    />
                    <Legend
                      formatter={(value) => (value === 'consumption' ? t('resourceAccounting.meterDetail.consumption') : t('resourceAccounting.meterDetail.reading'))}
                    />
                    <Bar yAxisId="consumption" dataKey="consumption" name="consumption" fill={accentColor}>
                      {chartData.map((p, i) => (
                        <Cell key={i} fill={STATUS_COLORS[p.status] ?? STATUS_COLORS.ok} />
                      ))}
                    </Bar>
                    <Line
                      yAxisId="reading"
                      dataKey="reading"
                      name="reading"
                      type="monotone"
                      stroke="#0f172a"
                      strokeWidth={2}
                      connectNulls
                      dot={{ r: 3 }}
                    />
                  </ComposedChart>
                </ResponsiveContainer>
              </div>
              {analytics && (
                <div className="stats-row">
                  <Stat label={t('resourceAccounting.meterDetail.avgMonths', { n: 3 })} value={analytics.stats.avg_3m} unit={meter.unit} />
                  <Stat label={t('resourceAccounting.meterDetail.avgMonths', { n: 6 })} value={analytics.stats.avg_6m} unit={meter.unit} />
                  <Stat label={t('resourceAccounting.meterDetail.avgMonths', { n: 12 })} value={analytics.stats.avg_12m} unit={meter.unit} />
                  <Stat
                    label={t('resourceAccounting.meterDetail.changePrevMonth')}
                    value={analytics.stats.change_abs}
                    unit={meter.unit}
                    extra={
                      analytics.stats.change_pct !== null
                        ? ` (${analytics.stats.change_pct > 0 ? '+' : ''}${analytics.stats.change_pct}%)`
                        : ''
                    }
                  />
                  <Stat
                    label={t('resourceAccounting.meterDetail.yearOverYear')}
                    value={analytics.stats.year_over_year?.change_pct ?? null}
                    unit="%"
                  />
                </div>
              )}
            </>
          )}
        </section>
      )}

      {modal === 'edit' && (
        <Modal title={t('resourceAccounting.meterDetail.editTitle')} width={680} onClose={closeModal}>
          <MeterForm
            mode="edit"
            initial={meter}
            pending={patchMeter.isPending}
            error={modalError}
            onSubmit={(payload) => {
              const { meter_number, resource_type, unit, ...rest } = payload;
              void meter_number;
              void resource_type;
              void unit;
              patchMeter.mutate(rest);
            }}
            onCancel={closeModal}
          />
        </Modal>
      )}

      {modal === 'correct' && (
        <Modal title={t('resourceAccounting.meterDetail.correctTitle')} onClose={closeModal}>
          <p className="muted">
            {t('resourceAccounting.meterDetail.correctHint')}{' '}
            <span className="mono">{meter.meter_number}</span>
          </p>
          <label className="field">
            <span>{t('resourceAccounting.meterDetail.newNumber')}</span>
            <input value={newNumber} onChange={(e) => setNewNumber(e.target.value)} />
          </label>
          <label className="field">
            <span>{t('resourceAccounting.meterDetail.reason')}</span>
            <textarea value={reason} onChange={(e) => setReason(e.target.value)} rows={2} />
          </label>
          {modalError && <div className="form-error">{modalError}</div>}
          <div className="modal-actions">
            <button className="btn" onClick={closeModal}>
              {t('resourceAccounting.common.cancel')}
            </button>
            <button
              className="btn btn-primary"
              disabled={!newNumber.trim() || reason.trim().length < 3 || correctNumber.isPending}
              onClick={() => correctNumber.mutate()}
            >
              {t('resourceAccounting.meterDetail.correct')}
            </button>
          </div>
        </Modal>
      )}

      {modal === 'replace' && (
        <Modal title={t('resourceAccounting.meterDetail.replaceTitle')} width={680} onClose={closeModal}>
          <div className="form-row">
            <label className="field">
              <span>{t('resourceAccounting.meterDetail.removalDate')}</span>
              <input type="date" value={removedAt} onChange={(e) => setRemovedAt(e.target.value)} />
            </label>
            <label className="field">
              <span>{t('resourceAccounting.meterDetail.replaceReason')}</span>
              <input value={reason} onChange={(e) => setReason(e.target.value)} />
            </label>
          </div>
          <h3 className="subheading">{t('resourceAccounting.meterDetail.newMeter')}</h3>
          <MeterForm
            mode="create"
            pending={replaceMeter.isPending}
            error={modalError}
            submitLabel={t('resourceAccounting.meterDetail.replace')}
            onSubmit={(payload) => {
              if (!removedAt || reason.trim().length < 3) {
                setModalError(t('resourceAccounting.meterDetail.replaceValidation'));
                return;
              }
              replaceMeter.mutate(payload);
            }}
            onCancel={closeModal}
          />
        </Modal>
      )}

      {modal === 'archive' && (
        <Modal title={t('resourceAccounting.meterDetail.archiveTitle')} onClose={closeModal}>
          <p>
            {t('resourceAccounting.meterDetail.archiveConfirmBefore')} <span className="mono">{meter.meter_number}</span>{' '}
            {t('resourceAccounting.meterDetail.archiveConfirmAfter')}
          </p>
          {modalError && <div className="form-error">{modalError}</div>}
          <div className="modal-actions">
            <button className="btn" onClick={closeModal}>
              {t('resourceAccounting.common.cancel')}
            </button>
            <button
              className="btn btn-danger"
              disabled={archiveMeter.isPending}
              onClick={() => archiveMeter.mutate()}
            >
              {t('resourceAccounting.meterDetail.toArchive')}
            </button>
          </div>
        </Modal>
      )}
    </div>
  );
}

function Stat({
  label,
  value,
  unit,
  extra = '',
}: {
  label: string;
  value: number | null;
  unit: string;
  extra?: string;
}) {
  return (
    <div className="stat">
      <div className="stat-label">{label}</div>
      <div className="stat-value">
        {value !== null ? `${formatNumber(value)} ${unit}${extra}` : '—'}
      </div>
    </div>
  );
}
