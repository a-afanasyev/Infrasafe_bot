import { useMemo, useState, type JSX } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
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
  const { t } = useTranslation();
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
    onError: (e) => setFormError(e instanceof ApiError ? e.message : t('resourceAccounting.common.saveError')),
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
    typesQuery.data?.find((ty) => ty.id === typeId)?.name ?? '—';

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
              {node.tags.map((tag) => (
                <span key={tag.id} className="chip">
                  {tag.name}
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
              {t('resourceAccounting.objects.addChild')}
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
              {t('resourceAccounting.objects.edit')}
            </button>
            <button
              className="btn btn-sm btn-ghost text-error"
              onClick={() => {
                if (window.confirm(t('resourceAccounting.objects.archiveConfirm', { name: node.name }))) {
                  archiveObject.mutate(node.id);
                }
              }}
            >
              {t('resourceAccounting.objects.archive')}
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
        <h1>{t('resourceAccounting.objects.title')}</h1>
        {canEdit && tab === 'objects' && (
          <button className="btn btn-primary" onClick={() => setForm({ ...emptyForm })}>
            {t('resourceAccounting.objects.newObjectButton')}
          </button>
        )}
      </div>

      <div className="tabs">
        <button className={`tab${tab === 'objects' ? ' active' : ''}`} onClick={() => setTab('objects')}>
          {t('resourceAccounting.objects.tabTree')}
        </button>
        <button className={`tab${tab === 'types' ? ' active' : ''}`} onClick={() => setTab('types')}>
          {t('resourceAccounting.objects.tabTypes')}
        </button>
        <button className={`tab${tab === 'tags' ? ' active' : ''}`} onClick={() => setTab('tags')}>
          {t('resourceAccounting.objects.tabTags')}
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
            {t('resourceAccounting.objects.showArchived')}
          </label>
          {objectsQuery.isLoading ? (
            <Loading />
          ) : objectsQuery.isError ? (
            <ErrorState error={objectsQuery.error} onRetry={() => objectsQuery.refetch()} />
          ) : objects.length === 0 ? (
            <Empty text={t('resourceAccounting.objects.empty')} />
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
          title={t('resourceAccounting.objects.tabTypes')}
          query={typesQuery}
          canEdit={canEdit}
          basePath="/v1/object-types"
          queryKey={['object-types']}
        />
      )}

      {tab === 'tags' && (
        <CatalogTable
          title={t('resourceAccounting.objects.tabTags')}
          query={tagsQuery}
          canEdit={canEdit}
          basePath="/v1/tags"
          queryKey={['tags']}
        />
      )}

      {form && (
        <Modal
          title={form.id ? t('resourceAccounting.objects.editTitle') : t('resourceAccounting.objects.newTitle')}
          onClose={() => {
            setForm(null);
            setFormError(null);
          }}
        >
          <label className="field">
            <span>{t('resourceAccounting.objects.nameRequired')}</span>
            <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          </label>
          <div className="form-row">
            <label className="field">
              <span>{t('resourceAccounting.objects.code')}</span>
              <input value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} />
            </label>
            <label className="field">
              <span>{t('resourceAccounting.objects.type')}</span>
              <select
                value={form.type_id}
                onChange={(e) => setForm({ ...form, type_id: e.target.value })}
              >
                <option value="">—</option>
                {(typesQuery.data ?? [])
                  .filter((ty) => ty.is_active)
                  .map((ty) => (
                    <option key={ty.id} value={ty.id}>
                      {ty.name}
                    </option>
                  ))}
              </select>
            </label>
          </div>
          <div className="form-row">
            <label className="field">
              <span>{t('resourceAccounting.objects.parent')}</span>
              <select
                value={form.parent_id}
                onChange={(e) => setForm({ ...form, parent_id: e.target.value })}
              >
                <option value="">{t('resourceAccounting.objects.root')}</option>
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
              <span>{t('resourceAccounting.objects.sortOrder')}</span>
              <input
                inputMode="numeric"
                value={form.sort_order}
                onChange={(e) => setForm({ ...form, sort_order: e.target.value.replace(/\D/g, '') })}
              />
            </label>
          </div>
          <label className="field">
            <span>{t('resourceAccounting.objects.description')}</span>
            <textarea
              rows={2}
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
            />
          </label>
          {formError && <div className="form-error">{formError}</div>}
          <div className="modal-actions">
            <button className="btn" onClick={() => setForm(null)}>
              {t('resourceAccounting.common.cancel')}
            </button>
            <button
              className="btn btn-primary"
              disabled={!form.name.trim() || saveObject.isPending}
              onClick={() => saveObject.mutate(form)}
            >
              {t('resourceAccounting.common.save')}
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
  const { t } = useTranslation();
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
    onError: (e) => setError(e instanceof ApiError ? e.message : t('resourceAccounting.common.error')),
  });

  const patch = useMutation({
    mutationFn: (item: { id: string; is_active: boolean }) =>
      api(`${basePath}/${item.id}`, { method: 'PATCH', body: { is_active: item.is_active } }),
    onSuccess: invalidate,
    onError: (e) => setError(e instanceof ApiError ? e.message : t('resourceAccounting.common.error')),
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
            placeholder={t('resourceAccounting.objects.namePlaceholder')}
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
          />
          <button
            className="btn btn-primary"
            disabled={!newName.trim() || create.isPending}
            onClick={() => create.mutate(newName.trim())}
          >
            {t('resourceAccounting.objects.add')}
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
              <th>{t('resourceAccounting.objects.colName')}</th>
              <th>{t('resourceAccounting.objects.colStatus')}</th>
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
                      {item.is_active ? t('resourceAccounting.objects.toArchive') : t('resourceAccounting.objects.restore')}
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
