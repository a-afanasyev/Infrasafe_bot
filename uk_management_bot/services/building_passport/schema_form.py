"""Разделы 1–13 формы №3824: поля схемы по строкам эталона.

Номера и строки — из `form_3824.json`; соответствие каталогу исходной
страницы — `docs/PASSPORT_FORM_MAPPING.md`. Тексты вариантов формы (`form=`)
дословные, включая опечатки оригинала («пенаблок», «индивидувал»).
"""
from __future__ import annotations

from .schema import Field, Group, Option, Section, etalon, field, opt

M2, M, MM, PCS, PCT, LM, KW, YEAR = "м²", "м", "мм", "шт", "%", "п.м", "кВт", "год"

OTHER_1 = "(бошқалар аниқ кўрсатилинади)"
OTHER_2 = "(бошқалар аниқ кўрсатилади)"

YES_NO_BOR = (opt("yes", "есть", "бор"), opt("no", "нет", "йўқ"))
YES_NO_MAVJUD = (opt("yes", "есть", "мавжуд"), opt("no", "нет", "мавжуд эмас"))
CONDITION = (opt("ok", "удовлетворительное", "қониқарли"), opt("bad", "неудовлетворительное", "қониқарсиз"))


def _others(form: str, *pairs: tuple[str, str, str]) -> tuple[Option, ...]:
    """Варианты сверх формы: печатаются в её строку «другое» с расшифровкой."""
    return tuple(opt(key, ru, form, uz=uz, other=True) for key, ru, uz in pairs)


def _section_title(no: int) -> str:
    return next(r["title"] for r in etalon()["rows"] if r["kind"] == "section" and r["section"] == no)


def _section(no: int, ru: str, *items: Field | Group) -> Section:
    from .schema import uz_latin

    return Section(key=f"s{no}", no=no, ru=ru, uz=uz_latin(_section_title(no)), items=items)


def _apartments() -> tuple[Field, ...]:
    out: list[Field] = []
    for rooms in range(1, 8):
        out.append(field(f"apt_{rooms}_count", "int", f"Квартиры {rooms}-комнатные: количество", unit=PCS,
                         form="2.13", rows=(rooms,), label="sub", uz=f"{rooms} xonali xonadonlar soni"))
        out.append(field(f"apt_{rooms}_area", "decimal", f"Квартиры {rooms}-комнатные: площадь", unit=M2,
                         form="2.13", rows=(rooms,), label="sub", uz=f"{rooms} xonali xonadonlar maydoni"))
    return tuple(out)


def _row(key: str, type_: str, ru: str, uz: str, **kwargs) -> Field:
    return field(key, type_, ru, uz=uz, **kwargs)


_OPENING_SIZE = (
    _row("count", "int", "Количество", "Soni", unit=PCS),
    _row("width", "decimal", "Ширина", "Eni", unit=M),
    _row("height", "decimal", "Высота", "Bo'yi", unit=M),
    _row("area", "decimal", "Площадь", "Maydoni", unit=M2, computed=True),
)

WINDOWS = Group(
    key="windows", ru="Окна в подъездах", uz="Kirish yo'laklaridagi derazalar", form=(("2.17", None),),
    fields=(
        _row("type", "choice", "Тип", "Turi", options=(
            opt("plastic", "пластиковые (ПВХ)", "Пластик", uz="plastik (PVX)"),
            opt("aluminium", "алюминиевые", "Алюминли", uz="alyuminiy"),
            opt("wood", "деревянные", "Ёғоч", uz="yog'och"),
            opt("metal_plastic_grille", "металлопластиковые с решёткой", "Пластик", uz="panjarali metall-plastik"),
            opt("metal", "металлические", uz="metall"),
            opt("glass_blocks", "стеклоблоки", uz="shisha bloklar"),
            opt("other", "другое", uz="boshqa", other=True),
        )),
        *_OPENING_SIZE,
    ),
)

