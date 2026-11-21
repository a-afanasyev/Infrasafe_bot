"""Фото паспорта дома: идемпотентность загрузки, лимит, подписание, сбой финализации, чистка (sqlite)."""
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select, update

from uk_management_bot.database.models.building_passport import BuildingPassportPhoto
from uk_management_bot.services.building_passport import photos, validation
from uk_management_bot.services.building_passport import service as svc
from uk_management_bot.services.building_passport.photos import Media, MediaUnavailable
from uk_management_bot.services.building_passport.service import Actor, PassportError
from uk_management_bot.utils.datetime_utils import utc_now

ENGINEER, MANAGER = Actor(11, "Инженер Иванов"), Actor(1, "Менеджер Петров")
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
SECTION = "playgrounds"


class FakeMedia:
    """Медиа-сервис в памяти: файлы лежат под своим `media_ref`."""

    def __init__(self):
        self.files: dict[int, str] = {}
        self.down = False
        self.uploads = 0

    async def find(self, ref):
        if self.down:
            raise MediaUnavailable
        return sorted(i for i, r in self.files.items() if r == ref)

    async def upload(self, ref, user_id, data, mime, section):
        if self.down:
            raise MediaUnavailable
        self.uploads += 1
        self.files[len(self.files) + 100 + self.uploads] = ref
        return max(self.files)

    async def delete(self, media_id):
        self.files.pop(media_id, None)

    @property
    def api(self) -> Media:
        return Media(find=self.find, upload=self.upload, delete=self.delete)


@pytest.fixture
async def factory(el_async_factory, el_seed):
    async with el_async_factory() as session:
        session.add_all([el_seed.yard(), el_seed.building(1), el_seed.building(2, address="д. 7"),
                         el_seed.user(1, roles='["manager"]'), el_seed.user(11, roles='["executor","engineer"]')])
        await session.commit()
    return el_async_factory


@pytest.fixture
def media():
    return FakeMedia()


def _key() -> str:
    return str(uuid.uuid4())


async def _up(factory, media, *, key=None, data=PNG, section=SECTION, building=1, **kw):
    return await photos.upload(factory, building, ENGINEER, section=section, op_key=key or _key(),
                               photo_bytes=data, media=media.api, **kw)


async def _refused(coro) -> PassportError:
    with pytest.raises(PassportError) as exc:
        await coro
    return exc.value


async def _view(factory, building=1) -> dict:
    async with factory() as db:
        return await svc.view(db, building)


async def _sign(factory) -> None:
    async with factory() as db:
        view = await svc.view(db, 1)
        view = await svc.patch(db, 1, ENGINEER, expected_version=view["version"], meta={"inspection_date": "2026-11-20"})
        groups = validation._groups()
        view = await svc.patch(db, 1, ENGINEER, expected_version=view["version"],
                               unknown={k: "нет" for k in view["missing"] if k not in groups},
                               absent={k: True for k in view["missing"] if k in groups})
        view = await svc.set_status(db, 1, ENGINEER, status="filled", expected_version=view["version"])
        await svc.set_status(db, 1, MANAGER, status="signed", expected_version=view["version"], can_sign=True)
        await db.commit()


async def test_upload_lands_in_the_passport_and_bumps_version(factory, media):
    photo = await _up(factory, media)
    view = await _view(factory)
    assert [p["id"] for p in view["photos"]] == [photo["id"]] and view["version"] == 1
    assert photo["media_id"] in media.files and not photo["replay"]


async def test_retry_with_the_same_key_gives_the_same_photo_and_one_file(factory, media):
    key = _key()
    first = await _up(factory, media, key=key)
    again = await _up(factory, media, key=key)
    assert again["id"] == first["id"] and again["replay"] and len(media.files) == 1


async def test_same_key_with_another_file_or_section_is_refused(factory, media):
    key = _key()
    await _up(factory, media, key=key)
    assert (await _refused(_up(factory, media, key=key, data=PNG + b"x"))).code == "key_reused"
    assert (await _refused(_up(factory, media, key=key, section="s1"))).code in ("key_reused", "bad_section")


async def test_bad_key_file_and_section_are_refused(factory, media):
    assert (await _refused(_up(factory, media, key="nope"))).http_status == 422
    assert (await _refused(_up(factory, media, data=b"not an image"))).http_status == 415
    assert (await _refused(_up(factory, media, section="no_such"))).code == "bad_section"
    assert media.files == {}


async def test_twenty_first_photo_of_a_section_is_refused(factory, media, monkeypatch):
    monkeypatch.setattr(photos, "MAX_PER_SECTION", 2)
    await _up(factory, media)
    await _up(factory, media)
    error = await _refused(_up(factory, media))
    assert (error.code, error.http_status) == ("photo_limit", 409) and len(media.files) == 2


async def test_signed_passport_takes_no_uploads_and_no_removals(factory, media):
    photo = await _up(factory, media)
    await _sign(factory)
    assert (await _refused(_up(factory, media))).code == "signed"
    async with factory() as db:
        assert (await _refused(photos.remove(db, 1, photo["id"], ENGINEER))).code == "signed"
    assert len(media.files) == 1


async def test_media_down_is_retryable_with_the_same_key(factory, media):
    key = _key()
    media.down = True
    error = await _refused(_up(factory, media, key=key))
    assert (error.code, error.http_status) == ("media_unavailable", 503)
    media.down = False
    assert (await _up(factory, media, key=key))["media_id"] in media.files


