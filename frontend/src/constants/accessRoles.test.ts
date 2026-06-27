import { describe, it, expect } from 'vitest'
import { ACCESS_MODULE_ROLES, ACCESS_MANAGER_ROLES } from './roles'

// Контракт RBAC-гвардов модуля доступа (зеркало бэкенда registry.py):
//  - пост охраны (/dashboard/access) — ACCESS_MODULE_ROLES (оператор + менеджер
//    + system_admin);
//  - экраны менеджера (/dashboard/access/history, /database) — ACCESS_MANAGER_ROLES
//    (только manager/system_admin; оператор охраны базой не управляет).
describe('access RBAC role sets', () => {
  it('ACCESS_MODULE_ROLES = оператор охраны + менеджер + system_admin', () => {
    expect(ACCESS_MODULE_ROLES).toEqual(['manager', 'system_admin', 'security_operator'])
  })

  it('ACCESS_MANAGER_ROLES = только manager/system_admin (без оператора охраны)', () => {
    expect(ACCESS_MANAGER_ROLES).toEqual(['manager', 'system_admin'])
    expect(ACCESS_MANAGER_ROLES).not.toContain('security_operator')
  })

  it('никакая исполнительская/жительская роль не входит ни в один набор', () => {
    for (const role of ['executor', 'inspector', 'applicant']) {
      expect(ACCESS_MODULE_ROLES).not.toContain(role)
      expect(ACCESS_MANAGER_ROLES).not.toContain(role)
    }
  })
})
