import { useCallback, useEffect, useState } from 'react'
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
import { Columns2, GripVertical, Plus, RectangleHorizontal, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { usePageTitle } from '../hooks/usePageTitle'
import { useBoardConfig, useUpdateBoardConfig } from '../hooks/useBoardConfig'
import { defaultBoardConfig, defaultHomeConfig, toEditableBoardConfig } from '../types/boardConfig'
import { isoToDatetimeLocal } from '../utils/timezone'
import type {
  AnnouncementCfg,
  BoardConfigData,
  LayoutItem,
} from '../types/boardConfig'
import HomePageEditor from '../components/board/HomePageEditor'
import LocalizedField from '../components/board/LocalizedField'
import PlannedWorksEditor from '../components/board/PlannedWorksEditor'
import ScaledPreview from '../components/board/ScaledPreview'
import ResidentBoardPage from './ResidentBoardPage'
import ResidentHomePage from './ResidentHomePage'

type HomeView = 'desktop' | 'phone'

// Превью рендерит страницу в ширину реального экрана и уменьшает до колонки
// (миниатюра): табло — ТВ в холле, страница жителей — компьютер; «телефон» —
// в натуральную ширину смартфона.
const DESKTOP_PREVIEW_WIDTH = 1280
const PHONE_PREVIEW_WIDTH = 390

// ── helpers ───────────────────────────────────────────────────────────────────

const DAY_ORDER = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']

function clone(c: BoardConfigData): BoardConfigData {
  return JSON.parse(JSON.stringify(c))
}

// ── small editor primitives ─────────────────────────────────────────────────────

type Surface = 'board' | 'home'

// Раздел редактора + пометка, на какой публичной странице видны его данные:
// один конфиг кормит и табло для экрана, и страницу жителей.
interface SectionProps {
  title: string
  // Страницы, на которых видны данные раздела.
  usedOn: Surface[]
  // Активная вкладка редактора: раздел чужой страницы не показывается.
  active: Surface
  children: React.ReactNode
}

function Section({ title, usedOn, active, children }: SectionProps) {
  const { t } = useTranslation()
  if (!usedOn.includes(active)) return null
  return (
    <section className="rounded-md border border-border-default bg-bg-card p-4">
      <h3 className="mb-1 text-sm font-bold text-text-primary">{title}</h3>
      <div className="mb-3 flex flex-wrap items-center gap-1 text-[11px] text-text-muted">
        {t('boardEditor.usedOn')}
        {usedOn.map((surface) => (
          <span key={surface} className="rounded-sm border border-border-default px-1.5 py-0.5 font-semibold">
            {surface === 'board' ? t('boardEditor.usedOnBoard') : t('boardEditor.usedOnHome')}
          </span>
        ))}
      </div>
      <div className="flex flex-col gap-3">{children}</div>
    </section>
  )
}

function SortableModuleRow({
  item,
  label,
  onToggle,
  onWidthToggle,
}: {
  item: LayoutItem
  label: string
  onToggle: () => void
  onWidthToggle: () => void
}) {
  const { t } = useTranslation()
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({ id: item.id })
  const isHalf = item.width === 'half'
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
      <button
        type="button"
        onClick={onWidthToggle}
        title={isHalf ? t('boardEditor.widthHalf') : t('boardEditor.widthFull')}
        aria-label={isHalf ? t('boardEditor.widthHalf') : t('boardEditor.widthFull')}
        className={isHalf ? 'text-accent' : 'text-text-muted hover:text-text-primary'}
      >
        {isHalf ? <Columns2 size={16} /> : <RectangleHorizontal size={16} />}
      </button>
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
  // Вкладка редактора: страница жителей (главная для гостей) или табло для
  // экрана. Определяет и набор полей слева, и превью справа.
  const [tab, setTab] = useState<Surface>('home')
  const [homeView, setHomeView] = useState<HomeView>('desktop')
  // FE-034: seed the editable draft from server config when it arrives, using the
  // render-time "adjust state when input changes" pattern (no effect → no cascading
  // re-render / set-state-in-effect smell; see react.dev "You Might Not Need an Effect").
  // WR-09: track the *reference* of the server config we last seeded from instead of
  // a one-shot boolean. React Query's structural sharing keeps the same reference
  // while data is unchanged and hands back a NEW reference once the data actually
  // changes — so after a successful save (mutation invalidates ['board-config'] →
  // refetch) the fresh config re-seeds `draft`, clearing the phantom `isDirty`
  // (and its lingering beforeunload guard). User edits live only in `draft`, so a
  // background refetch that returns identical data won't stomp on them.
  const [seededFrom, setSeededFrom] = useState<BoardConfigData | null>(null)
  if (serverConfig && serverConfig !== seededFrom) {
    setSeededFrom(serverConfig)
    setDraft(toEditableBoardConfig(serverConfig))
  }

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 8 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  )

  // immutable patch helper (FE-039: stable identity via useCallback; declared
  // before the early return to satisfy rules-of-hooks). `prev` is the live draft
  // state, so no closure dep on `draft` is needed → deps stay empty.
  const patch = useCallback((fn: (d: BoardConfigData) => void) => {
    setDraft((prev) => {
      if (!prev) return prev
      const next = clone(prev)
      fn(next)
      return next
    })
  }, [])

  // FE-043: guard against accidental data loss while the draft has unsaved edits.
  // beforeunload covers reload / tab-close / browser-close (the common vectors).
  // In-app route blocking needs a data router (createBrowserRouter); this app uses
  // <BrowserRouter>, so router-level blocking is out of scope here.
  // BUG-191: сравнивать с ОЧИЩЕННЫМ ответом — сырой несёт display_tz, которого в
  // draft нет по построению, и «грязным» редактор был всегда (guard на каждый уход).
  const isDirty =
    !!serverConfig && !!draft && JSON.stringify(draft) !== JSON.stringify(toEditableBoardConfig(serverConfig))
  useEffect(() => {
    if (!isDirty) return
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault()
      e.returnValue = ''
    }
    window.addEventListener('beforeunload', handler)
    return () => window.removeEventListener('beforeunload', handler)
  }, [isDirty])

  if (!draft) {
    return <div className="p-8 text-sm text-text-muted">{t('common.loading')}</div>
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
      // ARCH-138: дефолт «сейчас» — стенка display-зоны, не UTC (−5ч)
      published_at: isoToDatetimeLocal(new Date().toISOString()),
    }
    patch((d) => {
      d.announcements = [...d.announcements, fresh]
    })
  }

  // WR-09: re-seeding is driven by the serverConfig-reference check above; the
  // mutation's invalidate → refetch yields a fresh reference that re-syncs `draft`.
  const onSave = () => updateConfig.mutate(draft)
  const onReset = () => setDraft(serverConfig ? toEditableBoardConfig(serverConfig) : clone(defaultBoardConfig))

  return (
    <div className="flex flex-col gap-4 p-6">
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

      <div>
        <div className="flex gap-1 border-b border-border-default" role="tablist">
          {(['home', 'board'] as const).map((surface) => (
            <button
              key={surface}
              type="button"
              role="tab"
              aria-selected={tab === surface}
              onClick={() => setTab(surface)}
              className={tab === surface
                ? '-mb-px border-b-2 border-accent px-4 py-2 text-sm font-semibold text-text-primary'
                : '-mb-px border-b-2 border-transparent px-4 py-2 text-sm font-semibold text-text-muted hover:text-text-primary'}
            >
              {surface === 'home' ? t('boardEditor.tabHome') : t('boardEditor.tabBoard')}
            </button>
          ))}
        </div>
        <p className="mt-2 text-xs text-text-muted">
          {tab === 'home' ? t('boardEditor.tabHomeHint') : t('boardEditor.tabBoardHint')}
        </p>
      </div>

      <div className="grid grid-cols-1 items-start gap-4 lg:grid-cols-[minmax(360px,460px)_minmax(0,1fr)]">
        {/* ── Left: поля выбранной вкладки — во всю длину страницы ─────── */}
        <div className="flex min-w-0 flex-col gap-4">
          {/* Module order */}
          {/* Resident home page — тексты и блоки страницы /home */}
          <Section title={t('boardEditor.homePage')} active={tab} usedOn={['home']}>
            <HomePageEditor
              home={draft.home ?? defaultHomeConfig}
              onChange={(home) => patch((d) => { d.home = home })}
            />
          </Section>

          <Section title={t('boardEditor.modulesOrder')} active={tab} usedOn={['board']}>
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
                      onWidthToggle={() =>
                        patch((d) => {
                          const l = d.layout.find((x) => x.id === item.id)
                          if (l) l.width = l.width === 'half' ? 'full' : 'half'
                        })
                      }
                    />
                  ))}
                </div>
              </SortableContext>
            </DndContext>
          </Section>

          {/* Organisation */}
          <Section title={t('boardEditor.org')} active={tab} usedOn={['board', 'home']}>
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
          <Section title={t('boardEditor.contacts')} active={tab} usedOn={['board', 'home']}>
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
          <Section title={t('boardEditor.bot')} active={tab} usedOn={['board', 'home']}>
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
          <Section title={t('boardEditor.announcements')} active={tab} usedOn={['board', 'home']}>
            {draft.announcements.map((ann, idx) => (
              <div key={ann.id} className="rounded-sm border border-border-default bg-bg-surface p-3">
                <div className="mb-2 flex flex-wrap items-center gap-2">
                  <Input
                    className="w-14 text-center"
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
                    className="min-w-0 rounded-sm border border-border-default bg-bg-surface px-2 py-1 text-xs text-text-primary"
                    value={ann.published_at.slice(0, 16)}
                    onChange={(e) => patch((d) => { d.announcements[idx].published_at = e.target.value })}
                  />
                  <button
                    type="button"
                    aria-label="remove"
                    className="ml-auto text-text-muted hover:text-red-500"
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

          {/* Planned works — блок «Ближайшие работы» страницы жителей */}
          <Section title={t('boardEditor.plannedWorks')} active={tab} usedOn={['home']}>
            <PlannedWorksEditor
              works={draft.planned_works ?? []}
              onChange={(works) => patch((d) => { d.planned_works = works })}
            />
          </Section>

          {/* Working hours */}
          <Section title={t('boardEditor.workingHours')} active={tab} usedOn={['board', 'home']}>
            {[...draft.working_hours]
              .sort((a, b) => DAY_ORDER.indexOf(a.day) - DAY_ORDER.indexOf(b.day))
              .map((wh) => {
                const idx = draft.working_hours.findIndex((x) => x.day === wh.day)
                return (
                  <div key={wh.day} className="flex items-center gap-2">
                    <span className="w-8 shrink-0 text-xs font-bold text-text-primary">{t(`days.short.${wh.day}`)}</span>
                    <Input
                      type="time"
                      className="w-auto min-w-0 flex-1"
                      value={wh.open}
                      disabled={wh.closed}
                      onChange={(e) => patch((d) => { d.working_hours[idx].open = e.target.value })}
                    />
                    <span className="text-text-muted">–</span>
                    <Input
                      type="time"
                      className="w-auto min-w-0 flex-1"
                      value={wh.close}
                      disabled={wh.closed}
                      onChange={(e) => patch((d) => { d.working_hours[idx].close = e.target.value })}
                    />
                    <label className="flex shrink-0 items-center gap-1.5 text-xs text-text-muted">
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

        {/* ── Right: живое превью выбранной вкладки — прилипает при прокрутке ── */}
        <div className="flex min-w-0 flex-col gap-2 lg:sticky lg:top-4">
          {tab === 'home' && (
            <div className="flex gap-1 self-start rounded-md border border-border-default p-1" role="group">
              {(['desktop', 'phone'] as const).map((view) => (
                <button
                  key={view}
                  type="button"
                  aria-pressed={homeView === view}
                  onClick={() => setHomeView(view)}
                  className={homeView === view
                    ? 'rounded-sm bg-accent px-3 py-1 text-xs font-semibold text-white'
                    : 'rounded-sm px-3 py-1 text-xs font-semibold text-text-muted hover:text-text-primary'}
                >
                  {view === 'desktop' ? t('boardEditor.previewDesktop') : t('boardEditor.previewPhone')}
                </button>
              ))}
            </div>
          )}
          <div className="max-h-[calc(100dvh-var(--topbar-h)-6rem)] overflow-auto rounded-md border border-border-default">
            {tab === 'board' && (
              <ScaledPreview width={DESKTOP_PREVIEW_WIDTH}><ResidentBoardPage configOverride={draft} /></ScaledPreview>
            )}
            {tab === 'home' && homeView === 'desktop' && (
              <ScaledPreview width={DESKTOP_PREVIEW_WIDTH}><ResidentHomePage configOverride={draft} /></ScaledPreview>
            )}
            {tab === 'home' && homeView === 'phone' && (
              <div className="mx-auto my-4 overflow-hidden rounded-[24px] border border-border-default" style={{ width: PHONE_PREVIEW_WIDTH }}>
                <ResidentHomePage configOverride={draft} />
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
