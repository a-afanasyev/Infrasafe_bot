import type { TFunction } from 'i18next'
import i18n from '../../i18n'
import type { RbacAction, RbacRole } from '../../hooks/useRbac'

// Названия ролей и прав на языке интерфейса. Сервер отдаёт их по-русски:
// права — из каталога, роли — из таблицы rbac_roles (их можно переименовать
// в админке). Переводы лежат в локалях (rbac.actionTitles / roleTitles /
// roleDescriptions); русские значения там — ровно серверные тексты, это
// сверяют тесты.

const ru = i18n.getFixedT('ru')

type RoleLike = Pick<RbacRole, 'key' | 'is_system'> & { title: string; description?: string | null }

/** Системная роль, которую не переименовывали, — переводится; иначе показываем как назвали. */
export function roleTitle(t: TFunction, role: RoleLike): string {
  const key = `rbac.roleTitles.${role.key}`
  return role.is_system && i18n.exists(key, { lng: 'ru' }) && role.title === ru(key) ? t(key) : role.title
}

export function roleDescription(t: TFunction, role: RoleLike): string | null {
  const key = `rbac.roleDescriptions.${role.key}`
  if (!role.description) return null
  return role.is_system && i18n.exists(key, { lng: 'ru' }) && role.description === ru(key) ? t(key) : role.description
}

/** Право — перевод по ключу; для нового действия без перевода — текст с сервера. */
export function actionTitle(t: TFunction, action: Pick<RbacAction, 'key' | 'title'>): string {
  return t(`rbac.actionTitles.${action.key}`, { defaultValue: action.title })
}
