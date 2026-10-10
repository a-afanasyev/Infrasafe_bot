"""RBAC: действия вместо имён ролей.

Как пользоваться (подробно — docs/tech/RBAC.md):

* API:  `user: User = Depends(require_action("staff.manage"))`
  (`uk_management_bot.api.dependencies.require_action`);
* бот:  `@require_action("admin_panel.use")` вместо `@require_role([...])`
  (`uk_management_bot.middlewares.auth.require_action`), root-фильтр роутера —
  `ActionGate("...")`;
* в коде: `can(user, "requests.manage")` / `can(roles, "admin_panel.use")`.

Кто что может — только в `authz/catalog.py`.
"""
from uk_management_bot.authz.catalog import ACTIONS, Action, actions_for_roles, get_action
from uk_management_bot.authz.policy import can, has_action_roles, roles_of

__all__ = [
    "ACTIONS", "Action", "actions_for_roles", "can", "get_action",
    "has_action_roles", "roles_of",
]
