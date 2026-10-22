/** Высота растра логотипа: в шапке .xlsx он 48 px, запас — под Retina/печать. */
const LOGO_HEIGHT = 160

/**
 * Логотип страницы (SVG бренда) → PNG в base64 без `data:`-префикса.
 * Excel не умеет SVG, поэтому растрируем в браузере; сервер кладёт PNG в шапку.
 * null — не получилось (нет canvas, картинка не загрузилась): отчёт уйдёт без логотипа.
 */
export async function logoToPngBase64(src: string): Promise<string | null> {
  try {
    const img = new Image()
    img.decoding = 'async'
    img.src = src
    await img.decode()
    const ratio = img.naturalWidth && img.naturalHeight ? img.naturalWidth / img.naturalHeight : 1
    const canvas = document.createElement('canvas')
    canvas.height = LOGO_HEIGHT
    canvas.width = Math.round(LOGO_HEIGHT * ratio)
    const ctx = canvas.getContext('2d')
    if (!ctx) return null
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height)
    return canvas.toDataURL('image/png').split(',')[1] ?? null
  } catch {
    return null
  }
}
