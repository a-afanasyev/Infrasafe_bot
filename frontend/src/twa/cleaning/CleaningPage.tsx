import { useCallback, useEffect, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router'
import { useTranslation } from 'react-i18next'
import { Camera, Check, ChevronLeft, CloudUpload, XCircle } from 'lucide-react'
import { twaClient } from '../twaClient'
import { PRIMARY_BTN, SECONDARY_BTN } from '../simple/components/Ui'
import {
  CLEANING_TASKS_KEY,
  type CleaningMyTask,
  floorOf,
  openCleaningSession,
  sendCleaningPhoto,
  useMyCleaningTasks,
} from './api'
import LiveCamera from './LiveCamera'
import {
  type CameraSource,
  type CleaningQueueItem,
  type CleaningQueueStore,
  type SendFn,
  enqueue,
  flush,
  openCleaningStore,
} from './queue'

/**
 * Уборка для уборщицы — одна страница на оба режима Mini App.
 *
 * Список подъездов на сегодня → подъезд: по кнопке на каждый этаж задания.
 * Снять этаж можно только камерой приложения; фото и есть отметка «помыто».
 * Кадр сначала ложится в очередь на телефоне и уходит, когда есть связь.
 */
const RETRY_EVERY_MS = 15_000
const formatTime = (iso: string) => new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })

interface Props {
  backTo: string
  /** Подмена в тестах. */
  openStore?: () => Promise<CleaningQueueStore>
  send?: SendFn
}

function useCleaningQueue(userId: number | null, openStore: () => Promise<CleaningQueueStore>, send: SendFn) {
  const queryClient = useQueryClient()
  const storeRef = useRef<CleaningQueueStore | null>(null)
  const [items, setItems] = useState<CleaningQueueItem[]>([])

  const refresh = useCallback(async () => {
    if (storeRef.current) setItems(await storeRef.current.list())
  }, [])

  const busyRef = useRef(false)
  const againRef = useRef(false)
  const flushNow = useCallback(async () => {
    // Один проход за раз: параллельные (таймер, online, новый кадр) слали бы одно фото дважды.
    if (!storeRef.current || userId === null) return
    if (busyRef.current) { againRef.current = true; return }
    busyRef.current = true
    try {
      const sent = await flush(storeRef.current, send, userId)
      await refresh()
      if (sent > 0) void queryClient.invalidateQueries({ queryKey: CLEANING_TASKS_KEY })
    } finally {
      busyRef.current = false
    }
    if (againRef.current) { againRef.current = false; void flushNowRef.current() }
  }, [userId, send, refresh, queryClient])
  const flushNowRef = useRef(flushNow)
  flushNowRef.current = flushNow

  useEffect(() => {
    let alive = true
    void openStore().then(async (store) => {
      if (!alive) return
      storeRef.current = store
      await flushNow()
    })
    const timer = window.setInterval(() => void flushNow(), RETRY_EVERY_MS)
    window.addEventListener('online', flushNow)
    return () => {
      alive = false
      window.clearInterval(timer)
      window.removeEventListener('online', flushNow)
    }
  }, [openStore, flushNow])

  const add = useCallback(async (item: CleaningQueueItem) => {
    if (!storeRef.current) return
    await enqueue(storeRef.current, item)
    await refresh()
    void flushNow()
  }, [refresh, flushNow])

  const dismiss = useCallback(async (id: string) => {
    await storeRef.current?.remove(id)
    await refresh()
  }, [refresh])

  return { items, add, dismiss, flushNow }
}

/** Запись очереди для нового кадра. Время съёмки — не меньше прошлого кадра точки:
 *  порядок пересъёмок не ломается, если часы телефона перевели назад. */
function newQueueItem(
  userId: number, task: CleaningMyTask, slot: string, photo: Blob, source: CameraSource, previousShot: number,
): CleaningQueueItem {
  return {
    id: crypto.randomUUID(), userId, taskId: task.id, slot, photo, source,
    capturedAt: Math.max(Date.now(), previousShot + 1), attempts: 0, nextAttemptAt: 0,
  }
}

