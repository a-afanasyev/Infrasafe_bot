/* eslint-disable react-refresh/only-export-components -- провайдер и его хук живут вместе */
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { twaClient } from '../../twaClient'
import { sendCompletion } from '../api'
import { attemptSend, createQueueItem, type SendFn } from './engine'
import { dueItems, isSendable, nextWakeDelay, ownItems, staleForeign } from './policy'
import { createMemoryStore, createStoreHolder, openQueueStore } from './store'
import type { FinalReason, QueueItem, QueueStore, SendOutcome } from './types'

interface SubmitArgs {
  requestNumber: string
  photo: Blob
  fileName: string
  label?: string
}

interface CompletionQueueValue {
  /** Записи текущего пользователя, старые первыми (включая проваленные). */
  items: QueueItem[]
  /** Сколько «Готово» ещё ждут отправки (без проваленных). */
  pendingCount: number
  /** Сохранить фото в очередь и сразу попробовать отправить. */
  submit: (args: SubmitArgs) => Promise<{ id: string; outcome: SendOutcome }>
  /** Отправить запись сейчас (кнопка «Ещё раз») — с тем же ключом. */
  retry: (id: string) => Promise<SendOutcome>
  /** Началась смена: дослать всё, включая ждавшее смены. */
  flushNow: () => void
  /** Исполнитель увидел исход — убрать запись. */
  dismiss: (id: string) => Promise<void>
}

const CompletionQueueContext = createContext<CompletionQueueValue | null>(null)

export const FINAL_REASON_KEY: Record<FinalReason, string> = {
  closed: 'twa.simple.final.closed',
  not_yours: 'twa.simple.final.notYours',
  bad_photo: 'twa.simple.final.badPhoto',
}

type FlushMode = 'due' | 'open' | 'shift'

interface Props {
  children: ReactNode
  /** Для тестов: хранилище, сетевой вызов, пользователь (иначе — из профиля). */
  openStore?: () => Promise<QueueStore>
  send?: SendFn
  userId?: number
}

/**
 * Очередь «Готово»: запись в хранилище → попытка → автоповтор по расписанию
 * (policy.retryDelay), досылка при открытии приложения и при возврате сети —
 * по одной, только записи текущего пользователя. Исход попытки с экрана
 * «Готово» возвращается экрану; фоновый окончательный отказ не удаляется,
 * а помечается и показывается на плитке/карточке.
 */
