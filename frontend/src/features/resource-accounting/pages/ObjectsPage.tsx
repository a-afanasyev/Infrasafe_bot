import { useMemo, useState, type JSX } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, ApiError } from '../api/client';
import type { ObjectNode, ObjectType, Tag } from '../api/types';
import { Empty, ErrorState, Loading } from '../components/DataState';
import { Modal } from '../components/Modal';
import { ActiveBadge } from '../components/StatusBadge';
import { canEnterReadings } from '../auth/roles';
import { useResourceAuth } from '../auth/ResourceAuthContext';

type Tab = 'objects' | 'types' | 'tags';

interface ObjectFormState {
  id: string | null;
  name: string;
  code: string;
  type_id: string;
  parent_id: string;
  description: string;
  sort_order: string;
}

const emptyForm: ObjectFormState = {
  id: null,
  name: '',
  code: '',
  type_id: '',
  parent_id: '',
  description: '',
  sort_order: '0',
};

export function ObjectsPage() {
  const { role } = useResourceAuth();
  const canEdit = canEnterReadings(role);
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<Tab>('objects');
  const [form, setForm] = useState<ObjectFormState | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [showArchived, setShowArchived] = useState(false);

  const objectsQuery = useQuery({
    queryKey: ['objects', 'tree', showArchived],
    queryFn: () =>
      api<ObjectNode[]>('/v1/objects', {
        params: showArchived ? {} : { status: 'active' },
      }),
  });
  const typesQuery = useQuery({
    queryKey: ['object-types'],
    queryFn: () => api<ObjectType[]>('/v1/object-types'),
  });
  const tagsQuery = useQuery({
    queryKey: ['tags'],
    queryFn: () => api<Tag[]>('/v1/tags'),
  });

  const invalidateObjects = () => {
    void queryClient.invalidateQueries({ queryKey: ['objects'] });
  };

  const saveObject = useMutation({
    mutationFn: (f: ObjectFormState) => {
      const body = {
        name: f.name.trim(),
        code: f.code.trim() || null,
        type_id: f.type_id || null,
        parent_id: f.parent_id || null,
        description: f.description.trim() || null,
        sort_order: Number(f.sort_order) || 0,
      };
      return f.id
        ? api<ObjectNode>(`/v1/objects/${f.id}`, { method: 'PATCH', body })
        : api<ObjectNode>('/v1/objects', { method: 'POST', body });
    },
    onSuccess: () => {
      invalidateObjects();
      setForm(null);
      setFormError(null);
    },
    onError: (e) => setFormError(e instanceof ApiError ? e.message : 'Ошибка сохранения'),
  });

  const archiveObject = useMutation({
    mutationFn: (objectId: string) => api(`/v1/objects/${objectId}/archive`, { method: 'POST' }),
    onSuccess: invalidateObjects,
  });

  const objects = objectsQuery.data ?? [];
  const childrenMap = useMemo(() => {
    const map = new Map<string | null, ObjectNode[]>();
    for (const o of objects) {
      const key = o.parent_id ?? null;
      const list = map.get(key) ?? [];
      map.set(key, [...list, o]);
    }
    // Узлы, чей родитель не попал в выборку (например, архивирован), показываем как корневые
    const knownIds = new Set(objects.map((o) => o.id));
    const roots = map.get(null) ?? [];
    const orphans = objects.filter((o) => o.parent_id !== null && !knownIds.has(o.parent_id));
    // COR-10: узлы, недостижимые от корней (цикл parent_id A↔B), иначе молча исчезнут — показываем как корневые
    const reachable = new Set<string>();
    const stack = [...roots, ...orphans];
    while (stack.length) {
      const n = stack.pop()!;
      if (reachable.has(n.id)) continue;
      reachable.add(n.id);
      for (const c of map.get(n.id) ?? []) stack.push(c);
    }
    const unreachable = objects.filter((o) => !reachable.has(o.id));
    map.set(null, [...roots, ...orphans, ...unreachable]);
    return map;
  }, [objects]);

  const typeName = (typeId: string | null) =>
    typesQuery.data?.find((t) => t.id === typeId)?.name ?? '—';

  const renderNode = (node: ObjectNode, depth: number, visited: Set<string>): JSX.Element | null => {
    if (visited.has(node.id)) return null; // COR-10: не зацикливаться на цикле parent_id
    visited.add(node.id);
    return (
    <div key={node.id}>
      <div className="tree-row" style={{ paddingLeft: depth * 24 }}>
        <div className="tree-main">
          <span className="tree-name">{node.name}</span>
          {node.code && <span className="mono muted small"> [{node.code}]</span>}
          <span className="muted small"> · {typeName(node.type_id)}</span>
          {node.tags.length > 0 && (
            <span className="small">
              {' '}
              {node.tags.map((t) => (
                <span key={t.id} className="chip">
                  {t.name}
                </span>
              ))}
            </span>
          )}
          {!node.is_active && <ActiveBadge active={false} />}
        </div>
        {canEdit && node.is_active && (
          <div className="tree-actions">
            <button
              className="btn btn-sm btn-ghost"
              onClick={() =>
                setForm({
                  id: null,
                  name: '',
                  code: '',
                  type_id: '',
                  parent_id: node.id,
                  description: '',
                  sort_order: '0',
                })
              }
            >
              + Дочерний
            </button>
            <button
              className="btn btn-sm btn-ghost"
              onClick={() =>
                setForm({
                  id: node.id,
                  name: node.name,
                  code: node.code ?? '',
                  type_id: node.type_id ?? '',
                  parent_id: node.parent_id ?? '',
                  description: node.description ?? '',
                  sort_order: String(node.sort_order),
                })
              }
            >
              Изменить
            </button>
            <button
              className="btn btn-sm btn-ghost text-error"
              onClick={() => {
                if (window.confirm(`Архивировать объект «${node.name}»?`)) {
                  archiveObject.mutate(node.id);
                }
              }}
            >
              Архив
            </button>
          </div>
        )}
      </div>
      {(childrenMap.get(node.id) ?? []).map((child) => renderNode(child, depth + 1, visited))}
    </div>
    );
  };

  return (
    <div>
      <div className="page-header">
        <h1>Объекты</h1>
        {canEdit && tab === 'objects' && (
          <button className="btn btn-primary" onClick={() => setForm({ ...emptyForm })}>
            + Новый объект
          </button>
        )}
      </div>

      <div className="tabs">
        <button className={`tab${tab === 'objects' ? ' active' : ''}`} onClick={() => setTab('objects')}>
          Дерево объектов
        </button>
        <button className={`tab${tab === 'types' ? ' active' : ''}`} onClick={() => setTab('types')}>
          Типы объектов
        </button>
        <button className={`tab${tab === 'tags' ? ' active' : ''}`} onClick={() => setTab('tags')}>
          Теги
        </button>
      </div>

      {tab === 'objects' && (
        <>
          <label className="checkbox-inline">
            <input
              type="checkbox"
              checked={showArchived}
              onChange={(e) => setShowArchived(e.target.checked)}
            />
            Показывать архивные
          </label>
          {objectsQuery.isLoading ? (
            <Loading />
          ) : objectsQuery.isError ? (
            <ErrorState error={objectsQuery.error} onRetry={() => objectsQuery.refetch()} />
          ) : objects.length === 0 ? (
            <Empty text="Объекты ещё не созданы" />
          ) : (
            <div className="tree panel">
              {(() => {
                const visited = new Set<string>();
                return (childrenMap.get(null) ?? []).map((node) => renderNode(node, 0, visited));
              })()}
            </div>
          )}
        </>
      )}

      {tab === 'types' && (
        <CatalogTable
          title="Типы объектов"
          query={typesQuery}
          canEdit={canEdit}
          basePath="/v1/object-types"
          queryKey={['object-types']}
        />
      )}

      {tab === 'tags' && (
        <CatalogTable
          title="Теги"
          query={tagsQuery}
          canEdit={canEdit}
          basePath="/v1/tags"
          queryKey={['tags']}
        />
      )}

      {form && (
        <Modal
          title={form.id ? 'Редактировать объект' : 'Новый объект'}
          onClose={() => {
            setForm(null);
            setFormError(null);
          }}
        >
          <label className="field">
            <span>Название *</span>
            <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          </label>
          <div className="form-row">
            <label className="field">
              <span>Код</span>
              <input value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} />
            </label>
            <label className="field">
              <span>Тип</span>
              <select
                value={form.type_id}
                onChange={(e) => setForm({ ...form, type_id: e.target.value })}
              >
                <option value="">—</option>
                {(typesQuery.data ?? [])
                  .filter((t) => t.is_active)
                  .map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.name}
                    </option>
                  ))}
              </select>
            </label>
          </div>
          <div className="form-row">
            <label className="field">
              <span>Родитель</span>
              <select
                value={form.parent_id}
                onChange={(e) => setForm({ ...form, parent_id: e.target.value })}
              >
                <option value="">— корневой —</option>
                {objects
                  .filter((o) => o.id !== form.id && o.is_active)
                  .map((o) => (
                    <option key={o.id} value={o.id}>
                      {o.name}
                    </option>
                  ))}
              </select>
            </label>
            <label className="field">
              <span>Порядок</span>
              <input
                inputMode="numeric"
                value={form.sort_order}
                onChange={(e) => setForm({ ...form, sort_order: e.target.value.replace(/\D/g, '') })}
              />
            </label>
          </div>
          <label className="field">
            <span>Описание</span>
            <textarea
              rows={2}
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
            />
          </label>
          {formError && <div className="form-error">{formError}</div>}
          <div className="modal-actions">
            <button className="btn" onClick={() => setForm(null)}>
              Отмена
            </button>
            <button
              className="btn btn-primary"
              disabled={!form.name.trim() || saveObject.isPending}
              onClick={() => saveObject.mutate(form)}
            >
              Сохранить
            </button>
          </div>
        </Modal>
      )}
    </div>
  );
}

