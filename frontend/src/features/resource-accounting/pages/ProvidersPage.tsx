import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, ApiError } from '../api/client';
import type { Provider } from '../api/types';
import { Empty, ErrorState, Loading } from '../components/DataState';
import { Modal } from '../components/Modal';
import { ActiveBadge } from '../components/StatusBadge';
import { canEnterReadings } from '../auth/roles';
import { useResourceAuth } from '../auth/ResourceAuthContext';

interface ProviderForm {
  id: string | null;
  name: string;
  contact: string;
}

export function ProvidersPage() {
  const { role } = useResourceAuth();
  const canEdit = canEnterReadings(role);
  const queryClient = useQueryClient();
  const [form, setForm] = useState<ProviderForm | null>(null);
  const [error, setError] = useState<string | null>(null);

  const providersQuery = useQuery({
    queryKey: ['providers'],
    queryFn: () => api<Provider[]>('/v1/providers'),
  });

  const invalidate = () => void queryClient.invalidateQueries({ queryKey: ['providers'] });

  const save = useMutation({
    mutationFn: (f: ProviderForm) => {
      const body = { name: f.name.trim(), contact: f.contact.trim() || null };
      return f.id
        ? api<Provider>(`/v1/providers/${f.id}`, { method: 'PATCH', body })
        : api<Provider>('/v1/providers', { method: 'POST', body });
    },
    onSuccess: () => {
      setForm(null);
      setError(null);
      invalidate();
    },
    onError: (e) => setError(e instanceof ApiError ? e.message : 'Ошибка сохранения'),
  });

  const toggleActive = useMutation({
    mutationFn: (p: Provider) =>
      api<Provider>(`/v1/providers/${p.id}`, { method: 'PATCH', body: { is_active: !p.is_active } }),
    onSuccess: invalidate,
  });

  return (
    <div>
      <div className="page-header">
        <h1>Поставщики</h1>
        {canEdit && (
          <button
            className="btn btn-primary"
            onClick={() => setForm({ id: null, name: '', contact: '' })}
          >
            + Новый поставщик
          </button>
        )}
      </div>

      {providersQuery.isLoading ? (
        <Loading />
      ) : providersQuery.isError ? (
        <ErrorState error={providersQuery.error} onRetry={() => providersQuery.refetch()} />
      ) : (providersQuery.data ?? []).length === 0 ? (
        <Empty text="Поставщики не добавлены" />
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>Название</th>
              <th>Контакты</th>
              <th>Статус</th>
              {canEdit && <th />}
            </tr>
          </thead>
          <tbody>
            {providersQuery.data!.map((p) => (
              <tr key={p.id}>
                <td>{p.name}</td>
                <td className="small">{p.contact ?? '—'}</td>
                <td>
                  <ActiveBadge active={p.is_active} />
                </td>
                {canEdit && (
                  <td className="cell-actions">
                    <button
                      className="btn btn-sm btn-ghost"
                      onClick={() => setForm({ id: p.id, name: p.name, contact: p.contact ?? '' })}
                    >
                      Изменить
                    </button>
                    <button className="btn btn-sm btn-ghost" onClick={() => toggleActive.mutate(p)}>
                      {p.is_active ? 'В архив' : 'Вернуть'}
                    </button>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {form && (
        <Modal
          title={form.id ? 'Редактировать поставщика' : 'Новый поставщик'}
          onClose={() => setForm(null)}
        >
          <label className="field">
            <span>Название *</span>
            <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          </label>
          <label className="field">
            <span>Контакты</span>
            <textarea
              rows={2}
              value={form.contact}
              onChange={(e) => setForm({ ...form, contact: e.target.value })}
            />
          </label>
          {error && <div className="form-error">{error}</div>}
          <div className="modal-actions">
            <button className="btn" onClick={() => setForm(null)}>
              Отмена
            </button>
            <button
              className="btn btn-primary"
              disabled={!form.name.trim() || save.isPending}
              onClick={() => save.mutate(form)}
            >
              Сохранить
            </button>
          </div>
        </Modal>
      )}
    </div>
  );
}
