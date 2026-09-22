import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { api, ApiError, downloadUrl } from '../api/client';
import type { ExportFormat, ExportItem, Period, Provider, ResourceType } from '../api/types';
import { EXPORT_STATUS_KEYS } from '../api/types';
import { Empty, ErrorState, Loading } from '../components/DataState';
import { Modal } from '../components/Modal';
import { useResourceFormat } from '../utils/useResourceFormat';
import { canEnterReadings } from '../auth/roles';
import { useResourceAuth } from '../auth/ResourceAuthContext';

const CHANNEL_KEYS: Record<string, string> = {
  email: 'resourceAccounting.exports.channels.email',
  edi: 'resourceAccounting.exports.channels.edi',
  paper: 'resourceAccounting.exports.channels.paper',
  other: 'resourceAccounting.exports.channels.other',
};

export function ExportsPage() {
  const { t } = useTranslation();
  const { formatDateTime, formatMonth } = useResourceFormat();
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
    onError: (e) => setCreateError(e instanceof ApiError ? e.message : t('resourceAccounting.exports.createError')),
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
    onError: (e) => setActionError(e instanceof ApiError ? e.message : t('resourceAccounting.common.error')),
  });

  const cancelExport = useMutation({
    mutationFn: (exp: ExportItem) => api(`/v1/exports/${exp.id}/cancel`, { method: 'POST' }),
    onSuccess: invalidate,
    onError: (e) => setActionError(e instanceof ApiError ? e.message : t('resourceAccounting.common.error')),
  });

  const periods = [...(periodsQuery.data ?? [])].sort((a, b) => b.month.localeCompare(a.month));

  return (
    <div>
      <div className="page-header">
        <h1>{t('resourceAccounting.exports.title')}</h1>
      </div>

      {canCreate && (
        <div className="panel">
          <h2>{t('resourceAccounting.exports.createTitle')}</h2>
          <div className="toolbar">
            <label className="field-inline">
              <span>{t('resourceAccounting.exports.period')}</span>
              <select value={month} onChange={(e) => setMonth(e.target.value)}>
                <option value="">{t('resourceAccounting.exports.choose')}</option>
                {periods.map((p) => (
                  <option key={p.id} value={p.month}>
                    {formatMonth(p.month)}
                  </option>
                ))}
              </select>
            </label>
            <label className="field-inline">
              <span>{t('resourceAccounting.exports.format')}</span>
              <select value={format} onChange={(e) => setFormat(e.target.value as ExportFormat)}>
                <option value="xlsx">XLSX</option>
                <option value="csv">CSV</option>
                <option value="pdf">PDF</option>
              </select>
            </label>
            <label className="field-inline">
              <span>{t('resourceAccounting.exports.provider')}</span>
              <select value={providerId} onChange={(e) => setProviderId(e.target.value)}>
                <option value="">{t('resourceAccounting.common.all')}</option>
                {(providersQuery.data ?? []).map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="field-inline">
              <span>{t('resourceAccounting.exports.resource')}</span>
              <select
                value={resourceType}
                onChange={(e) => setResourceType(e.target.value as '' | ResourceType)}
              >
                <option value="">{t('resourceAccounting.common.all')}</option>
                <option value="electricity">{t('resourceAccounting.resourceTypes.electricity')}</option>
                <option value="cold_water">{t('resourceAccounting.resourceTypes.cold_water')}</option>
              </select>
            </label>
            <label className="checkbox-inline">
              <input
                type="checkbox"
                checked={isCorrection}
                onChange={(e) => setIsCorrection(e.target.checked)}
              />
              {t('resourceAccounting.exports.correction')}
            </label>
            <button
              className="btn btn-primary"
              disabled={!month || createExport.isPending}
              onClick={() => createExport.mutate()}
            >
              {createExport.isPending ? t('resourceAccounting.exports.creating') : t('resourceAccounting.exports.createTitle')}
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
        <h2>{t('resourceAccounting.exports.history')}</h2>
        {exportsQuery.isLoading ? (
          <Loading />
        ) : exportsQuery.isError ? (
          <ErrorState error={exportsQuery.error} onRetry={() => exportsQuery.refetch()} />
        ) : (exportsQuery.data ?? []).length === 0 ? (
          <Empty text={t('resourceAccounting.exports.empty')} />
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>{t('resourceAccounting.exports.period')}</th>
                  <th>{t('resourceAccounting.exports.format')}</th>
                  <th>{t('resourceAccounting.exports.provider')}</th>
                  <th>{t('resourceAccounting.exports.rows')}</th>
                  <th>{t('resourceAccounting.exports.colStatus')}</th>
                  <th>{t('resourceAccounting.exports.colCreated')}</th>
                  <th>{t('resourceAccounting.exports.colSent')}</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {exportsQuery.data!.map((exp) => (
                  <tr key={exp.id}>
                    <td>
                      {exp.period_month ? formatMonth(exp.period_month) : '—'}
                      {exp.is_correction && <span className="chip">{t('resourceAccounting.exports.correctionChip')}</span>}
                    </td>
                    <td className="mono">{exp.format.toUpperCase()}</td>
                    <td>{exp.provider_name ?? t('resourceAccounting.common.all')}</td>
                    <td className="num">{exp.row_count ?? '—'}</td>
                    <td>{EXPORT_STATUS_KEYS[exp.status] ? t(EXPORT_STATUS_KEYS[exp.status]) : exp.status}</td>
                    <td className="small">{formatDateTime(exp.created_at)}</td>
                    <td className="small">
                      {exp.sent_at
                        ? `${formatDateTime(exp.sent_at)}${exp.sent_channel ? ` (${CHANNEL_KEYS[exp.sent_channel] ? t(CHANNEL_KEYS[exp.sent_channel]) : exp.sent_channel})` : ''}`
                        : '—'}
                    </td>
                    <td className="cell-actions">
                      {exp.status !== 'cancelled' && (
                        <button
                          className="btn btn-sm"
                          onClick={() => window.open(downloadUrl(`/v1/exports/${exp.id}/download`))}
                        >
                          {t('resourceAccounting.exports.download')}
                        </button>
                      )}
                      {canCreate && exp.status !== 'cancelled' && !exp.sent_at && (
                        <>
                          <button className="btn btn-sm" onClick={() => setMarkSentFor(exp)}>
                            {t('resourceAccounting.exports.markSentButton')}
                          </button>
                          <button
                            className="btn btn-sm btn-ghost text-error"
                            onClick={() => {
                              if (window.confirm(t('resourceAccounting.exports.cancelConfirm'))) cancelExport.mutate(exp);
                            }}
                          >
                            {t('resourceAccounting.exports.cancelExport')}
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
        <Modal title={t('resourceAccounting.exports.markSentTitle')} onClose={() => setMarkSentFor(null)}>
          <label className="field">
            <span>{t('resourceAccounting.exports.channel')}</span>
            <select value={channel} onChange={(e) => setChannel(e.target.value)}>
              <option value="email">{t('resourceAccounting.exports.channels.email')}</option>
              <option value="edi">{t('resourceAccounting.exports.channels.edi')}</option>
              <option value="paper">{t('resourceAccounting.exports.channels.paper')}</option>
              <option value="other">{t('resourceAccounting.exports.channels.other')}</option>
            </select>
          </label>
          <label className="field">
            <span>{t('resourceAccounting.exports.comment')}</span>
            <textarea rows={2} value={comment} onChange={(e) => setComment(e.target.value)} />
          </label>
          <div className="modal-actions">
            <button className="btn" onClick={() => setMarkSentFor(null)}>
              {t('resourceAccounting.common.cancel')}
            </button>
            <button
              className="btn btn-primary"
              disabled={markSent.isPending}
              onClick={() => markSent.mutate(markSentFor)}
            >
              {t('resourceAccounting.exports.confirm')}
            </button>
          </div>
        </Modal>
      )}
    </div>
  );
}