function slotLabel(slot: string, t: (key: string, options?: Record<string, unknown>) => string): string {
  const floor = floorOf(slot)
  return floor !== null ? t('twa.cleaning.floor', { n: floor }) : t(`twa.cleaning.point.${slot.slice(6)}`, { defaultValue: slot.slice(6) })
}

export default function CleaningPage({ backTo, openStore = openCleaningStore, send = sendCleaningPhoto }: Props) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { data, isLoading, isError } = useMyCleaningTasks()
  const { data: profile } = useQuery<{ id: number }>({
    queryKey: ['twa', 'profile'],
    queryFn: () => twaClient.get('/api/v2/profile').then((r) => r.data),
    staleTime: 60_000,
  })
  const userId = profile?.id ?? null
  const queue = useCleaningQueue(userId, openStore, send)
  const [taskId, setTaskId] = useState<number | null>(null)
  const [shooting, setShooting] = useState<string | null>(null)

  const task = data?.tasks.find((item) => item.id === taskId) ?? null
  const mine = queue.items.filter((item) => item.userId === userId)
  const queued = (id: number, slot: string) => mine.find((item) => item.taskId === id && item.slot === slot)
  const doneCount = (item: CleaningMyTask) => // Отклонённый кадр не считается снятым: иначе «9 из 9» при красной кнопке.
    item.slots.filter((s) => { const q = queued(item.id, s.slot); return q ? !q.failed : s.done }).length
  const deadline = data?.day_end_at ? formatTime(data.day_end_at) : null

  const open = (item: CleaningMyTask) => {
    setTaskId(item.id)
    if (!item.session_open) void openCleaningSession(item.id)
  }

  const shot = (photo: Blob, source: CameraSource) => {
    if (!task || !shooting || userId === null) return
    const onServer = Date.parse(task.slots.find((s) => s.slot === shooting)?.captured_at ?? '')
    const previous = queued(task.id, shooting)?.capturedAt ?? (Number.isFinite(onServer) ? onServer : 0)
    void queue.add(newQueueItem(userId, task, shooting, photo, source, previous))
    setShooting(null)
  }

  if (isLoading) return <p className="p-6 text-center text-[20px]">{t('twa.cleaning.loading')}</p>
  if (isError || !data) return <p role="alert" className="p-6 text-center text-[20px]">{t('twa.cleaning.unavailable')}</p>

  if (task) {
    const frozen = !['planned', 'in_progress'].includes(task.status)
    return (
      <div className="flex min-h-screen flex-col gap-4 bg-gray-100 p-4 text-gray-900 dark:bg-gray-950 dark:text-gray-50">
        <button type="button" onClick={() => setTaskId(null)} className="flex h-12 items-center gap-2 text-[20px] font-semibold">
          <ChevronLeft size={28} aria-hidden /> {t('twa.cleaning.back')}
        </button>
        <div className="rounded-2xl bg-white p-4 dark:bg-gray-900">
          <p className="text-[26px] font-bold">{task.address} · {t('twa.cleaning.entrance', { n: task.entrance })}</p>
          <p className="text-[18px] text-gray-600 dark:text-gray-300">{task.works.map((w) => t(`twa.cleaning.work.${w}`)).join(' · ')}</p>
        </div>
        <div className="rounded-2xl bg-white p-4 dark:bg-gray-900">
          <p className="text-[20px] font-bold">{t('twa.cleaning.shootEach')}</p>
          <p className="mb-3 text-[18px] font-semibold" data-testid="cleaning-progress">
            {t('twa.cleaning.progress', { done: doneCount(task), total: task.slots.length })}
          </p>
          <div className="grid grid-cols-2 gap-2">
            {task.slots.map((slot) => {
              const pending = queued(task.id, slot.slot)
              const label = slotLabel(slot.slot, t)
              const state = pending?.failed ? 'failed' : pending ? 'queued' : slot.done ? 'done' : 'todo'
              return (
                <button
                  key={slot.slot} type="button" disabled={frozen} onClick={() => setShooting(slot.slot)}
                  aria-label={`${label}: ${t(`twa.cleaning.slotState.${state}`)}`}
                  className={`flex min-h-[64px] flex-col items-center justify-center rounded-2xl border-2 px-2 text-[19px] font-bold disabled:opacity-60 ${
                    state === 'done' ? 'border-emerald-700 bg-emerald-700 text-white'
                      : state === 'queued' ? 'border-blue-700 bg-white text-blue-800 dark:bg-gray-900 dark:text-blue-200'
                        : state === 'failed' ? 'border-red-700 bg-red-50 text-red-800 dark:bg-red-950 dark:text-red-200'
                          : 'border-gray-500 bg-white dark:bg-gray-900'
                  }`}
                >
                  <span className="flex items-center gap-2">
                    {state === 'done' && <Check size={22} aria-hidden />}
                    {state === 'queued' && <CloudUpload size={22} aria-hidden />}
                    {state === 'failed' && <XCircle size={22} aria-hidden />}
                    {state === 'todo' && <Camera size={22} aria-hidden />}
                    {label}
                  </span>
                  <span className="text-[14px] font-medium">
                    {pending?.failed ? t(`twa.cleaning.refused.${pending.failed}`, { defaultValue: t('twa.cleaning.refused.other') }) : t(`twa.cleaning.slotState.${state}`)}
                  </span>
                </button>
              )
            })}
          </div>
        </div>
        {frozen
          ? <p role="status" className="rounded-2xl bg-gray-300 p-4 text-center text-[20px] font-bold dark:bg-gray-700">{t(`twa.cleaning.status.${task.status}`)}</p>
          : deadline && <p className="rounded-2xl border-2 border-amber-700 bg-amber-50 p-4 text-[18px] text-amber-900 dark:bg-amber-950 dark:text-amber-100">{t('twa.cleaning.deadline', { time: deadline })}</p>}
        {shooting && (
          <LiveCamera
            title={slotLabel(shooting, t)}
            subtitle={`${task.address}, ${t('twa.cleaning.entrance', { n: task.entrance })}`}
            onShot={shot} onClose={() => setShooting(null)}
          />
        )}
      </div>
    )
  }

  const pendingTotal = mine.filter((item) => !item.failed).length
  return (
    <div className="flex min-h-screen flex-col gap-3 bg-gray-100 p-4 text-gray-900 dark:bg-gray-950 dark:text-gray-50">
      <button type="button" onClick={() => navigate(backTo)} className="flex h-12 items-center gap-2 text-[20px] font-semibold">
        <ChevronLeft size={28} aria-hidden /> {t('twa.cleaning.back')}
      </button>
      <h1 className="text-[26px] font-bold">{t('twa.cleaning.title')}</h1>
      {deadline && <p className="text-[18px] text-gray-600 dark:text-gray-300">{t('twa.cleaning.deadline', { time: deadline })}</p>}
      {pendingTotal > 0 && (
        <div className="flex flex-col gap-2 rounded-2xl border-2 border-blue-700 bg-white p-4 dark:bg-gray-900">
          <p className="text-[19px] font-bold text-blue-800 dark:text-blue-200">{t('twa.cleaning.waiting', { count: pendingTotal })}</p>
          <button type="button" onClick={() => void queue.flushNow()} className={`${SECONDARY_BTN} bg-blue-700 text-white`}>
            <CloudUpload size={24} aria-hidden /> {t('twa.cleaning.sendNow')}
          </button>
        </div>
      )}
      {data.tasks.length === 0 && <p className="py-12 text-center text-[22px] font-bold">{t('twa.cleaning.empty')}</p>}
      <ul className="flex flex-col gap-3">
        {data.tasks.map((item) => {
          const done = doneCount(item)
          return (
            <li key={item.id} className="list-none">
              <button
                type="button" onClick={() => open(item)}
                className={`${PRIMARY_BTN} h-auto min-h-[96px] flex-col items-start gap-1 border-2 px-4 py-3 text-left ${
                  item.status === 'accepted' ? 'border-emerald-700 bg-emerald-50 dark:bg-emerald-950'
                    : 'border-gray-400 bg-white dark:bg-gray-900'
                }`}
              >
                <span className="text-[21px] font-bold">{item.address} · {t('twa.cleaning.entrance', { n: item.entrance })}</span>
                <span className="text-[17px] font-semibold">{t(`twa.cleaning.status.${item.status}`)} · {t('twa.cleaning.progress', { done, total: item.slots.length })}</span>
              </button>
            </li>
          )
        })}
      </ul>
    </div>
  )
}
