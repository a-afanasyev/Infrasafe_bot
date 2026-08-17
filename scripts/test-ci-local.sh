#!/usr/bin/env bash
# Канонический локальный прогон бэкенд-тестов, эквивалентный CI-джобе
# `backend-tests`. Запускать через `make test-ci`.
#
# Зачем отдельный харнесс, если в CLAUDE.md написано `docker exec uk-management-bot pytest`.
# Тот способ — быстрая петля, а не эталон, и расходится с CI сразу по трём причинам:
#
#   1. образ печётся (`COPY`, без bind-mount), поэтому `docker exec` гоняет код
#      на момент последней сборки, а не рабочего дерева;
#   2. в живой контейнер во время отладки попадают файлы через `docker cp` —
#      после этого его содержимое вообще не соответствует ни одному коммиту;
#   3. образ сознательно НЕ содержит конфигурационных файлов репозитория
#      (`docker-compose*.yml`, `frontend/nginx.conf`) — это деплой-описания, не
#      рантайм приложения. А config-гейты (`test_compose_secret_env_ssot.py`,
#      `test_health_contract.py`) читают именно их — в контейнере они падали
#      FileNotFoundError при полностью зелёном CI. Это дефект харнесса, а не
#      тестов: они проверяют файлы репо, значит харнесс обязан их предоставить.
#      Здесь такие файлы монтируются read-only ПОФАЙЛОВО — складывать их в
#      образ было бы неверно, а монтировать каталог целиком означало бы
#      перекрыть код из образа и вернуть подмену из пункта 1.
#
# Что воспроизводится один-в-один с `ci.yml`:
#   * тот же образ, что и прод-бот (сборка из текущего дерева);
#   * пустая БД postgres:15-alpine + redis:7-alpine, те же dummy-креды;
#   * `alembic upgrade head` + `alembic check` (дрейф-гейт);
#   * два РАЗДЕЛЬНЫХ прогона pytest — у сьютов разные conftest'ы, смешивать
#     нельзя: `tests/api` поднимает in-memory aiosqlite, `uk_management_bot` —
#     postgres;
#   * `INFRASAFE_WEBHOOK_ENABLED=true` ТОЛЬКО на втором прогоне (в CI он
#     step-scoped: outbox-гейт должен пройти реальный путь эмиссии, а unit-сьют
#     обязан остаться с выключенным вебхуком).
#
# Coverage-ratchet сюда НЕ вынесен намеренно: floor'ы в CI подняты по замеру
# ubuntu-раннера, локальный прогон их только зашумит. Гейт живёт в CI.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

IMAGE="uk-app:ci-local"
NET="uk-ci-net"
PG="uk-ci-pg"
REDIS="uk-ci-redis"

# Креды намеренно совпадают с ci.yml: одноразовые контейнеры, никаких реальных
# секретов. Локальный `uk-postgres` НЕ используется — прогон не должен зависеть
# от состояния рабочей БД и не должен её трогать.
PG_DSN="postgresql://uk_bot:postgres@${PG}:5432/uk_management"
REDIS_DSN="redis://${REDIS}:6379/0"

ENV_ARGS=(
  -e "DATABASE_URL=${PG_DSN}"
  -e "REDIS_URL=${REDIS_DSN}"
  -e PYTHONPATH=/app
  -e BOT_TOKEN="ci:dummy-token"
  -e JWT_SECRET="ci-dummy-secret"
  -e INVITE_SECRET="ci-dummy-secret"
  -e UK_WEBHOOK_SECRET="ci-dummy-secret"
  -e INFRASAFE_WEBHOOK_SECRET="ci-dummy-secret"
  -e ADMIN_PASSWORD="ci-dummy-admin-pw-0123456"
  -e DEBUG=true
)

# Конфиг-файлы репозитория, которые читают config-гейты. Пофайлово и только
# нужные: монтирование каталога перекрыло бы код из образа.
#   docker-compose{,.profk,.media}.yml — tests/services/test_compose_secret_env_ssot.py
#   frontend/nginx.conf               — tests/api/test_health_contract.py (PENT-F17)
#   docs/security/security.txt        — tests/services/test_security_txt.py (PENT-F14)
CONFIG_MOUNTS=(
  -v "${ROOT}/docker-compose.yml:/app/docker-compose.yml:ro"
  -v "${ROOT}/docker-compose.profk.yml:/app/docker-compose.profk.yml:ro"
  -v "${ROOT}/docker-compose.media.yml:/app/docker-compose.media.yml:ro"
  -v "${ROOT}/frontend/nginx.conf:/app/frontend/nginx.conf:ro"
  -v "${ROOT}/docs/security/security.txt:/app/docs/security/security.txt:ro"
  # BUG-132: контрактный тест сниффера читает ФАЙЛЫ соседнего сервиса — общий
  # модуль невозможен, media отдельный контейнер. В образе бота media_service нет,
  # а в CI-джобе `backend-tests` есть полный чекаут, поэтому без этих двух строк
  # эталон расходился бы с CI ровно наоборот обычного: локально красно, в CI зелено.
  -v "${ROOT}/media_service/app/api/v1/media.py:/app/media_service/app/api/v1/media.py:ro"
  -v "${ROOT}/media_service/app/core/config.py:/app/media_service/app/core/config.py:ro"
  # Канон специализаций фронт держит своей копией (формы не ходят в API за
  # списком), и парити-тест сверяет её с бэкендом. В образе бота frontend/ нет,
  # в CI-джобе backend-tests — полный чекаут, поэтому там строка не нужна.
  -v "${ROOT}/frontend/src/constants/specializations.ts:/app/frontend/src/constants/specializations.ts:ro"
)

