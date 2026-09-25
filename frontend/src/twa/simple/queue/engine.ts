import { classifyCompletionError, newIdempotencyKey, retryDelay } from './policy'
import type { QueueItem, QueueStore, SendOutcome } from './types'

/** Сетевой вызов «Готово» (подменяется в тестах). */
export type SendFn = (item: QueueItem) => Promise<unknown>

interface NewItem {
  userId: number
  requestNumber: string
  photo: Blob
  fileName: string
  label?: string
}

/** Новая запись очереди — одна попытка «Готово» со своим ключом идемпотентности. */
export function createQueueItem(
  { userId, requestNumber, photo, fileName, label }: NewItem,
  now: number,
  key: string = newIdempotencyKey(),
): QueueItem {
  return {
    id: key,
    userId,
    requestNumber,
    idempotencyKey: key,
    photo,
    fileName,
    ...(label ? { label } : {}),
    attempts: 0,
    nextAttemptAt: now,
    createdAt: now,
  }
}

/**
 * Одна попытка отправки записи и обновление очереди по исходу:
 * успех — запись удаляется; временный сбой — остаётся с увеличенным счётчиком
 * и сроком следующей попытки (при «нет смены» — с флагом noShift, её пошлёт
 * начало смены); окончательный отказ — запись помечается `failed` и больше
 * не шлётся: удалить её решает вызывающий (экран уже показал исход) или
 * исполнитель (увидел плитку). Ключ идемпотентности НЕ меняется.
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
      await store.put({ ...item, failed: verdict.reason, noShift: false })
      return { kind: 'final', reason: verdict.reason }
    }
    const attempts = item.attempts + 1
    await store.put({
      ...item,
      attempts,
      noShift: verdict.noShift,
      nextAttemptAt: now() + retryDelay(attempts),
    })
    return { kind: 'queued', noShift: verdict.noShift }
  }
  await store.remove(item.id)
  return { kind: 'sent' }
}