interface CatalogQuery {
  data: { id: string; name: string; is_active: boolean }[] | undefined;
  isLoading: boolean;
  isError: boolean;
  error: unknown;
  refetch: () => void;
}

function CatalogTable({
  title,
  query,
  canEdit,
  basePath,
  queryKey,
}: {
  title: string;
  query: CatalogQuery;
  canEdit: boolean;
  basePath: string;
  queryKey: string[];
}) {
  const queryClient = useQueryClient();
  const [newName, setNewName] = useState('');
  const [error, setError] = useState<string | null>(null);

  const invalidate = () => void queryClient.invalidateQueries({ queryKey });

  const create = useMutation({
    mutationFn: (name: string) => api(basePath, { method: 'POST', body: { name } }),
    onSuccess: () => {
      setNewName('');
      setError(null);
      invalidate();
    },
    onError: (e) => setError(e instanceof ApiError ? e.message : 'Ошибка'),
  });

  const patch = useMutation({
    mutationFn: (item: { id: string; is_active: boolean }) =>
      api(`${basePath}/${item.id}`, { method: 'PATCH', body: { is_active: item.is_active } }),
    onSuccess: invalidate,
    onError: (e) => setError(e instanceof ApiError ? e.message : 'Ошибка'),
  });

  if (query.isLoading) return <Loading />;
  if (query.isError) return <ErrorState error={query.error} onRetry={query.refetch} />;
  const items = query.data ?? [];

  return (
    <div className="panel">
      <h2>{title}</h2>
      {canEdit && (
        <div className="toolbar">
          <input
            placeholder="Название…"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
          />
          <button
            className="btn btn-primary"
            disabled={!newName.trim() || create.isPending}
            onClick={() => create.mutate(newName.trim())}
          >
            Добавить
          </button>
        </div>
      )}
      {error && <div className="form-error">{error}</div>}
      {items.length === 0 ? (
        <Empty />
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>Название</th>
              <th>Статус</th>
              {canEdit && <th />}
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.id}>
                <td>{item.name}</td>
                <td>
                  <ActiveBadge active={item.is_active} />
                </td>
                {canEdit && (
                  <td className="cell-actions">
                    <button
                      className="btn btn-sm btn-ghost"
                      onClick={() => patch.mutate({ id: item.id, is_active: !item.is_active })}
                    >
                      {item.is_active ? 'В архив' : 'Вернуть'}
                    </button>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
