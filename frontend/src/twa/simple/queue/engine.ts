import { classifyCompletionError, newIdempotencyKey, retryDelay } from './policy'
import type { QueueItem, QueueStore, SendOutcome } from './types'

/** Сетевой вызов «Готово» (подменяется в тестах). */
export type SendFn = (item: QueueItem) => Promise<unknown>

/** Новая запись очереди — одна попытка «Готово» со своим ключом идемпотентности. */
export function createQueueItem(
  requestNumber: string,
  photo: Blob,
  fileName: string,
  now: number,
  key: string = newIdempotencyKey(),
): QueueItem {
  return {
    id: key,
    requestNumber,
    idempotencyKey: key,
    photo,
    fileName,
    attempts: 0,
    nextAttemptAt: now,
    createdAt: now,
  }
}

/**
 * Одна попытка отправки записи и обновление очереди по исходу:
 * успех / окончательный отказ — запись удаляется; временный сбой — запись
 * остаётся с увеличенным счётчиком и сроком следующей попытки. Ключ
 * идемпотентности при этом НЕ меняется — повтор для сервера тот же запрос.
 */
export async function attemptSend(
  store: QueueStore,
  item: QueueItem,
  send: SendFn,
  now: () => number = Date.now,
): Promise<SendOutcome> {
  try {
    await send(item)
  } catch (err) {
    const verdict = classifyCompletionError(err)
    if (verdict.kind === 'final') {
      await store.remove(item.id)
      return { kind: 'final', reason: verdict.reason }
    }
    const attempts = item.attempts + 1
    await store.put({ ...item, attempts, nextAttemptAt: now() + retryDelay(attempts) })
    return { kind: 'queued', noShift: verdict.noShift }
  }
  await store.remove(item.id)
  return { kind: 'sent' }
}
