"""П5 / AUD3-14 — матрица канона доступа к заявке.

Это тест ПРАВИЛ, а не реализации: он фиксирует решение владельца от 2026-07-27
(семантика API; сосед только на «Исполнено»; групповое назначение — да, но при
активной смене) до того, как пять расходящихся копий сводятся к одной.

Проверяется `access_reason`, а не `has_request_access`: булев ответ скрыл бы
регрессию вида «менеджер проходит, но не как менеджер, а потому что он же и
владелец заявки».
"""
import pytest

from uk_management_bot.utils.request_access import (
    ACCESS_RULES,
    MONOTONE_BOOLEAN_FACTS,
    RESIDENT_ACCESS_STATUS,
    RequestAccessFacts,
    access_reason,
    has_request_access,
)

OWNER_ID = 1
OTHER_ID = 2


def facts(**over) -> RequestAccessFacts:
    """Посторонний пользователь без единого основания на доступ."""
    base = dict(
        roles=frozenset({"applicant"}),
        user_id=OTHER_ID,
        request_owner_id=OWNER_ID,
        request_executor_id=None,
        request_status="Новая",
        request_apartment_id=None,
        has_individual_assignment=False,
        group_specializations=frozenset(),
        user_specializations=frozenset(),
        has_active_shift=False,
        is_approved_resident=False,
    )
    base.update(over)
    return RequestAccessFacts(**base)


class TestBaseline:
    def test_stranger_has_no_access(self):
        assert access_reason(facts()) is None
        assert has_request_access(facts()) is False

    def test_reason_values_are_declared_rules(self):
        """Любая возвращаемая причина обязана быть в ACCESS_RULES."""
        cases = [
            facts(roles=frozenset({"manager"})),
            facts(user_id=OWNER_ID),
            facts(roles=frozenset({"executor"}), request_executor_id=OTHER_ID),
        ]
        for f in cases:
            assert access_reason(f) in ACCESS_RULES


class TestManager:
    def test_manager_sees_a_foreign_request(self):
        """Дефект бота: ветки менеджера не было вовсе.

        Достижимо в два нажатия — менеджер открывает отчёт (там гейт его
        пускает), жмёт «Назад к заявке» и получает «нет доступа к заявке».
        """
        assert access_reason(facts(roles=frozenset({"manager"}))) == "manager"

    def test_manager_wins_before_ownership(self):
        f = facts(roles=frozenset({"manager"}), user_id=OWNER_ID)
        assert access_reason(f) == "manager"


class TestOwner:
    def test_owner_always(self):
        assert access_reason(facts(user_id=OWNER_ID)) == "owner"

    def test_owner_regardless_of_status(self):
        f = facts(user_id=OWNER_ID, request_status="Отменена")
        assert access_reason(f) == "owner"


class TestExecutor:
    def test_direct_executor_id(self):
        f = facts(roles=frozenset({"executor"}), request_executor_id=OTHER_ID)
        assert access_reason(f) == "executor_direct"

    def test_individual_assignment(self):
        f = facts(roles=frozenset({"executor"}), has_individual_assignment=True)
        assert access_reason(f) == "executor_individual_assignment"

    def test_individual_assignment_needs_no_shift(self):
        """Условие про смену — только для группового назначения."""
        f = facts(
            roles=frozenset({"executor"}),
            has_individual_assignment=True,
            has_active_shift=False,
        )
        assert access_reason(f) == "executor_individual_assignment"

    def test_multi_role_executor_keeps_access(self):
        """Главный дефект AUD3-14.

        Бот выбирал ветку по `active_role` через `if/else`, поэтому исполнитель
        с ролями ['applicant','executor'], временно переключённый в applicant,
        проваливался в ветку заявителя и терял доступ к своему назначению.
        Канон смотрит на СОСТАВ ролей, а не на активную.
        """
        f = facts(
            roles=frozenset({"applicant", "executor"}),
            has_individual_assignment=True,
        )
        assert access_reason(f) == "executor_individual_assignment"

    def test_executor_without_the_role_gets_nothing(self):
        """Контроль: без роли executor назначение само по себе не пускает."""
        f = facts(roles=frozenset({"applicant"}), has_individual_assignment=True)
        assert access_reason(f) is None


