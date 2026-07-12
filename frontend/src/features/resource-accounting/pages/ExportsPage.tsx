import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, ApiError, downloadUrl } from '../api/client';
import type { ExportFormat, ExportItem, Period, Provider, ResourceType } from '../api/types';
import { Empty, ErrorState, Loading } from '../components/DataState';
import { Modal } from '../components/Modal';
import { formatDateTime, formatMonth } from '../utils/format';
import { canEnterReadings } from '../auth/roles';
import { useResourceAuth } from '../auth/ResourceAuthContext';

const EXPORT_STATUS_LABELS: Record<string, string> = {
  created: 'Создан',
  generated: 'Сформирован',
  sent: 'Отправлен',
  cancelled: 'Отменён',
};

export function ExportsPage() {
  const { role } = useResourceAuth();
  const canCreate = canEnterReadings(role);
  const queryClient = useQueryClient();

  const [month, setMonth] = useState('');
  const [format, setFormat] = useState<ExportFormat>('xlsx');
  const [providerId, setProviderId] = useState('');
  const [resourceType, setResourceType] = useState<'' | ResourceType>('');
  const [isCorrection, setIsCorrection] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const [markSentFor, setMarkSentFor] = useState<ExportItem | null>(null);
  const [channel, setChannel] = useState('email');
  const [comment, setComment] = useState('');
  const [actionError, setActionError] = useState<string | null>(null);

  const periodsQuery = useQuery({
    queryKey: ['periods'],
    queryFn: () => api<Period[]>('/v1/periods'),
  });
  const providersQuery = useQuery({
    queryKey: ['providers'],
    queryFn: () => api<Provider[]>('/v1/providers'),
  });
  const exportsQuery = useQuery({
    queryKey: ['exports'],
    queryFn: () => api<ExportItem[]>('/v1/exports'),
  });

  const invalidate = () => void queryClient.invalidateQueries({ queryKey: ['exports'] });

  const createExport = useMutation({
    mutationFn: () =>
      api<ExportItem>('/v1/exports', {
        method: 'POST',
        body: {
          month,
          format,
          provider_id: providerId || null,
          resource_type: resourceType || null,
          is_correction: isCorrection,
        },
      }),
    onSuccess: () => {
      setCreateError(null);
      invalidate();
    },
    onError: (e) => setCreateError(e instanceof ApiError ? e.message : 'Ошибка создания акта'),
  });

  const markSent = useMutation({
    mutationFn: (exp: ExportItem) =>
      api(`/v1/exports/${exp.id}/mark-sent`, {
        method: 'POST',
        body: { channel, comment: comment.trim() || null },
      }),
    onSuccess: () => {
      setMarkSentFor(null);
      setChannel('email');
      setComment('');
      invalidate();
    },
    onError: (e) => setActionError(e instanceof ApiError ? e.message : 'Ошибка'),
  });

  const cancelExport = useMutation({
    mutationFn: (exp: ExportItem) => api(`/v1/exports/${exp.id}/cancel`, { method: 'POST' }),
    onSuccess: invalidate,
    onError: (e) => setActionError(e instanceof ApiError ? e.message : 'Ошибка'),
  });

  const periods = [...(periodsQuery.data ?? [])].sort((a, b) => b.month.localeCompare(a.month));

  return (
    <div>
      <div className="page-header">
        <h1>Акты сверки</h1>
      </div>

      {canCreate && (
        <div className="panel">
          <h2>Создать акт</h2>
          <div className="toolbar">
            <label className="field-inline">
              <span>Период</span>
              <select value={month} onChange={(e) => setMonth(e.target.value)}>
                <option value="">— выберите —</option>
                {periods.map((p) => (
                  <option key={p.id} value={p.month}>
                    {formatMonth(p.month)}
                  </option>
                ))}
              </select>
            </label>
            <label className="field-inline">
              <span>Формат</span>
              <select value={format} onChange={(e) => setFormat(e.target.value as ExportFormat)}>
                <option value="xlsx">XLSX</option>
                <option value="csv">CSV</option>
                <option value="pdf">PDF</option>
              </select>
            </label>
            <label className="field-inline">
              <span>Поставщик</span>
              <select value={providerId} onChange={(e) => setProviderId(e.target.value)}>
                <option value="">Все</option>
                {(providersQuery.data ?? []).map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="field-inline">
              <span>Ресурс</span>
              <select
                value={resourceType}
                onChange={(e) => setResourceType(e.target.value as '' | ResourceType)}
              >
                <option value="">Все</option>
                <option value="electricity">Электроэнергия</option>
                <option value="cold_water">Холодная вода</option>
              </select>
            </label>
            <label className="checkbox-inline">
              <input
                type="checkbox"
                checked={isCorrection}
                onChange={(e) => setIsCorrection(e.target.checked)}
              />
              Корректировочный
            </label>
            <button
              className="btn btn-primary"
              disabled={!month || createExport.isPending}
              onClick={() => createExport.mutate()}
            >
              {createExport.isPending ? 'Создание…' : 'Создать акт'}
            </button>
          </div>
          {createError && <div className="form-error">{createError}</div>}
        </div>
      )}

      {actionError && (
        <div className="form-error" role="alert">
          {actionError}
          <button className="btn btn-sm btn-ghost" onClick={() => setActionError(null)}>
            ×
          </button>
        </div>
      )}

      <div className="panel">
        <h2>История</h2>
        {exportsQuery.isLoading ? (
          <Loading />
        ) : exportsQuery.isError ? (
          <ErrorState error={exportsQuery.error} onRetry={() => exportsQuery.refetch()} />
        ) : (exportsQuery.data ?? []).length === 0 ? (
          <Empty text="Актов пока нет" />
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Период</th>
                  <th>Формат</th>
                  <th>Поставщик</th>
                  <th>Строк</th>
                  <th>Статус</th>
                  <th>Создан</th>
                  <th>Отправлен</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {exportsQuery.data!.map((exp) => (
                  <tr key={exp.id}>
                    <td>
                      {exp.period_month ? formatMonth(exp.period_month) : '—'}
                      {exp.is_correction && <span className="chip">корр.</span>}
                    </td>
                    <td className="mono">{exp.format.toUpperCase()}</td>
                    <td>{exp.provider_name ?? 'Все'}</td>
                    <td className="num">{exp.row_count ?? '—'}</td>
                    <td>{EXPORT_STATUS_LABELS[exp.status] ?? exp.status}</td>
                    <td className="small">{formatDateTime(exp.created_at)}</td>
                    <td className="small">
                      {exp.sent_at
                        ? `${formatDateTime(exp.sent_at)}${exp.sent_channel ? ` (${exp.sent_channel})` : ''}`
                        : '—'}
                    </td>
                    <td className="cell-actions">
                      {exp.status !== 'cancelled' && (
                        <button
                          className="btn btn-sm"
                          onClick={() => window.open(downloadUrl(`/v1/exports/${exp.id}/download`))}
                        >
                          Скачать
                        </button>
                      )}
                      {canCreate && exp.status !== 'cancelled' && !exp.sent_at && (
                        <>
                          <button className="btn btn-sm" onClick={() => setMarkSentFor(exp)}>
                            Отправлен
                          </button>
                          <button
                            className="btn btn-sm btn-ghost text-error"
                            onClick={() => {
                              if (window.confirm('Отменить акт?')) cancelExport.mutate(exp);
                            }}
                          >
                            Отменить
                          </button>
                        </>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {markSentFor && (
        <Modal title="Отметить как отправленный" onClose={() => setMarkSentFor(null)}>
          <label className="field">
            <span>Канал отправки *</span>
            <select value={channel} onChange={(e) => setChannel(e.target.value)}>
              <option value="email">Email</option>
              <option value="edi">ЭДО</option>
              <option value="paper">Бумажный</option>
              <option value="other">Другое</option>
            </select>
          </label>
          <label className="field">
            <span>Комментарий</span>
            <textarea rows={2} value={comment} onChange={(e) => setComment(e.target.value)} />
          </label>
          <div className="modal-actions">
            <button className="btn" onClick={() => setMarkSentFor(null)}>
              Отмена
            </button>
            <button
              className="btn btn-primary"
              disabled={markSent.isPending}
              onClick={() => markSent.mutate(markSentFor)}
            >
              Подтвердить
            </button>
          </div>
        </Modal>
      )}
    </div>
  );
}
