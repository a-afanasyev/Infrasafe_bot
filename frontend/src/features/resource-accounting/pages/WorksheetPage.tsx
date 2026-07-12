import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../api/client';
import type {
  ObjectNode,
  Period,
  ResourceType,
  ValidationSummary,
  Worksheet,
} from '../api/types';
import { RESOURCE_TYPE_LABELS } from '../api/types';
import { Empty, ErrorState, Loading } from '../components/DataState';
import { PeriodStatusBadge, ReadingStatusBadge } from '../components/StatusBadge';
import { Modal } from '../components/Modal';
import { formatMonth, formatNumber } from '../utils/format';
import { canEnterReadings, canReview } from '../auth/roles';
import { useResourceAuth } from '../auth/ResourceAuthContext';

interface DraftRow {
  value: string;
  comment: string;
}

function useDebounced<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}

function defaultMonth(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
}

export function WorksheetPage({ entryMode = false }: { entryMode?: boolean } = {}) {
  const { role } = useResourceAuth();
  const queryClient = useQueryClient();

  const [selectedMonth, setSelectedMonth] = useState<string | null>(null);
  const [resourceType, setResourceType] = useState<'' | ResourceType>('');
  const [objectId, setObjectId] = useState('');
  const [search, setSearch] = useState('');
  const debouncedSearch = useDebounced(search, 300);
  const [drafts, setDrafts] = useState<Record<string, DraftRow>>({});
  const [createPeriodOpen, setCreatePeriodOpen] = useState(false);
  const [newMonth, setNewMonth] = useState(defaultMonth());
  const [actionError, setActionError] = useState<string | null>(null);

  const periodsQuery = useQuery({
    queryKey: ['periods'],
    queryFn: () => api<Period[]>('/v1/periods'),
  });

  const periods = useMemo(
    () => [...(periodsQuery.data ?? [])].sort((a, b) => b.month.localeCompare(a.month)),
    [periodsQuery.data],
  );

  // Контролёр (entryMode): работает только в открытом периоде, без переключения на прочие.
  const openMonth = periods.find((p) => p.status === 'open')?.month ?? null;
  const month = selectedMonth ?? (entryMode ? openMonth : periods[0]?.month) ?? null;
  const period = periods.find((p) => p.month === month) ?? null;
  const editable = Boolean(period && period.status === 'open' && canEnterReadings(role));

  const worksheetQuery = useQuery({
    queryKey: ['worksheet', month, resourceType, objectId],
    queryFn: () =>
      api<Worksheet>(`/v1/periods/${month}/worksheet`, {
        params: { resource_type: resourceType, object_id: objectId },
      }),
    enabled: Boolean(month),
  });

  const objectsQuery = useQuery({
    queryKey: ['objects', 'all'],
    queryFn: () => api<ObjectNode[]>('/v1/objects', { params: { status: 'active' } }),
    enabled: !entryMode, // контролёру объекты недоступны (403)
  });

  const canValidate = !entryMode && role !== 'resource_viewer';
  const validationQuery = useQuery({
    queryKey: ['validate', month],
    queryFn: () => api<ValidationSummary>(`/v1/periods/${month}/validate`, { method: 'POST' }),
    enabled: Boolean(month) && canValidate,
  });

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ['worksheet'] });
    void queryClient.invalidateQueries({ queryKey: ['validate'] });
    void queryClient.invalidateQueries({ queryKey: ['periods'] });
  };

  const createPeriod = useMutation({
    mutationFn: (m: string) => api<Period>('/v1/periods', { method: 'POST', body: { month: m } }),
    onSuccess: (created) => {
      setCreatePeriodOpen(false);
      setSelectedMonth(created.month);
      invalidate();
    },
    onError: (e: Error) => setActionError(e.message),
  });

  const bulkSave = useMutation({
    mutationFn: (items: { meter_id: string; value: string; comment?: string | null }[]) =>
      api(`/v1/periods/${month}/readings/bulk`, {
        method: 'POST',
        body: {
          items: items.map((item) => ({
            meter_id: item.meter_id,
            value: item.value,
            comment: item.comment || null,
          })),
        },
      }),
    onSuccess: () => {
      setDrafts({});
      invalidate();
    },
    onError: (e: Error) => setActionError(e.message),
  });

  const transition = useMutation({
    mutationFn: (action: 'move-to-review' | 'reopen' | 'submit' | 'close') =>
      api(`/v1/periods/${month}/${action}`, { method: 'POST' }),
    onSuccess: invalidate,
    onError: (e: Error) => setActionError(e.message),
  });

  const rows = worksheetQuery.data?.rows ?? [];
  const filteredRows = useMemo(() => {
    const q = debouncedSearch.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter((r) => r.meter_number.toLowerCase().includes(q));
  }, [rows, debouncedSearch]);

  const changedItems = useMemo(() => {
    const items: { meter_id: string; value: string; comment?: string | null }[] = [];
    for (const row of rows) {
      const draft = drafts[row.meter_id];
      if (!draft) continue;
      const current = row.reading?.value != null ? formatNumber(row.reading.value) : '';
      const draftValue = draft.value.trim();
      const currentComment = row.reading?.comment ?? '';
      // COR-12: сравниваем нормализованные числа, чтобы "123.0" vs "123.0000" не считалось изменением
      const valueChanged = formatNumber(draftValue) !== current;
      if (draftValue !== '' && (valueChanged || draft.comment !== currentComment)) {
        items.push({ meter_id: row.meter_id, value: draftValue, comment: draft.comment || null });
      }
    }
    return items;
  }, [rows, drafts]);

  const setDraft = (meterId: string, patch: Partial<DraftRow>, row: (typeof rows)[number]) => {
    setDrafts((prev) => {
      const existing = prev[meterId] ?? {
        value: row.reading?.value != null ? formatNumber(row.reading.value) : '',
        comment: row.reading?.comment ?? '',
      };
      return { ...prev, [meterId]: { ...existing, ...patch } };
    });
  };

  const v = validationQuery.data;

  return (
    <div>
      <div className="page-header">
        <h1>Ввод показаний</h1>
      </div>

      <div className="toolbar">
        {entryMode ? (
          <span className="field-inline">
            <span>Период</span>
            <strong>{month ? formatMonth(month) : '— нет открытого периода —'}</strong>
          </span>
        ) : (
          <label className="field-inline">
            <span>Период</span>
            <select
              value={month ?? ''}
              onChange={(e) => {
                setSelectedMonth(e.target.value);
                setDrafts({});
              }}
            >
              {periods.length === 0 && <option value="">—</option>}
              {periods.map((p) => (
                <option key={p.id} value={p.month}>
                  {formatMonth(p.month)}
                </option>
              ))}
            </select>
          </label>
        )}
        {!entryMode && canEnterReadings(role) && (
          <button className="btn" onClick={() => setCreatePeriodOpen(true)}>
            Создать период
          </button>
        )}
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
        {!entryMode && (
          <label className="field-inline">
            <span>Объект</span>
            <select value={objectId} onChange={(e) => setObjectId(e.target.value)}>
              <option value="">Все</option>
              {(objectsQuery.data ?? []).map((o) => (
                <option key={o.id} value={o.id}>
                  {o.name}
                </option>
              ))}
            </select>
          </label>
        )}
        <input
          className="search-input"
          placeholder="Поиск по номеру…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        {editable && (
          <button
            className="btn btn-primary"
            disabled={changedItems.length === 0 || bulkSave.isPending}
            onClick={() => bulkSave.mutate(changedItems)}
          >
            {bulkSave.isPending ? 'Сохранение…' : `Сохранить всё (${changedItems.length})`}
          </button>
        )}
      </div>

      {actionError && (
        <div className="form-error" role="alert">
          {actionError}
          <button className="btn btn-sm btn-ghost" onClick={() => setActionError(null)}>
            ×
          </button>
        </div>
      )}

      {period && !entryMode && (
        <div className="period-panel">
          <div className="period-panel-status">
            Статус периода: <PeriodStatusBadge status={period.status} />
            {v && (
              <span className="period-panel-validation">
                введено {v.entered} из {v.active_meters}, не введено {v.not_entered},{' '}
                <span className="text-warning">предупр. {v.by_status?.warning ?? 0}</span>,{' '}
                <span className="text-error">ошибок {v.errors}</span>
                {v.warnings_without_comment > 0 &&
                  `, без комментария ${v.warnings_without_comment}`}
              </span>
            )}
          </div>
          <div className="period-panel-actions">
            {period.status === 'open' && canEnterReadings(role) && (
              <button
                className="btn btn-sm"
                disabled={transition.isPending}
                onClick={() => transition.mutate('move-to-review')}
              >
                На проверку
              </button>
            )}
            {period.status === 'review' && canReview(role) && (
              <>
                <button
                  className="btn btn-sm"
                  disabled={transition.isPending}
                  onClick={() => transition.mutate('reopen')}
                >
                  Вернуть в работу
                </button>
                <button
                  className="btn btn-sm btn-primary"
                  disabled={transition.isPending || (v ? !v.can_submit : false)}
                  onClick={() => transition.mutate('submit')}
                  title={v && !v.can_submit ? 'Есть ошибки или незаполненные показания' : ''}
                >
                  Передать
                </button>
              </>
            )}
            {period.status === 'submitted' && canReview(role) && (
              <button
                className="btn btn-sm"
                disabled={transition.isPending}
                onClick={() => transition.mutate('close')}
              >
                Закрыть период
              </button>
            )}
          </div>
        </div>
      )}

      {!month ? (
        <Empty text={entryMode ? 'Нет открытого периода. Обратитесь к менеджеру.' : 'Периоды ещё не созданы'} />
      ) : worksheetQuery.isLoading ? (
        <Loading />
      ) : worksheetQuery.isError ? (
        <ErrorState error={worksheetQuery.error} onRetry={() => worksheetQuery.refetch()} />
      ) : filteredRows.length === 0 ? (
        <Empty text={debouncedSearch ? 'Ничего не найдено' : 'В ведомости нет счётчиков'} />
      ) : (
        <div className="table-wrap">
          <table className="table table-worksheet">
            <thead>
              <tr>
                <th>Номер</th>
                <th>Счётчик</th>
                <th>Объект</th>
                <th>Потребители</th>
                <th className="num">Предыдущее</th>
                <th className="num">Текущее</th>
                <th className="num">Расход</th>
                <th>Статус</th>
                <th>Комментарий</th>
              </tr>
            </thead>
            <tbody>
              {filteredRows.map((row) => {
                const draft = drafts[row.meter_id];
                const inputValue =
                  draft !== undefined
                    ? draft.value
                    : row.reading?.value != null
                      ? formatNumber(row.reading.value)
                      : '';
                const commentValue =
                  draft !== undefined ? draft.comment : (row.reading?.comment ?? '');
                return (
                  <tr key={row.meter_id}>
                    <td className="mono">{row.meter_number}</td>
                    <td>
                      <div>{row.meter_name}</div>
                      <div className="muted small">
                        {RESOURCE_TYPE_LABELS[row.resource_type]}, {row.unit}
                      </div>
                    </td>
                    <td>{row.primary_object_name}</td>
                    <td className="small">{row.consumers.join(', ') || '—'}</td>
                    <td className="num mono">{formatNumber(row.previous_value)}</td>
                    <td className="num">
                      {editable ? (
                        <input
                          className="input-reading"
                          inputMode="decimal"
                          aria-label={`Показание ${row.meter_number}`}
                          value={inputValue}
                          onChange={(e) => setDraft(row.meter_id, { value: e.target.value }, row)}
                        />
                      ) : (
                        <span className="mono">{formatNumber(row.reading?.value)}</span>
                      )}
                    </td>
                    <td className="num mono">{formatNumber(row.reading?.consumption)}</td>
                    <td>
                      <ReadingStatusBadge status={row.reading?.status ?? null} />
                      {row.reading?.validation_message && (
                        <div className="muted small">{row.reading.validation_message}</div>
                      )}
                    </td>
                    <td>
                      {editable ? (
                        <input
                          className="input-comment"
                          aria-label={`Комментарий ${row.meter_number}`}
                          value={commentValue}
                          onChange={(e) => setDraft(row.meter_id, { comment: e.target.value }, row)}
                        />
                      ) : (
                        <span className="small">{row.reading?.comment ?? '—'}</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {createPeriodOpen && (
        <Modal title="Создать период" onClose={() => setCreatePeriodOpen(false)}>
          <label className="field">
            <span>Месяц</span>
            <input
              type="month"
              value={newMonth}
              onChange={(e) => setNewMonth(e.target.value)}
            />
          </label>
          <div className="modal-actions">
            <button className="btn" onClick={() => setCreatePeriodOpen(false)}>
              Отмена
            </button>
            <button
              className="btn btn-primary"
              disabled={!/^\d{4}-\d{2}$/.test(newMonth) || createPeriod.isPending}
              onClick={() => createPeriod.mutate(newMonth)}
            >
              Создать
            </button>
          </div>
        </Modal>
      )}
    </div>
  );
}
