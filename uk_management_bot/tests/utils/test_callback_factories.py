"""
Unit tests for callback_factories.py

Tests that every CallbackData subclass can pack() and unpack() a round-trip
correctly, exercising all defined fields with representative values.
No DB or network calls — these are pure dataclass/pydantic operations.
"""

from uk_management_bot.utils.callback_factories import (
    CategoryCB,
    UrgencyCB,
    PageCB,
    RequestActionCB,
    RoleSwitchCB,
    StatusFilterCB,
    RatingCB,
    ShiftActionCB,
    AddressCB,
    UserActionCB,
)


class TestCategoryCB:
    def test_pack_unpack(self):
        packed = CategoryCB(id="electric").pack()
        assert isinstance(packed, str)
        unpacked = CategoryCB.unpack(packed)
        assert unpacked.id == "electric"

    def test_prefix_in_packed(self):
        packed = CategoryCB(id="plumbing").pack()
        assert packed.startswith("cat")

    def test_different_ids_produce_different_packed(self):
        assert CategoryCB(id="a").pack() != CategoryCB(id="b").pack()


class TestUrgencyCB:
    def test_pack_unpack(self):
        packed = UrgencyCB(level="high").pack()
        unpacked = UrgencyCB.unpack(packed)
        assert unpacked.level == "high"

    def test_prefix_in_packed(self):
        packed = UrgencyCB(level="low").pack()
        assert packed.startswith("urg")


class TestPageCB:
    def test_pack_unpack_with_context(self):
        packed = PageCB(page=3, context="my_requests").pack()
        unpacked = PageCB.unpack(packed)
        assert unpacked.page == 3
        assert unpacked.context == "my_requests"

    def test_pack_unpack_default_context(self):
        packed = PageCB(page=1).pack()
        unpacked = PageCB.unpack(packed)
        assert unpacked.page == 1
        assert unpacked.context == ""

    def test_prefix_in_packed(self):
        packed = PageCB(page=0).pack()
        assert packed.startswith("pg")

    def test_page_zero(self):
        packed = PageCB(page=0, context="all_requests").pack()
        unpacked = PageCB.unpack(packed)
        assert unpacked.page == 0


class TestRequestActionCB:
    def test_pack_unpack(self):
        packed = RequestActionCB(action="view", id=42).pack()
        unpacked = RequestActionCB.unpack(packed)
        assert unpacked.action == "view"
        assert unpacked.id == 42

    def test_various_actions(self):
        for action in ("view", "edit", "assign", "status", "comment", "report"):
            packed = RequestActionCB(action=action, id=1).pack()
            unpacked = RequestActionCB.unpack(packed)
            assert unpacked.action == action

    def test_prefix_in_packed(self):
        packed = RequestActionCB(action="view", id=1).pack()
        assert packed.startswith("req")


class TestRoleSwitchCB:
    def test_pack_unpack_applicant(self):
        packed = RoleSwitchCB(target="applicant").pack()
        unpacked = RoleSwitchCB.unpack(packed)
        assert unpacked.target == "applicant"

    def test_pack_unpack_executor(self):
        packed = RoleSwitchCB(target="executor").pack()
        unpacked = RoleSwitchCB.unpack(packed)
        assert unpacked.target == "executor"

    def test_pack_unpack_manager(self):
        packed = RoleSwitchCB(target="manager").pack()
        unpacked = RoleSwitchCB.unpack(packed)
        assert unpacked.target == "manager"

    def test_prefix_in_packed(self):
        packed = RoleSwitchCB(target="applicant").pack()
        assert packed.startswith("role")


class TestStatusFilterCB:
    def test_pack_unpack(self):
        packed = StatusFilterCB(status="new").pack()
        unpacked = StatusFilterCB.unpack(packed)
        assert unpacked.status == "new"

    def test_prefix_in_packed(self):
        packed = StatusFilterCB(status="done").pack()
        assert packed.startswith("sf")


class TestRatingCB:
    def test_pack_unpack_with_request_id(self):
        packed = RatingCB(score=5, request_id=101).pack()
        unpacked = RatingCB.unpack(packed)
        assert unpacked.score == 5
        assert unpacked.request_id == 101

    def test_pack_unpack_default_request_id(self):
        packed = RatingCB(score=3).pack()
        unpacked = RatingCB.unpack(packed)
        assert unpacked.score == 3
        assert unpacked.request_id == 0

    def test_prefix_in_packed(self):
        packed = RatingCB(score=1).pack()
        assert packed.startswith("rate")


class TestShiftActionCB:
    def test_pack_unpack_with_id(self):
        packed = ShiftActionCB(action="start", id=7).pack()
        unpacked = ShiftActionCB.unpack(packed)
        assert unpacked.action == "start"
        assert unpacked.id == 7

    def test_pack_unpack_default_id(self):
        packed = ShiftActionCB(action="end").pack()
        unpacked = ShiftActionCB.unpack(packed)
        assert unpacked.action == "end"
        assert unpacked.id == 0

    def test_prefix_in_packed(self):
        packed = ShiftActionCB(action="details").pack()
        assert packed.startswith("shft")

    def test_various_actions(self):
        for action in ("details", "start", "end", "transfer"):
            packed = ShiftActionCB(action=action, id=1).pack()
            unpacked = ShiftActionCB.unpack(packed)
            assert unpacked.action == action


class TestAddressCB:
    def test_pack_unpack(self):
        packed = AddressCB(entity="apartment", action="select", id=55).pack()
        unpacked = AddressCB.unpack(packed)
        assert unpacked.entity == "apartment"
        assert unpacked.action == "select"
        assert unpacked.id == 55

    def test_entity_types(self):
        for entity in ("yard", "building", "apartment"):
            packed = AddressCB(entity=entity, action="edit", id=1).pack()
            unpacked = AddressCB.unpack(packed)
            assert unpacked.entity == entity

    def test_action_types(self):
        for action in ("select", "edit", "delete"):
            packed = AddressCB(entity="yard", action=action, id=1).pack()
            unpacked = AddressCB.unpack(packed)
            assert unpacked.action == action

    def test_prefix_in_packed(self):
        packed = AddressCB(entity="yard", action="select", id=1).pack()
        assert packed.startswith("addr")


class TestUserActionCB:
    def test_pack_unpack(self):
        packed = UserActionCB(action="approve", id=99).pack()
        unpacked = UserActionCB.unpack(packed)
        assert unpacked.action == "approve"
        assert unpacked.id == 99

    def test_various_actions(self):
        for action in ("approve", "block", "unblock", "delete", "role"):
            packed = UserActionCB(action=action, id=1).pack()
            unpacked = UserActionCB.unpack(packed)
            assert unpacked.action == action

    def test_prefix_in_packed(self):
        packed = UserActionCB(action="block", id=1).pack()
        assert packed.startswith("usr")
