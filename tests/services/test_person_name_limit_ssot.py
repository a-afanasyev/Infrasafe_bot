"""Лимит длины ФИО обязан совпадать в бэкенде и в UI.

Правило живёт в двух языках: `utils/person_name.py` (истина, даёт 422) и
`frontend/src/utils/personName.ts` (чтобы менеджер увидел ошибку до запроса).
Разъехавшись, они дают худший из исходов — форму, которую можно заполнить, но
нельзя отправить, причём без внятного объяснения.

Гейт двусторонний: он падает и когда TS-константу подняли, и когда её унесли
или переименовали.
"""
import re
from pathlib import Path

from uk_management_bot.utils.person_name import MAX_FULL_NAME_LEN

TS_CANON = Path(__file__).resolve().parents[2] / "frontend/src/utils/personName.ts"


def test_ts_mirror_declares_the_same_limit():
    source = TS_CANON.read_text(encoding="utf-8")
    match = re.search(r"export const MAX_FULL_NAME_LEN\s*=\s*(\d+)", source)
    assert match, f"{TS_CANON.name}: константа MAX_FULL_NAME_LEN не найдена"
    assert int(match.group(1)) == MAX_FULL_NAME_LEN


def test_no_locale_hardcodes_the_number():
    """Тексты обязаны подставлять предел, а не называть его цифрой.

    Локаль с зашитым числом — третья копия правила, и она молча устареет при
    смене лимита. Плейсхолдер разный по стекам (`{{max}}` у i18next,
    `{max_len}` у бота), общее требование — чтобы цифры в тексте не было.
    """
    import json

    root = Path(__file__).resolve().parents[2]
    checked = 0
    for path, key_path, placeholder in (
        (root / "uk_management_bot/config/locales/ru.json",
         ("user_rename", "error_too_long"), "{max_len}"),
        (root / "uk_management_bot/config/locales/uz.json",
         ("user_rename", "error_too_long"), "{max_len}"),
    ):
        node = json.loads(path.read_text(encoding="utf-8"))
        for key in key_path:
            node = node[key]
        assert placeholder in node, f"{path.name}: нет плейсхолдера — {node}"
        assert not re.search(r"\d", node.replace(placeholder, "")), f"{path.name}: {node}"
        checked += 1
    assert checked == 2
