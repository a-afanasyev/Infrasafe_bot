import type { QueueItem, QueueStore } from './types'

const DB_NAME = 'uk-twa-simple'
const DB_VERSION = 1
const STORE = 'completion-queue'

function byCreatedAt(a: QueueItem, b: QueueItem): number {
  return a.createdAt - b.createdAt
}

/** Очередь в памяти: тесты и фолбэк, когда IndexedDB недоступна. */
export function createMemoryStore(): QueueStore {
  let items: readonly QueueItem[] = []
  return {
    persistent: false,
    async list() {
      return [...items].sort(byCreatedAt)
    },
    async put(item) {
      items = [...items.filter((i) => i.id !== item.id), item]
    },
    async remove(id) {
      items = items.filter((i) => i.id !== id)
    },
  }
}

// В IndexedDB фото лежит как ArrayBuffer + MIME: Blob в IDB на части старых
// WebView (iOS < 14, ранний Android WebView) сохранялся битым.
interface StoredItem extends Omit<QueueItem, 'photo'> {
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
    const req = factory.open(DB_NAME, DB_VERSION)
    req.onupgradeneeded = () => {
      if (!req.result.objectStoreNames.contains(STORE)) {
        req.result.createObjectStore(STORE, { keyPath: 'id' })
      }
    }
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error ?? new Error('IndexedDB open failed'))
    req.onblocked = () => reject(new Error('IndexedDB open blocked'))
  })
}

function blobToArrayBuffer(blob: Blob): Promise<ArrayBuffer> {
  if (typeof blob.arrayBuffer === 'function') return blob.arrayBuffer()
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(reader.result as ArrayBuffer)
    reader.onerror = () => reject(reader.error ?? new Error('FileReader failed'))
    reader.readAsArrayBuffer(blob)
  })
}

function createIdbStore(db: IDBDatabase): QueueStore {
  const tx = (mode: IDBTransactionMode) => db.transaction(STORE, mode).objectStore(STORE)
  return {
    persistent: true,
    async list() {
      const rows = await promisify(tx('readonly').getAll() as IDBRequest<StoredItem[]>)
      return rows
        .map(({ photoBytes, photoType, ...rest }) => ({
          ...rest,
          photo: new Blob([photoBytes], { type: photoType }),
        }))
        .sort(byCreatedAt)
    },
    async put(item) {
      const { photo, ...rest } = item
      // Байты читаем ДО открытия транзакции: await внутри неё её закрывает.
      const photoBytes = await blobToArrayBuffer(photo)
      const row: StoredItem = { ...rest, photoBytes, photoType: photo.type || 'image/jpeg' }
      await promisify(tx('readwrite').put(row))
    },
    async remove(id) {
      await promisify(tx('readwrite').delete(id))
    },
  }
}

/**
 * IndexedDB-очередь, а если её нет (приватный режим, отключена, ошибка
 * открытия) — очередь в памяти: «Готово» всё равно уходит и повторяется в
 * пределах сеанса, просто не переживёт закрытие приложения.
 */
export async function openQueueStore(
  factory: IDBFactory | undefined = globalThis.indexedDB,
): Promise<QueueStore> {
  if (!factory) return createMemoryStore()
  try {
    return createIdbStore(await openDb(factory))
  } catch (err) {
    console.warn('[simple-queue] IndexedDB unavailable, queue kept in memory', err)
    return createMemoryStore()
  }
}

/**
 * Текущее хранилище очереди. Открывается асинхронно; если запись в IndexedDB
 * отказала посреди сеанса — подменяется памятью (replace).
 */
export interface StoreHolder {
  get(): Promise<QueueStore>
  replace(store: QueueStore): void
}

export function createStoreHolder(open: () => Promise<QueueStore>): StoreHolder {
  let current: QueueStore | null = null
  const ready = open().then((store) => {
    current = current ?? store
  })
  return {
    async get() {
      await ready
      return current as QueueStore
    },
    replace(store) {
      current = store
    },
  }
}
