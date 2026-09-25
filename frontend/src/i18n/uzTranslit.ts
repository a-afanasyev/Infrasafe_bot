/**
 * Узбекская латиница → узбекская кириллица (локаль `uz_cyrl`).
 *
 * Порт `uk_management_bot/utils/uz_translit.py` (Фаза 3): фронтовая
 * локаль uz_cyrl = транслитерация всего uz.json + поверх ручные правки
 * `locales/uz_cyrl.json` (только там, где правило ошибается). Так новые
 * ключи uz сразу появляются и в кириллице, без смеси письменностей.
 *
 * Правила (официальная орфография 1995 г. в обратную сторону):
 * - o‘ / g‘ (апостроф ‘ ʻ ' ’ `) → ў / ғ; sh → ш, ch → ч, ng → нг;
 * - yo / yu / ya → ё / ю / я; ye → е в начале слова и после гласной, иначе ъе;
 *   одиночная y → й;
 * - e → э в начале слова и после гласной, иначе е;
 * - q → қ, h → ҳ, x → х, j → ж; ts перед «iy»/«io» → ц, прочие ts — т+с;
 * - тутуқ белгиси (' ’ ʼ) после гласной перед буквой → ъ; s'h → сҳ;
 *   апостроф после согласной — кавычка, остаётся.
 *
 * Не трогаются: плейсхолдеры i18next `{{…}}` и `{…}`, вложенные `$t(…)`,
 * HTML-теги и сущности, URL, @username, #теги, /команды, `код`,
 * snake_case-идентификаторы, аббревиатуры и бренды из ABBREVIATIONS.
 */

// Латинские аббревиатуры/бренды, которые в кириллице остаются латиницей.
const ABBREVIATIONS = [
  'TWA', 'ID', 'SMS', 'QR', 'PDF', 'API', 'URL', 'AI', 'OK', 'GPS', 'TV',
  'JPG', 'PNG', 'DOCX', 'DOC', 'MB', 'KB', 'HH:MM',
  'Telegram', 'InfraSafe', 'PROFK', 'Excel', 'CSV', 'XLSX', 'Wi-Fi', 'Email', 'E-mail', 'email',
]

const PROTECTED_RE = new RegExp(
  [
    String.raw`\{\{[^{}]*\}\}`, // плейсхолдеры i18next
    String.raw`\{[^{}]*\}`, // плейсхолдеры {name}
    String.raw`\$t\([^)]*\)`, // вложенные ключи i18next
    String.raw`<[^<>]+>`, // HTML-теги вместе с атрибутами
    String.raw`&(?:[A-Za-z]+|#\d+|#x[0-9A-Fa-f]+);`, // HTML-сущности
    String.raw`(?:https?://|www\.)[^\s<>"']+`, // URL
    String.raw`(?<![\w/])t\.me/[^\s<>"']+`,
    String.raw`(?<!\w)@\w+`, // @username
    String.raw`(?<!\w)#\w+`, // #теги
    String.raw`(?<![\w/])/[A-Za-z_]+`, // /команды
    String.raw`(?<![A-Za-z])` + '`[^`\\n]+`', // `код` (не o`/g`)
    String.raw`\b[A-Za-z]+(?:_[A-Za-z0-9]+)+(?:=[A-Za-z0-9]+)?\b`, // snake_case
    String.raw`(?<![A-Za-z])(?:` + ABBREVIATIONS.map((a) => a.replace(/[-:]/g, (c) => `\\${c}`)).join('|') + String.raw`)(?![A-Za-z])`,
  ].join('|'),
  'g',
)

const SINGLE: Record<string, string> = {
  a: 'а', b: 'б', c: 'ц', d: 'д', f: 'ф', g: 'г', h: 'ҳ', i: 'и', j: 'ж', k: 'к',
  l: 'л', m: 'м', n: 'н', o: 'о', p: 'п', q: 'қ', r: 'р', s: 'с', t: 'т', u: 'у',
  v: 'в', w: 'в', x: 'х', y: 'й', z: 'з',
}
const Y_VOWELS: Record<string, string> = { o: 'ё', u: 'ю', a: 'я' }
const VOWELS = new Set('aeiouаеёиоуэюяў')
// Апостроф-модификатор в o‘/g‘; ‘ и ʻ однозначны, остальные — только перед буквой.
const MODIFIERS_STRICT = new Set(['‘', 'ʻ'])
const MODIFIERS_LOOSE = new Set(["'", '’', '`'])
// Тутуқ белгиси (разделительный знак).
const TUTUQ = new Set(["'", '’', 'ʼ'])

