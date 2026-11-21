import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { normalizeApiLang, type ApiLang } from '../../utils/apiLang'
import PassportPhotos from './PassportPhotos'
import type {
  PassportField, PassportGroup, PassportItem, PassportPatch, PassportPhoto, PassportRow, PassportSchema, PassportValue, PassportValues,
} from './api'

/**
 * Форма паспорта по схеме с сервера. Одиночный пункт сохраняется сам при уходе
 * с поля; строки группы (окна, двери, трубы) — кнопкой, целиком. Тот же
 * компонент читает подписанную редакцию (`onPatch` не передан).
 */

/** Данные паспорта или редакции — то, что нужно для рисования. */
export interface PassportData {
  values: PassportValues
  unknown: Record<string, string>
  absent: string[]
  shared_from: Record<string, number>
  issues?: { key: string; code: string }[]
  missing?: string[]
  hints?: Record<string, string | number | null>
  photos?: PassportPhoto[]
}

interface Props {
  schema: PassportSchema
  data: PassportData
  /** Нет — только чтение. */
  onPatch?: (body: PassportPatch) => void
  /** Дома для выбора «учтено в паспорте дома…». */
  buildings?: { building_id: number; address: string }[]
  onlyMissing?: boolean
  /** Дом — для фото разделов; без него фото не показываются. */
  buildingId?: number
}

/** Пункт паспорта → ключ подсказки из справочника. */
const HINT_OF: Record<string, string> = {
  floors: 'floors', entrances: 'entrances', apt_total_area: 'apartments_area',
  addr_region: 'region', addr_district: 'district',
}

const SELECT_CLASS =
  'h-9 w-full rounded-sm border border-border-default bg-bg-surface px-2 text-sm text-text-primary disabled:opacity-50'

function isVisible(item: PassportItem, byKey: Map<string, PassportItem>, values: PassportValues): boolean {
  if (!item.show_if) return true
  const [parentKey, allowed] = item.show_if
  const parent = byKey.get(parentKey)
  return !!parent && isVisible(parent, byKey, values) && allowed.includes(String(values[parentKey]))
}

const isNumeric = (field: PassportField) => field.type === 'int' || field.type === 'decimal'

/** Текст поля → значение для сервера. Не-число уходит как есть: откажет сервер. */
function parse(field: PassportField, raw: string): string | number | null {
  const text = raw.trim()
  if (text === '') return null
  if (!isNumeric(field)) return text
  const num = Number(text.replace(',', '.'))
  return Number.isNaN(num) ? text : num
}

interface ScalarProps {
  field: PassportField
  value: string | number | null
  lang: ApiLang
  disabled: boolean
  onSave: (value: string | number | null) => void
}

function Scalar({ field, value, lang, disabled, onSave }: ScalarProps) {
  if (field.type === 'choice') {
    return (
      <select className={SELECT_CLASS} aria-label={field[lang]} value={value ?? ''} disabled={disabled}
              onChange={(e) => onSave(e.target.value || null)}>
        <option value="">—</option>
        {field.options?.map((o) => <option key={o.key} value={o.key}>{o[lang]}</option>)}
      </select>
    )
  }
  return (
    <Input key={String(value)} aria-label={field[lang]} defaultValue={value ?? ''} disabled={disabled}
           inputMode={isNumeric(field) ? 'decimal' : undefined}
           onBlur={(e) => {
             const next = parse(field, e.target.value)
             if (next !== value) onSave(next)
           }} />
  )
}

interface GroupProps {
  group: PassportGroup
  rows: PassportRow[]
  lang: ApiLang
  disabled: boolean
  onSave: (rows: PassportRow[]) => void
}

