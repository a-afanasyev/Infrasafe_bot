import { useState } from 'react'
import { Link, useParams } from 'react-router'
import { useTranslation } from 'react-i18next'
import { ArrowLeft } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { usePageTitle } from '../../hooks/usePageTitle'
import { useCan } from '../../hooks/useCan'
import AccessTabBar from '../../components/access/AccessTabBar'
import LoadingSpinner from '../../components/shared/LoadingSpinner'
import EmptyState from '../../components/shared/EmptyState'
import { fmtInstant } from '../../utils/elevatorsFormat'
import { downloadCsv } from '../../utils/download'
import { useApiLang } from '../../utils/apiLang'
import PassportForm from '../../features/passport/PassportForm'
import {
  usePassport, usePassportHistory, usePassportRevision, usePassportRevisions, usePassports, usePassportSchema,
  usePassportWrite, PASSPORTS_BASE, type PassportMeta, type PassportStatus,
} from '../../features/passport/api'

/**
 * Паспорт одного дома: шапка со статусом, сведения об осмотре, форма по
 * разделам, журнал и подписанные редакции. Правит — `passport.edit`,
 * подписывает и возвращает в работу — `passport.sign`.
 */
type Tab = 'form' | 'history' | 'revisions'
const OPEN_STATUSES: Exclude<PassportStatus, 'signed'>[] = ['not_started', 'collecting', 'inspected', 'filled']
const META: { key: keyof PassportMeta; type: string }[] = [
  { key: 'inspection_date', type: 'date' }, { key: 'responsible_name', type: 'text' }, { key: 'note', type: 'text' },
]

