import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { apiPaged, api, ApiError } from '../api/client';
import type { Meter, MeterCreatePayload, Provider, ResourceType } from '../api/types';
import { METER_STATUS_LABELS, RESOURCE_TYPE_LABELS } from '../api/types';
import { Empty, ErrorState, Loading } from '../components/DataState';
import { Modal } from '../components/Modal';
import { MeterForm } from '../components/MeterForm';
import { canEnterReadings } from '../auth/roles';
import { useResourceAuth } from '../auth/ResourceAuthContext';
import { useResourceLink } from '../paths';

const PER_PAGE = 25;

export function MetersPage() {
  const navigate = useNavigate();
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
    const t = setTimeout(() => {
      setDebouncedQ(q);
      setPage(1);
    }, 300);
    return () => clearTimeout(t);
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

  const createMeter = useMutation({
    mutationFn: (payload: MeterCreatePayload) =>
      api<Meter>('/v1/meters', { method: 'POST', body: payload }),
    onSuccess: (meter) => {
      setCreateOpen(false);
      setCreateError(null);
      void queryClient.invalidateQueries({ queryKey: ['meters'] });
      navigate(link(`/meters/${meter.id}`));
    },
    onError: (e) => setCreateError(e instanceof ApiError ? e.message : 'Ошибка сохранения'),
  });

  const meta = metersQuery.data?.meta;
  const totalPages = useMemo(
    () => (meta ? Math.max(1, Math.ceil(meta.total / meta.per_page)) : 1),
    [meta],
  );

  return (
    <div>
      <div className="page-header">
        <h1>Счётчики</h1>
        {canEnterReadings(role) && (
          <button className="btn btn-primary" onClick={() => setCreateOpen(true)}>
            + Новый счётчик
          </button>
        )}
      </div>

      <div className="toolbar">
        <input
          className="search-input"
          placeholder="Поиск (номер, название)…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <label className="field-inline">
          <span>Ресурс</span>
          <select
            value={resourceType}
            onChange={(e) => {
              setResourceType(e.target.value as '' | ResourceType);
              setPage(1);
            }}
          >
            <option value="">Все</option>
            <option value="electricity">Электроэнергия</option>
            <option value="cold_water">Холодная вода</option>
          </select>
        </label>
        <label className="field-inline">
          <span>Статус</span>
          <select
            value={status}
            onChange={(e) => {
              setStatus(e.target.value);
              setPage(1);
            }}
          >
            <option value="">Все</option>
            <option value="active">Активные</option>
            <option value="decommissioned">Снятые</option>
            <option value="archived">Архив</option>
          </select>
        </label>
        <label className="field-inline">
          <span>Поставщик</span>
          <select
            value={providerId}
            onChange={(e) => {
              setProviderId(e.target.value);
              setPage(1);
            }}
          >
            <option value="">Все</option>
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
        <Empty text="Счётчики не найдены" />
      ) : (
        <>
          <div className="table-wrap">
            <table className="table table-clickable">
              <thead>
                <tr>
                  <th>Номер</th>
                  <th>Название</th>
                  <th>Ресурс</th>
                  <th>Объект</th>
                  <th>Место установки</th>
                  <th>Поставщик / лиц. счёт</th>
                  <th>Статус</th>
                </tr>
              </thead>
              <tbody>
                {metersQuery.data!.data.map((m) => (
                  <tr key={m.id} onClick={() => navigate(link(`/meters/${m.id}`))}>
                    <td className="mono">{m.meter_number}</td>
                    <td>{m.name}</td>
                    <td>{RESOURCE_TYPE_LABELS[m.resource_type]}</td>
                    <td>{m.primary_object_name ?? '—'}</td>
                    <td className="small">{m.install_location}</td>
                    <td className="small">
                      {m.provider_id
                        ? `${providersQuery.data?.find((p) => p.id === m.provider_id)?.name ?? ''} ${
                            m.provider_account ?? ''
                          }`.trim() || '—'
                        : '—'}
                    </td>
                    <td>{METER_STATUS_LABELS[m.status] ?? m.status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="pagination">
            <button className="btn btn-sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>
              ← Назад
            </button>
            <span>
              Стр. {page} из {totalPages} (всего {meta?.total ?? 0})
            </span>
            <button
              className="btn btn-sm"
              disabled={page >= totalPages}
              onClick={() => setPage(page + 1)}
            >
              Вперёд →
            </button>
          </div>
        </>
      )}

      {createOpen && (
        <Modal title="Новый счётчик" width={680} onClose={() => setCreateOpen(false)}>
          <MeterForm
            mode="create"
            pending={createMeter.isPending}
            error={createError}
            submitLabel="Создать"
            onSubmit={(payload) => createMeter.mutate(payload)}
            onCancel={() => setCreateOpen(false)}
          />
        </Modal>
      )}
    </div>
  );
}
