"""Агрегатор раздела «Жители» — монтируется в api/main.py под /api/v2/residents.

Разбит по типу операций (как addresses по сущностям): чтения в residents.py,
мутации и верификация приедут отдельными модулями. Порядок include важен: в
residents.py статический /stats объявлен до динамического /{resident_id}.
"""
from uk_management_bot.api.residents import residents

# Базой агрегатора служит роутер чтений, а не пустой APIRouter(): у списка путь
# "" (корень раздела), а FastAPI запрещает include маршрута с пустым путём в
# пустой префикс («Prefix and path cannot be both empty»). Альтернатива — путь
# "/" у списка — дала бы 307-редирект на каждый GET /api/v2/residents через
# edge. Модули мутаций/верификации включаются поверх этого роутера.
router = residents.router
