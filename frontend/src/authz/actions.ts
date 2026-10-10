/**
 * RBAC: действия вместо имён ролей (подробно — docs/tech/RBAC.md).
 *
 * Интерфейс показывает разделы и кнопки по списку `actions`, который сервер
 * кладёт в профиль (`GET /api/v2/profile`). Кто что может — решается на бэкенде
 * в `uk_management_bot/authz/catalog.py`; здесь только ключи. Тип `ActionKey`
 * выводится из сгенерированной копии каталога, поэтому опечатка в ключе —
 * ошибка компиляции, а не тихо пропавшая кнопка.
 *
 * Скрытая кнопка — подсказка, не защита: каждое действие сервер проверяет сам.
 */
import catalog from './catalog.generated.json'

export type ActionKey = keyof typeof catalog.actions

/** Есть ли действие в списке, пришедшем с сервера. */
export function hasAction(actions: readonly string[] | undefined, action: ActionKey): boolean {
  return actions?.includes(action) ?? false
}
