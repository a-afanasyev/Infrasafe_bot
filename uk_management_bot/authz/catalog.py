"""Каталог действий — ЕДИНСТВЕННОЕ место, где решается «какая роль что может».

Принцип (RBAC A1, вариант O3, 2026-10-10):

* Точка входа (маршрут API, хендлер бота, workflow-команда) спрашивает не
  «есть ли у человека роль manager», а «разрешено ли ему действие
  `staff.manage`». Какие роли дают действие — написано здесь, одной строкой.
* Роли по-прежнему хранятся в `users.roles`; новых таблиц нет. Действие —
  это имя операции плюс набор ролей, которые её разрешают.
* `approved_only=True` — действие доступно только одобренному аккаунту
  (`users.status == "approved"`); прежний `require_approved_roles`.

Состав ролей у каждого действия на момент введения каталога в точности равен
прежнему гейту — это доказывает снимок прав (tests/rbac_baseline/*.json).
Изменить, кто что может, = поправить строку здесь; снимок покажет разницу,
и это изменение полномочий оформляется отдельно, с решением владельца.

Роль как ПРАВО и роль как ПРИЗНАК — разные вещи. «Назначить на смену можно
только исполнителя» — это свойство человека-объекта, а не право того, кто
назначает; такие проверки остаются сравнением роли и сюда не попадают.
"""
from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Iterable, Mapping

# Имена ролей. Канонический реестр — utils/constants.USER_ROLES; здесь — все
# роли, которые встречаются в правах, включая admin и капабилити meter-entry.
APPLICANT = "applicant"
EXECUTOR = "executor"
MANAGER = "manager"
INSPECTOR = "inspector"
ADMIN = "admin"
SYSTEM_ADMIN = "system_admin"
SECURITY_OPERATOR = "security_operator"
RESOURCE_METER_ENTRY = "resource_meter_entry"

KNOWN_ROLES: frozenset[str] = frozenset({
    APPLICANT, EXECUTOR, MANAGER, INSPECTOR, ADMIN, SYSTEM_ADMIN,
    SECURITY_OPERATOR, RESOURCE_METER_ENTRY,
})


@dataclass(frozen=True)
class Action:
    """Именованная операция и роли, которые её разрешают."""

    key: str
    roles: frozenset[str]
    title: str
    approved_only: bool = False

    def allows(self, roles: Iterable[str]) -> bool:
        return any(role in self.roles for role in roles)


def _action(key: str, roles: Iterable[str], title: str, *, approved_only: bool = False) -> Action:
    return Action(key=key, roles=frozenset(roles), title=title, approved_only=approved_only)


_M, _A, _E, _AP = MANAGER, ADMIN, EXECUTOR, APPLICANT
_I, _SA, _SO = INSPECTOR, SYSTEM_ADMIN, SECURITY_OPERATOR