export default function PassportHousePage() {
  const { t } = useTranslation()
  const id = Number(useParams<{ id: string }>().id)
  const canEdit = useCan('passport.edit')
  const canSign = useCan('passport.sign')
  const [tab, setTab] = useState<Tab>('form')
  const [onlyMissing, setOnlyMissing] = useState(false)
  const [reason, setReason] = useState('')
  const [revisionNo, setRevisionNo] = useState<number | null>(null)

  const schema = usePassportSchema()
  const passport = usePassport(id)
  const buildings = usePassports()
  const history = usePassportHistory(id, tab === 'history')
  const revisions = usePassportRevisions(id, tab === 'revisions')
  const revision = usePassportRevision(id, revisionNo)
  const write = usePassportWrite(id)
  const lang = useApiLang()
  const saveMeta = (key: keyof PassportMeta, raw: string) => {
    const next = raw.trim() || null
    if (next !== (passport.data?.meta[key] ?? null)) write.mutate({ op: 'patch', body: { meta: { [key]: next } } })
  }
  // Файл формы; у редакции — по её собственной копии схемы и эталона.
  const download = (path: string, name: string) => downloadCsv(`${PASSPORTS_BASE}/buildings/${id}${path}/export.xlsx`, { lang }, `${name}.xlsx`)
  usePageTitle(passport.data ? `${t('housePassport.title')} · ${passport.data.address}` : t('housePassport.title'))

  if (passport.isLoading || schema.isLoading) return <LoadingSpinner />
  if (!passport.data || !schema.data) {
    return <div className="p-6"><EmptyState icon="🏢" title={t('housePassport.errors.not_found')} /></div>
  }
  const p = passport.data
  // Журнал хранит ключи пунктов («unknown.built_year») — показываем названия.
  const titles = new Map(schema.data.sections.flatMap((s) => s.items).map((item) => [item.key, item[lang]]))
  const changed = (key: string) => titles.get(key.split('.').pop() ?? key) ?? t(`housePassport.meta.${key.split('.').pop()}`, { defaultValue: key })
  const editable = canEdit && p.editable
  const signed = p.status === 'signed'

  return (
    <div className="p-4 sm:p-6 flex flex-col gap-5">
      <div className="flex flex-wrap items-start gap-3">
        <Button asChild variant="outline" size="sm">
          <Link to="/dashboard/passports" aria-label={t('common.back')}><ArrowLeft size={15} /></Link>
        </Button>
        <div className="flex flex-col gap-1">
          <h1 className="text-xl font-semibold text-text-primary">{p.address}</h1>
          <p className="text-[13px] text-text-muted">
            {t(`housePassport.status.${p.status}`)} · {p.progress.done} / {p.progress.total}
            {p.revision_no > 0 && ` · ${t('housePassport.revisionNo', { no: p.revision_no })}`}
            {p.updated_at && ` · ${fmtInstant(p.updated_at)}${p.updated_by_name ? `, ${p.updated_by_name}` : ''}`}
          </p>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {editable && (
          <select className="h-9 rounded-sm border border-border-default bg-bg-surface px-2 text-sm text-text-primary"
                  aria-label={t('housePassport.statusLabel')} value={p.status} disabled={write.isPending}
                  onChange={(e) => write.mutate({ op: 'status', status: e.target.value as Exclude<PassportStatus, 'signed'> })}>
            {OPEN_STATUSES.map((s) => <option key={s} value={s}>{t(`housePassport.status.${s}`)}</option>)}
          </select>
        )}
        {canSign && p.editable && p.status === 'filled' && (
          <Button size="sm" disabled={write.isPending} onClick={() => write.mutate({ op: 'sign' })}>{t('housePassport.sign')}</Button>
        )}
        <Button size="sm" variant="outline" onClick={() => download('', `passport-${id}-draft`)}>{t('housePassport.download')}</Button>
        {canSign && signed && (
          <>
            <Input className="max-w-xs" aria-label={t('housePassport.reopenReason')} placeholder={t('housePassport.reopenReason')}
                   value={reason} maxLength={300} onChange={(e) => setReason(e.target.value)} />
            <Button size="sm" variant="outline" disabled={!reason.trim() || write.isPending}
                    onClick={() => write.mutate({ op: 'reopen', reason: reason.trim() }, { onSuccess: () => setReason('') })}>
              {t('housePassport.reopen')}
            </Button>
          </>
        )}
      </div>

      <AccessTabBar active={tab} onChange={(key) => setTab(key as Tab)}
                    tabs={(['form', 'history', 'revisions'] as const).map((key) => ({ key, label: t(`housePassport.tabs.${key}`) }))} />

      {tab === 'form' && (
        <>
          <div className="grid gap-3 sm:grid-cols-3">
            {META.map(({ key, type }) => (
              <label key={key} className="flex flex-col gap-1 text-[12px] text-text-muted">
                {t(`housePassport.meta.${key}`)}
                <Input key={String(p.meta[key])} type={type} defaultValue={p.meta[key] ?? ''} disabled={!editable}
                       onBlur={(e) => saveMeta(key, e.target.value)} />
              </label>
            ))}
          </div>
          <label className="flex items-center gap-2 text-[13px] text-text-primary">
            <input type="checkbox" checked={onlyMissing} onChange={(e) => setOnlyMissing(e.target.checked)} />
            {t('housePassport.onlyMissing', { count: p.missing.length })}
          </label>
          <PassportForm schema={schema.data} data={p} onlyMissing={onlyMissing} buildingId={id}
                        buildings={(buildings.data ?? []).filter((b) => b.building_id !== id)}
                        onPatch={editable ? (body) => write.mutate({ op: 'patch', body }) : undefined} />
        </>
      )}

      {tab === 'history' && (history.isLoading ? <LoadingSpinner /> : (
        <ul className="flex flex-col gap-2">
          {(history.data ?? []).map((e) => (
            <li key={e.id} className="rounded-md border border-border-default bg-bg-card px-4 py-2 text-[13px] text-text-primary">
              <span className="text-text-muted">{fmtInstant(e.created_at)} · {e.actor_name ?? '—'} · </span>
              {t(`housePassport.events.${e.kind}`, { defaultValue: e.kind })}
              {Object.keys(e.changes).length > 0 && `: ${[...new Set(Object.keys(e.changes).map(changed))].join(', ')}`}
              {e.reason && <span className="text-text-muted"> — {e.reason}</span>}
            </li>
          ))}
          {history.data?.length === 0 && <EmptyState icon="📝" title={t('housePassport.historyEmpty')} />}
        </ul>
      ))}

      {tab === 'revisions' && (revisions.isLoading ? <LoadingSpinner /> : (
        <div className="flex flex-col gap-3">
          {revisions.data?.length === 0 && <EmptyState icon="📄" title={t('housePassport.revisionsEmpty')} />}
          <div className="flex flex-wrap gap-2">
            {(revisions.data ?? []).map((r) => (
              <Button key={r.revision_no} size="sm" variant={revisionNo === r.revision_no ? 'default' : 'outline'}
                      onClick={() => setRevisionNo(r.revision_no)}>
                {t('housePassport.revisionNo', { no: r.revision_no })} · {fmtInstant(r.signed_at)}{r.signed_by_name ? ` · ${r.signed_by_name}` : ''}
              </Button>
            ))}
          </div>
          {revision.data && (
            <Button size="sm" variant="outline" className="self-start"
                    onClick={() => download(`/revisions/${revision.data.revision_no}`, `passport-${id}-rev${revision.data.revision_no}`)}>
              {t('housePassport.download')}
            </Button>
          )}
          {revision.data && <PassportForm schema={revision.data.schema} data={revision.data} buildingId={id} />}
        </div>
      ))}
    </div>
  )
}
