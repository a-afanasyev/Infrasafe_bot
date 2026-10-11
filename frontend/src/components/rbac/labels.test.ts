import { afterAll, describe, expect, it } from 'vitest'
import i18n from '../../i18n'
import catalog from '../../authz/catalog.generated.json'
import ru from '../../i18n/locales/ru.json'
import uz from '../../i18n/locales/uz.json'
import { actionTitle, roleDescription, roleTitle } from './labels'

// Гейт переводов админки ролей: новое действие в каталоге без перевода —
// красный тест, а не русская строка посреди узбекского интерфейса.

const actions = catalog.actions as Record<string, { title: string }>
const CYRILLIC = /[А-Яа-яЁё]/

afterAll(async () => {
  await i18n.changeLanguage('ru')
})

describe('rbac labels', () => {
  it('every catalog action has ru (= server text) and uz titles', () => {
    for (const [key, action] of Object.entries(actions)) {
      expect(ru.rbac.actionTitles[key as keyof typeof ru.rbac.actionTitles], key).toBe(action.title)
      const uzTitle = uz.rbac.actionTitles[key as keyof typeof uz.rbac.actionTitles]
      expect(uzTitle, key).toBeTruthy()
      expect(CYRILLIC.test(uzTitle), `${key}: ${uzTitle}`).toBe(false)
    }
    expect(Object.keys(uz.rbac.actionTitles).sort()).toEqual(Object.keys(actions).sort())
  })

  it('system roles have uz titles and descriptions without cyrillic', () => {
    expect(Object.keys(uz.rbac.roleTitles).sort()).toEqual(Object.keys(ru.rbac.roleTitles).sort())
    for (const value of [...Object.values(uz.rbac.roleTitles), ...Object.values(uz.rbac.roleDescriptions)]) {
      expect(CYRILLIC.test(value), value).toBe(false)
    }
  })

  it('translates untouched system roles and keeps renamed and custom ones', async () => {
    await i18n.changeLanguage('uz')
    const t = i18n.t.bind(i18n)
    const manager = { key: 'manager', is_system: true, title: 'Менеджер', description: 'Управление заявками, персоналом, сменами' }
    expect(roleTitle(t, manager)).toBe('Menejer')
    expect(roleDescription(t, manager)).toBe('Arizalar, xodimlar va smenalarni boshqarish')
    expect(roleTitle(t, { ...manager, title: 'Старший менеджер' })).toBe('Старший менеджер')
    expect(roleTitle(t, { key: 'senior_exec', is_system: false, title: 'Старший исполнитель' })).toBe('Старший исполнитель')
    expect(actionTitle(t, { key: 'requests.stats', title: 'Статистика заявок' })).toBe('Arizalar statistikasi')
    expect(actionTitle(t, { key: 'brand.new', title: 'Новое действие' })).toBe('Новое действие')
  })
})
