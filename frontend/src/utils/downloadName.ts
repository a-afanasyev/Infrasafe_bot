// A10-FE-04: имя скачиваемого документа жителя — из id и MIME ответа, а не из
// имени файла, которое задал сам житель при загрузке в Telegram (там
// расширение могло не совпадать с содержимым: «PDF под именем акт.html»).
const EXT_BY_MIME: Record<string, string> = {
  'application/pdf': 'pdf',
  'image/jpeg': 'jpg',
  'image/png': 'png',
  'image/gif': 'gif',
  'image/webp': 'webp',
}

export function downloadName(id: number, mime: string): string {
  const ext = EXT_BY_MIME[mime.split(';')[0].trim().toLowerCase()]
  return ext ? `document-${id}.${ext}` : `document-${id}`
}
