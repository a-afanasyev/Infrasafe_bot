"""Чтения домена «Жители» (PR-1).

Контракт (зеркало `services/addresses/queries.py`):
  * функции принимают AsyncSession и примитивы — НИКАКОГО pydantic и
    НИКАКИХ импортов из `api/` (services не зависит от api);
  * возвращают ORM-объекты / кортежи / dict; маппинг в схемы — в роутере.

Две сквозные семантики, зафиксированные здесь один раз:

**Кто такой «житель».** Пользователь с ролью `applicant` в JSON-массиве
`users.roles` и `deleted_at IS NULL`. Мультиролевые (`applicant` + `executor`)
— тоже жители: у них есть квартира, и раздел обязан их показывать. Чистый
стафф (`manager`/`executor` без `applicant`) в раздел не попадает.

**Что считается принадлежностью к адресу.** Привязки в статусах
`approved` + `pending`. `rejected` — НЕ принадлежность: менеджер уже отказал,
житель к этому адресу отношения не имеет. Одна и та же семантика у адресных
фильтров списка и у поля `apartments_count`, иначе фильтр по двору отдавал бы
жителя, у которого в карточке к этому двору «0 квартир».
"""

from sqlalchemy import and_, case, exists, func, or_, select

from uk_management_bot.database.models.apartment import Apartment
from uk_management_bot.database.models.building import Building
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.user_apartment import (
    UserApartment, UserApartmentStatus,
)
from uk_management_bot.database.models.user_verification import (
    UserDocument, UserVerification,
)
from uk_management_bot.database.models.yard import Yard
from uk_management_bot.services.sql_sorting import apply_sort, text_key
# Поиск по кириллице на проде работает только через эти хелперы — локаль
# кластера `C` ломает голый ILIKE (см. докстринг `utils/sql_search`).
from uk_management_bot.utils.sql_search import (
    ci_contains as _ci_contains,
    escape_like as _escape_like,
    is_postgres as _is_postgres,
)

RESIDENT_ROLE = "applicant"

# Порядок раздела по умолчанию: новые сверху.
DEFAULT_RESIDENT_ORDER = (User.created_at.desc(),)
# Ранги статусов: «по возрастанию» = сначала то, что требует внимания
# менеджера. Алфавит канон-ключей здесь бессмыслен, а сортировка по
# локализованному ярлыку ещё и разъезжалась бы между ru и uz.
_VERIFICATION_WEIGHT = case(
    {"requested": 0, "pending": 1, "rejected": 2, "verified": 3},
    value=User.verification_status,
    else_=4,
)
_ACCOUNT_WEIGHT = case(
    {"pending": 0, "blocked": 1, "approved": 2},
    value=User.status,
    else_=3,
)
# Белый список сортировок раздела. Адрес и число квартир не сортируются:
# оба собираются вне выборки пользователей.
RESIDENT_SORT_FIELDS = {
    # Порядок ключей — как в ПОКАЗАННОЙ строке ФИО. Колонки не несут семантику
    # «имя/фамилия»: ФИО вводится одной строкой, первое слово уходит в
    # `first_name`, остаток — в `last_name` (см. `utils/person_name`), а показ
    # склеивает их обратно. Начать с `last_name` значило бы сортировать список
    # по второму слову — на глаз это выглядит как несортированный список.
    "name": (text_key(User.first_name), text_key(User.last_name)),
    "created_at": (User.created_at,),
    "verification": (_VERIFICATION_WEIGHT,),
    "status": (_ACCOUNT_WEIGHT,),
}
RESIDENT_SORT_IDS: tuple[str, ...] = tuple(RESIDENT_SORT_FIELDS)

# Статусы привязки, означающие принадлежность жителя к адресу (см. докстринг).
BELONGING_STATUSES = (
    UserApartmentStatus.APPROVED.value,
    UserApartmentStatus.PENDING.value,
)


def _resident_scope():
    """Общий WHERE «это житель»: роль applicant + не soft-deleted."""
    return (
        User.roles.like(f'%"{RESIDENT_ROLE}"%'),
        User.deleted_at.is_(None),
    )


