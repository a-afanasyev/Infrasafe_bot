"""Паспорт дома: чтение, правка под версией, статусы, подписанные редакции.

Правила (план ~/.claude/plans/cozy-hopping-nova.md):

* правка идёт под блокировкой строки паспорта и с `expected_version`: правки
  разных пунктов двумя людьми проходят, поздняя запись устаревшего значения
  того же пункта получает отказ `stale` (образец — `elevator_service/passport`);
* «нет данных» у пункта и «нет в доме» у группы — ответы: без них неизвестный
  кадастровый номер навсегда блокировал бы статус «Заполнен»;
* общий на несколько домов объект хранится в одном «основном» доме, остальные
  на него ссылаются; подписание копирует значение в редакцию;
* подписание создаёт неизменяемую редакцию со своей копией схемы и эталона
  формы; возврат в работу её не трогает.

Commit — у вызывающего.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from functools import lru_cache
from typing import Any, Mapping, Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.database.models.building import Building
from uk_management_bot.database.models.building_passport import (
    PASSPORT_STATUSES,
    BuildingPassport,
    BuildingPassportEvent,
    BuildingPassportPhoto,
    BuildingPassportRevision,
)
from uk_management_bot.utils.datetime_utils import utc_now

from . import prefill, schema, validation
from .validation import BadValue

REASON_MAX = 300
NOTE_MAX = 2000
NAME_MAX = 200
HISTORY_LIMIT = 200
_META_KEYS = ("inspection_date", "responsible_name", "note")


@dataclass(frozen=True)
class Actor:
    user_id: Optional[int]
    name: str


class PassportError(Exception):
    """Отказ с кодом для клиента; `keys` — пункты, к которым он относится."""

    def __init__(self, code: str, http_status: int, keys: tuple[str, ...] = ()):
        super().__init__(code)
        self.code, self.http_status, self.keys = code, http_status, keys


# ── чтение ──────────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _unit_keys() -> dict[str, tuple[str, ...]]:
    return {unit: tuple(f.key for f in schema.iter_fields() if f.share == unit and not f.computed)
            for unit in schema.SHARE_UNITS}


@lru_cache(maxsize=1)
def _unit_of() -> dict[str, str]:
    return {key: unit for unit, keys in _unit_keys().items() for key in keys}


async def _building(db: AsyncSession, building_id: int) -> Building:
    building = await db.get(Building, building_id)
    if building is None:
        raise PassportError("not_found", 404)
    return building


async def load(db: AsyncSession, building_id: int, *, for_update: bool = False) -> Optional[BuildingPassport]:
    query = select(BuildingPassport).where(BuildingPassport.building_id == building_id)
    if for_update:
        query = query.with_for_update().execution_options(populate_existing=True)
    return (await db.execute(query)).scalar_one_or_none()


async def _effective(db: AsyncSession, values: Mapping[str, Any], unknown: Mapping[str, str],
                     shared: Mapping[str, int]) -> tuple[dict, dict]:
    """Значения с подставленными общими объектами и вычисляемыми пунктами."""
    values, unknown = dict(values), dict(unknown)
    for unit, primary_id in shared.items():
        primary = await load(db, primary_id)
        for key in _unit_keys()[unit]:
            values.pop(key, None)
            unknown.pop(key, None)
            if primary is None:
                continue
            if primary.values.get(key) is not None:
                values[key] = primary.values[key]
            elif key in primary.unknown:
                unknown[key] = primary.unknown[key]
    return validation.with_computed(values), unknown


def _meta(passport: Optional[BuildingPassport]) -> dict:
    if passport is None:
        return dict.fromkeys(_META_KEYS)
    return {"inspection_date": passport.inspection_date.isoformat() if passport.inspection_date else None,
            "responsible_name": passport.responsible_name, "note": passport.note}


async def _summary(db: AsyncSession, building: Building, passport: Optional[BuildingPassport]) -> dict:
    stored = passport.values if passport else {}
    values, unknown = await _effective(db, stored, passport.unknown if passport else {},
                                       passport.shared_from if passport else {})
    absent = set(passport.absent) if passport else set()
    done, total = validation.progress(values, unknown=unknown, absent=absent)
    status = passport.status if passport else "not_started"
    return {
        "building_id": building.id, "address": building.address, "status": status,
        "version": passport.version if passport else 0,
        "revision_no": passport.revision_no if passport else 0,
        "progress": {"done": done, "total": total},
        "editable": bool(building.is_active) and status != "signed",
        "_values": values, "_unknown": unknown, "_absent": absent,
    }


async def view(db: AsyncSession, building_id: int) -> dict:
    building = await _building(db, building_id)
    passport = await load(db, building_id)
    out = await _summary(db, building, passport)
    values, unknown, absent = out.pop("_values"), out.pop("_unknown"), out.pop("_absent")
    known = {f.key for f in schema.iter_fields()} | {g.key for g in schema.iter_groups()}
    return {
        **out,
        "schema_version": passport.schema_version if passport else schema.SCHEMA_VERSION,
        "values": values, "unknown": unknown, "absent": sorted(absent),
        "shared_from": dict(passport.shared_from) if passport else {},
        "meta": _meta(passport),
        "issues": [{"key": i.key, "code": i.code} for i in validation.issues(values)],
        "missing": validation.missing(values, unknown=unknown, absent=absent),
        # Значения пунктов, которых в текущей схеме уже нет: не теряются при смене версии формы.
        "legacy": {k: v for k, v in values.items()
                   if k not in known and not k.endswith(validation.TEXT_SUFFIX)},
        "hints": await prefill.hints(db, building),
        "photos": await _photos(db, passport.id) if passport else [],
        "updated_at": passport.updated_at.isoformat() if passport and passport.updated_at else None,
        "updated_by_name": passport.updated_by_name if passport else None,
    }


async def overview(db: AsyncSession) -> list[dict]:
    buildings = (await db.execute(
        select(Building).where(Building.is_active.is_(True)).order_by(Building.id))).scalars().all()
    passports = {p.building_id: p for p in (await db.execute(select(BuildingPassport))).scalars()}
    out = []
    for building in buildings:
        row = await _summary(db, building, passports.get(building.id))
        out.append({k: v for k, v in row.items() if not k.startswith("_")})
    return out


# ── правка ──────────────────────────────────────────────────────────────────

async def _is_referenced(db: AsyncSession, building_id: int, unit: str) -> bool:
    # ponytail: полный перебор паспортов — их столько же, сколько домов (десятки);
    # при тысячах домов вынести ссылки в отдельную таблицу с индексом.
    rows = (await db.execute(select(BuildingPassport.shared_from).join(
        Building, Building.id == BuildingPassport.building_id).where(
        BuildingPassport.building_id != building_id, Building.is_active.is_(True)))).scalars()
    return any((shared or {}).get(unit) == building_id for shared in rows)


def _reason(raw: Any, key: str) -> str:
    text = raw.strip() if isinstance(raw, str) else ""
    if not text:
        raise PassportError("reason_required", 422, (key,))
    if len(text) > REASON_MAX:
        raise PassportError("too_long", 422, (key,))
    return text


def _meta_value(key: str, raw: Any) -> Any:
    if raw is None or raw == "":
        return None
    if key == "inspection_date":
        try:
            day = date.fromisoformat(raw) if isinstance(raw, str) else raw
        except ValueError:
            day = None
        # Осмотр не раньше 2000 года и не в будущем (сутки запаса на часовой пояс):
        # иначе опечатка в годе молча уходит в подписанный паспорт.
        if not isinstance(day, date) or not date(2000, 1, 1) <= day <= utc_now().date() + timedelta(days=1):
            raise PassportError("bad_date", 422, (f"meta.{key}",))
        return day
    limit = NOTE_MAX if key == "note" else NAME_MAX
    if not isinstance(raw, str) or len(raw.strip()) > limit:
        raise PassportError("too_long", 422, (f"meta.{key}",))
    return raw.strip() or None


@dataclass
class _Draft:
    """Рабочая копия состояния паспорта на время одной правки."""

    values: dict
    unknown: dict
    absent: set
    shared: dict
    meta: dict
    changes: dict   # {ключ журнала: [было, стало]}
    touched: set    # ключи версий, которые меняет правка

    def note(self, log_key: str, old: Any, new: Any, *version_keys: str) -> None:
        self.changes[log_key] = [old, new]
        self.touched.update(version_keys or (log_key,))


async def _apply_shared(db: AsyncSession, draft: _Draft, building_id: int, shared: Mapping[str, Any]) -> None:
    for unit, primary_id in shared.items():
        if unit not in schema.SHARE_UNITS:
            raise PassportError("unknown_field", 422, (unit,))
        old = draft.shared.get(unit)
        if primary_id == old:
            continue
        if primary_id is not None:
            if primary_id == building_id:
                raise PassportError("shared_self", 422, (unit,))
            primary_building = await db.get(Building, primary_id) if isinstance(primary_id, int) else None
            if primary_building is None or not primary_building.is_active:
                raise PassportError("shared_primary_not_found", 422, (unit,))
            # Строка основного дома блокируется: иначе два параллельных запроса
            # (A→B и B→C) оба пройдут проверку и сложатся в цепочку.
            # ponytail: встречные ссылки A→B и B→A одновременно дадут deadlock (Postgres
            # снимет один запрос ошибкой); упорядочить блокировки по id, если это случится.
            primary = await load(db, primary_id, for_update=True)
            # Цепочек нет: основной дом сам хранит значение, а мы не можем
            # сослаться, пока кто-то ссылается на нас.
            if primary is not None and unit in primary.shared_from:
                raise PassportError("shared_chain", 409, (unit,))
            if await _is_referenced(db, building_id, unit):
                raise PassportError("shared_referenced", 409, (unit,))
            draft.shared[unit] = primary_id
            for key in _unit_keys()[unit]:  # своих значений у ссылающегося дома нет
                draft.values.pop(key, None)
                draft.unknown.pop(key, None)
        else:
            draft.shared.pop(unit)
            # Отвязка не должна терять данные: дом получает копию значений основного
            # и дальше ведёт их сам.
            primary = await load(db, old)
            for key in _unit_keys()[unit] if primary is not None else ():
                if primary.values.get(key) is not None:
                    draft.values[key] = primary.values[key]
                elif key in primary.unknown:
                    draft.unknown[key] = primary.unknown[key]
        draft.note(f"shared.{unit}", old, primary_id, f"shared.{unit}", *_unit_keys()[unit])


async def _apply_values(db: AsyncSession, draft: _Draft, building_id: int, values: Mapping[str, Any]) -> None:
    for key, raw in values.items():
        try:
            new = validation.normalize(key, raw)
        except BadValue as exc:
            raise PassportError(exc.code, 422, (key,)) from None
        unit = _unit_of().get(key)
        if unit in draft.shared:
            raise PassportError("shared_readonly", 409, (key,))
        new = new or None if isinstance(new, list) else new
        old = draft.values.get(key)
        if new == old:
            continue
        if new is None:
            if unit and await _is_referenced(db, building_id, unit):
                raise PassportError("shared_referenced", 409, (key,))
            draft.values.pop(key, None)
        else:
            draft.values[key] = new
            draft.unknown.pop(key, None)   # значение снимает «нет данных»
            draft.absent.discard(key)      # строки снимают «нет в доме»
        draft.note(key, old, new)


def _apply_unknown(draft: _Draft, unknown: Mapping[str, Any]) -> None:
    fields = {**{f.key: f for f in schema.iter_fields()}, **{g.key: g for g in schema.iter_groups()}}
    for key, raw in unknown.items():
        item = fields.get(key)
        if item is None or getattr(item, "computed", False):
            raise PassportError("unknown_field", 422, (key,))
        if _unit_of().get(key) in draft.shared:
            raise PassportError("shared_readonly", 409, (key,))
        old = draft.unknown.get(key)
        new = None if raw is None else _reason(raw, key)
        if new == old:
            continue
        if new is None:
            draft.unknown.pop(key)
        else:
            draft.unknown[key] = new
            draft.values.pop(key, None)
            draft.absent.discard(key)
        draft.note(f"unknown.{key}", old, new, key)


def _apply_absent(draft: _Draft, absent: Mapping[str, Any]) -> None:
    groups = {g.key for g in schema.iter_groups()}
    for key, flag in absent.items():
        if key not in groups:
            raise PassportError("unknown_field", 422, (key,))
        if bool(flag) == (key in draft.absent):
            continue
        if flag:
            draft.absent.add(key)
            draft.values.pop(key, None)
            draft.unknown.pop(key, None)
        else:
            draft.absent.discard(key)
        draft.note(f"absent.{key}", not flag, bool(flag), key)


def _apply_meta(draft: _Draft, meta: Mapping[str, Any]) -> None:
    for key, raw in meta.items():
        if key not in _META_KEYS:
            raise PassportError("unknown_field", 422, (f"meta.{key}",))
        new = _meta_value(key, raw)
        old = draft.meta.get(key)
        if new == old:
            continue
        draft.meta[key] = new
        as_text = [v.isoformat() if isinstance(v, date) else v for v in (old, new)]
        draft.note(f"meta.{key}", *as_text)


async def _store(db: AsyncSession, passport: Optional[BuildingPassport], building_id: int) -> BuildingPassport:
    if passport is not None:
        return passport
    passport = BuildingPassport(building_id=building_id, status="not_started", version=0,
                                schema_version=schema.SCHEMA_VERSION, values={}, unknown={}, absent=[],
                                shared_from={}, field_versions={}, revision_no=0)
    db.add(passport)
    try:
        await db.flush()
    except IntegrityError:  # паспорт этого дома только что создал параллельный запрос
        raise PassportError("stale", 409) from None
    return passport


def _log(db: AsyncSession, passport: BuildingPassport, actor: Actor, kind: str, changes: dict,
         reason: Optional[str] = None) -> None:
    passport.updated_at, passport.updated_by, passport.updated_by_name = utc_now(), actor.user_id, actor.name
    db.add(BuildingPassportEvent(passport_id=passport.id, kind=kind, changes=changes, reason=reason,
                                 actor_id=actor.user_id, actor_name=actor.name))


async def _open(db: AsyncSession, building_id: int) -> tuple[Building, Optional[BuildingPassport]]:
    building = await _building(db, building_id)
    if not building.is_active:
        raise PassportError("building_inactive", 409)
    return building, await load(db, building_id, for_update=True)


async def patch(db: AsyncSession, building_id: int, actor: Actor, *, expected_version: int,
                values: Optional[Mapping[str, Any]] = None, unknown: Optional[Mapping[str, Any]] = None,
                absent: Optional[Mapping[str, Any]] = None, shared_from: Optional[Mapping[str, Any]] = None,
                meta: Optional[Mapping[str, Any]] = None) -> dict:
    _, passport = await _open(db, building_id)
    if passport is not None and passport.status == "signed":
        raise PassportError("signed", 409)
    draft = _Draft(
        values=dict(passport.values) if passport else {}, unknown=dict(passport.unknown) if passport else {},
        absent=set(passport.absent) if passport else set(),
        shared=dict(passport.shared_from) if passport else {},
        meta={"inspection_date": passport.inspection_date if passport else None,
              "responsible_name": passport.responsible_name if passport else None,
              "note": passport.note if passport else None},
        changes={}, touched=set())
    await _apply_shared(db, draft, building_id, shared_from or {})
    await _apply_values(db, draft, building_id, values or {})
    _apply_unknown(draft, unknown or {})
    _apply_absent(draft, absent or {})
    _apply_meta(draft, meta or {})
    if not draft.changes:
        return await view(db, building_id)

    versions = dict(passport.field_versions) if passport else {}
    stale = tuple(sorted(k for k in draft.touched if versions.get(k, 0) > expected_version))
    if stale:
        raise PassportError("stale", 409, stale)

    passport = await _store(db, passport, building_id)
    passport.version += 1
    passport.schema_version = schema.SCHEMA_VERSION
    passport.values, passport.unknown = draft.values, draft.unknown
    passport.absent, passport.shared_from = sorted(draft.absent), draft.shared
    passport.field_versions = {**versions, **dict.fromkeys(draft.touched, passport.version)}
    passport.inspection_date = draft.meta["inspection_date"]
    passport.responsible_name, passport.note = draft.meta["responsible_name"], draft.meta["note"]
    _log(db, passport, actor, "values", draft.changes)
    await db.flush()
    out = await view(db, building_id)
    if passport.status == "filled" and (out["missing"] or out["issues"] or passport.inspection_date is None):
        # Статус «Заполнен» обещает полноту: правка, которая её нарушила, возвращает паспорт в сбор.
        passport.status = "collecting"
        _log(db, passport, actor, "status", {"status": ["filled", "collecting"]})
        await db.flush()
        out = await view(db, building_id)
    return out


# ── статусы и редакции ──────────────────────────────────────────────────────

async def _photos(db: AsyncSession, passport_id: int) -> list[dict]:
    rows = (await db.execute(
        select(BuildingPassportPhoto).where(
            BuildingPassportPhoto.passport_id == passport_id, BuildingPassportPhoto.state == "done",
            BuildingPassportPhoto.removed_at.is_(None)).order_by(BuildingPassportPhoto.id))).scalars()
    return [{"id": p.id, "section": p.section, "media_id": p.media_id, "uploaded_by_name": p.uploaded_by_name,
             "uploaded_at": p.created_at.isoformat() if p.created_at else None} for p in rows]


async def _sign(db: AsyncSession, building: Building, passport: BuildingPassport, actor: Actor,
                values: dict, unknown: dict) -> None:
    passport.revision_no += 1
    db.add(BuildingPassportRevision(
        passport_id=passport.id, revision_no=passport.revision_no, passport_version=passport.version,
        schema_version=schema.SCHEMA_VERSION, schema=schema.public_schema(), form=schema.etalon(),
        values=values, unknown=unknown, absent=sorted(passport.absent), shared_from=dict(passport.shared_from),
        meta={**_meta(passport), "address": building.address},
        photos=await _photos(db, passport.id),
        signed_by=actor.user_id, signed_by_name=actor.name, signed_at=utc_now()))


async def set_status(db: AsyncSession, building_id: int, actor: Actor, *, status: str, expected_version: int,
                     reason: Optional[str] = None, can_sign: bool = False) -> dict:
    if status not in PASSPORT_STATUSES:
        raise PassportError("bad_status", 422)
    building, passport = await _open(db, building_id)
    current = passport.version if passport else 0
    if current != expected_version:
        raise PassportError("stale", 409)
    old = passport.status if passport else "not_started"
    if old == status:
        return await view(db, building_id)
    if "signed" in (old, status) and not can_sign:
        raise PassportError("sign_forbidden", 403)
    if status == "signed" and old != "filled":
        raise PassportError("not_filled", 409)
    note = _reason(reason, "reason") if old == "signed" else (reason or "").strip()[:REASON_MAX] or None

    passport = await _store(db, passport, building_id)
    values, unknown = await _effective(db, passport.values, passport.unknown, passport.shared_from)
    if status in ("filled", "signed"):
        missing = validation.missing(values, unknown=unknown, absent=set(passport.absent))
        failed = [i.key for i in validation.issues(values)]
        if missing or failed or passport.inspection_date is None:
            keys = [*missing, *failed, *(["meta.inspection_date"] if passport.inspection_date is None else [])]
            raise PassportError("incomplete", 409, tuple(keys[:50]))

    passport.status = status
    passport.version += 1
    if status == "signed":
        await _sign(db, building, passport, actor, values, unknown)
    _log(db, passport, actor, "status", {"status": [old, status]}, note)
    await db.flush()
    return await view(db, building_id)


def _revision_out(revision: BuildingPassportRevision, *, full: bool) -> dict:
    out = {"revision_no": revision.revision_no, "schema_version": revision.schema_version,
           "signed_by_name": revision.signed_by_name,
           "signed_at": revision.signed_at.isoformat() if revision.signed_at else None}
    if full:
        out.update(schema=revision.schema, form=revision.form, values=revision.values,
                   unknown=revision.unknown, absent=revision.absent, shared_from=revision.shared_from,
                   meta=revision.meta, photos=revision.photos, passport_version=revision.passport_version)
    return out


async def _revisions(db: AsyncSession, building_id: int) -> list[BuildingPassportRevision]:
    await _building(db, building_id)
    return list((await db.execute(
        select(BuildingPassportRevision).join(BuildingPassport)
        .where(BuildingPassport.building_id == building_id)
        .order_by(BuildingPassportRevision.revision_no.desc()))).scalars())


async def revisions(db: AsyncSession, building_id: int) -> list[dict]:
    return [_revision_out(r, full=False) for r in await _revisions(db, building_id)]


async def revision(db: AsyncSession, building_id: int, revision_no: int) -> dict:
    found = next((r for r in await _revisions(db, building_id) if r.revision_no == revision_no), None)
    if found is None:
        raise PassportError("not_found", 404)
    return _revision_out(found, full=True)


async def history(db: AsyncSession, building_id: int) -> list[dict]:
    await _building(db, building_id)
    rows = (await db.execute(
        select(BuildingPassportEvent).join(BuildingPassport)
        .where(BuildingPassport.building_id == building_id)
        .order_by(BuildingPassportEvent.id.desc()).limit(HISTORY_LIMIT))).scalars()
    return [{"id": e.id, "kind": e.kind, "changes": e.changes, "reason": e.reason, "actor_name": e.actor_name,
             "created_at": e.created_at.isoformat() if e.created_at else None} for e in rows]


async def latest_revisions(db: AsyncSession) -> list[dict]:
    """Последняя подписанная редакция каждого активного дома — для сводной выгрузки."""
    rows = (await db.execute(
        select(BuildingPassportRevision, Building.address)
        .join(BuildingPassport, BuildingPassport.id == BuildingPassportRevision.passport_id)
        .join(Building, Building.id == BuildingPassport.building_id)
        .where(Building.is_active.is_(True),
               BuildingPassportRevision.revision_no == BuildingPassport.revision_no)
        .order_by(Building.id))).all()
    return [{"address": address, "revision_no": r.revision_no, "values": r.values, "shared_from": r.shared_from}
            for r, address in rows]