function GroupTable({ group, rows, lang, disabled, onSave }: GroupProps) {
  const { t } = useTranslation()
  const [draft, setDraft] = useState<PassportRow[]>(rows)
  const dirty = JSON.stringify(draft) !== JSON.stringify(rows)
  const setCell = (index: number, key: string, value: string | number | null) =>
    setDraft((prev) => prev.map((row, i) => (i === index ? { ...row, [key]: value } : row)))
  const save = () => onSave(draft.map((row) => Object.fromEntries(
    group.fields.filter((f) => !f.computed).map((f) => [f.key, typeof row[f.key] === 'string' ? parse(f, row[f.key] as string) : row[f.key] ?? null]),
  )))

  return (
    <div className="flex flex-col gap-2 overflow-x-auto">
      <table className="text-[13px]">
        <thead>
          <tr className="text-left text-text-muted">
            {group.fields.map((f) => <th key={f.key} className="pr-2 font-normal">{f[lang]}{f.unit ? `, ${f.unit}` : ''}</th>)}
            <th />
          </tr>
        </thead>
        <tbody>
          {draft.map((row, index) => (
            <tr key={index}>
              {group.fields.map((f) => (
                <td key={f.key} className="pr-2 py-0.5 min-w-24">
                  {f.type === 'choice' ? (
                    <select className={SELECT_CLASS} aria-label={f[lang]} value={row[f.key] ?? ''} disabled={disabled}
                            onChange={(e) => setCell(index, f.key, e.target.value || null)}>
                      <option value="">—</option>
                      {f.options?.map((o) => <option key={o.key} value={o.key}>{o[lang]}</option>)}
                    </select>
                  ) : (
                    <Input aria-label={f[lang]} value={row[f.key] ?? ''} disabled={disabled || f.computed}
                           inputMode={isNumeric(f) ? 'decimal' : undefined}
                           onChange={(e) => setCell(index, f.key, e.target.value)} />
                  )}
                </td>
              ))}
              <td>
                {!disabled && (
                  <Button variant="ghost" size="sm" aria-label={t('housePassport.rows.remove')}
                          onClick={() => setDraft((prev) => prev.filter((_, i) => i !== index))}>×</Button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {!disabled && (
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => setDraft((prev) => [...prev, {}])}>{t('housePassport.rows.add')}</Button>
          {dirty && <Button size="sm" onClick={save}>{t('housePassport.rows.save')}</Button>}
        </div>
      )}
    </div>
  )
}

function UnknownMark({ reason, canEdit, onSet }: { reason?: string; canEdit: boolean; onSet: (reason: string | null) => void }) {
  const { t } = useTranslation()
  const [asking, setAsking] = useState(false)
  const [text, setText] = useState('')
  if (reason) {
    return (
      <span className="text-[12px] text-text-muted">
        {t('housePassport.unknown.marked', { reason })}{' '}
        {canEdit && <button type="button" className="text-accent hover:underline" onClick={() => onSet(null)}>{t('housePassport.unknown.clear')}</button>}
      </span>
    )
  }
  if (!canEdit) return null
  if (!asking) {
    return <button type="button" className="text-[12px] text-accent hover:underline self-start" onClick={() => setAsking(true)}>{t('housePassport.unknown.mark')}</button>
  }
  return (
    <span className="flex gap-2">
      <Input aria-label={t('housePassport.unknown.reason')} placeholder={t('housePassport.unknown.reason')} value={text} maxLength={300}
             onChange={(e) => setText(e.target.value)} />
      <Button size="sm" disabled={!text.trim()} onClick={() => { onSet(text.trim()); setAsking(false) }}>{t('common.save')}</Button>
    </span>
  )
}

export default function PassportForm({ schema, data, onPatch, buildings = [], onlyMissing = false, buildingId }: Props) {
  const { t, i18n } = useTranslation()
  const lang = normalizeApiLang(i18n.language)
  const { values, unknown, shared_from: shared } = data
  const absent = new Set(data.absent)
  const missing = new Set(data.missing ?? [])
  const issues = new Map((data.issues ?? []).map((i) => [i.key, i.code]))
  const byKey = new Map(schema.sections.flatMap((s) => s.items).map((item) => [item.key, item]))
  const canEdit = !!onPatch
  const saveValue = (key: string, value: PassportValue) => onPatch?.({ values: { [key]: value } })
  const shownUnits = new Set<string>()

  const shareControl = (unit: string) => {
    if (shownUnits.has(unit)) return null
    shownUnits.add(unit)
    const label = t(`housePassport.shared.${unit}`)
    return (
      <label className="flex flex-wrap items-center gap-2 text-[12px] text-text-muted">
        {label}
        <select className={`${SELECT_CLASS} max-w-xs`} aria-label={label} value={shared[unit] ?? ''} disabled={!canEdit}
                onChange={(e) => onPatch?.({ shared_from: { [unit]: e.target.value ? Number(e.target.value) : null } })}>
          <option value="">{t('housePassport.shared.own')}</option>
          {buildings.map((b) => <option key={b.building_id} value={b.building_id}>{b.address}</option>)}
        </select>
      </label>
    )
  }

  const renderItem = (item: PassportItem) => {
    const linked = item.share !== null && shared[item.share] !== undefined
    const disabled = !canEdit || linked
    const value = values[item.key] ?? null
    const title = (
      <span className="text-[13px] text-text-primary">
        {item.kind === 'field' && item.form_no && <span className="text-text-muted">{item.form_no} </span>}
        {item[lang]}{item.kind === 'field' && item.unit ? `, ${item.unit}` : ''}
      </span>
    )
    const issue = issues.get(item.key)
    const tail = (
      <>
        {item.share && shareControl(item.share)}
        {issue && <span role="alert" className="text-[12px] text-red">{t(`housePassport.issues.${issue}`, { defaultValue: issue })}</span>}
      </>
    )
    if (item.kind === 'group') {
      const isAbsent = absent.has(item.key)
      return (
        <div key={item.key} className="flex flex-col gap-1.5">
          <div className="flex flex-wrap items-center gap-3">
            {title}
            <label className="flex items-center gap-1.5 text-[12px] text-text-muted">
              <input type="checkbox" checked={isAbsent} disabled={disabled}
                     onChange={(e) => onPatch?.({ absent: { [item.key]: e.target.checked } })} />
              {t('housePassport.absent')}
            </label>
          </div>
          {!isAbsent && (
            <GroupTable key={JSON.stringify(value)} group={item} rows={(value as PassportRow[] | null) ?? []} lang={lang}
                        disabled={disabled} onSave={(rows) => saveValue(item.key, rows)} />
          )}
          {tail}
        </div>
      )
    }
    const scalar = value as string | number | null
    const other = item.options?.find((o) => o.key === scalar)?.other
    const hint = data.hints?.[HINT_OF[item.key]]
    return (
      <div key={item.key} className="grid gap-1.5 sm:grid-cols-[minmax(0,1fr)_minmax(0,18rem)] sm:items-start">
        {title}
        <div className="flex flex-col gap-1">
          <Scalar field={item} value={scalar} lang={lang} disabled={disabled || item.computed}
                  onSave={(next) => saveValue(item.key, next)} />
          {other && (
            <Input key={String(values[`${item.key}_text`])} aria-label={t('housePassport.otherText')} placeholder={t('housePassport.otherText')}
                   defaultValue={(values[`${item.key}_text`] as string | null) ?? ''} disabled={disabled}
                   onBlur={(e) => saveValue(`${item.key}_text`, e.target.value.trim() || null)} />
          )}
          {!disabled && scalar === null && hint != null && (
            <button type="button" className="text-[12px] text-accent hover:underline self-start" onClick={() => saveValue(item.key, hint)}>
              {t('housePassport.hint', { value: hint })}
            </button>
          )}
          {!item.computed && scalar === null && (
            <UnknownMark reason={unknown[item.key]} canEdit={!disabled}
                         onSet={(reason) => onPatch?.({ unknown: { [item.key]: reason } })} />
          )}
          {linked && <span className="text-[12px] text-text-muted">{t('housePassport.shared.linked')}</span>}
          {tail}
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-3">
      {schema.sections.map((section) => {
        const visible = section.items.filter((item) => isVisible(item, byKey, values))
        const left = visible.filter((item) => missing.has(item.key)).length
        const shown = onlyMissing ? visible.filter((item) => missing.has(item.key) || issues.has(item.key)) : visible
        if (shown.length === 0) return null
        return (
          <details key={section.key} className="rounded-md border border-border-default bg-bg-card" open={onlyMissing || undefined}>
            <summary className="cursor-pointer px-4 py-3 text-sm font-medium text-text-primary flex flex-wrap items-center gap-2">
              <span>{section.no !== null ? `${section.no}. ` : ''}{section[lang]}</span>
              {left > 0 && <span className="rounded-full bg-bg-surface px-2 py-0.5 text-[11px] text-text-muted">{t('housePassport.left', { count: left })}</span>}
            </summary>
            <div className="flex flex-col gap-4 border-t border-border-default px-4 py-4">
              {shown.map(renderItem)}
              {buildingId !== undefined && (
                <PassportPhotos buildingId={buildingId} section={section.key} canEdit={canEdit}
                                photos={(data.photos ?? []).filter((photo) => photo.section === section.key)} />
              )}
            </div>
          </details>
        )
      })}
    </div>
  )
}
