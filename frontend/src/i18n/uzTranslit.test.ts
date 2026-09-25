import { describe, expect, it } from 'vitest'
import uz from './locales/uz.json'
import { deepMerge, stripProtected, toCyrillic, transliterateTree } from './uzTranslit'

// Порт таблицы из uk_management_bot/tests/utils/test_uz_translit.py: фронтовая
// uz_cyrl строится из uz.json той же транслитерацией, что и в боте.

const WORDS: [string, string][] = [
  ['Tayyor', 'Тайёр'],
  ['Muammo', 'Муаммо'],
  ['Yuborish', 'Юбориш'],
  ['Qayta', 'Қайта'],
  ['Boshlash', 'Бошлаш'],
  ['Tugatish', 'Тугатиш'],
  ['Material yo‘q', 'Материал йўқ'],
  ['Kiritishmadi', 'Киритишмади'],
  ['Aloqa yo‘q', 'Алоқа йўқ'],
  ['Meniki', 'Меники'],
  ['Olish', 'Олиш'],
  ['ta’mir', 'таъмир'],
  ['e’lon', 'эълон'],
  ['yangi', 'янги'],
  ['bo‘lim', 'бўлим'],
  ['ko‘cha', 'кўча'],
  ['g‘isht', 'ғишт'],
  ["bo'lim", 'бўлим'],
  ['boʻlim', 'бўлим'],
  ['bo’lim', 'бўлим'],
  ['bo`lim', 'бўлим'],
  ['tog‘', 'тоғ'],
  ["O'zbekiston", 'Ўзбекистон'],
  ["Yo'q", 'Йўқ'],
  ["G'isht", 'Ғишт'],
  ['Shahar', 'Шаҳар'],
  ['SHAHAR', 'ШАҲАР'],
  ['choy', 'чой'],
  ['Chiqish', 'Чиқиш'],
  ['tong', 'тонг'],
  ['smena', 'смена'],
  ['yozish', 'ёзиш'],
  ['Yopish', 'Ёпиш'],
  ['yuk', 'юк'],
  ['ariza yaratish', 'ариза яратиш'],
  ['yetarli', 'етарли'],
  ['reyestr', 'реестр'],
  ['obyekt', 'объект'],
  ['kutish', 'кутиш'],
  ['Endi', 'Энди'],
  ['eslatma', 'эслатма'],
  ['poeziya', 'поэзия'],
  ['menejer', 'менежер'],
  ['emas', 'эмас'],
  ['qabul', 'қабул'],
  ['hovli', 'ҳовли'],
  ['xodim', 'ходим'],
  ['joy', 'жой'],
  ['xona', 'хона'],
  ["ma'lumot", 'маълумот'],
  ["Ma'lumot", 'Маълумот'],
  ["a'zo", 'аъзо'],
  ['maʼlumot', 'маълумот'],
  ["is'hoq", 'исҳоқ'],
  ['Operatsiya', 'Операция'],
  ['muvaffaqiyatsiz', 'муваффақиятсиз'],
  ['Ventilyatsiya', 'Вентиляция'],
  ['09:00 dan', '09:00 дан'],
  ['Ариза', 'Ариза'],
  ['Ish tugadi!', 'Иш тугади!'],
  ['Arizalarim', 'Аризаларим'],
  ['Uy egasi uyda yo‘q', 'Уй эгаси уйда йўқ'],
]

describe('toCyrillic: таблица слов (как в боте)', () => {
  it.each(WORDS)('%s → %s', (latin, cyrillic) => {
    expect(toCyrillic(latin)).toBe(cyrillic)
  })

  it('кавычка после согласной остаётся кавычкой', () => {
    expect(toCyrillic("'Yakunlash'ni bosing")).toBe("'Якунлаш'ни босинг")
  })
})

describe('toCyrillic: защищённые фрагменты', () => {
  it.each([
    ['№ {{number}} ariza surati yuborildi', '№ {{number}} ариза сурати юборилди'],
    ['Yuborilmagan surat: {{count}}', 'Юборилмаган сурат: {{count}}'],
    ['Salom, {name}!', 'Салом, {name}!'],
    ['$t(common.save) bosing', '$t(common.save) босинг'],
    ['<b>Manzil:</b> {{address}}', '<b>Манзил:</b> {{address}}'],
    ['Tom &amp; Jamshid', 'Том &amp; Жамшид'],
    ['Sayt: https://profk.uz/uk/twa yoki www.example.com', 'Сайт: https://profk.uz/uk/twa ёки www.example.com'],
    ['@support_bot ga yozing', '@support_bot га ёзинг'],
    ['TWA orqali ID va SMS, QR, PDF', 'TWA орқали ID ва SMS, QR, PDF'],
    ['Telegram orqali oching', 'Telegram орқали очинг'],
    ['✅ Tayyor 🔧', '✅ Тайёр 🔧'],
  ])('%s', (text, expected) => {
    expect(toCyrillic(text)).toBe(expected)
  })
})

describe('дерево и слияние', () => {
  it('transliterateTree не мутирует исходник', () => {
    const tree = { a: { done: 'Tayyor', n: 3, list: ['yangi'] } }
    expect(transliterateTree(tree)).toEqual({ a: { done: 'Тайёр', n: 3, list: ['янги'] } })
    expect(tree.a.done).toBe('Tayyor')
  })

  it('deepMerge не мутирует', () => {
    const base = { a: { x: '1', y: '2' }, b: '3' }
    expect(deepMerge(base, { a: { y: 'Y' } })).toEqual({ a: { x: '1', y: 'Y' }, b: '3' })
    expect(base.a.y).toBe('2')
  })
})

function flatten(tree: unknown, prefix = ''): [string, string][] {
  if (typeof tree === 'string') return [[prefix, tree]]
  if (!tree || typeof tree !== 'object') return []
  return Object.entries(tree).flatMap(([k, v]) => flatten(v, prefix ? `${prefix}.${k}` : k))
}

const placeholders = (s: string) => [...s.matchAll(/\{\{[^{}]*\}\}/g)].map((m) => m[0]).sort()

describe('гейты по всему uz.json', () => {
  const entries = flatten(uz)

  it('плейсхолдеры {{…}} переживают транслитерацию', () => {
    const broken = entries.filter(([, s]) => placeholders(s).join() !== placeholders(toCyrillic(s)).join())
    expect(broken.map(([k]) => k)).toEqual([])
  })

  it('в twa.* не остаётся латиницы вне защищённых фрагментов', () => {
    const leftovers = entries
      .filter(([k]) => k.startsWith('twa.'))
      .map(([k, s]) => [k, stripProtected(toCyrillic(s)).match(/[A-Za-z]+/g)] as const)
      .filter(([, latin]) => latin)
    expect(leftovers).toEqual([])
  })
})
