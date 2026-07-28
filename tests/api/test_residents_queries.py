"""Модуль «Жители» — read-only слой (PR-1).

Покрывает три эндпоинта домена `api/residents/`:
  * GET /api/v2/residents          — список с фильтрами и пагинацией;
  * GET /api/v2/residents/stats    — счётчики по ДВУМ пересекающимся осям;
  * GET /api/v2/residents/{id}     — карточка жителя.

Ключевые инварианты, зафиксированные тестами:
  * scope — только «жители» (роль applicant), soft-deleted не видны нигде;
  * адресные фильтры считают принадлежностью привязки approved+pending
    (rejected — НЕ принадлежность), та же семантика, что у `apartments_count`;
  * сортировка стабильна (created_at DESC, id DESC) — иначе пагинация теряет
    и дублирует строки на равных created_at;
  * карточка отдаёт `roles` (фронту нужно прятать блокировку у мультиролевых)
    и НЕ отдаёт `file_id` документов (это токен доступа к файлу в Telegram);
  * RBAC — только manager.
"""
import datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.api.dependencies import get_current_user
from uk_management_bot.api.main import app
from uk_management_bot.database.models.apartment import Apartment
from uk_management_bot.database.models.building import Building
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.user_apartment import UserApartment
from uk_management_bot.database.models.user_verification import (
    DocumentType,
    UserDocument,
    UserVerification,
    VerificationStatus,
)
from uk_management_bot.database.models.yard import Yard

pytestmark = pytest.mark.asyncio

BASE = "/api/v2/residents"


# ═══════════════════════ Helpers ═══════════════════════


async def _resident(
    db: AsyncSession,
    tg: int,
    *,
    roles: str = '["applicant"]',
    status: str = "approved",
    verification: str = "pending",
    first_name: str = "Иван",
    last_name: str = "Иванов",
    phone: str | None = None,
    deleted_at: datetime.datetime | None = None,
    created_at: datetime.datetime | None = None,
) -> User:
    u = User(
        telegram_id=tg,
        username=f"u{tg}",
        first_name=first_name,
        last_name=last_name,
        roles=roles,
        active_role="applicant",
        status=status,
        verification_status=verification,
        phone=phone,
        deleted_at=deleted_at,
    )
    if created_at is not None:
        u.created_at = created_at
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


async def _address(db: AsyncSession, *, yard_name="Двор-1", address="ул. Тестовая 1", number="10"):
    """→ (yard, building, apartment) — минимальная адресная цепочка."""
    yard = Yard(name=yard_name)
    db.add(yard)
    await db.flush()
    bld = Building(address=address, yard_id=yard.id)
    db.add(bld)
    await db.flush()
    apt = Apartment(building_id=bld.id, apartment_number=number)
    db.add(apt)
    await db.commit()
    await db.refresh(yard)
    await db.refresh(bld)
    await db.refresh(apt)
    return yard, bld, apt


async def _bind(db: AsyncSession, user: User, apt: Apartment, *, status="approved",
                is_primary=False, is_owner=False) -> UserApartment:
    ua = UserApartment(
        user_id=user.id, apartment_id=apt.id, status=status,
        is_primary=is_primary, is_owner=is_owner,
    )
    db.add(ua)
    await db.commit()
    await db.refresh(ua)
    return ua


# ═══════════════════════ Список: scope ═══════════════════════


class TestListScope:

    async def test_only_applicants(self, client: AsyncClient, db_session: AsyncSession):
        await _resident(db_session, 3001)
        await _resident(db_session, 3002, roles='["applicant", "executor"]')  # мультироль — житель тоже
        await _resident(db_session, 3003, roles='["manager"]')                # чистый стафф — нет
        await _resident(db_session, 3004, roles='["executor"]')               # чистый стафф — нет

        r = await client.get(BASE)
        assert r.status_code == 200, r.text
        data = r.json()
        assert {i["telegram_id"] for i in data["items"]} == {3001, 3002}
        assert data["total"] == 2

    async def test_soft_deleted_excluded(self, client: AsyncClient, db_session: AsyncSession):
        await _resident(db_session, 3011)
        await _resident(db_session, 3012, deleted_at=datetime.datetime(2026, 7, 1))

        data = (await client.get(BASE)).json()
        assert {i["telegram_id"] for i in data["items"]} == {3011}
        assert data["total"] == 1

    async def test_roles_null_is_not_a_resident(self, client: AsyncClient, db_session: AsyncSession):
        """`roles=NULL` (недорегистрированный) не должен просачиваться в список."""
        u = User(telegram_id=3021, roles=None, status="pending")
        db_session.add(u)
        await db_session.commit()

        data = (await client.get(BASE)).json()
        assert data["total"] == 0


