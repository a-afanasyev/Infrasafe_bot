/* eslint-disable react-refresh/only-export-components -- тест-хелперы, не рантайм-компоненты */
import { vi } from 'vitest'
import type { ReactNode } from 'react'
import { CompletionQueueProvider } from '../twa/simple/queue/CompletionQueue'
import { createMemoryStore } from '../twa/simple/queue/store'
import type { QueueItem, QueueStore } from '../twa/simple/queue/types'

// Хелперы тестов простого режима исполнителя (twa/simple).

/** Заглушка window.Telegram.WebApp: вибрация и BackButton — шпионы. */
export function stubTelegram() {
  const haptic = { impactOccurred: vi.fn(), notificationOccurred: vi.fn(), selectionChanged: vi.fn() }
  const backButton = { show: vi.fn(), hide: vi.fn(), onClick: vi.fn(), offClick: vi.fn() }
  const webApp = {
    ready: vi.fn(),
    expand: vi.fn(),
    close: vi.fn(),
    initData: '',
    initDataUnsafe: {},
    themeParams: {},
    colorScheme: 'light',
    HapticFeedback: haptic,
    BackButton: backButton,
  }
  ;(window as unknown as { Telegram?: unknown }).Telegram = { WebApp: webApp }
  return { haptic, backButton }
}

export function unstubTelegram() {
  delete (window as unknown as { Telegram?: unknown }).Telegram
}

/** Очередь в памяти с заранее положенными записями. */
export async function memoryQueueWith(items: QueueItem[] = []): Promise<QueueStore> {
  const store = createMemoryStore()
  for (const item of items) await store.put(item)
  return store
}

export function QueueWrapper({ store, children }: { store: QueueStore; children: ReactNode }) {
  return <CompletionQueueProvider openStore={() => Promise.resolve(store)}>{children}</CompletionQueueProvider>
}

/** navigator.onLine для офлайн-сценариев. */
export function setOnline(value: boolean) {
  Object.defineProperty(window.navigator, 'onLine', { value, configurable: true })
}
