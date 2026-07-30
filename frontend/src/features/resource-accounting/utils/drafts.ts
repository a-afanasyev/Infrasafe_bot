/** Черновики ведомости ввода показаний (AUD6-P2-10).
 *
 * После успешного bulk-save нельзя делать `setDrafts({})`: элементы запроса
 * захвачены в момент клика, а пока он летел (полевой ввод по мобильной сети —
 * окно реальное), контролёр мог ввести новые значения — обнуление молча их
 * теряло. Удаляем только те meter_id, что ушли в ЭТОТ запрос, и только если
 * черновик с тех пор не менялся.
 */

export interface DraftRow {
  value: string
  comment: string
}

export interface SubmittedItem {
  meter_id: string
  value: string
  comment?: string | null
}

export function pruneSubmittedDrafts(
  prev: Record<string, DraftRow>,
  submitted: SubmittedItem[],
): Record<string, DraftRow> {
  const next = { ...prev }
  for (const item of submitted) {
    const draft = next[item.meter_id]
    if (!draft) continue
    const unchanged =
      draft.value.trim() === item.value && (draft.comment || null) === (item.comment ?? null)
    if (unchanged) delete next[item.meter_id]
  }
  return next
}
