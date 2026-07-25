/** Уменьшение фотографии перед загрузкой.
 *
 * Зачем: камера телефона отдаёт 8–15 МБ на кадр, а на пути наверх стоит
 * `client_max_body_size` edge-nginx — оригинал отбивается 413 ДО нашего API,
 * и загрузка фото к заявке просто не проходит. Плюс два следствия: такой файл
 * долго уходит по LTE, и он всё равно не попал бы в публичный отчёт «до/после»
 * (там лимит `PUBLIC_MEDIA_MAX_BYTES` = 8 МиБ).
 *
 * Политика: сжимаем только изображения и только если файл крупный; видео и
 * мелкие кадры отдаём как есть. Любая ошибка (нечитаемый файл, canvas
 * недоступен, экзотический формат) — возвращаем оригинал: задача утилиты
 * уменьшить типовой случай, а не стать новой точкой отказа.
 *
 * Побочная польза: canvas всегда отдаёт JPEG, поэтому HEIC с iPhone (который
 * media-service отклонил бы по `ALLOWED_FILE_TYPES`) уезжает уже как image/jpeg.
 */

/** Больше этого — сжимаем. Ниже порога возня с canvas не стоит потери качества. */
const COMPRESS_THRESHOLD_BYTES = 1_500_000
/** Максимальная сторона результата. 1600px хватает, чтобы разглядеть протечку
 *  или скол плитки, и даёт ~300–700 КБ на кадр. */
const MAX_DIMENSION = 1600
const JPEG_QUALITY = 0.82

function loadImage(dataUrl: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image()
    img.onload = () => resolve(img)
    img.onerror = () => reject(new Error('image decode failed'))
    img.src = dataUrl
  })
}

function readAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => {
      if (typeof reader.result === 'string') resolve(reader.result)
      else reject(new Error('unexpected FileReader result'))
    }
    reader.onerror = () => reject(new Error('file read failed'))
    reader.readAsDataURL(file)
  })
}

/** Вернуть уменьшенную копию изображения либо исходный файл, если сжатие не
 *  требуется или не удалось. Никогда не бросает. */
export async function downscaleImage(file: File): Promise<File> {
  if (!file.type.startsWith('image/')) return file
  if (file.size <= COMPRESS_THRESHOLD_BYTES) return file

  try {
    // FileReader + data: URL, а не URL.createObjectURL: тот же CSP-запрет на
    // blob: в /uk/*, из-за которого превью в PhotoUploader читаются через
    // FileReader (см. комментарий там).
    const img = await loadImage(await readAsDataUrl(file))
    const scale = Math.min(1, MAX_DIMENSION / Math.max(img.width, img.height))
    const width = Math.max(1, Math.round(img.width * scale))
    const height = Math.max(1, Math.round(img.height * scale))

    const canvas = document.createElement('canvas')
    canvas.width = width
    canvas.height = height
    const ctx = canvas.getContext('2d')
    if (!ctx) return file
    ctx.drawImage(img, 0, 0, width, height)

    const blob = await new Promise<Blob | null>((resolve) =>
      canvas.toBlob(resolve, 'image/jpeg', JPEG_QUALITY)
    )
    // Сжатие «в плюс» бывает на уже пережатых кадрах — тогда оригинал лучше.
    if (!blob || blob.size >= file.size) return file

    const name = file.name.replace(/\.[^.]+$/, '') + '.jpg'
    return new File([blob], name, { type: 'image/jpeg', lastModified: file.lastModified })
  } catch {
    return file
  }
}
