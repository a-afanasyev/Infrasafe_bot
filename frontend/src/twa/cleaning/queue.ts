/**
 * Очередь фото уборки: кадр и ключ операции сохраняются ДО отправки.
 *
 * Сеть в подъезде может пропасть в любой момент: запрос ушёл, ответ потерялся.
 * Сервер по ключу операции возвращает сохранённый исход, поэтому ключ живёт в
 * записи до конца и повтор безопасен. Отдельно от очереди «Готово» — та
 * завязана на номер заявки; здесь адрес записи — задание и точка съёмки.
 *
 * На точку — не больше одной неотправленной записи: пересъёмка заменяет её.
 */
import { retryDelay } from '../simple/queue/policy'

export type CameraSource = 'live' | 'system'

export interface CleaningQueueItem {
  /** = ключ операции (UUID). */
  id: string
  userId: number
  taskId: number
  slot: string
  photo: Blob
  capturedAt: number
  source: CameraSource
  attempts: number
  nextAttemptAt: number
  /** Окончательный отказ: запись не шлём, показываем на кнопке точки. */
  failed?: string
}

export interface CleaningQueueStore {
  list(): Promise<CleaningQueueItem[]>
  put(item: CleaningQueueItem): Promise<void>
  remove(id: string): Promise<void>
}

/** Исход одной попытки отправки. */
export type SendResult =
  | { kind: 'done' }
  | { kind: 'final'; reason: string }
  | { kind: 'retry' }

export type SendFn = (item: CleaningQueueItem) => Promise<SendResult>

export function createMemoryStore(): CleaningQueueStore {
  let items: readonly CleaningQueueItem[] = []
  return {
    async list() {
      return [...items].sort((a, b) => a.capturedAt - b.capturedAt)
    },
    async put(item) {
      items = [...items.filter((i) => i.id !== item.id), item]
    },
    async remove(id) {
      items = items.filter((i) => i.id !== id)
    },
  }
}

/** Поставить кадр в очередь; прежняя неотправленная запись этой точки заменяется. */
export async function enqueue(store: CleaningQueueStore, item: CleaningQueueItem): Promise<void> {
  for (const old of await store.list()) {
    if (old.userId === item.userId && old.taskId === item.taskId && old.slot === item.slot) await store.remove(old.id)
  }
  await store.put(item)
}

/**
 * Один проход по очереди: шлём по одной записи (медиа-сервис не любит пачки),
 * готовые удаляем, окончательные отказы помечаем, временные сбои откладываем.
 * Возвращает число отправленных.
 */
export async function flush(
  store: CleaningQueueStore, send: SendFn, userId: number, now: () => number = Date.now,
): Promise<number> {
  let sent = 0
  for (const item of await store.list()) {
    if (item.userId !== userId || item.failed || item.nextAttemptAt > now()) continue
    let result: SendResult
    try {
      result = await send(item)
    } catch {
      result = { kind: 'retry' }
    }
    if (result.kind === 'done') {
      await store.remove(item.id)
      sent += 1
    } else if (result.kind === 'final') {
      await store.put({ ...item, failed: result.reason })
    } else {
      const attempts = item.attempts + 1
      await store.put({ ...item, attempts, nextAttemptAt: now() + retryDelay(attempts) })
      break // нет связи — остальные записи ждут следующего прохода
    }
  }
  return sent
}

// ── IndexedDB ────────────────────────────────────────────────────────────────
// Кадр хранится как ArrayBuffer + MIME: Blob в IndexedDB на части старых WebView
// сохранялся битым (тот же приём, что в simple/queue/store.ts).

const DB_NAME = 'uk-twa-cleaning'
const STORE = 'photos'

interface StoredItem extends Omit<CleaningQueueItem, 'photo'> {
  photoBytes: ArrayBuffer
  photoType: string
}

function promisify<T>(req: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error ?? new Error('IndexedDB request failed'))
  })
}

function openDb(factory: IDBFactory): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = factory.open(DB_NAME, 1)
    req.onupgradeneeded = () => {
      if (!req.result.objectStoreNames.contains(STORE)) req.result.createObjectStore(STORE, { keyPath: 'id' })
    }
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error ?? new Error('IndexedDB open failed'))
    req.onblocked = () => reject(new Error('IndexedDB open blocked'))
  })
}

/** Хранилище очереди: IndexedDB, а если она недоступна — память до конца сеанса. */
export async function openCleaningStore(): Promise<CleaningQueueStore> {
  if (typeof indexedDB === 'undefined') return createMemoryStore()
  let db: IDBDatabase
  try {
    db = await openDb(indexedDB)
  } catch {
    return createMemoryStore()
  }
  const tx = (mode: IDBTransactionMode) => db.transaction(STORE, mode).objectStore(STORE)
  return {
    async list() {
      const rows = (await promisify(tx('readonly').getAll())) as StoredItem[]
      return rows
        .map(({ photoBytes, photoType, ...rest }) => ({ ...rest, photo: new Blob([photoBytes], { type: photoType }) }))
        .sort((a, b) => a.capturedAt - b.capturedAt)
    },
    async put({ photo, ...rest }) {
      const stored: StoredItem = { ...rest, photoBytes: await photo.arrayBuffer(), photoType: photo.type || 'image/jpeg' }
      await promisify(tx('readwrite').put(stored))
    },
    async remove(id) {
      await promisify(tx('readwrite').delete(id))
    },
  }
}