async def test_db_failure_after_upload_then_retry_keeps_one_file(factory, media, monkeypatch):
    """Файл уже в медиа, запись в БД сорвалась: повтор находит его по media_ref."""
    key = _key()
    real = photos._finalize

    async def boom(*a, **kw):
        raise RuntimeError("db down")

    monkeypatch.setattr(photos, "_finalize", boom)
    with pytest.raises(RuntimeError):
        await _up(factory, media, key=key)
    assert len(media.files) == 1
    monkeypatch.setattr(photos, "_finalize", real)

    assert (await _refused(_up(factory, media, key=key))).code == "in_progress"  # аренда ещё жива
    photo = await _up(factory, media, key=key, now=utc_now() + photos.LEASE + timedelta(seconds=1))
    assert media.uploads == 1 and list(media.files) == [photo["media_id"]]


async def test_signing_between_accept_and_finalize_refuses_and_drops_the_file(factory, media):
    real = media.upload

    async def upload_then_sign(*a):
        media_id = await real(*a)
        await _sign(factory)
        return media_id

    api = Media(find=media.find, upload=upload_then_sign, delete=media.delete)
    error = await _refused(photos.upload(factory, 1, ENGINEER, section=SECTION, op_key=_key(),
                                         photo_bytes=PNG, media=api))
    assert error.code == "signed" and media.files == {}
    async with factory() as db:
        assert (await svc.revision(db, 1, 1))["photos"] == []


async def test_removed_photo_keeps_its_file_while_a_revision_refers_to_it(factory, media):
    kept = await _up(factory, media)
    await _sign(factory)
    async with factory() as db:
        view = await svc.view(db, 1)
        await svc.set_status(db, 1, MANAGER, status="collecting", expected_version=view["version"],
                             reason="уточнить", can_sign=True)
        await db.commit()
    fresh = await _up(factory, media)
    async with factory() as db:
        assert await photos.remove(db, 1, kept["id"], ENGINEER) is None       # в редакции №1 — файл не трогаем
        assert await photos.remove(db, 1, fresh["id"], ENGINEER) == fresh["media_id"]
        await db.commit()
        assert (await svc.view(db, 1))["photos"] == []
        assert [p["id"] for p in (await svc.revision(db, 1, 1))["photos"]] == [kept["id"]]
        assert await photos.media_id_of(db, 1, kept["id"]) == kept["media_id"]  # редакция его показывает


async def test_removed_photo_is_gone_for_readers_and_its_key_is_spent(factory, media):
    key = _key()
    photo = await _up(factory, media, key=key)
    async with factory() as db:
        await photos.remove(db, 1, photo["id"], ENGINEER)
        await db.commit()
        assert (await _refused(photos.media_id_of(db, 1, photo["id"]))).http_status == 404
    assert (await _refused(_up(factory, media, key=key))).code == "key_reused", "повтор не выдаёт убранное за добавленное"


async def test_cleanup_holds_the_lease_so_a_retry_cannot_adopt_a_file_being_deleted(factory, media, monkeypatch):
    key = _key()

    async def boom(*a, **kw):
        raise RuntimeError("db down")

    real = photos._finalize
    monkeypatch.setattr(photos, "_finalize", boom)
    with pytest.raises(RuntimeError):
        await _up(factory, media, key=key)
    monkeypatch.setattr(photos, "_finalize", real)
    seen = []

    async def find_then_retry(ref):
        found = await media.find(ref)
        if not seen:  # повтор загрузки приходит посреди чистки
            seen.append((await _refused(_up(factory, media, key=key))).code)
        return found

    api = Media(find=find_then_retry, upload=media.upload, delete=media.delete)
    assert await photos.cleanup(factory, media=api, now=utc_now() + photos.ABANDON_AFTER + timedelta(minutes=1)) == 1
    assert seen == ["in_progress"] and media.files == {}


async def test_photo_of_another_building_is_not_found(factory, media):
    photo = await _up(factory, media)
    async with factory() as db:
        assert (await _refused(photos.media_id_of(db, 2, photo["id"]))).http_status == 404
        assert (await _refused(photos.remove(db, 2, photo["id"], ENGINEER))).http_status == 404


async def test_cleanup_closes_abandoned_uploads_and_removes_their_files(factory, media, monkeypatch):
    async def boom(*a, **kw):
        raise RuntimeError("db down")

    real = photos._finalize
    monkeypatch.setattr(photos, "_finalize", boom)
    with pytest.raises(RuntimeError):
        await _up(factory, media)
    monkeypatch.setattr(photos, "_finalize", real)
    done = await _up(factory, media)

    assert await photos.cleanup(factory, media=media.api) == 0  # сутки не прошли
    later = utc_now() + photos.ABANDON_AFTER + timedelta(minutes=1)
    media.down = True
    assert await photos.cleanup(factory, media=media.api, now=later) == 0  # медиа недоступно — ждём
    media.down = False
    assert await photos.cleanup(factory, media=media.api, now=later) == 1
    assert list(media.files) == [done["media_id"]]
    async with factory() as db:
        states = sorted((await db.execute(select(BuildingPassportPhoto.state))).scalars())
        assert states == ["abandoned", "done"]
        await db.execute(update(BuildingPassportPhoto).values(removed_at=None))
