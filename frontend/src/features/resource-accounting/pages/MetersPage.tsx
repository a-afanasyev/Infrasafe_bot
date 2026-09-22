import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router';
import { apiPaged, api, ApiError } from '../api/client';
import type {
  Meter,
  MeterCreatePayload,
  MetersSparklines,
  Provider,
  ResourceType,
} from '../api/types';
import { METER_STATUS_KEYS, RESOURCE_TYPE_KEYS } from '../api/types';
import { Empty, ErrorState, Loading } from '../components/DataState';
import { Modal } from '../components/Modal';
import { MeterForm } from '../components/MeterForm';
import { Sparkline } from '../components/Sparkline';
import { canEnterReadings } from '../auth/roles';
import { useResourceAuth } from '../auth/ResourceAuthContext';
import { useResourceLink } from '../paths';

const PER_PAGE = 25;

export function MetersPage() {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const link = useResourceLink();
  const { role } = useResourceAuth();
  const queryClient = useQueryClient();

  const [q, setQ] = useState('');
  const [debouncedQ, setDebouncedQ] = useState('');
  const [resourceType, setResourceType] = useState<'' | ResourceType>('');
  const [status, setStatus] = useState('active');
  const [providerId, setProviderId] = useState('');
  const [page, setPage] = useState(1);
  const [createOpen, setCreateOpen] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedQ(q);
      setPage(1);
    }, 300);
    return () => clearTimeout(timer);
  }, [q]);

  const providersQuery = useQuery({
    queryKey: ['providers'],
    queryFn: () => api<Provider[]>('/v1/providers'),
  });

  const metersQuery = useQuery({
    queryKey: ['meters', debouncedQ, resourceType, status, providerId, page],
    queryFn: () =>
      apiPaged<Meter>('/v1/meters', {
        params: {
          q: debouncedQ,
          resource_type: resourceType,
          status,
          provider_id: providerId,
          page,
          per_page: PER_PAGE,
        },
      }),
  });

  // Мини-график за 6 мес — одним запросом на все счётчики (не по строке), маппим по id.
  const sparklinesQuery = useQuery({
    queryKey: ['meters-sparklines', resourceType],
    queryFn: () =>
      api<MetersSparklines>('/v1/analytics/meters-sparklines', {
        params: { months: 6, resource_type: resourceType },
      }),
  });
  const seriesMap = sparklinesQuery.data?.series ?? {};

  const createMeter = useMutation({
    mutationFn: (payload: MeterCreatePayload) =>
      api<Meter>('/v1/meters', { method: 'POST', body: payload }),
    onSuccess: (meter) => {
      setCreateOpen(false);
      setCreateError(null);
      void queryClient.invalidateQueries({ queryKey: ['meters'] });
      navigate(link(`/meters/${meter.id}`));
    },
    onError: (e) => setCreateError(e instanceof ApiError ? e.message : t('resourceAccounting.common.saveError')),
  });

  const meta = metersQuery.data?.meta;
  const totalPages = useMemo(
    () => (meta ? Math.max(1, Math.ceil(meta.total / meta.per_page)) : 1),
    [meta],
  );

  return (
    <div>
      <div className="page-header">
        <h1>{t('resourceAccounting.meters.title')}</h1>
        {canEnterReadings(role) && (
          <button className="btn btn-primary" onClick={() => setCreateOpen(true)}>
            {t('resourceAccounting.meters.newMeterButton')}
          </button>
        )}
      </div>

      <div className="toolbar">
        <input
          className="search-input"
          placeholder={t('resourceAccounting.meters.searchPlaceholder')}
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <label className="field-inline">
          <span>{t('resourceAccounting.meters.resource')}</span>
          <select
            value={resourceType}
            onChange={(e) => {
              setResourceType(e.target.value as '' | ResourceType);
              setPage(1);
            }}
          >
            <option value="">{t('resourceAccounting.common.all')}</option>
            <option value="electricity">{t('resourceAccounting.resourceTypes.electricity')}</option>
            <option value="cold_water">{t('resourceAccounting.resourceTypes.cold_water')}</option>
          </select>
        </label>
        <label className="field-inline">
          <span>{t('resourceAccounting.meters.status')}</span>
          <select
            value={status}
            onChange={(e) => {
              setStatus(e.target.value);
              setPage(1);
            }}
          >
            <option value="">{t('resourceAccounting.common.all')}</option>
            <option value="active">{t('resourceAccounting.meters.filterActive')}</option>
            <option value="decommissioned">{t('resourceAccounting.meters.filterDecommissioned')}</option>
            <option value="archived">{t('resourceAccounting.meters.filterArchived')}</option>
          </select>
        </label>
        <label className="field-inline">
          <span>{t('resourceAccounting.meters.provider')}</span>
          <select
            value={providerId}
            onChange={(e) => {
              setProviderId(e.target.value);
              setPage(1);
            }}
          >
            <option value="">{t('resourceAccounting.common.all')}</option>
            {(providersQuery.data ?? []).map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </label>
      </div>

      {metersQuery.isLoading ? (
        <Loading />
      ) : metersQuery.isError ? (
        <ErrorState error={metersQuery.error} onRetry={() => metersQuery.refetch()} />
      ) : metersQuery.data!.data.length === 0 ? (
        <Empty text={t('resourceAccounting.meters.notFound')} />
      ) : (
        <>
          <div className="table-wrap">
            <table className="table table-clickable">
              <thead>
                <tr>
                  <th>{t('resourceAccounting.meters.colNumber')}</th>
                  <th>{t('resourceAccounting.meters.colName')}</th>
                  <th>{t('resourceAccounting.meters.resource')}</th>
                  <th>{t('resourceAccounting.meters.colObject')}</th>
                  <th>{t('resourceAccounting.meters.colInstallLocation')}</th>
                  <th>{t('resourceAccounting.meters.colConsumption6m')}</th>
                  <th>{t('resourceAccounting.meters.colProviderAccount')}</th>
                  <th>{t('resourceAccounting.meters.status')}</th>
                </tr>
              </thead>
              <tbody>
                {metersQuery.data!.data.map((m) => (
                  <tr key={m.id} onClick={() => navigate(link(`/meters/${m.id}`))}>
                    <td className="mono">{m.meter_number}</td>
                    <td>{m.name}</td>
                    <td>{t(RESOURCE_TYPE_KEYS[m.resource_type])}</td>
                    <td>{m.primary_object_name ?? '—'}</td>
                    <td className="small">{m.install_location}</td>
                    <td>
                      <Sparkline
                        values={(seriesMap[m.id] ?? []).map((p) => p.consumption)}
                        unit={m.unit}
                      />
                    </td>
                    <td className="small">
                      {m.provider_id
                        ? `${providersQuery.data?.find((p) => p.id === m.provider_id)?.name ?? ''} ${
                            m.provider_account ?? ''
                          }`.trim() || '—'
                        : '—'}
                    </td>
                    <td>{METER_STATUS_KEYS[m.status] ? t(METER_STATUS_KEYS[m.status]) : m.status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="pagination">
            <button className="btn btn-sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>
              {t('resourceAccounting.common.prev')}
            </button>
            <span>
              {t('resourceAccounting.common.pageOf', { page, total: totalPages, count: meta?.total ?? 0 })}
            </span>
            <button
              className="btn btn-sm"
              disabled={page >= totalPages}
              onClick={() => setPage(page + 1)}
            >
              {t('resourceAccounting.common.next')}
            </button>
          </div>
        </>
      )}

      {createOpen && (
        <Modal title={t('resourceAccounting.meters.newMeterTitle')} width={680} onClose={() => setCreateOpen(false)}>
          <MeterForm
            mode="create"
            pending={createMeter.isPending}
            error={createError}
            submitLabel={t('resourceAccounting.common.create')}
            onSubmit={(payload) => createMeter.mutate(payload)}
            onCancel={() => setCreateOpen(false)}
          />
        </Modal>
      )}
    </div>
  );
}