DOORS = Group(
    key="doors", ru="Двери в подъездах", uz="Kirish yo'laklaridagi eshiklar", form=(("2.20", (1, 2, 3)),),
    fields=(
        _row("type", "choice", "Тип", "Turi", options=(
            opt("metal", "металлические", "Пўлат", uz="metall"),
            opt("metal_insulated", "металлические утеплённые", "Пўлат", uz="issiqlik himoyali metall"),
            opt("wood", "деревянные", "Ёғоч", uz="yog'och"),
            opt("plastic", "пластиковые (ПВХ)", uz="plastik (PVX)"),
            opt("aluminium_glass", "алюминиевые со стеклом", uz="oynali alyuminiy"),
            opt("glass", "стеклянные", uz="shisha"),
            opt("fire", "противопожарные", "Пўлат", uz="yong'inga chidamli"),
            opt("other", "другое", uz="boshqa", other=True),
        )),
        *_OPENING_SIZE,
    ),
)

APT_MORE = Group(
    key="apt_more", ru="Квартиры более 7 комнат", uz="7 xonadan ortiq xonadonlar", form=(("2.13", (8,)),),
    fields=(
        _row("rooms", "int", "Число комнат", "Xonalar soni"),
        _row("count", "int", "Количество", "Soni", unit=PCS),
        _row("area", "decimal", "Площадь", "Maydoni", unit=M2),
    ),
)

_RUN = (opt("horizontal", "горизонтальные", "Ички горизонтал қувурлари", uz="gorizontal"),
        opt("riser", "стояки", "Ички вертикал қувурлари", uz="tik (stoyak)"))
_STEEL_PP = (opt("steel", "сталь", "Пўлат қувурлар", uz="po'lat"),
             opt("pp", "полипропилен", "Полипропилен қувурлар", uz="polipropilen"))
_SEWER_MATERIAL = (opt("asbestos_iron", "асбестоцемент / чугун", "Асбест цемент / қуйма темир қувурлар",
                       uz="asbest-sement / cho'yan"),
                   opt("pp_pvc", "полипропилен / ПВХ", "Полипропилен ва (ПВХ) қувурлар", uz="polipropilen / PVX"))


def _pipes(key: str, ru: str, uz: str, first: int, section: int, material: tuple[Option, ...],
           show_if: tuple[str, tuple[str, ...]]) -> Group:
    """Трубы системы: в форме по строке на (участок, материал), состояние — в п.м."""
    return Group(
        key=key, ru=ru, uz=uz, show_if=show_if,
        form=tuple((f"{section}.{first + i}", None) for i in range(4)),
        fields=(
            _row("run", "choice", "Участок", "Qism", options=_RUN),
            _row("material", "choice", "Материал", "Material", options=material),
            _row("diameter", "int", "Диаметр", "Diametr", unit=MM),
            _row("length", "decimal", "Длина", "Uzunligi", unit=LM),
            _row("ok_length", "decimal", "В удовлетворительном состоянии", "Qoniqarli holatda", unit=LM),
            _row("bad_length", "decimal", "В неудовлетворительном состоянии", "Qoniqarsiz holatda", unit=LM),
        ),
    )


