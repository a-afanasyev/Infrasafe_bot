/**
 * AUD8-FE-05: localStorage может бросать (Safari private mode на setItem,
 * sandboxed/restricted iframe на любой доступ). Читатели получают null и
 * работают с дефолтами; запись — best effort.
 */
export function readStorage(key: string): string | null {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}

export function writeStorage(key: string, value: string): void {
  try {
    localStorage.setItem(key, value)
  } catch {
    /* хранилище недоступно — настройка не переживёт перезагрузку, это допустимо */
  }
}
