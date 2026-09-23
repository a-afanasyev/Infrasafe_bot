import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { apiPaged } from '../api/client';
import type { AuditEntry } from '../api/types';
import { Empty, ErrorState, Loading } from '../components/DataState';
import { useResourceFormat } from '../utils/useResourceFormat';

const ENTITY_TYPES = [
  { value: '', labelKey: 'resourceAccounting.audit.entities.all' },
  { value: 'meter', labelKey: 'resourceAccounting.audit.entities.meter' },
  { value: 'reading', labelKey: 'resourceAccounting.audit.entities.reading' },
  { value: 'period', labelKey: 'resourceAccounting.audit.entities.period' },
  { value: 'object', labelKey: 'resourceAccounting.audit.entities.object' },
  { value: 'export', labelKey: 'resourceAccounting.audit.entities.export' },
  { value: 'provider', labelKey: 'resourceAccounting.audit.entities.provider' },
  { value: 'session', labelKey: 'resourceAccounting.audit.entities.session' },
];

function summarize(value: unknown): string {
  if (value === null || value === undefined) return '—';
  try {
    const s = JSON.stringify(value);
    return s.length > 120 ? `${s.slice(0, 120)}…` : s;
  } catch {
    return String(value);
  }
}

export function AuditPage() {
  const { t } = useTranslation();
  const { formatDateTime } = useResourceFormat();
  const [entityType, setEntityType] = useState('');
  const [action, setAction] = useState('');
  const [page, setPage] = useState(1);

  const auditQuery = useQuery({
    queryKey: ['audit', entityType, action, page],
    queryFn: () =>
      apiPaged<AuditEntry>('/v1/audit', {
        params: { entity_type: entityType, action, page },
      }),
  });

  const meta = auditQuery.data?.meta;
  const totalPages = useMemo(
    () => (meta ? Math.max(1, Math.ceil(meta.total / meta.per_page)) : 1),
    [meta],
  );

  return (
    <div>
      <div className="page-header">
        <h1>{t('resourceAccounting.audit.title')}</h1>
      </div>

      <div className="toolbar">
        <label className="field-inline">
          <span>{t('resourceAccounting.audit.entity')}</span>
          <select
            value={entityType}
            onChange={(e) => {
              setEntityType(e.target.value);
              setPage(1);
            }}
          >
            {ENTITY_TYPES.map((et) => (
              <option key={et.value} value={et.value}>
                {t(et.labelKey)}
              </option>
            ))}
          </select>
        </label>
        <label className="field-inline">
          <span>{t('resourceAccounting.audit.action')}</span>
          <input
            placeholder="create, update…"
            value={action}
            onChange={(e) => {
              setAction(e.target.value);
              setPage(1);
            }}
          />
        </label>
      </div>

      {auditQuery.isLoading ? (
        <Loading />
      ) : auditQuery.isError ? (
        <ErrorState error={auditQuery.error} onRetry={() => auditQuery.refetch()} />
      ) : auditQuery.data!.data.length === 0 ? (
        <Empty text={t('resourceAccounting.audit.empty')} />
      ) : (
        <>
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>{t('resourceAccounting.audit.colDate')}</th>
                  <th>{t('resourceAccounting.audit.entity')}</th>
                  <th>{t('resourceAccounting.audit.action')}</th>
                  <th>{t('resourceAccounting.audit.colActor')}</th>
                  <th>{t('resourceAccounting.audit.colBefore')}</th>
                  <th>{t('resourceAccounting.audit.colAfter')}</th>
                </tr>
              </thead>
              <tbody>
                {auditQuery.data!.data.map((entry) => (
                  <tr key={entry.id}>
                    <td className="small">{formatDateTime(entry.created_at)}</td>
                    <td>
                      {entry.entity_type}
                      <div className="mono muted small">{entry.entity_id}</div>
                    </td>
                    <td className="mono small">{entry.action}</td>
                    <td>{entry.actor_name ?? '—'}</td>
                    <td className="mono small cell-json">{summarize(entry.before)}</td>
                    <td className="mono small cell-json">{summarize(entry.after)}</td>
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
    </div>
  );
}
