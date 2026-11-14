import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select } from '@/components/ui/select'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import LocalizedField from '../board/LocalizedField'
import { NOTICE_RESOURCES, type NoticeBody, type NoticeResource } from '../../hooks/useNotices'
import { bodyOf, draftError, isScheduled, type NoticeDraft } from './noticeModel'

interface Props {
  /** Начальные значения; смена записи — через `key` у родителя. */
  initial: NoticeDraft
  /** Правка существующей записи (иначе создание). */
  editing: boolean
  /** Уже опубликованная запись: «Сохранить» без повторной публикации. */
  published: boolean
  pending: boolean
  onSubmit: (body: NoticeBody, publish: boolean) => void
  onClose: () => void
}

/** Форма новости или планового отключения: текст RU/UZ, окно, срок публикации и показа. */
export default function NoticeForm({ initial, editing, published, pending, onSubmit, onClose }: Props) {
  const { t } = useTranslation()
  const [draft, setDraft] = useState<NoticeDraft>(initial)
  const [error, setError] = useState<string | null>(null)
  const outage = draft.kind === 'outage'
  const patch = (p: Partial<NoticeDraft>) => setDraft((d) => ({ ...d, ...p }))

  const submit = (publish: boolean) => {
    const problem = draftError(draft)
    if (problem) {
      setError(t(`notices.form.error.${problem}`))
      return
    }
    setError(null)
    onSubmit(bodyOf(draft), publish)
  }

  const dateInput = (id: string, label: string, value: string, onChange: (v: string) => void) => (
    <div className="space-y-1.5">
      <Label htmlFor={id}>{label}</Label>
      <Input id={id} type="datetime-local" value={value} onChange={(e) => onChange(e.target.value)} />
    </div>
  )

  return (
    <Dialog open onOpenChange={(open) => { if (!open) onClose() }}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>{t(`notices.form.title.${draft.kind}`)}</DialogTitle>
        </DialogHeader>

        {outage && (
          <div className="space-y-1.5">
            <Label htmlFor="notice-resource">{t('notices.form.resource')}</Label>
            <Select id="notice-resource" value={draft.resource} onChange={(e) => patch({ resource: e.target.value as NoticeResource })}>
              {NOTICE_RESOURCES.map((r) => <option key={r} value={r}>{t(`notices.resource.${r}`)}</option>)}
            </Select>
          </div>
        )}

        <LocalizedField label={t('notices.form.heading')} value={draft.title} onChange={(title) => patch({ title })} />
        <LocalizedField label={t('notices.form.text')} value={draft.text} textarea onChange={(text) => patch({ text })} />

        {outage && (
          <>
            <LocalizedField label={t('notices.form.place')} value={draft.place} onChange={(place) => patch({ place })} />
            <div className="grid gap-3 sm:grid-cols-2">
              {dateInput('notice-starts', t('notices.form.startsAt'), draft.startsAt, (startsAt) => patch({ startsAt }))}
              {dateInput('notice-ends', t('notices.form.endsAt'), draft.endsAt, (endsAt) => patch({ endsAt }))}
            </div>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={draft.allDay} onChange={() => patch({ allDay: !draft.allDay })} />
              {t('notices.form.allDay')}
            </label>
          </>
        )}

        <div className="grid gap-3 sm:grid-cols-2">
          {dateInput('notice-publish', t('notices.form.publishAt'), draft.publishAt, (publishAt) => patch({ publishAt }))}
          {dateInput('notice-expires', t('notices.form.expiresAt'), draft.expiresAt, (expiresAt) => patch({ expiresAt }))}
        </div>
        <p className="text-xs text-text-muted">{t(`notices.form.hint.${draft.kind}`)}</p>

        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={draft.important} onChange={() => patch({ important: !draft.important })} />
          {t('notices.form.important')}
        </label>

        {error && <p role="alert" className="text-sm text-red">{error}</p>}

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>{t('common.cancel')}</Button>
          {!published && (
            <Button variant="outline" disabled={pending} onClick={() => submit(false)}>{t('notices.form.saveDraft')}</Button>
          )}
          <Button disabled={pending} onClick={() => submit(!published)}>
            {published ? t('common.save') : t(isScheduled(draft) ? 'notices.form.schedule' : 'notices.form.publish')}
          </Button>
        </DialogFooter>
        {editing && published && <p className="text-xs text-text-muted">{t('notices.form.liveNote')}</p>}
      </DialogContent>
    </Dialog>
  )
}
