import { describe, expect, it } from 'vitest'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'
import ts from 'typescript'
import ru from './locales/ru.json'
import uz from './locales/uz.json'

// A9-P2-31: гейт против RU-хардкода в UI. В перечисленных зонах любой строковый
// литерал / шаблон / JSX-текст с кириллицей — ошибка: текст должен идти через t()
// с ключами в ru.json и uz.json. Комментарии не проверяются (парсим AST).
// Новую зону i18n-чистоты добавлять в SCOPES.

const SRC = join(__dirname, '..')
const SCOPES = ['features/resource-accounting', 'twa', 'pages/LoginPage.tsx']

// Не UI-текст, а значения протокола: канон-статусы заявки приходят/уходят по API
// по-русски (см. utils/status_display.py в боте) — их сравнивают и шлют как есть.
const WIRE_VALUES = new Set([
  'Новая',
  'В работе',
  'Закуп',
  'Уточнение',
  'Выполнена',
  'Исполнено',
  'Возвращена',
  'Принято',
  'Отменена',
])
// Самоназвание языка в переключателе показывается на самом языке — не переводится.
const LANGUAGE_SELF_NAMES = new Set(['Русский', 'Ўзбекча'])

const CYRILLIC = /[А-Яа-яЁё]/

function walk(path: string, out: string[] = []): string[] {
  if (statSync(path).isFile()) {
    out.push(path)
    return out
  }
  for (const name of readdirSync(path)) {
    const p = join(path, name)
    if (statSync(p).isDirectory()) walk(p, out)
    else if (/\.(ts|tsx)$/.test(name) && !/\.test\.tsx?$/.test(name)) out.push(p)
  }
  return out
}

function isAllowed(text: string): boolean {
  const s = text.trim()
  return WIRE_VALUES.has(s) || LANGUAGE_SELF_NAMES.has(s)
}

function findCyrillicLiterals(fileName: string, source: string): string[] {
  const kind = fileName.endsWith('.tsx') ? ts.ScriptKind.TSX : ts.ScriptKind.TS
  const sf = ts.createSourceFile(fileName, source, ts.ScriptTarget.Latest, true, kind)
  const found: string[] = []
  const visit = (node: ts.Node) => {
    let text: string | undefined
    if (
      ts.isStringLiteral(node) ||
      ts.isNoSubstitutionTemplateLiteral(node) ||
      ts.isTemplateHead(node) ||
      ts.isTemplateMiddle(node) ||
      ts.isTemplateTail(node)
    ) {
      text = node.text
    } else if (ts.isJsxText(node)) {
      text = node.getText(sf)
    }
    if (text !== undefined && CYRILLIC.test(text) && !isAllowed(text)) {
      const { line } = sf.getLineAndCharacterOfPosition(node.getStart(sf))
      found.push(`${fileName}:${line + 1}: ${text.trim().slice(0, 60)}`)
    }
    ts.forEachChild(node, visit)
  }
  visit(sf)
  return found
}

describe('i18n: нет кириллицы в литералах UI (A9-P2-31)', () => {
  it('детектор ловит JSX-текст, атрибуты и шаблоны, но не комментарии и wire-значения', () => {
    const src = [
      '// комментарий',
      "const a = <b title=\"Заголовок\">Текст {x}</b>",
      'const b = `Итого ${n}`',
      "const c = status === 'В работе'",
      '/* ещё комментарий */',
    ].join('\n')
    const hits = findCyrillicLiterals('x.tsx', src)
    expect(hits).toHaveLength(3)
    expect(hits.join('\n')).toMatch(/Заголовок[\s\S]*Текст[\s\S]*Итого/)
  })

  it('в зонах SCOPES нет RU-хардкода', () => {
    const hits = SCOPES.flatMap((scope) =>
      walk(join(SRC, scope)).flatMap((file) =>
        findCyrillicLiterals(relative(SRC, file), readFileSync(file, 'utf8')),
      ),
    )
    expect(hits).toEqual([])
  })
})

// uz — латиница: кириллица в uz.json = непереведённая (скопированная из ru) строка.
// Исключение — подпись «переключить на русский», намеренно на русском.
const UZ_CYRILLIC_ALLOWED = new Set(['language.switchToRu'])

function leaves(obj: unknown, prefix = ''): [string, string][] {
  if (typeof obj === 'string') return [[prefix, obj]]
  if (!obj || typeof obj !== 'object') return []
  return Object.entries(obj as Record<string, unknown>).flatMap(([k, v]) =>
    leaves(v, prefix ? `${prefix}.${k}` : k),
  )
}

describe('i18n: uz-локаль переведена (A9-P2-31)', () => {
  it('в uz.json нет кириллицы (кроме явных исключений)', () => {
    const bad = leaves(uz)
      .filter(([key, value]) => CYRILLIC.test(value) && !UZ_CYRILLIC_ALLOWED.has(key))
      .map(([key]) => key)
    expect(bad).toEqual([])
  })

  it('resourceAccounting: одинаковый набор ключей в ru и uz', () => {
    const ruKeys = leaves(ru.resourceAccounting).map(([k]) => k).sort()
    const uzKeys = leaves(uz.resourceAccounting).map(([k]) => k).sort()
    expect(uzKeys).toEqual(ruKeys)
  })
})