class TestGroupAssignment:
    """Решение владельца: доступ есть, но требует активной смены."""

    def test_group_match_on_shift(self):
        f = facts(
            roles=frozenset({"executor"}),
            group_specializations=frozenset({"plumber"}),
            user_specializations=frozenset({"plumber", "electric"}),
            has_active_shift=True,
        )
        assert access_reason(f) == "executor_group_assignment_on_shift"

    def test_group_match_off_shift_is_denied(self):
        f = facts(
            roles=frozenset({"executor"}),
            group_specializations=frozenset({"plumber"}),
            user_specializations=frozenset({"plumber"}),
            has_active_shift=False,
        )
        assert access_reason(f) is None

    def test_shift_without_matching_specialization_is_denied(self):
        f = facts(
            roles=frozenset({"executor"}),
            group_specializations=frozenset({"plumber"}),
            user_specializations=frozenset({"electric"}),
            has_active_shift=True,
        )
        assert access_reason(f) is None

    def test_any_overlapping_specialization_is_enough(self):
        f = facts(
            roles=frozenset({"executor"}),
            group_specializations=frozenset({"plumber", "hvac"}),
            user_specializations=frozenset({"electric", "hvac"}),
            has_active_shift=True,
        )
        assert access_reason(f) == "executor_group_assignment_on_shift"


class TestMonotonicity:
    """На этом свойстве стоит оптимизация сборщиков фактов.

    Сборщик сначала спрашивает ядро по дешёвым фактам, подставляя недостающие
    как False, и лезет в БД только если доступа не дали. Это корректно ровно
    до тех пор, пока ни один факт не способен доступ ОТОБРАТЬ. Появись в каноне
    отрицательное правило (например «заблокированному не показывать»), тест
    покраснеет — и оптимизацию придётся снимать вместе с ним.
    """

    @pytest.mark.parametrize("field", MONOTONE_BOOLEAN_FACTS)
    @pytest.mark.parametrize(
        "ctx",
        [
            {},
            {"roles": frozenset({"executor"})},
            {"roles": frozenset({"executor"}), "has_active_shift": True},
            {"roles": frozenset({"executor"}),
             "group_specializations": frozenset({"plumber"}),
             "user_specializations": frozenset({"plumber"})},
            {"request_apartment_id": 10, "request_status": RESIDENT_ACCESS_STATUS},
            {"request_apartment_id": 10, "request_status": "Новая"},
            {"user_id": OWNER_ID},
            {"roles": frozenset({"manager"})},
        ],
        ids=lambda c: "-".join(sorted(c)) or "bare",
    )
    def test_flipping_a_fact_on_never_removes_access(self, field, ctx):
        off = facts(**{**ctx, field: False})
        on = facts(**{**ctx, field: True})
        if has_request_access(off):
            assert has_request_access(on), (
                f"{field}=True отобрал доступ — предикат перестал быть монотонным, "
                "оптимизация дешёвого прохода в services/request_access.py стала неверной"
            )

    def test_all_boolean_fact_fields_are_declared(self):
        """Новое булево поле фактов обязано попасть в MONOTONE_BOOLEAN_FACTS.

        Иначе оно останется непроверенным на монотонность, а оптимизация
        продолжит молча на неё опираться.
        """
        booleans = {
            name
            for name, typ in RequestAccessFacts.__annotations__.items()
            if typ is bool or typ == "bool"
        }
        assert booleans == set(MONOTONE_BOOLEAN_FACTS)


class TestApartmentResident:
    """Ужесточение относительно бота: сосед только на «Исполнено»."""

    def test_resident_on_accepted_status(self):
        f = facts(
            request_apartment_id=10,
            request_status=RESIDENT_ACCESS_STATUS,
            is_approved_resident=True,
        )
        assert access_reason(f) == "apartment_resident_on_accepted"

    @pytest.mark.parametrize("status", ["Новая", "В работе", "Выполнена", "Принято", "Отменена"])
    def test_resident_denied_on_other_statuses(self, status):
        f = facts(
            request_apartment_id=10,
            request_status=status,
            is_approved_resident=True,
        )
        assert access_reason(f) is None

    def test_unapproved_resident_denied_even_on_accepted(self):
        f = facts(
            request_apartment_id=10,
            request_status=RESIDENT_ACCESS_STATUS,
            is_approved_resident=False,
        )
        assert access_reason(f) is None

    def test_request_without_apartment_denies_resident(self):
        f = facts(
            request_apartment_id=None,
            request_status=RESIDENT_ACCESS_STATUS,
            is_approved_resident=True,
        )
        assert access_reason(f) is None
