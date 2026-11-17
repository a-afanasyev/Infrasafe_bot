"""От кого заявка: житель, сотрудник или система."""
from types import SimpleNamespace

import pytest

from uk_management_bot.api.requests.author_kind import author_kind


def _req(**over):
    fields = dict(source="twa", reported_by_user_id=None, acceptance_mode="resident", user_id=7)
    return SimpleNamespace(**{**fields, **over})


@pytest.mark.parametrize("req, owner_roles, expected", [
    (_req(), {}, "resident"),                                              # житель сам, приложение
    (_req(source="bot"), {}, "resident"),
    (_req(source="group"), {}, "resident"),                                # житель в группе дома
    (_req(source="inspector"), {}, "staff"),                               # обходчик
    (_req(source="group", reported_by_user_id=3, acceptance_mode="manager"), {}, "staff"),  # staff-группа
    (_req(source="bot", acceptance_mode="manager"), {}, "staff"),          # ремонт лифта от мастера
    (_req(source="call_center"), {7: ["applicant"]}, "resident"),          # диспетчер записал звонок жителя
    (_req(source="call_center"), {7: ["manager"]}, "staff"),               # диспетчер завёл от себя
    (_req(source="call_center"), {7: ["manager", "applicant"]}, "resident"),
    (_req(source="call_center"), {}, "resident"),                          # роли не загружены — не выдумываем
    (_req(source="infrasafe"), {}, "system"),                              # авария от мониторинга
    (_req(source=None), {}, "resident"),
])
def test_author_kind(req, owner_roles, expected):
    assert author_kind(req, owner_roles) == expected
