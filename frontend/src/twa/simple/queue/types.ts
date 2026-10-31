/**
 * Очередь отправки «Готово» простого режима.
 *
 * Фото и ключ идемпотентности сохраняются ДО первой попытки: на плохой сети
 * запрос может уйти, а ответ — потеряться. Повтор с тем же
 * `idempotencyKey` сервер принимает как тот же самый (200 без второй
 * загрузки), поэтому ключ генерируется ОДИН раз на попытку «Готово» и живёт
 * в записи очереди до её удаления.
 *
 * Та же очередь возит «Фото до» (`kind: 'before'`): та же съёмка и тот же
 * офлайн-повтор, но это НЕ завершение — состояние плитки и карточки от него
 * не зависит (см. `isDone`).
 */
/** Операция записи: «Готово» (фото «после» + закрытие) или «Фото до». */
export type QueueKind = 'done' | 'before'

export interface QueueItem {
  /** = idempotencyKey: одна запись очереди — одна попытка «Готово». */
  id: string
  /** Нет поля = «Готово» (записи IndexedDB до появления «Фото до»). */
  kind?: QueueKind
  /** Чей «Готово»: на общем телефоне очередь другого сотрудника не шлём. */
  userId: number
  requestNumber: string
  idempotencyKey: string
  photo: Blob
  fileName: string
  /** Адрес для плитки, если заявка уже ушла из списка «Мои». */
  label?: string
  /** Сколько неудачных отправок уже было. */
  attempts: number
  /** Когда пробовать снова (ms since epoch). */
  nextAttemptAt: number
  createdAt: number
  /** Сервер ответил «нет активной смены»: ждём начала смены, не таймер. */
  noShift?: boolean
  /** Окончательный отказ в фоне: запись не шлём, показываем исполнителю. */
  failed?: FinalReason
}

/** Хранилище очереди: IndexedDB в проде, память — в тестах и как фолбэк. */
export interface QueueStore {
  /** Все записи, старые первыми. */
  list(): Promise<QueueItem[]>
  put(item: QueueItem): Promise<void>
  remove(id: string): Promise<void>
  /** false — запись переживёт только текущий сеанс (IndexedDB недоступна). */
  readonly persistent: boolean
}

/** Окончательный отказ: повтор не поможет. */
export type FinalReason =
  | 'closed' // заявка уже закрыта / статус не позволяет
  | 'not_yours' // не назначена этому исполнителю / не найдена
  | 'bad_photo' // пустое / большое / не тот формат / отвергнуто медиа-сервисом
  | 'limit' // «Фото до»: у заявки уже максимум фото

/** Операция записи; нет поля — «Готово». */
export function queueKind(item: Pick<QueueItem, 'kind'>): QueueKind {
  return item.kind ?? 'done'
}

/** Запись — «Готово» (а не «Фото до»): только она определяет состояние заявки. */
export function isDone(item: Pick<QueueItem, 'kind'>): boolean {
  return queueKind(item) === 'done'
}

/** Исход одной попытки отправки. */
export type SendOutcome =
  | { kind: 'sent' }
  | { kind: 'queued'; noShift: boolean }
  | { kind: 'final'; reason: FinalReason }