FORM_SECTIONS: tuple[Section, ...] = (
    _section(
        1, "Общие сведения",
        field("addr_region", "text", "Адрес: область", form="1.1", rows=(1,), label="sub"),
        field("addr_district", "text", "Адрес: город (район)", form="1.1", rows=(2,), label="sub"),
        field("addr_mahalla", "text", "Адрес: махалля", form="1.1", rows=(3,), label="sub"),
        field("addr_street", "text", "Адрес: улица", form="1.1", rows=(4,), label="sub"),
        field("addr_house_no", "text", "Адрес: номер дома", form="1.1", rows=(5,), label="sub"),
        field("cadastre_no", "text", "Кадастровый номер", form="1.2"),
        field("built_year", "int", "Год постройки", unit=YEAR, form="1.3"),
        field("plot_area", "decimal", "Площадь прилегающего участка", unit=M2, form="1.4", share="plot"),
        field("heritage", "choice", "Статус объекта культурного наследия", form="1.5", options=(
            opt("no", "не присвоен", "берилмаган"), opt("yes", "присвоен", "Берилган"))),
    ),
    _section(
        2, "Основные показатели",
        field("area_basement", "decimal", "Общая площадь подвала", unit=M2, form="2.1", rows=(1,), label="sub",
              uz="Yerto'laning umumiy maydoni"),
        field("area_typical_floor", "decimal", "Общая площадь типового этажа", unit=M2, form="2.1", rows=(2,),
              label="sub", uz="Namunaviy qavatning umumiy maydoni"),
        field("footprint_area", "decimal", "Площадь застройки", unit=M2, form="2.2"),
        field("common_area", "decimal", "Площадь общего пользования", unit=M2, form="2.3"),
        field("green_share", "decimal", "Доля озеленённых площадей", unit=PCT, form="2.4", share="plot",
              uz="Ko'kalamzorlashtirilgan maydonlar ulushi"),
        field("nonres_count", "int", "Количество нежилых объектов", unit=PCS, form="2.5"),
        field("nonres_area", "decimal", "Площадь нежилых объектов", unit=M2, form="2.6",
              uz="Noturar obyektlarning umumiy maydoni"),
        field("length_m", "decimal", "Длина дома", unit=M, form="2.7"),
        field("width_m", "decimal", "Ширина дома", unit=M, form="2.8"),
        field("height_m", "decimal", "Высота дома", unit=M, form="2.9"),
        field("floors", "int", "Количество этажей", unit=PCS, form="2.10"),
        field("floor_h_basement", "decimal", "Высота подвала", unit=M, form="2.11", rows=(1,), label="sub",
              uz="Yerto'la balandligi"),
        field("floor_h_typical", "decimal", "Высота типового этажа", unit=M, form="2.11", rows=(2,), label="sub",
              uz="Namunaviy qavat balandligi"),
        field("management", "choice", "Способ управления", form="2.12", options=(
            opt("management_body", "управляющий орган (УК)", "Бошқариш органи"),
            opt("hoa", "ТСЖ", "Уй-жой мулкдорлари ширкати"),
            opt("direct", "непосредственное управление", "Бевосита бошқариш"),
            opt("not_chosen", "способ не выбран", "Кўп квартирали уйнинг бошқариш усули танланмаган",
                uz="boshqarish usuli tanlanmagan"),
            opt("developer", "на балансе застройщика", "Қурувчи балансида"),
            opt("unmanaged", "без управления", "Бошқаришсиз"),
            opt("organizations", "на балансе организаций", "Идора ва ташкилотлар балансида"),
        )),
        *_apartments(),
        APT_MORE,
        field("apt_total_area", "decimal", "Общая площадь квартир", unit=M2, form="2.14"),
        field("entrances", "int", "Количество подъездов", unit=PCS, form="2.15"),
        # Строку 3 «мавжуд эмас» печатает то же поле: лифтов нет ⟺ оба количества нулевые.
        field("lifts_passenger", "int", "Лифты пассажирские", unit=PCS, form="2.16", rows=(1, 3), label="sub",
              uz="Yo'lovchi liftlari soni"),
        field("lifts_cargo", "int", "Лифты грузовые", unit=PCS, form="2.16", rows=(2,), label="sub",
              uz="Yuk liftlari soni"),
        WINDOWS,
        field("windows_total_count", "int", "Итого окон: количество", unit=PCS, form="2.19", computed=True,
              uz="Jami derazalar soni"),
        field("windows_total_area", "decimal", "Итого окон: площадь", unit=M2, form="2.19", computed=True,
              uz="Jami derazalar maydoni"),
        DOORS,
        field("door_insulation", "choice", "Двери: теплоизоляция", form="2.20", rows=(4,), label="own",
              options=YES_NO_BOR),
    ),
    _section(
        3, "Конструктивная часть",
        field("blind_area_width", "decimal", "Ширина отмостки", unit=M, form="3.1"),
        field("sewer_pipes_length", "decimal", "Канализация в подвалах: длина труб", unit=LM, form="3.2",
              rows=(1,)),
        # В оригинале длина стояков записана дважды (строки 2 и 4) — одно значение на обе.
        field("sewer_risers_length", "decimal", "Канализация в подвалах: длина стояков", unit=LM, form="3.2",
              rows=(2, 4), label="own"),
        field("sewer_risers_count", "int", "Канализация в подвалах: количество стояков", unit=PCS, form="3.2",
              rows=(3,), label="own"),
        field("sewer_revisions", "int", "Канализация в подвалах: количество ревизий", unit=PCS, form="3.2",
              rows=(5,), label="own"),
        field("sewer_other", "text", "Канализация в подвалах: прочее", form="3.2", rows=(6,), label="own"),
        field("wall_type", "choice", "Тип наружной стены", form="3.3", options=(
            opt("brick_ceramic", "кирпич керамический (жжёный)", "ғишт", uz="pishiq g'isht"),
            opt("brick_silicate", "кирпич силикатный", "ғишт", uz="silikat g'isht"),
            opt("gas_block", "газоблок (газобетон)", "газоблок"),
            opt("foam_block", "пеноблок (пенобетон)", "пенаблок", uz="penoblok"),
            opt("large_panel", "крупнопанельная сборная (ж/б панели)", "йиғма йирик панелли"),
            *_others(
                OTHER_1,
                ("claydite_block", "керамзитобетонный блок", "keramzitbeton blok"),
                ("cinder_block", "шлакоблок", "shlakoblok"),
                ("porous_ceramic", "керамический поризованный блок", "g'ovakli keramik blok"),
                ("monolith", "монолитный железобетон", "monolit temir-beton"),
                ("frame_brick", "каркас монолитный + заполнение кирпичом", "monolit karkas, g'isht bilan to'ldirilgan"),
                ("frame_gas_block", "каркас монолитный + заполнение газоблоком", "monolit karkas, gazoblok bilan to'ldirilgan"),
                ("frame_foam_block", "каркас монолитный + заполнение пеноблоком", "monolit karkas, penoblok bilan to'ldirilgan"),
                ("large_block", "крупноблочная", "yirik blokli"),
                ("sandwich", "сэндвич-панели", "sendvich-panellar"),
                ("wood_frame", "каркасно-деревянная", "yog'och karkasli"),
                ("adobe", "сырцовый кирпич / пахса / гуваля", "xom g'isht / paxsa / guvala"),
                ("mixed", "смешанная", "aralash"),
                ("other", "другое", "boshqa"),
            ),
        )),
        field("wall_thickness", "int", "Толщина наружной стены", unit=MM, form="3.4"),
    ),
    _section(
        4, "Фасад",
        field("facade_insulation", "choice", "Теплоизоляция фасада: материал", form="4.1", options=(
            opt("basalt", "минеральная вата (базальт)", "Базалт"),
            opt("fiberglass", "стекловолокно", "шиша толали"),
            opt("none", "отсутствует", "мавжуд эмас"),
            *_others(
                OTHER_2,
                ("eps", "пенополистирол", "penopolistirol"),
                ("xps", "экструдированный пенополистирол", "ekstruziyalangan penopolistirol"),
                ("pur", "пенополиуретан", "penopoliuretan"),
                ("plaster", "теплоизоляционная штукатурка", "issiqlik saqlovchi suvoq"),
                ("other", "другое", "boshqa"),
            ),
        )),
        field("facade_insulation_thickness", "int", "Теплоизоляция фасада: толщина", unit=MM,
              uz="Fasad issiqlik himoyasi qalinligi",
              show_if=("facade_insulation", ("basalt", "fiberglass", "eps", "xps", "pur", "plaster", "other"))),
        field("facade_finish", "choice", "Отделка фасада", form="4.2", options=(
            opt("mosaic", "мозаика", "мозаика"),
            opt("emulsion", "эмульсионная краска", "эмулсия бўёқ"),
            opt("travertine", "травертин", "травертин"),
            opt("fine_plaster", "мелкозернистая штукатурка", "майда тошли сувоқлар"),
            *_others(
                OTHER_1,
                ("facade_paint", "фасадная краска", "fasad bo'yog'i"),
                ("decor_plaster", "декоративная штукатурка (короед)", "dekorativ suvoq (koroed)"),
                ("facing_brick", "облицовочный кирпич", "pardozbop g'isht"),
                ("porcelain", "керамогранит (вентфасад)", "keramogranit (ventfasad)"),
                ("composite", "алюминиевые композитные панели", "alyuminiy kompozit panellar"),
                ("stone", "натуральный камень", "tabiiy tosh"),
                ("unfinished", "без отделки", "pardozsiz"),
                ("other", "другое", "boshqa"),
            ),
        )),
        field("facade_area", "decimal", "Площадь фасада", unit=M2, form="4.3"),
        field("facade_ok_pct", "decimal", "Фасад в удовлетворительном состоянии", unit=PCT, form="4.4",
              rows=(1,), label="sub"),
        field("facade_bad_pct", "decimal", "Фасад в неудовлетворительном состоянии", unit=PCT, form="4.4",
              rows=(2,), label="sub"),
        field("below_zero_area", "decimal", "Подвальная / цокольная часть ниже 0.000", unit=M2, form="4.5",
              uz="0.000 m sathdan pastki qavat (yerto'la / sokol qismi)"),
        field("basement_repaired_pct", "decimal", "Подвал отремонтирован", unit=PCT, form="4.6", rows=(1,),
              label="sub"),
        field("basement_partly_pct", "decimal", "Подвал отремонтирован частично", unit=PCT, form="4.6", rows=(2,),
              label="sub"),
        field("basement_needs_pct", "decimal", "Подвал требует ремонта", unit=PCT, form="4.6", rows=(3,),
              label="sub"),
    ),
    _section(
        5, "Кровля",
        field("roof_type", "choice", "Тип крыши", form="5.1", options=(
            opt("flat", "плоская", "Ясси том"), opt("pitched", "скатная", "Нишабли том"),
            opt("mansard", "мансардная", "Мансардали том"), opt("green", "озеленённая", "Яшил том"))),
        field("roof_height", "decimal", "Высота крыши", unit=M, form="5.2"),
        field("roof_structure", "choice", "Конструкция крыши", form="5.3", options=(
            opt("wood", "дерево", "ёғоч"), opt("metal", "металлоконструкция", "металл конструкция"),
            opt("monolith", "монолит", "монолит"), opt("precast", "сборный железобетон", "йиғма темирбетон"))),
        field("roof_cover", "choice", "Покрытие кровли", form="5.4", options=(
            opt("folgoizol", "фалгаизол", "Фалгаизол"), opt("slate", "шифер", "шифер"),
            opt("ruberoid", "рубероид", "рубероид"), opt("profiled", "профнастил", "профнастил"),
            *_others(
                "бошқа турдаги",
                ("metal_tile", "металлочерепица", "metall cherepitsa"),
                ("membrane", "мембрана (ПВХ / ТПО)", "membrana (PVX / TPO)"),
                ("bitumen", "наплавляемый битумный материал", "eritib yopishtiriladigan bitum material"),
                ("other", "другое", "boshqa"),
            ),
        )),
        field("roof_area", "decimal", "Площадь крыши", unit=M2, form="5.5"),
        field("roof_insulation", "choice", "Теплоизоляция кровли: материал", form="5.7", options=(
            opt("mineral_wool", "минеральная вата", "минерал пахта (мм)", uz="mineral paxta"),
            opt("claydite", "керамзит", "керамзит (мм)", uz="keramzit"),
            *_others(
                "бошқа турдаги (мм)",
                ("eps", "пенополистирол", "penopolistirol"),
                ("xps", "экструдированный пенополистирол", "ekstruziyalangan penopolistirol"),
                ("other", "другое", "boshqa"),
            ),
            opt("none", "отсутствует", uz="yo'q"),
        )),
        # В форме толщина пишется в скобках у выбранного материала, отдельной строки нет.
        field("roof_insulation_thickness", "int", "Теплоизоляция кровли: толщина", unit=MM, form="5.7",
              uz="Tom issiqlik himoyasi qalinligi",
              show_if=("roof_insulation", ("mineral_wool", "claydite", "eps", "xps", "other"))),
        field("attic_type", "choice", "Тип чердака", form="5.8", options=(
            opt("open", "открытый", "Очиқ"), opt("ventilated", "проветриваемый", "шамоллатиладиган"),
            opt("closed", "закрытый", "ёпиқ"),
            # В 5.8 формы варианта нет: «нет чердака» печатается в 5.9 значением «йўқ».
            opt("none", "нет чердака", uz="cherdak yo'q"))),
        field("attic_height", "decimal", "Высота чердака", unit=M, form="5.9",
              show_if=("attic_type", ("open", "ventilated", "closed"))),
        field("attic_insulation", "choice", "Теплоудерживающие слои чердака", form="5.10",
              show_if=("attic_type", ("open", "ventilated", "closed")), options=(
                  opt("mineral_wool", "минеральная вата", "минерал пахта"),
                  opt("claydite", "керамзит", "керамзит"),
                  opt("none", "отсутствует", uz="yo'q"),
                  opt("other", "другое", uz="boshqa", other=True))),
        field("attic_insulation_state", "choice", "Состояние теплоудерживающих слоёв", form="5.11",
              show_if=("attic_insulation", ("mineral_wool", "claydite", "other")), options=CONDITION),
        field("roof_leaks", "choice", "Протечки", form="5.12", options=YES_NO_BOR),
    ),
    _section(
        6, "Отопление",
        field("heating_type", "choice", "Тип отопления", form="6.1", options=(
            opt("central", "центральная", "марказий"), opt("local", "локальная", "локал"),
            opt("autonomous", "автономная", "автоном"), opt("individual", "индивидуальная", "индивидуал"),
            opt("handmade", "самодельная", "қўлбола"), opt("none", "отсутствует", "йўқ"))),
        field("heat_elevators", "int", "Тепловые узлы: элеваторы", unit=PCS, form="6.2", rows=(1,), label="sub"),
        field("heat_itp", "int", "Тепловые узлы: ИТП", unit=PCS, form="6.2", rows=(2,), label="sub"),
        field("heating_inlets", "int", "Вводы отопления", unit=PCS, form="6.3"),
        _pipes("heating_pipes", "Трубы отопления", "Isitish tizimi quvurlari", 4, 6, _STEEL_PP,
               ("heating_type", ("central", "local", "autonomous", "individual", "handmade"))),
    ),
    _section(
        7, "Холодное водоснабжение",
        # В форме двухуровневый выбор: «доимий» и «Вақтбай» — подвиды «Марказий».
        field("water_type", "choice", "Тип системы", form="7.1", options=(
            opt("central_constant", "центральная, постоянная", "доимий", uz="markaziy, doimiy"),
            opt("central_scheduled", "центральная, по графику", "Вақтбай (режали вақтда)",
                uz="markaziy, vaqtbay (rejali vaqtda)"),
            opt("carried", "водовозная", "Ташиб ичувчи"), opt("well", "из скважины", "Қудуқ"),
            opt("none", "отсутствует", "Мавжуд эмас"))),
        field("cold_inlets", "int", "Вводы ХВС", unit=PCS, form="7.2"),
        _pipes("cold_pipes", "Трубы холодного водоснабжения", "Sovuq suv quvurlari", 3, 7, _STEEL_PP,
               ("water_type", ("central_constant", "central_scheduled", "carried", "well"))),
    ),
    _section(
        8, "Горячее водоснабжение",
        field("hot_type", "choice", "Тип ГВС", form="8.1", options=(
            opt("central", "центральная", "Марказий"), opt("autonomous", "автономная", "Автоном (алоҳида)"),
            opt("none", "отсутствует", "йўқ"))),
        _pipes("hot_pipes", "Трубы горячего водоснабжения", "Issiq suv quvurlari", 2, 8, _STEEL_PP,
               ("hot_type", ("central", "autonomous"))),
    ),
    _section(
        9, "Канализация",
        field("sewer_type", "choice", "Тип канализации", form="9.1", options=(
            opt("central", "централизованная", "марказлашган"),
            opt("cesspit", "индивидуальный выгреб", "индивидувал ҳандақ", uz="individual handaq"),
            opt("none", "отсутствует", "йўқ"))),
        _pipes("sewer_pipes", "Трубы канализации", "Oqova suv quvurlari", 2, 9, _SEWER_MATERIAL,
               ("sewer_type", ("central", "cesspit"))),
    ),
    _section(
        10, "Газ",
        field("gas", "choice", "Газоснабжение", form="10.1", options=(
            opt("yes", "газифицирован", "газлашган"), opt("no", "не газифицирован", "газлашмаган"))),
        field("gas_inlets", "int", "Точки ввода газа", unit=PCS, form="10.2", show_if=("gas", ("yes",))),
    ),
    _section(
        11, "Электроснабжение",
        field("power_type", "choice", "Электроснабжение: тип", form="11.1", options=(
            opt("central", "центральное", "марказий"),
            opt("autonomous", "автономное (солнечные панели)",
                "автоном (мустақил қуёш панеллари мавжудлиги кW да ёзилади)", uz="avtonom (quyosh panellari)"),
            opt("central_solar", "центральное + солнечные панели", "марказий",
                uz="markaziy + quyosh panellari"))),
        # В форме мощность — это мощность солнечных панелей в строке «автоном».
        field("solar_kw", "decimal", "Мощность солнечных панелей", unit=KW, form="11.1", rows=(2,),
              uz="Quyosh panellari quvvati", show_if=("power_type", ("autonomous", "central_solar"))),
        field("power_inlets", "int", "Точки ввода", unit=PCS, form="11.2"),
        field("power_nonres_kw", "decimal", "Мощность нежилых помещений", unit=KW, form="11.3"),
        field("power_common_kw", "decimal", "Мощность мест общего пользования", unit=KW, form="11.4"),
        field("vru_total", "int", "ВРУ: всего", unit=PCS, form="11.5", rows=(1,), label="sub"),
        field("vru_ok", "int", "ВРУ: в удовлетворительном состоянии", unit=PCS, form="11.5", rows=(2,),
              label="sub"),
        field("vru_bad", "int", "ВРУ: в неудовлетворительном состоянии", unit=PCS, form="11.5", rows=(3,),
              label="sub"),
        field("grsh_total", "int", "ГРЩ: всего", unit=PCS, form="11.6", rows=(1,), label="sub"),
        field("grsh_ok", "int", "ГРЩ: в удовлетворительном состоянии", unit=PCS, form="11.6", rows=(2,),
              label="sub"),
        field("grsh_bad", "int", "ГРЩ: в неудовлетворительном состоянии", unit=PCS, form="11.6", rows=(3,),
              label="sub"),
        field("common_meters", "int", "Счётчики общего пользования", unit=PCS, form="11.7"),
    ),
    _section(
        12, "Зелёные зоны",
        # «Всего» в форме есть, в каталоге не было: считается по разбивке (строка 2 — «шу жумладан»).
        field("planted_total", "int", "Высаженные саженцы: всего", unit=PCS, form="12.1", rows=(1, 2),
              computed=True, share="greenery"),
        field("planted_conifer", "int", "Высаженные саженцы: хвойные", unit=PCS, form="12.1", rows=(3,),
              label="own", share="greenery", uz="Ekilgan igna bargli daraxtlar soni"),
        field("planted_leaf", "int", "Высаженные саженцы: лиственные", unit=PCS, form="12.1", rows=(4,),
              label="own", share="greenery", uz="Ekilgan yaproq bargli daraxtlar soni"),
        field("planted_shrub", "int", "Высаженные саженцы: кустарники", unit=PCS, form="12.1", rows=(5,),
              label="own", share="greenery", uz="Ekilgan butalar soni"),
        field("existing_total", "int", "Существующие деревья и кустарники: всего", unit=PCS, form="12.2",
              rows=(1, 2), computed=True, share="greenery"),
        field("existing_conifer", "int", "Существующие деревья: хвойные", unit=PCS, form="12.2", rows=(3,),
              label="own", share="greenery", uz="Mavjud igna bargli daraxtlar soni"),
        field("existing_leaf", "int", "Существующие деревья: лиственные", unit=PCS, form="12.2", rows=(4,),
              label="own", share="greenery", uz="Mavjud yaproq bargli daraxtlar soni"),
        field("existing_shrub", "int", "Существующие кустарники", unit=PCS, form="12.2", rows=(5,),
              label="own", share="greenery", uz="Mavjud butalar soni"),
        field("green_plots_area", "decimal", "Зелёные площадки", unit=M2, form="12.3", share="greenery"),
        field("perennials", "int", "Многолетние цветы", unit=PCS, form="12.4", share="greenery"),
        field("annuals", "int", "Однолетние цветы", unit=PCS, form="12.5", share="greenery"),
    ),
    _section(
        13, "Пожарная автоматика",
        field("fire_alarm", "choice", "Пожарная сигнализация", form="13.1", options=YES_NO_MAVJUD),
        field("fire_notify", "choice", "Оповещение и эвакуация", form="13.2", options=YES_NO_MAVJUD),
        field("fire_hydrants", "choice", "Внутренние пожарные краны", form="13.3", options=YES_NO_MAVJUD),
        field("smoke_removal", "choice", "Дымоудаление", form="13.4", options=YES_NO_MAVJUD),
        field("fire_auto", "choice", "Автоматическое пожаротушение", form="13.5", options=YES_NO_MAVJUD),
    ),
)