cleanup() {
  docker rm -f "$PG" "$REDIS" >/dev/null 2>&1 || true
  docker network rm "$NET" >/dev/null 2>&1 || true
}

if [ "${KEEP_STACK:-}" != "1" ]; then
  trap cleanup EXIT
fi

echo "==> сборка образа из текущего дерева ($IMAGE)"
docker build -q -t "$IMAGE" . >/dev/null

echo "==> одноразовые postgres + redis"
cleanup
docker network create "$NET" >/dev/null
docker run -d --name "$PG" --network "$NET" \
  -e POSTGRES_DB=uk_management -e POSTGRES_USER=uk_bot -e POSTGRES_PASSWORD=postgres \
  postgres:15-alpine >/dev/null
docker run -d --name "$REDIS" --network "$NET" redis:7-alpine >/dev/null

for _ in $(seq 1 60); do
  if docker exec "$PG" pg_isready -U uk_bot -d uk_management >/dev/null 2>&1; then break; fi
  sleep 1
done
docker exec "$PG" pg_isready -U uk_bot -d uk_management >/dev/null \
  || { echo "postgres не поднялся" >&2; exit 1; }

# `alembic/env.py` в образ не копируется (боту alembic не нужен — миграции гоняет
# отдельный сервис `migrate`), поэтому для этого шага каталог монтируется.
echo "==> alembic upgrade head + check (дрейф-гейт)"
docker run --rm --network "$NET" -v "${ROOT}/alembic:/app/alembic:ro" \
  "${ENV_ARGS[@]}" --entrypoint sh "$IMAGE" -c \
  'python -m alembic upgrade head >/dev/null && python -m alembic check'

# В CI оба прогона идут в одном workspace и копят покрытие в общий `.coverage`
# (второй — с `-a`). Здесь прогоны в РАЗНЫХ контейнерах, поэтому файл данных
# выносится на смонтированный том — иначе шаг ratchet ниже видел бы только
# половину покрытия и «локально зелено» опять значило бы не то же, что в CI.
COVDIR="$(mktemp -d)"
chmod 777 "$COVDIR"
trap 'rm -rf "$COVDIR"' EXIT
COV_ARGS=(-v "${COVDIR}:/covdata" -e COVERAGE_FILE=/covdata/.coverage)

echo "==> сьют 1/2: pytest -q (uk_management_bot, postgres)"
docker run --rm --network "$NET" "${ENV_ARGS[@]}" "${CONFIG_MOUNTS[@]}" "${COV_ARGS[@]}" \
  --entrypoint sh "$IMAGE" -c 'coverage run -m pytest -q'

echo "==> сьют 2/2: pytest -q tests/api tests/services (sqlite-conftest'ы)"
docker run --rm --network "$NET" "${ENV_ARGS[@]}" "${CONFIG_MOUNTS[@]}" "${COV_ARGS[@]}" \
  -e INFRASAFE_WEBHOOK_ENABLED=true \
  --entrypoint sh "$IMAGE" -c 'coverage run -a -m pytest -q tests/api tests/services'

# Джоба CI `backend-tests` состоит НЕ только из двух прогонов pytest — в ней есть
# ещё и этот шаг. Без него «локально зелено» значило бы не то же, что в CI, и
# эталон переставал быть эталоном (ровно так П4 уехал в CI с разошедшимся
# снапшотом: docstring эндпоинта попал в `description` публичного контракта).
echo "==> OpenAPI-снапшот (гейт публичного контракта)"
docker run --rm --network "$NET" "${ENV_ARGS[@]}" "${CONFIG_MOUNTS[@]}" \
  -v "${ROOT}/docs/tech/openapi.json:/app/docs/tech/openapi.json:ro" \
  -v "${ROOT}/scripts/dump_openapi.py:/app/scripts/dump_openapi.py:ro" \
  --entrypoint sh "$IMAGE" -c 'python3 scripts/dump_openapi.py --check'

# Второй шаг джобы `backend-tests`, которого здесь не хватало. Поймано в П7:
# удаление ~980 строк мёртвого кода двигает знаменатель покрытия, и без этого
# шага изменение уехало бы в CI вслепую.
echo "==> coverage floor (ratchet: core / handlers)"
docker run --rm "${ENV_ARGS[@]}" "${COV_ARGS[@]}" --entrypoint sh "$IMAGE" -c '
  # именно строка TOTAL: последней в выводе идёт «N empty files skipped.»
  core=$(coverage report --omit="uk_management_bot/handlers/*" | awk "/^TOTAL/{print \$NF}")
  hnd=$(coverage report --include="uk_management_bot/handlers/*" | awk "/^TOTAL/{print \$NF}")
  echo "core=${core} (floor 69%) · handlers=${hnd} (floor 27.5%)"
  coverage report --omit="uk_management_bot/handlers/*" --fail-under=69 >/dev/null \
    || { echo "core ниже floor 69%"; exit 1; }
  coverage report --include="uk_management_bot/handlers/*" --fail-under=27.5 >/dev/null \
    || { echo "handlers ниже floor 27.5%"; exit 1; }
  echo "оба floor пройдены"'

echo "==> оба сьюта, OpenAPI-гейт и coverage-floor зелёные"