# ═══════════════════════ Список: фильтры ═══════════════════════


class TestListFilters:

    async def test_status_filter(self, client: AsyncClient, db_session: AsyncSession):
        await _resident(db_session, 3101, status="pending")
        await _resident(db_session, 3102, status="approved")
        await _resident(db_session, 3103, status="blocked")

        data = (await client.get(f"{BASE}?status=pending")).json()
        assert {i["telegram_id"] for i in data["items"]} == {3101}

    async def test_verification_status_filter(self, client: AsyncClient, db_session: AsyncSession):
        await _resident(db_session, 3111, verification="requested")
        await _resident(db_session, 3112, verification="verified")

        data = (await client.get(f"{BASE}?verification_status=requested")).json()
        assert {i["telegram_id"] for i in data["items"]} == {3111}

    async def test_search_by_name_and_phone(self, client: AsyncClient, db_session: AsyncSession):
        await _resident(db_session, 3121, first_name="Пётр", last_name="Сидоров", phone="+998901112233")
        await _resident(db_session, 3122, first_name="Мария", last_name="Ким", phone="+998907778899")

        by_last = (await client.get(f"{BASE}?q=Сидор")).json()
        assert {i["telegram_id"] for i in by_last["items"]} == {3121}

        by_first = (await client.get(f"{BASE}?q=Мари")).json()
        assert {i["telegram_id"] for i in by_first["items"]} == {3122}

        by_phone = (await client.get(f"{BASE}?q=7778899")).json()
        assert {i["telegram_id"] for i in by_phone["items"]} == {3122}

    async def test_search_is_case_insensitive(self, client: AsyncClient, db_session: AsyncSession):
        """ILIKE, а не LIKE.

        Проверяется на латинице СОЗНАТЕЛЬНО: сьют гоняется на sqlite, чей
        LOWER() не сворачивает регистр вне ASCII, поэтому «сидор» → «Сидоров»
        здесь не сматчится, хотя на боевом PostgreSQL сматчится. Регистр
        кириллицы проверяется вручную в прод-сценарии.
        """
        await _resident(db_session, 3123, first_name="Alex", last_name="Karimov")

        data = (await client.get(f"{BASE}?q=karim")).json()
        assert {i["telegram_id"] for i in data["items"]} == {3123}

    async def test_search_escapes_like_wildcards(self, client: AsyncClient, db_session: AsyncSession):
        """`%` в запросе — литерал, а не «совпадает со всем»."""
        await _resident(db_session, 3131, first_name="Анна", last_name="Петрова")

        data = (await client.get(f"{BASE}?q=%25")).json()  # %25 == '%'
        assert data["total"] == 0

    async def test_address_filters_cascade(self, client: AsyncClient, db_session: AsyncSession):
        yard_a, bld_a, apt_a = await _address(db_session, yard_name="Двор-А", address="А-1", number="1")
        yard_b, bld_b, apt_b = await _address(db_session, yard_name="Двор-Б", address="Б-1", number="2")

        u_a = await _resident(db_session, 3141)
        u_b = await _resident(db_session, 3142)
        await _bind(db_session, u_a, apt_a)
        await _bind(db_session, u_b, apt_b)

        by_yard = (await client.get(f"{BASE}?yard_id={yard_a.id}")).json()
        assert {i["telegram_id"] for i in by_yard["items"]} == {3141}

        by_bld = (await client.get(f"{BASE}?building_id={bld_b.id}")).json()
        assert {i["telegram_id"] for i in by_bld["items"]} == {3142}

        by_apt = (await client.get(f"{BASE}?apartment_id={apt_a.id}")).json()
        assert {i["telegram_id"] for i in by_apt["items"]} == {3141}

    async def test_address_filter_counts_pending_but_not_rejected(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        yard, bld, apt = await _address(db_session)
        u_pending = await _resident(db_session, 3151)
        u_rejected = await _resident(db_session, 3152)
        await _bind(db_session, u_pending, apt, status="pending")
        await _bind(db_session, u_rejected, apt, status="rejected")

        data = (await client.get(f"{BASE}?yard_id={yard.id}")).json()
        assert {i["telegram_id"] for i in data["items"]} == {3151}

    async def test_apartments_count_matches_address_filter_semantics(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        _, _, apt1 = await _address(db_session, yard_name="Y1", address="A1", number="1")
        _, _, apt2 = await _address(db_session, yard_name="Y2", address="A2", number="2")
        _, _, apt3 = await _address(db_session, yard_name="Y3", address="A3", number="3")
        u = await _resident(db_session, 3161)
        await _bind(db_session, u, apt1, status="approved")
        await _bind(db_session, u, apt2, status="pending")
        await _bind(db_session, u, apt3, status="rejected")

        data = (await client.get(BASE)).json()
        assert data["items"][0]["apartments_count"] == 2


# ═══════════════════════ Список: пагинация и сортировка ═══════════════════════


class TestListPagination:

    async def test_pagination_envelope(self, client: AsyncClient, db_session: AsyncSession):
        for tg in range(3201, 3206):
            await _resident(db_session, tg)

        data = (await client.get(f"{BASE}?limit=2&offset=0")).json()
        assert data["total"] == 5
        assert data["limit"] == 2
        assert data["offset"] == 0
        assert len(data["items"]) == 2

    async def test_limit_is_capped(self, client: AsyncClient, db_session: AsyncSession):
        await _resident(db_session, 3211)
        r = await client.get(f"{BASE}?limit=500")
        assert r.status_code == 422  # выше потолка 100 — валидация, не молчаливый клип

    async def test_sort_is_stable_across_pages(self, client: AsyncClient, db_session: AsyncSession):
        """Одинаковый created_at ⇒ порядок доопределяется id DESC, страницы не пересекаются."""
        same = datetime.datetime(2026, 7, 20, 12, 0, 0)
        for tg in range(3221, 3227):
            await _resident(db_session, tg, created_at=same)

        page1 = (await client.get(f"{BASE}?limit=3&offset=0")).json()["items"]
        page2 = (await client.get(f"{BASE}?limit=3&offset=3")).json()["items"]
        ids1 = [i["id"] for i in page1]
        ids2 = [i["id"] for i in page2]

        assert ids1 == sorted(ids1, reverse=True)
        assert not set(ids1) & set(ids2)
        assert len(set(ids1) | set(ids2)) == 6


# ═══════════════════════ Stats ═══════════════════════


class TestStats:

    async def test_two_independent_axes(self, client: AsyncClient, db_session: AsyncSession):
        await _resident(db_session, 3301, status="pending", verification="pending")
        await _resident(db_session, 3302, status="approved", verification="requested")
        await _resident(db_session, 3303, status="approved", verification="verified")
        await _resident(db_session, 3304, status="blocked", verification="rejected")
        await _resident(db_session, 3305, roles='["manager"]')                 # не житель
        await _resident(db_session, 3306, deleted_at=datetime.datetime(2026, 7, 1))

        s = (await client.get(f"{BASE}/stats")).json()
        assert s["total"] == 4
        assert s["pending"] == 1
        assert s["approved"] == 2
        assert s["blocked"] == 1
        assert s["verification_requested"] == 1
        assert s["verified"] == 1

    async def test_stats_route_not_shadowed_by_detail(self, client: AsyncClient):
        """`/stats` объявлен ДО `/{resident_id}` — иначе получили бы 422 на int."""
        r = await client.get(f"{BASE}/stats")
        assert r.status_code == 200


# ═══════════════════════ Карточка ═══════════════════════


class TestDetail:

    async def test_full_payload(self, client: AsyncClient, db_session: AsyncSession):
        yard, bld, apt = await _address(db_session, yard_name="Двор-Д", address="Д-1", number="42")
        u = await _resident(db_session, 3401, roles='["applicant", "executor"]', phone="+998900000000")
        ua = await _bind(db_session, u, apt, is_primary=True, is_owner=True)

        doc = UserDocument(
            user_id=u.id, document_type=DocumentType.PASSPORT,
            file_id="AgACSECRET", file_name="passport.jpg", file_size=1024,
        )
        db_session.add(doc)
        ver = UserVerification(
            user_id=u.id, status=VerificationStatus.REQUESTED,
            requested_info={"documents": ["passport"]},
        )
        db_session.add(ver)
        await db_session.commit()

        r = await client.get(f"{BASE}/{u.id}")
        assert r.status_code == 200, r.text
        data = r.json()

        assert data["id"] == u.id
        assert data["telegram_id"] == 3401
        assert data["phone"] == "+998900000000"
        assert data["roles"] == ["applicant", "executor"]

        assert len(data["apartments"]) == 1
        a = data["apartments"][0]
        assert a["id"] == ua.id
        assert a["apartment_id"] == apt.id
        assert a["apartment_number"] == "42"
        assert a["building_id"] == bld.id
        assert a["building_address"] == "Д-1"
        assert a["yard_id"] == yard.id
        assert a["yard_name"] == "Двор-Д"
        assert a["status"] == "approved"
        assert a["is_primary"] is True
        assert a["is_owner"] is True

        assert len(data["documents"]) == 1
        d = data["documents"][0]
        assert d["document_type"] == "passport"
        assert d["file_name"] == "passport.jpg"
        assert "file_id" not in d          # токен доступа к файлу наружу не отдаём

        assert data["latest_verification"]["status"] == "requested"

    async def test_all_binding_statuses_visible(self, client: AsyncClient, db_session: AsyncSession):
        """В карточке — ВСЕ привязки, включая rejected (история решений менеджера)."""
        _, _, apt1 = await _address(db_session, yard_name="Y1", address="A1", number="1")
        _, _, apt2 = await _address(db_session, yard_name="Y2", address="A2", number="2")
        u = await _resident(db_session, 3411)
        await _bind(db_session, u, apt1, status="approved")
        await _bind(db_session, u, apt2, status="rejected")

        data = (await client.get(f"{BASE}/{u.id}")).json()
        assert {a["status"] for a in data["apartments"]} == {"approved", "rejected"}

    async def test_latest_verification_is_the_newest_record(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Unique(user_id) на user_verifications нет — «последняя» = created_at DESC, id DESC."""
        u = await _resident(db_session, 3421)
        same = datetime.datetime(2026, 7, 10, 9, 0, 0)
        old = UserVerification(user_id=u.id, status=VerificationStatus.PENDING, created_at=same)
        new = UserVerification(user_id=u.id, status=VerificationStatus.APPROVED, created_at=same)
        db_session.add_all([old, new])
        await db_session.commit()
        await db_session.refresh(new)

        data = (await client.get(f"{BASE}/{u.id}")).json()
        assert data["latest_verification"]["id"] == new.id
        assert data["latest_verification"]["status"] == "approved"

    async def test_no_verification_records(self, client: AsyncClient, db_session: AsyncSession):
        u = await _resident(db_session, 3431)
        data = (await client.get(f"{BASE}/{u.id}")).json()
        assert data["latest_verification"] is None
        assert data["documents"] == []
        assert data["apartments"] == []

    async def test_404_for_staff(self, client: AsyncClient, db_session: AsyncSession):
        u = await _resident(db_session, 3441, roles='["manager"]')
        assert (await client.get(f"{BASE}/{u.id}")).status_code == 404

    async def test_404_for_soft_deleted(self, client: AsyncClient, db_session: AsyncSession):
        u = await _resident(db_session, 3451, deleted_at=datetime.datetime(2026, 7, 1))
        assert (await client.get(f"{BASE}/{u.id}")).status_code == 404

    async def test_404_for_missing(self, client: AsyncClient):
        assert (await client.get(f"{BASE}/987654")).status_code == 404


# ═══════════════════════ RBAC ═══════════════════════


class TestRBAC:

    @pytest.mark.parametrize("path", ["", "/stats", "/1"])
    async def test_non_manager_forbidden(self, client: AsyncClient, db_session: AsyncSession, path):
        applicant = await _resident(db_session, 3501)
        prev = app.dependency_overrides[get_current_user]
        app.dependency_overrides[get_current_user] = lambda: applicant
        try:
            assert (await client.get(f"{BASE}{path}")).status_code == 403
        finally:
            app.dependency_overrides[get_current_user] = prev
