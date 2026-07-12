import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { apiPaged } from '../api/client';
import type { AuditEntry } from '../api/types';
import { Empty, ErrorState, Loading } from '../components/DataState';
import { formatDateTime } from '../utils/format';

const ENTITY_TYPES = [
  { value: '', label: 'Все сущности' },
  { value: 'meter', label: 'Счётчики' },
  { value: 'reading', label: 'Показания' },
  { value: 'period', label: 'Периоды' },
  { value: 'object', label: 'Объекты' },
  { value: 'export', label: 'Акты' },
  { value: 'provider', label: 'Поставщики' },
  { value: 'session', label: 'Сессии' },
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
        <h1>Журнал изменений</h1>
      </div>

      <div className="toolbar">
        <label className="field-inline">
          <span>Сущность</span>
          <select
            value={entityType}
            onChange={(e) => {
              setEntityType(e.target.value);
              setPage(1);
            }}
          >
            {ENTITY_TYPES.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </select>
        </label>
        <label className="field-inline">
          <span>Действие</span>
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
        <Empty text="Записей не найдено" />
      ) : (
        <>
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Дата</th>
                  <th>Сущность</th>
                  <th>Действие</th>
                  <th>Кто</th>
                  <th>Было</th>
                  <th>Стало</th>
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
    </div>
  );
}
