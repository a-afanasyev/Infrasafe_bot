"""Дополнение УК: детские и спортивные площадки.

В форме №3824 этих сведений нет — 33 пункта перенесены с исходной страницы и
печатаются на листе «Дополнение УК». Ключ блока — `playgrounds`, а не «раздел
14»: если министерство добавит свой 14-й раздел, номера не столкнутся.
"""
from __future__ import annotations

from .schema import Field, Option, Section, field, opt

M2, PCS, YEAR = "м²", "шт", "год"
SHARE = "playgrounds"

_YES_NO = (opt("yes", "есть", uz="bor"), opt("no", "нет", uz="yo'q"))
_CONDITION = (opt("ok", "удовлетворительное", uz="qoniqarli"),
              opt("bad", "неудовлетворительное", uz="qoniqarsiz"))
_MATERIAL = (
    opt("metal", "металл", uz="metall"), opt("wood", "дерево", uz="yog'och"),
    opt("plastic", "пластик", uz="plastik"), opt("metal_plastic", "металл + пластик", uz="metall + plastik"),
    opt("metal_wood", "металл + дерево", uz="metall + yog'och"), opt("other", "другое", uz="boshqa", other=True),
)
_SURFACE_COMMON = (
    opt("rubber_crumb", "резиновая крошка", uz="rezina ushoq"),
    opt("epdm", "наливное покрытие ЭПДМ", uz="quyma EPDM qoplama"),
    opt("artificial_grass", "искусственная трава", uz="sun'iy maysa"),
)


def _pg(key: str, type_: str, ru: str, uz: str, *, unit: str | None = None,
        options: tuple[Option, ...] = ()) -> Field:
    return field(f"pg_{key}", type_, ru, uz=uz, unit=unit, options=options, share=SHARE)


def _count(key: str, ru: str, uz: str) -> Field:
    return _pg(key, "int", ru, uz, unit=PCS)


PLAYGROUNDS = Section(
    key="playgrounds", no=None, ru="Детские и спортивные площадки", uz="Bolalar va sport maydonchalari",
    items=(
        _count("child_count", "Детские площадки: количество", "Bolalar maydonchalari soni"),
        _pg("child_area", "decimal", "Детские площадки: общая площадь", "Bolalar maydonchalarining umumiy maydoni",
            unit=M2),
        _pg("child_surface", "choice", "Детская площадка: покрытие", "Bolalar maydonchasi qoplamasi", options=(
            *_SURFACE_COMMON,
            opt("pvc_tile", "модульная плитка ПВХ", uz="modulli PVX plitka"),
            opt("sand", "песок", uz="qum"), opt("lawn", "газон", uz="maysazor"),
            opt("asphalt", "асфальт", uz="asfalt"), opt("ground", "грунт", uz="tuproq"),
            opt("other", "другое", uz="boshqa", other=True))),
        _pg("child_fence", "choice", "Детская площадка: ограждение", "Bolalar maydonchasi to'sig'i",
            options=_YES_NO),
        _count("child_complexes", "Игровые комплексы", "O'yin majmualari"),
        _count("child_slides", "Горки", "Sirpanchiqlar"),
        _count("child_swings", "Качели", "Arg'imchoqlar"),
        _count("child_carousels", "Карусели", "Karusellar"),
        _count("child_rockers", "Качалки (балансиры, на пружине)", "Tebranma o'yinchoqlar (balansir, prujinali)"),
        _count("child_sandboxes", "Песочницы", "Qum qutilari"),
        _count("child_houses", "Детские домики / беседки", "Bolalar uychalari / shiyponlar"),
        _count("child_benches", "Детская площадка: скамейки", "Bolalar maydonchasidagi o'rindiqlar"),
        _count("child_bins", "Детская площадка: урны", "Bolalar maydonchasidagi axlat qutilari"),
        _pg("child_material", "choice", "Детское оборудование: материал", "Bolalar jihozlari materiali",
            options=_MATERIAL),
        _pg("child_condition", "choice", "Детское оборудование: состояние", "Bolalar jihozlari holati",
            options=_CONDITION),
        _pg("child_lighting", "choice", "Детская площадка: освещение", "Bolalar maydonchasi yoritilishi",
            options=_YES_NO),
        _pg("child_install_year", "int", "Детское оборудование: год установки",
            "Bolalar jihozlari o'rnatilgan yili", unit=YEAR),
        _count("sport_count", "Спортивные площадки: количество", "Sport maydonchalari soni"),
        _pg("sport_area", "decimal", "Спортивные площадки: общая площадь",
            "Sport maydonchalarining umumiy maydoni", unit=M2),
        _pg("sport_type", "choice", "Спортивная площадка: тип", "Sport maydonchasi turi", options=(
            opt("multi", "многофункциональная", uz="ko'p funksiyali"), opt("football", "футбольная", uz="futbol"),
            opt("basketball", "баскетбольная", uz="basketbol"), opt("volleyball", "волейбольная", uz="voleybol"),
            opt("tennis", "теннисная", uz="tennis"), opt("workout", "воркаут", uz="vorkaut"),
            opt("gym", "тренажёрная", uz="trenajyor"), opt("other", "другое", uz="boshqa", other=True))),
        _pg("sport_surface", "choice", "Спортивная площадка: покрытие", "Sport maydonchasi qoplamasi", options=(
            *_SURFACE_COMMON,
            opt("pvc_modular", "модульное покрытие ПВХ", uz="modulli PVX qoplama"),
            opt("polyurethane", "полиуретан (тартан)", uz="poliuretan (tartan)"),
            opt("asphalt", "асфальт", uz="asfalt"), opt("concrete", "бетон", uz="beton"),
            opt("ground", "грунт", uz="tuproq"), opt("other", "другое", uz="boshqa", other=True))),
        _pg("sport_fence", "choice", "Спортивная площадка: ограждение", "Sport maydonchasi to'sig'i",
            options=_YES_NO),
        _count("sport_trainers", "Уличные тренажёры", "Ko'cha trenajyorlari"),
        _count("sport_bars", "Турники / брусья / шведские стенки", "Turniklar / bruslar / shved devorlari"),
        _count("sport_goals", "Футбольные ворота", "Futbol darvozalari"),
        _count("sport_hoops", "Баскетбольные стойки со щитами", "Shchitli basketbol ustunlari"),
        _count("sport_net_posts", "Стойки с сеткой (волейбол / теннис)", "To'rli ustunlar (voleybol / tennis)"),
        _count("sport_tables", "Теннисные столы", "Tennis stollari"),
        _pg("sport_material", "choice", "Спортивное оборудование: материал", "Sport jihozlari materiali",
            options=_MATERIAL),
        _pg("sport_condition", "choice", "Спортивное оборудование: состояние", "Sport jihozlari holati",
            options=_CONDITION),
        _pg("sport_lighting", "choice", "Спортивная площадка: освещение", "Sport maydonchasi yoritilishi",
            options=_YES_NO),
        _count("sport_benches", "Спортивная площадка: скамейки", "Sport maydonchasidagi o'rindiqlar"),
        _count("sport_bins", "Спортивная площадка: урны", "Sport maydonchasidagi axlat qutilari"),
    ),
)