_ACTIONS: tuple[Action, ...] = (
    # ---------------------------------------------------------- заявки
    _action("requests.create", {_AP}, "Подать заявку и получить адреса для неё", approved_only=True),
    _action("requests.create_inspection", {_I}, "Создать заявку обхода", approved_only=True),
    _action("requests.update", {_M, _AP, _E}, "Редактировать заявку (бизнес-проверки внутри)"),
    _action("requests.execute", {_E}, "Работать с заявками как исполнитель: пул, взять, выполнить, проблема"),
    _action("requests.own", {_AP}, "Действия автора со своей заявкой: отменить новую, оценить"),
    _action("requests.manage", {_M}, "Управлять заявками: смена категории, назначение дежурным, правка любой"),
    _action("requests.read_all", {_M}, "Видеть любую заявку: карточка и список без ограничения «свои/назначенные»"),
    _action("requests.internal_comments", {_M, _A}, "Видеть и писать внутренние комментарии заявки"),
    _action("requests.stats", {_M}, "Статистика заявок"),
    _action("dashboard.use", {_A, _M}, "Вход в основной веб-дашборд управления"),
    _action("dashboard.live", {_M}, "Живой поток событий дашборда (WebSocket)"),
    # Подсказка интерфейса: кнопка «прикрепить фото» в карточке. Сервер пускает
    # загрузку всем, у кого есть доступ к заявке (check_request_access).
    _action("requests.photos.attach", {_M, _SA}, "Дашборд: кнопка прикрепить фото к заявке"),
    _action("callcenter.use", {_M}, "Колл-центр: заявки по звонку"),
    _action("feedback.manage", {_M}, "Обратная связь жителей"),
    _action("group_intake.manage", {_M}, "Group Intake: группы и заявки из чатов"),
    _action("board.configure", {_M}, "Настройка табло"),
    _action("auto_manager.configure", {_M, _A}, "Настройка автоматического менеджера"),
    _action("work_reports.moderate", {_M}, "Модерация отчётов о работах", approved_only=True),
    # ---------------------------------------------------------- персонал и смены
    _action("staff.manage", {_M}, "Сотрудники: список, приглашения, активация, роли"),
    _action("shifts.manage", {_M}, "Смены: создание, шаблоны, чтение, передачи"),
    _action("shifts.own", {_E}, "Свои смены исполнителя: начать, закончить, передать"),
    # ---------------------------------------------------------- адреса и жители
    _action("addresses.manage", {_M}, "Справочник адресов: изменение и модерация"),
    _action("addresses.read", {_M, _I}, "Чтение дворов и домов", approved_only=True),
    _action("residents.manage", {_M}, "Жители: список, карточка, модерация, документы"),
    _action("apartments.moderate", {_M, _A}, "Одобрить или отклонить заявку жителя на привязку квартиры"),
    # ---------------------------------------------------------- прочие модули
    _action("payments.manage", {_M, _A}, "Контроль платежей", approved_only=True),
    _action("resources.launch", {_M, _SA, _A}, "Вход в учёт ресурсов"),
    _action("resources.admin", {_SA, _A}, "Учёт ресурсов: роль администратора у сервиса (иначе — оператор)"),
    _action("resources.meter_entry", {RESOURCE_METER_ENTRY}, "Ввод показаний счётчиков из Mini App",
            approved_only=True),
    _action("materials.manage", {_M, _SA}, "Склад материалов", approved_only=True),
    _action("elevators.lookup", {_AP, _E, _I, _M}, "Лифты дома при подаче заявки", approved_only=True),
    _action("elevators.read", {_E, _M}, "Лифты: реестр, карточка, статус, ТО", approved_only=True),
    _action("elevators.manage", {_M}, "Лифты: изменение реестра и календаря", approved_only=True),
    # ---------------------------------------------------------- охрана (access-api)
    _action("access.events.read", {_SO, _M, _SA}, "Охрана: события и пропуска", approved_only=True),
    _action("access.photos.read", {_SO, _M, _SA}, "Охрана: фото проездов", approved_only=True),
    _action("access.operator", {_SO, _M, _SA}, "Охрана: пульт оператора", approved_only=True),
    _action("access.presence.read", {_M, _SA, _SO}, "Охрана: кто на парковке", approved_only=True),
    _action("access.live", {_SO, _M, _SA}, "Охрана: живой поток событий", approved_only=True),
    _action("access.registry.manage", {_M, _SA}, "Охрана: база авто и заявок, история", approved_only=True),
    _action("access.management", {_M, _SA}, "Охрана: управление доступом", approved_only=True),
    _action("access.zones.manage", {_M, _SA}, "Охрана: зоны и шлагбаумы", approved_only=True),
    _action("access.metrics.read", {_M, _SA}, "Охрана: метрики модуля", approved_only=True),
    _action("access.equipment.manage", {_SA}, "Охрана: оборудование", approved_only=True),
    _action("access.diagnostics", {_SA}, "Охрана: диагностика", approved_only=True),
    _action("access.resident.self", {_AP}, "Охрана: свои авто и пропуска жителя", approved_only=True),
    # ---------------------------------------------------------- бот
    # Бот исторически пускает admin наравне с manager и не смотрит на статус —
    # отсюда отдельные действия, а не переиспользование API-шных.
    _action("admin_panel.use", {_A, _M}, "Бот: админ-панель и менеджерские экраны"),
    _action("management.decide", {_M}, "Решения именно менеджера (без admin): назначение, приёмка, workflow"),
    _action("execution.work", {_E}, "Бот: экраны и команды исполнителя"),
    _action("execution.view", {_E, _M, _A}, "Бот: просмотр исполнительских разделов"),
    _action("shift_transfers.approve", {_M}, "Бот: одобрение передачи смены"),
    _action("shift_transfers.respond", {_E, _M}, "Бот: ответ на передачу смены"),
    _action("shifts.history", {_A, _M, _E}, "Бот: история и просмотр смен"),
    _action("elevators.technician", {_E, _M, _A}, "Бот: раздел лифтов"),
)

ACTIONS: Mapping[str, Action] = MappingProxyType({a.key: a for a in _ACTIONS})


def get_action(key: str) -> Action:
    """Действие по ключу. Неизвестный ключ — ошибка сразу, а не тихий отказ."""
    try:
        return ACTIONS[key]
    except KeyError:
        raise KeyError(f"Неизвестное действие RBAC: {key!r} — добавьте его в authz/catalog.py") from None


def actions_for_roles(roles: Iterable[str]) -> frozenset[str]:
    """Все действия, которые дают перечисленные роли (без учёта статуса)."""
    role_set = set(roles)
    return frozenset(a.key for a in _ACTIONS if a.roles & role_set)


def _validate() -> None:
    keys = [a.key for a in _ACTIONS]
    duplicates = {k for k in keys if keys.count(k) > 1}
    if duplicates:
        raise RuntimeError(f"Дубли действий в каталоге: {sorted(duplicates)}")
    for action in _ACTIONS:
        unknown = action.roles - KNOWN_ROLES
        if not action.roles or unknown:
            raise RuntimeError(f"Действие {action.key}: пустой или неизвестный набор ролей {sorted(unknown)}")


_validate()
