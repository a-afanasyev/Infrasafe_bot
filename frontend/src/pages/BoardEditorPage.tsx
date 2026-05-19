import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from '@dnd-kit/core'
import {
  SortableContext,
  sortableKeyboardCoordinates,
  verticalListSortingStrategy,
  useSortable,
  arrayMove,
} from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { GripVertical, Plus, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { usePageTitle } from '../hooks/usePageTitle'
import { useBoardConfig, useUpdateBoardConfig } from '../hooks/useBoardConfig'
import { defaultBoardConfig } from '../types/boardConfig'
import type {
  AnnouncementCfg,
  BoardConfigData,
  LayoutItem,
  LocalizedText,
} from '../types/boardConfig'
import ResidentBoardPage from './ResidentBoardPage'

// ── helpers ───────────────────────────────────────────────────────────────────

const DAY_ORDER = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']

function clone(c: BoardConfigData): BoardConfigData {
  return JSON.parse(JSON.stringify(c))
}

// ── small editor primitives ─────────────────────────────────────────────────────

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-md border border-border-default bg-bg-card p-4">
      <h3 className="mb-3 text-sm font-bold text-text-primary">{title}</h3>
      <div className="flex flex-col gap-3">{children}</div>
    </section>
  )
}

function LocalizedField({
  label,
  value,
  onChange,
  textarea,
}: {
  label: string
  value: LocalizedText
  onChange: (v: LocalizedText) => void
  textarea?: boolean
}) {
  const Field = textarea ? Textarea : Input
  return (
    <div>
      <div className="mb-1 text-xs font-semibold text-text-muted">{label}</div>
      <div className="grid grid-cols-2 gap-2">
        <Field
          value={value.ru}
          placeholder="RU"
          onChange={(e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
            onChange({ ...value, ru: e.target.value })
          }
        />
        <Field
          value={value.uz}
          placeholder="UZ"
          onChange={(e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
            onChange({ ...value, uz: e.target.value })
          }
        />
      </div>
    </div>
  )
}

function SortableModuleRow({
  item,
  label,
  onToggle,
}: {
  item: LayoutItem
  label: string
  onToggle: () => void
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({ id: item.id })
  return (
    <div
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition, opacity: isDragging ? 0.5 : 1 }}
      className="flex items-center gap-2 rounded-sm border border-border-default bg-bg-surface px-3 py-2"
    >
      <button
        type="button"
        className="cursor-grab text-text-muted active:cursor-grabbing"
        {...attributes}
        {...listeners}
        aria-label="drag"
      >
        <GripVertical size={16} />
      </button>
      <span className="flex-1 text-sm font-medium text-text-primary">{label}</span>
      <label className="flex items-center gap-1.5 text-xs text-text-muted">
        <input type="checkbox" checked={item.visible} onChange={onToggle} />
      </label>
    </div>
  )
}

// ── page ────────────────────────────────────────────────────────────────────────

export default function BoardEditorPage() {
  const { t } = useTranslation()
  usePageTitle(t('nav.boardEditor'))
  const { data: serverConfig } = useBoardConfig()
  const updateConfig = useUpdateBoardConfig()

  const [draft, setDraft] = useState<BoardConfigData | null>(null)

  useEffect(() => {
    if (serverConfig && draft === null) setDraft(clone(serverConfig))
  }, [serverConfig, draft])

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 8 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  )

  if (!draft) {
    return <div className="p-8 text-sm text-text-muted">{t('common.loading')}</div>
  }

  // immutable patch helper
  const patch = (fn: (d: BoardConfigData) => void) => {
    setDraft((prev) => {
      const next = clone(prev ?? draft)
      fn(next)
      return next
    })
  }

  const handleModuleDragEnd = (e: DragEndEvent) => {
    const { active, over } = e
    if (!over || active.id === over.id) return
    patch((d) => {
      const from = d.layout.findIndex((l) => l.id === active.id)
      const to = d.layout.findIndex((l) => l.id === over.id)
      if (from >= 0 && to >= 0) d.layout = arrayMove(d.layout, from, to)
    })
  }

  const addAnnouncement = () => {
    const fresh: AnnouncementCfg = {
      id: `ann-${Date.now()}`,
      icon: '📢',
      important: false,
      title: { ru: '', uz: '' },
      text: { ru: '', uz: '' },
      published_at: new Date().toISOString().slice(0, 16),
    }
    patch((d) => {
      d.announcements = [...d.announcements, fresh]
    })
  }

  const onSave = () => updateConfig.mutate(draft)
  const onReset = () => setDraft(serverConfig ? clone(serverConfig) : clone(defaultBoardConfig))

  return (
    <div className="flex h-full flex-col gap-4 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-bold text-text-primary">{t('nav.boardEditor')}</h1>
        <div className="flex gap-2">
          <Button variant="outline" onClick={onReset} disabled={updateConfig.isPending}>
            {t('boardEditor.reset')}
          </Button>
          <Button onClick={onSave} disabled={updateConfig.isPending}>
            {t('boardEditor.save')}
          </Button>
        </div>
      </div>

      <div className="grid flex-1 grid-cols-1 gap-4 lg:grid-cols-[minmax(0,420px)_1fr]">
        {/* ── Left: controls ───────────────────────────────────────────── */}
        <div className="flex max-h-[calc(100vh-180px)] flex-col gap-4 overflow-y-auto pr-1">
          {/* Module order */}
          <Section title={t('boardEditor.modulesOrder')}>
            <p className="text-xs text-text-muted">{t('boardEditor.modulesHint')}</p>
            <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleModuleDragEnd}>
              <SortableContext items={draft.layout.map((l) => l.id)} strategy={verticalListSortingStrategy}>
                <div className="flex flex-col gap-2">
                  {draft.layout.map((item) => (
                    <SortableModuleRow
                      key={item.id}
                      item={item}
                      label={t(`boardEditor.modules.${item.id}`)}
                      onToggle={() =>
                        patch((d) => {
                          const l = d.layout.find((x) => x.id === item.id)
                          if (l) l.visible = !l.visible
                        })
                      }
                    />
                  ))}
                </div>
              </SortableContext>
            </DndContext>
          </Section>

          {/* Organisation */}
          <Section title={t('boardEditor.org')}>
            <LocalizedField
              label={t('boardEditor.orgName')}
              value={draft.org.name}
              onChange={(v) => patch((d) => { d.org.name = v })}
            />
            <LocalizedField
              label={t('boardEditor.orgSubtitle')}
              value={draft.org.subtitle}
              onChange={(v) => patch((d) => { d.org.subtitle = v })}
            />
          </Section>

          {/* Contacts */}
          <Section title={t('boardEditor.contacts')}>
            <div>
              <div className="mb-1 text-xs font-semibold text-text-muted">{t('boardEditor.dispatchPhone')}</div>
              <Input
                value={draft.contacts.dispatch_phone}
                onChange={(e) => patch((d) => { d.contacts.dispatch_phone = e.target.value })}
              />
            </div>
            <LocalizedField
              label={t('boardEditor.dispatchLabel')}
              value={draft.contacts.dispatch_label}
              onChange={(v) => patch((d) => { d.contacts.dispatch_label = v })}
            />
            <LocalizedField
              label={t('boardEditor.emergency')}
              value={draft.contacts.emergency}
              onChange={(v) => patch((d) => { d.contacts.emergency = v })}
            />
          </Section>

          {/* Bot */}
          <Section title={t('boardEditor.bot')}>
            <div>
              <div className="mb-1 text-xs font-semibold text-text-muted">{t('boardEditor.botUsername')}</div>
              <Input
                value={draft.bot.username}
                onChange={(e) => patch((d) => { d.bot.username = e.target.value.replace(/^@/, '') })}
              />
            </div>
            <LocalizedField
              label={t('boardEditor.botLabel')}
              value={draft.bot.label}
              onChange={(v) => patch((d) => { d.bot.label = v })}
            />
          </Section>

          {/* Announcements */}
          <Section title={t('boardEditor.announcements')}>
            {draft.announcements.map((ann, idx) => (
              <div key={ann.id} className="rounded-sm border border-border-default bg-bg-surface p-3">
                <div className="mb-2 flex items-center gap-2">
                  <Input
                    className="w-16"
                    value={ann.icon}
                    placeholder="📢"
                    onChange={(e) => patch((d) => { d.announcements[idx].icon = e.target.value })}
                  />
                  <label className="flex items-center gap-1.5 text-xs text-text-muted">
                    <input
                      type="checkbox"
                      checked={ann.important}
                      onChange={() => patch((d) => { d.announcements[idx].important = !d.announcements[idx].important })}
                    />
                    {t('boardEditor.important')}
                  </label>
                  <input
                    type="datetime-local"
                    className="ml-auto rounded-sm border border-border-default bg-bg-surface px-2 py-1 text-xs text-text-primary"
                    value={ann.published_at.slice(0, 16)}
                    onChange={(e) => patch((d) => { d.announcements[idx].published_at = e.target.value })}
                  />
                  <button
                    type="button"
                    aria-label="remove"
                    className="text-text-muted hover:text-red-500"
                    onClick={() => patch((d) => { d.announcements.splice(idx, 1) })}
                  >
                    <Trash2 size={16} />
                  </button>
                </div>
                <div className="flex flex-col gap-2">
                  <LocalizedField
                    label={t('boardEditor.annTitle')}
                    value={ann.title}
                    onChange={(v) => patch((d) => { d.announcements[idx].title = v })}
                  />
                  <LocalizedField
                    label={t('boardEditor.annText')}
                    value={ann.text}
                    textarea
                    onChange={(v) => patch((d) => { d.announcements[idx].text = v })}
                  />
                </div>
              </div>
            ))}
            <Button variant="outline" size="sm" onClick={addAnnouncement}>
              <Plus size={14} className="mr-1" />
              {t('boardEditor.addAnnouncement')}
            </Button>
          </Section>

          {/* Working hours */}
          <Section title={t('boardEditor.workingHours')}>
            {[...draft.working_hours]
              .sort((a, b) => DAY_ORDER.indexOf(a.day) - DAY_ORDER.indexOf(b.day))
              .map((wh) => {
                const idx = draft.working_hours.findIndex((x) => x.day === wh.day)
                return (
                  <div key={wh.day} className="flex items-center gap-2">
                    <span className="w-9 text-xs font-bold text-text-primary">{t(`days.short.${wh.day}`)}</span>
                    <Input
                      type="time"
                      className="w-28"
                      value={wh.open}
                      disabled={wh.closed}
                      onChange={(e) => patch((d) => { d.working_hours[idx].open = e.target.value })}
                    />
                    <span className="text-text-muted">–</span>
                    <Input
                      type="time"
                      className="w-28"
                      value={wh.close}
                      disabled={wh.closed}
                      onChange={(e) => patch((d) => { d.working_hours[idx].close = e.target.value })}
                    />
                    <label className="ml-auto flex items-center gap-1.5 text-xs text-text-muted">
                      <input
                        type="checkbox"
                        checked={wh.closed}
                        onChange={() => patch((d) => { d.working_hours[idx].closed = !d.working_hours[idx].closed })}
                      />
                      {t('boardEditor.closed')}
                    </label>
                  </div>
                )
              })}
          </Section>
        </div>

        {/* ── Right: live preview ───────────────────────────────────────── */}
        <div className="overflow-auto rounded-md border border-border-default">
          <ResidentBoardPage configOverride={draft} />
        </div>
      </div>
    </div>
  )
}