export function CompletionQueueProvider({ children, openStore = openQueueStore, send = sendCompletion, userId: userIdProp }: Props) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const { data: profile } = useQuery<{ id?: number }>({
    queryKey: ['twa', 'profile'],
    queryFn: () => twaClient.get('/api/v2/profile').then((r) => r.data),
    staleTime: 60_000,
    enabled: userIdProp === undefined,
  })
  const userId = userIdProp ?? profile?.id ?? null

  const [all, setAll] = useState<QueueItem[]>([])
  const [ready, setReady] = useState(false)
  const [stores] = useState(() => createStoreHolder(openStore))
  const inFlight = useRef(new Map<string, Promise<SendOutcome>>())
  // Итог уже завершённых записей: «Ещё раз» по записи, которую успел
  // закрыть фоновый повтор, должен показать настоящий исход, а не угадывать.
  const settled = useRef(new Map<string, SendOutcome>())

  const refresh = useCallback(async () => {
    setAll(await (await stores.get()).list())
  }, [stores])

  const run = useCallback(
    (item: QueueItem, foreground: boolean): Promise<SendOutcome> => {
      const running = inFlight.current.get(item.id)
      if (running) return running
      const promise = stores
        .get()
        .then(async (store) => {
          const outcome = await attemptSend(store, item, send)
          if (outcome.kind === 'sent') {
            // Доставлено — прежние проваленные попытки этой заявки больше не нужны.
            const stale = (await store.list()).filter(
              (i) => i.failed && i.requestNumber === item.requestNumber && i.userId === item.userId,
            )
            for (const i of stale) await store.remove(i.id)
          }
          // Экран «Готово» сам показал окончательный отказ — запись не нужна.
          if (outcome.kind === 'final' && foreground) await store.remove(item.id)
          return outcome
        })
        .finally(() => {
          inFlight.current.delete(item.id)
          void refresh()
        })
      inFlight.current.set(item.id, promise)
      return promise.then((outcome) => {
        if (outcome.kind !== 'queued') {
          settled.current.set(item.id, outcome)
          queryClient.invalidateQueries({ queryKey: ['twa', 'executor-tasks'] })
          queryClient.invalidateQueries({ queryKey: ['twa', 'request', item.requestNumber] })
        }
        return outcome
      })
    },
    [stores, send, refresh, queryClient],
  )

  /** Досылка по одной: на плохой сети параллельные фото мешают друг другу. */
  const flush = useCallback(
    async (mode: FlushMode) => {
      if (userId == null) return
      const mine = ownItems(await (await stores.get()).list(), userId)
      const batch =
        mode === 'due' ? dueItems(mine, Date.now())
          : mode === 'open' ? mine.filter((i) => isSendable(i) && !i.noShift)
            : mine.filter(isSendable)
      for (const item of batch) {
        const outcome = await run(item, false).catch(() => null)
        if (outcome?.kind === 'sent') {
          toast.success(t('twa.simple.done.sentLater', { number: item.requestNumber }))
        }
      }
    },
    [userId, stores, run, t],
  )

  // Ссылка на актуальный flush: смена языка пересоздаёт колбэки, а досылка
  // «при открытии» должна случиться ровно один раз, не на каждый ререндер.
  const flushRef = useRef(flush)
  useEffect(() => {
    flushRef.current = flush
  }, [flush])

  // Открытие приложения (как только известен пользователь): убираем старые
  // чужие записи и досылаем свои.
  useEffect(() => {
    if (userId == null) return
    let cancelled = false
    void stores
      .get()
      .then(async (store) => {
        for (const i of staleForeign(await store.list(), userId, Date.now())) await store.remove(i.id)
        return store.list()
      })
      .then((list) => {
        if (cancelled) return
        setAll(list)
        setReady(true)
        void flushRef.current('open')
      })
    return () => {
      cancelled = true
    }
  }, [stores, userId])

  // Вернулась сеть — не ждём таймера.
  useEffect(() => {
    const onOnline = () => void flushRef.current('open')
    window.addEventListener('online', onOnline)
    return () => window.removeEventListener('online', onOnline)
  }, [])

  const items = useMemo(() => ownItems(all, userId), [all, userId])

  // Будильник на ближайший срок повтора (без ждущих смены и проваленных).
  useEffect(() => {
    if (!ready) return
    const delay = nextWakeDelay(items, Date.now())
    if (delay === null) return
    const id = window.setTimeout(() => void flushRef.current('due'), delay)
    return () => window.clearTimeout(id)
  }, [items, ready])

  const submit = useCallback(
    async ({ requestNumber, photo, fileName, label }: SubmitArgs) => {
      if (userId == null) throw new Error('queue: user unknown')
      const item = createQueueItem({ userId, requestNumber, photo, fileName, label }, Date.now())
      try {
        await (await stores.get()).put(item)
      } catch (err) {
        // IndexedDB отказала (квота, приватный режим): отправляем без
        // сохранения между сеансами — очередь до конца сеанса в памяти.
        console.warn('[simple-queue] IndexedDB write failed, falling back to memory', err)
        const memory = createMemoryStore()
        await memory.put(item)
        stores.replace(memory)
      }
      await refresh()
      const outcome = await run(item, true)
      return { id: item.id, outcome }
    },
    [userId, stores, refresh, run],
  )

  const retry = useCallback(
    async (id: string): Promise<SendOutcome> => {
      const item = (await (await stores.get()).list()).find((i) => i.id === id)
      // Записи нет — её уже закрыл фоновый повтор.
      if (!item) return settled.current.get(id) ?? { kind: 'sent' }
      return run(item, true)
    },
    [stores, run],
  )

  const dismiss = useCallback(
    async (id: string) => {
      await (await stores.get()).remove(id)
      await refresh()
    },
    [stores, refresh],
  )

  const flushNow = useCallback(() => void flushRef.current('shift'), [])
  const pendingCount = useMemo(() => items.filter(isSendable).length, [items])

  return (
    <CompletionQueueContext.Provider value={{ items, pendingCount, submit, retry, flushNow, dismiss }}>
      {children}
    </CompletionQueueContext.Provider>
  )
}

export function useCompletionQueue(): CompletionQueueValue {
  const value = useContext(CompletionQueueContext)
  if (!value) throw new Error('useCompletionQueue must be used inside CompletionQueueProvider')
  return value
}