def _belonging_exists(*extra_conditions):
    """EXISTS-подзапрос «у пользователя есть привязка к этому адресу».

    EXISTS, а не JOIN: JOIN размножил бы строки пользователя по числу привязок
    и сломал бы `total`/пагинацию.
    """
    return exists(
        select(UserApartment.id)
        .join(Apartment, UserApartment.apartment_id == Apartment.id)
        .join(Building, Apartment.building_id == Building.id)
        .where(
            UserApartment.user_id == User.id,
            UserApartment.status.in_(BELONGING_STATUSES),
            *extra_conditions,
        )
    )


def _apply_list_filters(
    query,
    *,
    status: str | None,
    verification_status: str | None,
    yard_id: int | None,
    building_id: int | None,
    apartment_id: int | None,
    q: str | None,
    is_postgres: bool,
):
    """Общие фильтры списка и его COUNT — один источник, чтобы total не разъехался."""
    query = query.where(*_resident_scope())

    if status:
        query = query.where(User.status == status)
    if verification_status:
        query = query.where(User.verification_status == verification_status)

    if apartment_id is not None:
        query = query.where(_belonging_exists(Apartment.id == apartment_id))
    elif building_id is not None:
        query = query.where(_belonging_exists(Building.id == building_id))
    elif yard_id is not None:
        query = query.where(_belonging_exists(Building.yard_id == yard_id))

    if q:
        pattern = f"%{_escape_like(q)}%"
        query = query.where(or_(
            _ci_contains(User.first_name, pattern, is_postgres=is_postgres),
            _ci_contains(User.last_name, pattern, is_postgres=is_postgres),
            _ci_contains(User.phone, pattern, is_postgres=is_postgres),
        ))
    return query


async def list_residents(
    db,
    *,
    status: str | None = None,
    verification_status: str | None = None,
    yard_id: int | None = None,
    building_id: int | None = None,
    apartment_id: int | None = None,
    q: str | None = None,
    sort: str | None = None,
    order: str | None = None,
    limit: int = 25,
    offset: int = 0,
) -> tuple[list[User], int]:
    """→ (страница жителей, total).

    Сортировка `created_at DESC, id DESC` — второй ключ обязателен: у
    импортированных пачкой жителей `created_at` совпадает до секунды, и без
    доопределения порядка соседние страницы теряли бы и дублировали строки.

    `sort` из `RESIDENT_SORT_IDS` переупорядочивает ВСЮ выборку, а не страницу:
    иначе «первый по алфавиту» на странице 2 начинался бы с «А» заново.

    Адресные фильтры взаимоисключающи по уровню детализации: задан
    `apartment_id` — двор и дом уже не сужают, они лишь родители этой квартиры.
    """
    is_postgres = _is_postgres(db)
    page_query = _apply_list_filters(
        select(User),
        status=status, verification_status=verification_status,
        yard_id=yard_id, building_id=building_id, apartment_id=apartment_id, q=q,
        is_postgres=is_postgres,
    )
    page_query = apply_sort(
        page_query,
        fields=RESIDENT_SORT_FIELDS,
        sort=sort,
        order=order,
        default=DEFAULT_RESIDENT_ORDER,
        tiebreak=User.id.desc(),
    ).limit(limit).offset(offset)

    count_query = _apply_list_filters(
        select(func.count(User.id)),
        status=status, verification_status=verification_status,
        yard_id=yard_id, building_id=building_id, apartment_id=apartment_id, q=q,
        is_postgres=is_postgres,
    )

    users = list((await db.execute(page_query)).scalars().all())
    total = (await db.execute(count_query)).scalar() or 0
    return users, total


async def apartments_count_map(db, user_ids: list[int]) -> dict[int, int]:
    """{user_id: число привязок approved+pending} для строк текущей страницы."""
    if not user_ids:
        return {}
    result = await db.execute(
        select(UserApartment.user_id, func.count(UserApartment.id))
        .where(and_(
            UserApartment.user_id.in_(user_ids),
            UserApartment.status.in_(BELONGING_STATUSES),
        ))
        .group_by(UserApartment.user_id)
    )
    return dict(result.all())


