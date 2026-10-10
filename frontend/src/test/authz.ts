import catalog from '../authz/catalog.generated.json'

/**
 * Действия, которые сервер положил бы в профиль пользователю с этими ролями.
 * Вычисляется из той же копии каталога, что использует интерфейс, — тест
 * «менеджер видит кнопку» остаётся тестом про менеджера, а не про список строк.
 */
export function actionsFor(roles: readonly string[]): string[] {
  return Object.entries(catalog.actions)
    .filter(([, action]) => action.roles.some((role) => roles.includes(role)))
    .map(([key]) => key)
    .sort()
}
