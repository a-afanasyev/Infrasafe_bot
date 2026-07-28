"""Верификация жителя и выдача документов (PR-5).

Ключевые вещи, ради которых эти тесты существуют:

* **Одна транзакция вместо трёх.** Legacy-сервис коммитит статус, авто-одобрение
  квартир и удаление документов ТРЕМЯ независимыми commit'ами, продолжая после
  сбоя каждого. Здесь сбой на любом шаге обязан не оставить следов.
* **Parity побочных эффектов** с бот-путём: pending-квартиры одобряются, записи
  документов удаляются, инвариант основной квартиры (Т6) при этом держится.
* **Деградация Media Service** (Т4): недоступный внешний сервис не имеет права
  превратить успешную верификацию в 500, но и молчать о себе не должен.
* **Прокси документов** (Т7): `file_id` наружу не уходит, тип определяется по
  содержимому, PDF отдаётся вложением, превышение лимита — 413 ДО отправки
  тела, недоступный Telegram — 502, исчезнувший файл — 404.
"""
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.database.models.apartment import Apartment
from uk_management_bot.database.models.building import Building
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.user_apartment import UserApartment
from uk_management_bot.database.models.user_verification import (
    DocumentType, UserDocument, UserVerification, VerificationStatus,
)
from uk_management_bot.database.models.yard import Yard

pytestmark = pytest.mark.asyncio

BASE = "/api/v2/residents"


@pytest_asyncio.fixture(autouse=True)
def _mute_telegram():
    with patch("uk_management_bot.api.residents.notify._send", new=AsyncMock()):
        yield


@pytest_asyncio.fixture
async def address(db_session: AsyncSession):
    yard = Yard(name="Двор-В")
    db_session.add(yard)
    await db_session.flush()
    bld = Building(address="В-1", yard_id=yard.id)
    db_session.add(bld)
    await db_session.flush()
    apts = [Apartment(building_id=bld.id, apartment_number=str(n)) for n in (1, 2)]
    db_session.add_all(apts)
    await db_session.commit()
    for a in apts:
        await db_session.refresh(a)
    return apts


async def _resident(db, tg, *, verification="pending") -> User:
    u = User(telegram_id=tg, first_name="В", last_name=str(tg), roles='["applicant"]',
             active_role="applicant", status="approved", language="ru",
             verification_status=verification)
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


async def _doc(db, user_id, *, file_id="AgACSECRET", dtype=DocumentType.PASSPORT):
    d = UserDocument(user_id=user_id, document_type=dtype, file_id=file_id,
                     file_name="passport.jpg", file_size=1024)
    db.add(d)
    await db.commit()
    await db.refresh(d)
    return d


# ═══════════════════════ Запрос документов ═══════════════════════