function isLetter(ch: string | undefined): boolean {
  return !!ch && /\p{L}/u.test(ch)
}

function isUpper(ch: string): boolean {
  return ch !== ch.toLowerCase() && ch === ch.toUpperCase()
}

function withCase(src: string, cyr: string): string {
  return isUpper(src) ? cyr.toUpperCase() : cyr
}

function isModifier(s: string, i: number): boolean {
  if (i >= s.length) return false
  if (MODIFIERS_STRICT.has(s[i])) return true
  return MODIFIERS_LOOSE.has(s[i]) && isLetter(s[i + 1])
}

function wordStartOrAfterVowel(s: string, i: number): boolean {
  if (i === 0) return true
  const prev = s[i - 1]
  return !isLetter(prev) || VOWELS.has(prev.toLowerCase())
}

/** Одна единица транслитерации: [кириллица, сколько символов съедено]. */
function step(s: string, i: number): [string, number] {
  const ch = s[i]
  const low = ch.toLowerCase()
  const nxt = (s[i + 1] ?? '').toLowerCase()

  if ((low === 'o' || low === 'g') && isModifier(s, i + 1)) return [withCase(ch, low === 'o' ? 'ў' : 'ғ'), 2]
  if (low === 's' && nxt === 'h') return [withCase(ch, 'ш'), 2]
  if (low === 'c' && nxt === 'h') return [withCase(ch, 'ч'), 2]
  if (low === 't' && nxt === 's' && ['iy', 'io'].includes(s.slice(i + 2, i + 4).toLowerCase())) return [withCase(ch, 'ц'), 2]
  if (low === 'y' && nxt in Y_VOWELS && !(nxt === 'o' && isModifier(s, i + 2))) return [withCase(ch, Y_VOWELS[nxt]), 2]
  if (low === 'y' && nxt === 'e') {
    return wordStartOrAfterVowel(s, i) ? [withCase(ch, 'е'), 2] : ['ъ' + withCase(ch, 'е'), 2]
  }
  if (low === 'e') return [withCase(ch, wordStartOrAfterVowel(s, i) ? 'э' : 'е'), 1]
  if (TUTUQ.has(ch) && i > 0 && isLetter(s[i - 1]) && nxt && isLetter(s[i + 1])) {
    const prev = s[i - 1].toLowerCase()
    if (prev === 's' && nxt === 'h') return ['', 1] // is'hoq → исҳоқ
    if (VOWELS.has(prev) || ch === 'ʼ') return ['ъ', 1]
    return [ch, 1] // после согласной — кавычка ('Yakunlash'ni)
  }
  if (low in SINGLE) return [withCase(ch, SINGLE[low]), 1]
  return [ch, 1]
}

function translitPlain(s: string): string {
  let out = ''
  let i = 0
  while (i < s.length) {
    const [piece, used] = step(s, i)
    out += piece
    i += used
  }
  return out
}

/** Транслитерировать строку, не трогая защищённые фрагменты. */
export function toCyrillic(text: string): string {
  let out = ''
  let pos = 0
  for (const m of text.matchAll(PROTECTED_RE)) {
    const start = m.index ?? 0
    out += translitPlain(text.slice(pos, start)) + m[0]
    pos = start + m[0].length
  }
  return out + translitPlain(text.slice(pos))
}

/** Текст без защищённых фрагментов (для гейта «латиница не осталась»). */
export function stripProtected(text: string): string {
  return text.replace(PROTECTED_RE, ' ')
}

/** Новая структура: все строковые значения в кириллице, ключи как есть. */
export function transliterateTree<T>(data: T): T {
  if (Array.isArray(data)) return data.map((v) => transliterateTree(v)) as T
  if (data && typeof data === 'object') {
    return Object.fromEntries(
      Object.entries(data as Record<string, unknown>).map(([k, v]) => [k, transliterateTree(v)]),
    ) as T
  }
  if (typeof data === 'string') return toCyrillic(data) as T
  return data
}

type Tree = Record<string, unknown>

/** Новый объект: `base` с наложенными поверх `overrides` (рекурсивно). */
export function deepMerge(base: Tree, overrides: Tree): Tree {
  const merged: Tree = { ...base }
  for (const [key, value] of Object.entries(overrides)) {
    const cur = merged[key]
    merged[key] =
      value && typeof value === 'object' && !Array.isArray(value) && cur && typeof cur === 'object' && !Array.isArray(cur)
        ? deepMerge(cur as Tree, value as Tree)
        : value
  }
  return merged
}