async def primary_address_map(db, user_ids: list[int]) -> dict[int, tuple[str, str, str]]:
    """{user_id: (yard_name, building_address, apartment_number)} для основной квартиры.

    Берётся approved-привязка с `is_primary=true`. Инвариант «не более одной
    primary» держит слой мутаций (PR-3); здесь при нарушении просто выигрывает
    последняя строка — список не место падать из-за грязных данных.
    """
    if not user_ids:
        return {}
    result = await db.execute(
        select(
            UserApartment.user_id, Yard.name, Building.address, Apartment.apartment_number,
        )
        .join(Apartment, UserApartment.apartment_id == Apartment.id)
        .join(Building, Apartment.building_id == Building.id)
        .join(Yard, Building.yard_id == Yard.id)
        .where(and_(
            UserApartment.user_id.in_(user_ids),
            UserApartment.status == UserApartmentStatus.APPROVED.value,
            UserApartment.is_primary.is_(True),
        ))
    )
    return {row[0]: (row[1], row[2], row[3]) for row in result.all()}


async def get_stats(db) -> dict:
    """Счётчики раздела по ДВУМ независимым осям одним проходом.

    Оси пересекаются (approved-аккаунт может быть и `verified`, и `requested`),
    поэтому это НЕ один GROUP BY по статусу, а условная агрегация: каждая
    ячейка считается своим условием на общем scope «жители».
    """
    def _count_if(condition):
        return func.count(case((condition, 1)))

    row = (await db.execute(
        select(
            func.count(User.id),
            _count_if(User.status == "pending"),
            _count_if(User.status == "approved"),
            _count_if(User.status == "blocked"),
            _count_if(User.verification_status == "pending"),
            _count_if(User.verification_status == "requested"),
            _count_if(User.verification_status == "verified"),
            _count_if(User.verification_status == "rejected"),
        ).where(*_resident_scope())
    )).one()

    return {
        "total": row[0] or 0,
        "pending": row[1] or 0,
        "approved": row[2] or 0,
        "blocked": row[3] or 0,
        "verification_pending": row[4] or 0,
        "verification_requested": row[5] or 0,
        "verified": row[6] or 0,
        "verification_rejected": row[7] or 0,
    }


async def get_resident(db, resident_id: int) -> User | None:
    """Житель по id или None (не житель / soft-deleted → None)."""
    return (await db.execute(
        select(User).where(User.id == resident_id, *_resident_scope())
    )).scalar_one_or_none()


async def list_resident_apartments(
    db, user_id: int
) -> list[tuple[UserApartment, Apartment, Building, Yard]]:
    """ВСЕ привязки жителя с адресной цепочкой, включая `rejected`.

    Отклонённые остаются в карточке осознанно: менеджеру нужна история решений,
    иначе повторная заявка на ту же квартиру выглядит как первая.
    """
    result = await db.execute(
        select(UserApartment, Apartment, Building, Yard)
        .join(Apartment, UserApartment.apartment_id == Apartment.id)
        .join(Building, Apartment.building_id == Building.id)
        .join(Yard, Building.yard_id == Yard.id)
        .where(UserApartment.user_id == user_id)
        .order_by(UserApartment.requested_at.desc(), UserApartment.id.desc())
    )
    return list(result.all())


async def list_resident_documents(db, user_id: int) -> list[UserDocument]:
    """Документы жителя (метаданные; `file_id` наружу не отдаётся — см. схемы)."""
    result = await db.execute(
        select(UserDocument)
        .where(UserDocument.user_id == user_id)
        .order_by(UserDocument.created_at.desc(), UserDocument.id.desc())
    )
    return list(result.scalars().all())


async def get_latest_verification(db, user_id: int) -> UserVerification | None:
    """Последняя запись верификации: `created_at DESC, id DESC`.

    Т5: unique(user_id) на `user_verifications` НЕТ, записей может быть много.
    Этот хелпер — ЕДИНСТВЕННАЯ точка определения «последней»; все операции
    верификации (PR-5) обязаны ходить через него, иначе «последняя» разъедется
    между чтением и записью.
    """
    return (await db.execute(
        select(UserVerification)
        .where(UserVerification.user_id == user_id)
        .order_by(UserVerification.created_at.desc(), UserVerification.id.desc())
        .limit(1)
    )).scalar_one_or_none()
