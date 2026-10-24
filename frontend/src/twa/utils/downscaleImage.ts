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
 * Форматы кроме JPEG/PNG (HEIC, WebP, AVIF…) перекодируются в JPEG ВСЕГДА,
 * независимо от размера: сервер принимает фото «после» только как JPEG/PNG
 * (`executor_completion.COMPLETION_PHOTO_TYPES`), и небольшой HEIC раньше
 * проходил мимо порога и получал 415 (profk, 2026-10-24).
 */

/** Больше этого — сжимаем. Ниже порога возня с canvas не стоит потери качества. */
const COMPRESS_THRESHOLD_BYTES = 1_500_000
/** Максимальная сторона результата. 1600px хватает, чтобы разглядеть протечку
 *  или скол плитки, и даёт ~300–700 КБ на кадр. */
const MAX_DIMENSION = 1600
const JPEG_QUALITY = 0.82
/** Что сервер принимает как есть. Остальное — только через перекодировку. */
const SERVER_PHOTO_TYPES = new Set(['image/jpeg', 'image/png'])
/** Android WebView отдаёт HEIC/WebP с пустым `type` — узнаём по расширению. */
const IMAGE_EXTENSION = /\.(heic|heif|webp|avif)$/i

function isImage(file: File): boolean {
  return file.type.startsWith('image/') || (file.type === '' && IMAGE_EXTENSION.test(file.name))
}

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

export interface DownscaleOptions {
  /** Максимальная сторона результата (по умолчанию MAX_DIMENSION). */
  maxDimension?: number
  /** Файлы не больше этого размера отдаются как есть (по умолчанию COMPRESS_THRESHOLD_BYTES). */
  thresholdBytes?: number
}

interface Decoded {
  source: CanvasImageSource
  width: number
  height: number
  release: () => void
}

/**
 * Декодирование: createImageBitmap, где он есть (без data: URL-копии всего
 * файла в памяти — на дешёвом Android это разница между «сжалось» и
 * «вкладку убило»), иначе прежний путь FileReader → Image.
 */
async function decode(file: File): Promise<Decoded> {
  if (typeof createImageBitmap === 'function') {
    try {
      const bitmap = await createImageBitmap(file)
      return { source: bitmap, width: bitmap.width, height: bitmap.height, release: () => bitmap.close?.() }
    } catch {
      /* формат не поддержан createImageBitmap — пробуем через <img> */
    }
  }
  // FileReader + data: URL, а не URL.createObjectURL: тот же CSP-запрет на
  // blob: в /uk/*, из-за которого превью в PhotoUploader читаются через
  // FileReader (см. комментарий там).
  const img = await loadImage(await readAsDataUrl(file))
  return { source: img, width: img.width, height: img.height, release: () => undefined }
}

/** Вернуть уменьшенную (или перекодированную в JPEG) копию изображения либо
 *  исходный файл, если это не требуется или не удалось. Никогда не бросает. */
export async function downscaleImage(file: File, options: DownscaleOptions = {}): Promise<File> {
  const maxDimension = options.maxDimension ?? MAX_DIMENSION
  const thresholdBytes = options.thresholdBytes ?? COMPRESS_THRESHOLD_BYTES
  if (!isImage(file)) return file
  const mustConvert = !SERVER_PHOTO_TYPES.has(file.type)
  if (!mustConvert && file.size <= thresholdBytes) return file

  try {
    const img = await decode(file)
    const scale = Math.min(1, maxDimension / Math.max(img.width, img.height))
    const width = Math.max(1, Math.round(img.width * scale))
    const height = Math.max(1, Math.round(img.height * scale))

    const canvas = document.createElement('canvas')
    canvas.width = width
    canvas.height = height
    const ctx = canvas.getContext('2d')
    if (!ctx) {
      img.release()
      return file
    }
    ctx.drawImage(img.source, 0, 0, width, height)
    img.release()

    const blob = await new Promise<Blob | null>((resolve) =>
      canvas.toBlob(resolve, 'image/jpeg', JPEG_QUALITY)
    )
    if (!blob) return file
    // Сжатие «в плюс» бывает на уже пережатых кадрах — тогда оригинал лучше.
    // Но не для HEIC/WebP: оригинал сервер не примет, JPEG крупнее — всё равно лучше.
    if (!mustConvert && blob.size >= file.size) return file

    const name = file.name.replace(/\.[^.]+$/, '') + '.jpg'
    return new File([blob], name, { type: 'image/jpeg', lastModified: file.lastModified })
  } catch {
    return file
  }
}
