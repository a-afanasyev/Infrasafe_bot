/* eslint-disable react-refresh/only-export-components -- провайдер и его хук живут вместе */
import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { sendCompletion } from '../api'
import { attemptSend, createQueueItem, type SendFn } from './engine'
import { dueItems, nextWakeDelay } from './policy'
import { createMemoryStore, createStoreHolder, openQueueStore } from './store'
import type { FinalReason, QueueItem, QueueStore, SendOutcome } from './types'

interface CompletionQueueValue {
  /** Недоставленные «Готово», старые первыми. */
  items: QueueItem[]
  /** Сохранить фото в очередь и сразу попробовать отправить. */
  submit: (requestNumber: string, photo: Blob, fileName: string) => Promise<{ id: string; outcome: SendOutcome }>
  /** Отправить запись сейчас (кнопка «Ещё раз») — с тем же ключом. */
  retry: (id: string) => Promise<SendOutcome>
  /** Дослать всё сейчас, не дожидаясь срока (например, началась смена). */
  flushNow: () => void
}

const CompletionQueueContext = createContext<CompletionQueueValue | null>(null)

export const FINAL_REASON_KEY: Record<FinalReason, string> = {
  closed: 'twa.simple.final.closed',
  not_yours: 'twa.simple.final.notYours',
  bad_photo: 'twa.simple.final.badPhoto',
}

interface Props {
  children: ReactNode
  /** Для тестов: хранилище и сетевой вызов. */
  openStore?: () => Promise<QueueStore>
  send?: SendFn
}

/**
 * Очередь «Готово»: запись в хранилище → попытка → автоповтор по расписанию
 * (policy.retryDelay), досылка при открытии приложения и при возврате сети.
 * Исходы фоновых попыток сообщаются тостом; исход попытки, запущенной с
 * экрана «Готово», возвращается вызывающему — экран сам рисует результат.
 */
export function CompletionQueueProvider({ children, openStore = openQueueStore, send = sendCompletion }: Props) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [items, setItems] = useState<QueueItem[]>([])
  const [ready, setReady] = useState(false)
  const [stores] = useState(() => createStoreHolder(openStore))
  const inFlight = useRef(new Map<string, Promise<SendOutcome>>())
  // Итог уже завершённых записей: «Ещё раз» по записи, которую успел
  // закрыть фоновый повтор, должен показать настоящий исход, а не угадывать.
  const settled = useRef(new Map<string, SendOutcome>())

  const refresh = useCallback(async () => {
    const store = await stores.get()
    setItems(await store.list())
  }, [stores])

  const run = useCallback(
    (item: QueueItem): Promise<SendOutcome> => {
      const running = inFlight.current.get(item.id)
      if (running) return running
      const promise = stores
        .get()
        .then((store) => attemptSend(store, item, send))
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

  const runBackground = useCallback(
    async (item: QueueItem) => {
      const outcome = await run(item)
      if (outcome.kind === 'final') toast.error(t(FINAL_REASON_KEY[outcome.reason]))
      else if (outcome.kind === 'sent') toast.success(t('twa.simple.done.sentLater', { number: item.requestNumber }))
    },
    [run, t],
  )

  /** force — всё подряд, не дожидаясь срока (открытие приложения, вернулась сеть). */
  const flush = useCallback(
    async (force: boolean) => {
      const all = await (await stores.get()).list()
      const due = force ? all : dueItems(all, Date.now())
      await Promise.all(due.map((item) => runBackground(item).catch(() => undefined)))
    },
    [stores, runBackground],
  )

  // Ссылка на актуальный flush: смена языка пересоздаёт колбэки, а досылка
  // «при открытии» должна случиться ровно один раз, не на каждый ререндер.
  const flushRef = useRef(flush)
  useEffect(() => {
    flushRef.current = flush
  }, [flush])

  // Открытие приложения: досылаем всё, что осталось с прошлого раза.
  useEffect(() => {
    let cancelled = false
    void stores
      .get()
      .then((store) => store.list())
      .then((list) => {
        if (cancelled) return
        setItems(list)
        setReady(true)
        void flushRef.current(true)
      })
    return () => {
      cancelled = true
    }
  }, [stores])

  // Вернулась сеть — не ждём таймера.
  useEffect(() => {
    const onOnline = () => void flushRef.current(true)
    window.addEventListener('online', onOnline)
    return () => window.removeEventListener('online', onOnline)
  }, [])

  // Будильник на ближайший срок повтора.
  useEffect(() => {
    if (!ready) return
    const delay = nextWakeDelay(items, Date.now())
    if (delay === null) return
    const id = window.setTimeout(() => void flushRef.current(false), delay)
    return () => window.clearTimeout(id)
  }, [items, ready])

  const submit = useCallback(
    async (requestNumber: string, photo: Blob, fileName: string) => {
      const item = createQueueItem(requestNumber, photo, fileName, Date.now())
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
      const outcome = await run(item)
      return { id: item.id, outcome }
    },
    [stores, refresh, run],
  )

  const retry = useCallback(
    async (id: string): Promise<SendOutcome> => {
      const item = (await (await stores.get()).list()).find((i) => i.id === id)
      // Записи нет — её уже закрыл фоновый повтор.
      if (!item) return settled.current.get(id) ?? { kind: 'sent' }
      return run(item)
    },
    [stores, run],
  )

  const flushNow = useCallback(() => void flushRef.current(true), [])

  return (
    <CompletionQueueContext.Provider value={{ items, submit, retry, flushNow }}>
      {children}
    </CompletionQueueContext.Provider>
  )
}

export function useCompletionQueue(): CompletionQueueValue {
  const value = useContext(CompletionQueueContext)
  if (!value) throw new Error('useCompletionQueue must be used inside CompletionQueueProvider')
  return value
}