class TestRequestDocuments:

    async def test_sets_requested_on_both_axes(self, client: AsyncClient, db_session: AsyncSession):
        resident = await _resident(db_session, 6001)
        resident_id = resident.id  # после expire_all атрибуты потребуют sync-IO
        r = await client.post(f"{BASE}/{resident_id}/verification/request-documents",
                              json={"document_types": ["passport"], "comment": "нужен паспорт"})
        assert r.status_code == 200, r.text
        assert r.json()["verification_status"] == "requested"

        db_session.expire_all()
        record = (await db_session.execute(
            select(UserVerification).where(UserVerification.user_id == resident_id)
        )).scalar_one()
        assert record.status == VerificationStatus.REQUESTED
        assert record.requested_info["document_types"] == ["passport"]

    async def test_reuses_open_record_instead_of_piling_up(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Т5: открытая запись обновляется, а не плодится — иначе «последняя»
        разъедется с тем, что показывает карточка."""
        resident = await _resident(db_session, 6002)
        resident_id = resident.id
        for types in (["passport"], ["utility_bill"]):
            await client.post(f"{BASE}/{resident_id}/verification/request-documents",
                              json={"document_types": types, "comment": "документы"})

        db_session.expire_all()
        records = (await db_session.execute(
            select(UserVerification).where(UserVerification.user_id == resident_id)
        )).scalars().all()
        assert len(records) == 1
        assert records[0].requested_info["document_types"] == ["utility_bill"]

    async def test_reopening_after_verified_creates_a_new_record(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Закрытая запись не переоткрывается — история решений сохраняется."""
        resident = await _resident(db_session, 6003)
        resident_id = resident.id
        closed = UserVerification(user_id=resident_id, status=VerificationStatus.APPROVED)
        db_session.add(closed)
        await db_session.commit()

        await client.post(f"{BASE}/{resident_id}/verification/request-documents",
                          json={"document_types": ["passport"], "comment": "ещё раз"})

        db_session.expire_all()
        records = (await db_session.execute(
            select(UserVerification).where(UserVerification.user_id == resident_id)
        )).scalars().all()
        assert len(records) == 2

    async def test_allowed_from_verified(self, client: AsyncClient, db_session: AsyncSession):
        """Осознанное переоткрытие: паспорт меняют, документы могут понадобиться снова."""
        resident = await _resident(db_session, 6004, verification="verified")
        r = await client.post(f"{BASE}/{resident.id}/verification/request-documents",
                              json={"document_types": ["passport"], "comment": "смена паспорта"})
        assert r.status_code == 200

    @pytest.mark.parametrize("body", [
        {"document_types": [], "comment": "текст"},
        {"document_types": ["passport"], "comment": "ab"},
        {"document_types": ["driver_license"], "comment": "текст"},
        {"document_types": ["passport"], "comment": "текст", "extra": 1},
    ])
    async def test_bad_bodies_rejected(self, client: AsyncClient, db_session: AsyncSession, body):
        resident = await _resident(db_session, 6005)
        r = await client.post(f"{BASE}/{resident.id}/verification/request-documents", json=body)
        assert r.status_code == 422, r.text

    async def test_duplicates_collapse(self, client: AsyncClient, db_session: AsyncSession):
        resident = await _resident(db_session, 6006)
        resident_id = resident.id
        await client.post(f"{BASE}/{resident_id}/verification/request-documents",
                          json={"document_types": ["passport", "passport"], "comment": "документы"})
        db_session.expire_all()
        record = (await db_session.execute(
            select(UserVerification).where(UserVerification.user_id == resident_id)
        )).scalar_one()
        assert record.requested_info["document_types"] == ["passport"]


# ═══════════════════════ Подтверждение личности ═══════════════════════


class TestApproveVerification:

    async def test_full_parity_of_side_effects(
        self, client: AsyncClient, db_session: AsyncSession, address
    ):
        resident = await _resident(db_session, 6101, verification="requested")
        resident_id = resident.id
        db_session.add_all([
            UserApartment(user_id=resident_id, apartment_id=address[0].id, status="pending"),
            UserApartment(user_id=resident_id, apartment_id=address[1].id, status="pending"),
            UserVerification(user_id=resident_id, status=VerificationStatus.REQUESTED),
        ])
        await db_session.commit()
        await _doc(db_session, resident_id)

        r = await client.post(f"{BASE}/{resident_id}/verification/approve", json={})
        assert r.status_code == 200, r.text
        assert r.json()["verification_status"] == "verified"
        assert r.json()["deleted_documents"] == 1

        db_session.expire_all()
        bindings = (await db_session.execute(
            select(UserApartment).where(UserApartment.user_id == resident_id)
        )).scalars().all()
        assert {b.status for b in bindings} == {"approved"}
        # Т6 держится и на массовом авто-одобрении.
        assert len([b for b in bindings if b.is_primary]) == 1

        docs = (await db_session.execute(
            select(UserDocument).where(UserDocument.user_id == resident_id)
        )).scalars().all()
        assert docs == []

        record = (await db_session.execute(
            select(UserVerification).where(UserVerification.user_id == resident_id)
        )).scalar_one()
        assert record.status == VerificationStatus.APPROVED

    async def test_existing_primary_survives_mass_approve(
        self, client: AsyncClient, db_session: AsyncSession, address
    ):
        resident = await _resident(db_session, 6102, verification="requested")
        resident_id = resident.id
        primary_apartment_id = address[0].id  # address[] тоже expire'нется
        db_session.add_all([
            UserApartment(user_id=resident_id, apartment_id=address[0].id,
                          status="approved", is_primary=True),
            UserApartment(user_id=resident_id, apartment_id=address[1].id, status="pending"),
        ])
        await db_session.commit()

        await client.post(f"{BASE}/{resident_id}/verification/approve", json={})

        db_session.expire_all()
        bindings = (await db_session.execute(
            select(UserApartment).where(UserApartment.user_id == resident_id)
        )).scalars().all()
        primary = [b for b in bindings if b.is_primary]
        assert len(primary) == 1
        assert primary[0].apartment_id == primary_apartment_id

    async def test_repeat_conflicts(self, client: AsyncClient, db_session: AsyncSession):
        resident = await _resident(db_session, 6103, verification="verified")
        r = await client.post(f"{BASE}/{resident.id}/verification/approve", json={})
        assert r.status_code == 409

    async def test_rejected_cannot_be_approved_without_reopening(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        resident = await _resident(db_session, 6104, verification="rejected")
        assert (await client.post(
            f"{BASE}/{resident.id}/verification/approve", json={})).status_code == 409

    async def test_everything_rolls_back_on_failure(
        self, client: AsyncClient, db_session: AsyncSession, address
    ):
        """Три независимых commit'а у legacy давали половинчатое состояние.
        Здесь сбой обязан не оставить следов вообще."""
        resident = await _resident(db_session, 6105, verification="requested")
        resident_id = resident.id
        db_session.add(UserApartment(user_id=resident_id, apartment_id=address[0].id,
                                     status="pending"))
        await db_session.commit()
        await _doc(db_session, resident_id)

        with patch("uk_management_bot.services.residents.core._audit",
                   side_effect=RuntimeError("audit down")):
            with pytest.raises(RuntimeError):
                await client.post(f"{BASE}/{resident_id}/verification/approve", json={})

        db_session.expire_all()
        fresh = (await db_session.execute(
            select(User).where(User.id == resident_id))).scalar_one()
        assert fresh.verification_status == "requested"
        bindings = (await db_session.execute(
            select(UserApartment).where(UserApartment.user_id == resident_id)
        )).scalars().all()
        assert bindings[0].status == "pending"
        docs = (await db_session.execute(
            select(UserDocument).where(UserDocument.user_id == resident_id)
        )).scalars().all()
        assert len(docs) == 1

    async def test_media_service_failure_does_not_fail_the_request(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Т4: запись в БД уже удалена, внешний сервис её не воскресит и не
        имеет права уронить запрос."""
        resident = await _resident(db_session, 6106, verification="requested")
        resident_id = resident.id
        await _doc(db_session, resident_id)

        with patch(
            "uk_management_bot.utils.media_helpers.delete_user_documents_from_media_service",
            side_effect=RuntimeError("media down"),
        ):
            r = await client.post(f"{BASE}/{resident_id}/verification/approve", json={})
        assert r.status_code == 200

        db_session.expire_all()
        assert (await db_session.execute(
            select(UserDocument).where(UserDocument.user_id == resident_id)
        )).scalars().all() == []

    async def test_media_failure_is_logged_without_file_id(
        self, client: AsyncClient, db_session: AsyncSession, caplog
    ):
        """`file_id` — токен скачивания файла; логи не то место, где он живёт."""
        resident = await _resident(db_session, 6107, verification="requested")
        await _doc(db_session, resident.id, file_id="AgACVerySecretToken")

        with patch(
            "uk_management_bot.utils.media_helpers.delete_user_documents_from_media_service",
            side_effect=RuntimeError("media down"),
        ):
            with caplog.at_level("WARNING"):
                await client.post(f"{BASE}/{resident.id}/verification/approve", json={})

        # Смотрим ТОЛЬКО свои записи: в полном прогоне caplog собирает ещё и
        # SQL-логи SQLAlchemy, где параметры INSERT содержат file_id — это
        # свойство тестовой конфигурации логирования, а не нашего кода.
        ours = [rec for rec in caplog.records
                if rec.name == "uk_management_bot.api.residents.verification"]
        assert ours, "предупреждение о сбое Media Service не записано"
        text = "\n".join(rec.getMessage() for rec in ours)
        assert "AgACVerySecretToken" not in text
        assert "Media Service" in text


# ═══════════════════════ Отказ ═══════════════════════


class TestRejectVerification:

    async def test_rejects_only_the_verification_axis(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """`User.status` не трогается: иначе отклонённый по документам житель
        вылетел бы из очереди активации аккаунта, которая смотрит на status."""
        resident = await _resident(db_session, 6201, verification="requested")
        resident_id = resident.id
        r = await client.post(f"{BASE}/{resident_id}/verification/reject",
                              json={"notes": "документ нечитаем"})
        assert r.status_code == 200
        assert r.json()["verification_status"] == "rejected"

        db_session.expire_all()
        fresh = (await db_session.execute(
            select(User).where(User.id == resident_id))).scalar_one()
        assert fresh.status == "approved"
        assert fresh.verification_notes == "документ нечитаем"

    async def test_reason_required(self, client: AsyncClient, db_session: AsyncSession):
        resident = await _resident(db_session, 6202, verification="requested")
        assert (await client.post(f"{BASE}/{resident.id}/verification/reject",
                                  json={"notes": "no"})).status_code == 422

    async def test_repeat_conflicts(self, client: AsyncClient, db_session: AsyncSession):
        resident = await _resident(db_session, 6203, verification="rejected")
        assert (await client.post(f"{BASE}/{resident.id}/verification/reject",
                                  json={"notes": "повтор"})).status_code == 409


# ═══════════════════════ Прокси документов ═══════════════════════


_JPEG = b"\xff\xd8\xff\xe0" + b"x" * 100
_PNG = b"\x89PNG\r\n\x1a\n" + b"x" * 100
_PDF = b"%PDF-1.7" + b"x" * 100


class _FakeStream:
    def __init__(self, chunks, status_code=200):
        self._chunks = chunks
        self.status_code = status_code

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def raise_for_status(self):
        return None

    async def aiter_bytes(self):
        for c in self._chunks:
            yield c


def _fake_client(*, file_path="documents/file.jpg", chunks=(_JPEG,), get_status=200):
    class _C:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, params=None):
            class _R:
                status_code = get_status

                def raise_for_status(self):
                    return None

                def json(self):
                    return {"ok": True, "result": {"file_path": file_path}}
            return _R()

        def stream(self, method, url):
            return _FakeStream(list(chunks))
    return _C


class TestDocumentProxy:

    async def test_metadata_never_exposes_file_id(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        resident = await _resident(db_session, 6301)
        await _doc(db_session, resident.id, file_id="AgACSECRETTOKEN")

        r = await client.get(f"{BASE}/{resident.id}/documents")
        assert r.status_code == 200
        assert "AgACSECRETTOKEN" not in r.text
        assert r.json()[0]["document_type"] == "passport"

    async def test_image_is_served_inline_with_sniffed_type(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        resident = await _resident(db_session, 6302)
        doc = await _doc(db_session, resident.id)

        with patch("uk_management_bot.api.residents.documents.httpx.AsyncClient",
                   _fake_client(chunks=(_PNG,))):
            r = await client.get(f"{BASE}/{resident.id}/documents/{doc.id}/file")

        assert r.status_code == 200
        # Тип от СОДЕРЖИМОГО, а не от расширения: file_name был passport.jpg.
        assert r.headers["content-type"] == "image/png"
        assert r.headers["x-content-type-options"] == "nosniff"
        assert r.headers["content-disposition"].startswith("inline")
        assert r.headers["cache-control"] == "private, max-age=300"

    async def test_pdf_is_forced_to_download(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Просмотр PDF в браузере — исполнение чужого документа в контексте
        нашего домена, поэтому вложением."""
        resident = await _resident(db_session, 6303)
        doc = await _doc(db_session, resident.id)

        with patch("uk_management_bot.api.residents.documents.httpx.AsyncClient",
                   _fake_client(chunks=(_PDF,))):
            r = await client.get(f"{BASE}/{resident.id}/documents/{doc.id}/file")

        assert r.headers["content-type"] == "application/pdf"
        assert r.headers["content-disposition"].startswith("attachment")

    async def test_unsupported_content_is_refused(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        resident = await _resident(db_session, 6304)
        doc = await _doc(db_session, resident.id)

        with patch("uk_management_bot.api.residents.documents.httpx.AsyncClient",
                   _fake_client(chunks=(b"<html>nope</html>",))):
            r = await client.get(f"{BASE}/{resident.id}/documents/{doc.id}/file")
        assert r.status_code == 415

    async def test_oversized_file_is_413_not_truncated_200(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Лимит проверяется ДО отправки заголовков — иначе клиент получил бы
        обрезанный файл с кодом 200."""
        resident = await _resident(db_session, 6305)
        doc = await _doc(db_session, resident.id)
        huge = [b"x" * (1024 * 1024)] * 21

        with patch("uk_management_bot.api.residents.documents.httpx.AsyncClient",
                   _fake_client(chunks=huge)):
            r = await client.get(f"{BASE}/{resident.id}/documents/{doc.id}/file")
        assert r.status_code == 413

    async def test_missing_file_in_telegram_is_404(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        resident = await _resident(db_session, 6306)
        doc = await _doc(db_session, resident.id)

        with patch("uk_management_bot.api.residents.documents.httpx.AsyncClient",
                   _fake_client(get_status=400)):
            r = await client.get(f"{BASE}/{resident.id}/documents/{doc.id}/file")
        assert r.status_code == 404

    async def test_telegram_down_is_502(self, client: AsyncClient, db_session: AsyncSession):
        resident = await _resident(db_session, 6307)
        doc = await _doc(db_session, resident.id)

        class _Boom:
            async def __aenter__(self):
                raise RuntimeError("network down")

            async def __aexit__(self, *a):
                return False

        with patch("uk_management_bot.api.residents.documents.httpx.AsyncClient", _Boom):
            r = await client.get(f"{BASE}/{resident.id}/documents/{doc.id}/file")
        assert r.status_code == 502

    async def test_foreign_document_is_404(self, client: AsyncClient, db_session: AsyncSession):
        victim = await _resident(db_session, 6308)
        attacker = await _resident(db_session, 6309)
        doc = await _doc(db_session, victim.id)

        r = await client.get(f"{BASE}/{attacker.id}/documents/{doc.id}/file")
        assert r.status_code == 404
