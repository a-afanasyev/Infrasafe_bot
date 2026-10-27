import { describe, it, expect } from 'vitest'
import catalog from './catalog.generated.json'
import { hasAction, type ActionKey } from './actions'

/**
 * Спецификация интерфейса «как есть» (RBAC A1): кто видит раздел или кнопку.
 *
 * Гейты фронта перешли с массивов ролей на действия. Состав ролей действия
 * задаёт бэкенд (authz/catalog.py), а здесь он ЯВНО записан для каждого
 * действия, которое использует интерфейс, — так перенос доказуемо не изменил
 * видимость. Единственное сознательное отличие от прежних массивов:
 * «Учёт ресурсов» теперь видит и admin — ровно как давно пускает API
 * (resources.launch); прежде интерфейс прятал раздел, который сервер открывал.
 */
const UI_ACTIONS: Record<string, readonly string[]> = {
  'dashboard.use': ['admin', 'engineer', 'manager'], // основной /dashboard
  'access.events.read': ['manager', 'security_operator', 'system_admin'], // пост охраны
  'access.registry.manage': ['manager', 'system_admin'], // история, база, оборудование (маршрут)
  'access.equipment.manage': ['system_admin'], // камеры/шлагбаумы/контроллеры внутри
  'materials.manage': ['manager', 'system_admin'], // склад + блок материалов в карточке
  'elevators.read': ['executor', 'manager'], // реестр лифтов
  'elevators.manage': ['manager'], // правки лифтов, конфиг
  'resources.launch': ['admin', 'manager', 'system_admin'], // учёт ресурсов (см. шапку)
  'payments.manage': ['admin', 'manager'], // контроль платежей
  'residents.manage': ['manager'], // жители
  'group_intake.manage': ['manager'], // группы
  'requests.manage': ['manager'], // правка карточки заявки
  'management.decide': ['manager'], // переназначение исполнителя
  'shifts.manage': ['manager'], // кнопки менеджера в сменах и передачах
  'requests.photos.attach': ['engineer', 'manager', 'system_admin'], // кнопка «прикрепить фото»
}

describe('RBAC: действия интерфейса', () => {
  it.each(Object.entries(UI_ACTIONS))('%s — состав ролей', (action, roles) => {
    const entry = catalog.actions[action as ActionKey]
    expect(entry, `действия ${action} нет в каталоге`).toBeDefined()
    expect(entry.roles).toEqual([...roles].sort())
  })

  it('hasAction: отказ по умолчанию', () => {
    expect(hasAction(undefined, 'dashboard.use')).toBe(false)
    expect(hasAction([], 'dashboard.use')).toBe(false)
    expect(hasAction(['dashboard.use'], 'dashboard.use')).toBe(true)
    expect(hasAction(['staff.manage'], 'dashboard.use')).toBe(false)
  })
})
