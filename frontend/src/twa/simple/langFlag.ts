/**
 * «Язык уже спросили» — экран выбора языка показывается один раз при первом
 * входе в простой режим. localStorage может бросать (приватный режим,
 * запрет хранилища) — тогда помним в памяти до конца сеанса.
 */
const KEY = 'twa.simple.langChosen'
let memoryFlag = false

export function isLangChosen(): boolean {
  if (memoryFlag) return true
  try {
    return window.localStorage.getItem(KEY) === '1'
  } catch {
    return false
  }
}

export function markLangChosen(): void {
  memoryFlag = true
  try {
    window.localStorage.setItem(KEY, '1')
  } catch {
    /* хранилище недоступно — хватит флага в памяти */
  }
}

/**
 * `next` приходит из URL: пускаем только внутренние пути простого режима,
 * без `..`-сегментов (иначе `/twa/s/../app` увёл бы из панели).
 */
export function safeNext(next: string | null): string {
  if (!next || !/^\/twa\/s(\/|$|\?)/.test(next)) return '/twa/s'
  const path = next.split('?')[0]
  if (path.split('/').some((seg) => seg === '..' || seg === '.')) return '/twa/s'
  if (path.startsWith('/twa/s/lang')) return '/twa/s'
  return next
}

/** Только для тестов. */
export function resetLangChosenForTests(): void {
  memoryFlag = false
  try {
    window.localStorage.removeItem(KEY)
  } catch {
    /* ignore */
  }
}
