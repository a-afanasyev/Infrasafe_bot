#!/bin/sh
set -eu
umask 077

: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}"
: "${POSTGRES_USER:?POSTGRES_USER is required}"
: "${POSTGRES_DB:?POSTGRES_DB is required}"
# RUNTIME_DB_HOST — обязательная переменная, разная для docker-compose.yml
# (postgres) и docker-compose.profk.yml (uk-postgres), см. план PR-7 §1б.
# Никогда не хардкодить "postgres" здесь — иначе на profk сгенерированные
# DATABASE_URL не резолвятся / рискуют коллизировать с чужой БД на shared сети.
: "${RUNTIME_DB_HOST:?RUNTIME_DB_HOST is required (differs per compose file)}"
test -w /output || { echo "provision_roles: /output not writable" >&2; exit 1; }

# Пароли генерируются ЗДЕСЬ, внутри контейнера — не на хосте и не через `-e
# migrator_pw=...` в вызывающей команде. Хостовая генерация + передача через
# `docker compose run -e VAR=value` светит пароль в plaintext в `ps aux`/
# `/proc/<pid>/cmdline` на хосте на всё время инвокации (виден любому
# локальному пользователю без прав root/docker-группы) и в `docker inspect
# <container>` → `Config.Env` на время жизни контейнера. Генерация внутри
# контейнера убирает оба пути: пароли никогда не существуют как host-side
# shell-переменные или CLI-аргументы.
#
# НЕ `openssl rand` — эмпирически проверено (`docker run --rm postgres:15-alpine
# sh -c 'openssl rand -hex 32'`): образ содержит только libssl3/libcrypto3, БЕЗ
# самого CLI-бинаря openssl ("openssl: not found", exit 127) — `set -eu` уронил
# бы весь скрипт на первой же строке генерации, ДО записи staging и ДО psql.
# `/dev/urandom` + `od`/`tr` (busybox, гарантированно есть в образе) — источник
# энтропии тот же (ядро), просто без зависимости от отсутствующего пакета.
# hex, не base64: base64-алфавит включает `/+=`, которые ломают/искажают
# разбор `postgresql://user:PASSWORD@host/db` URI (см. write_staging ниже) —
# hex (0-9a-f) не содержит спецсимволов URI вообще.
gen_hex32 () {
  head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n'
}
migrator_pw=$(gen_hex32)
bot_pw=$(gen_hex32)
api_pw=$(gen_hex32)
access_pw=$(gen_hex32)

# Явная таблица соответствий (НЕ шаблон имени) — migrate использует роль
# uk_migrator, а не "uk_migrate_runtime".
write_staging () {
  # $1=выходной файл-суффикс  $2=реальное имя Postgres-роли  $3=пароль
  tmp="/output/.env.${1}.tmp.$$"
  printf 'DATABASE_URL=postgresql://%s:%s@%s:5432/%s\n' \
    "$2" "$3" "$RUNTIME_DB_HOST" "$POSTGRES_DB" > "$tmp"
  mv "$tmp" "/output/.env.${1}.staging"
}

# Staging пишется ДО psql: если что-то помешает записи после успешного psql
# (диск полон и т.п.), БД уже приняла новые пароли, а файлов с ними нет —
# поэтому проверяем запись первой, пока в БД ещё старые пароли.
write_staging migrate uk_migrator       "$migrator_pw"
write_staging bot     uk_bot_runtime    "$bot_pw"
write_staging api     uk_api_runtime    "$api_pw"
write_staging access  uk_access_runtime "$access_pw"

# -h postgres — намеренно ЛИТЕРАЛЬНЫЙ, не $RUNTIME_DB_HOST (см. план PR-7:
# «Собственное соединение provision-roles можно оставить -h postgres буквально
# в обоих файлах»). Это безопасно ТОЛЬКО потому, что сервис называется именно
# "postgres" в обоих docker-compose.yml/docker-compose.profk.yml, а Compose
# автоматически резолвит имя сервиса как DNS-алиас в пределах СВОЕЙ сети —
# гарантия работает исключительно внутри `docker compose run`. Вне Compose
# (ручной `docker run` на произвольной сети без алиаса "postgres") хост
# "postgres" falls through на публичный DNS и резолвится в непредсказуемый
# внешний адрес вместо явной ошибки "host not found" — эмпирически
# воспроизведено при adhoc-тестировании этого скрипта. Это НЕ путь
# эксплуатации в штатном деплое (только `docker compose run` документирован
# как способ вызова), но если когда-нибудь потребуется гонять этот скрипт вне
# Compose — сначала завести отдельный явный host-параметр, не полагаться на
# то, что "postgres" останется недостижимым по случайности сетевой топологии.
export PGPASSWORD="$POSTGRES_PASSWORD"
psql -v ON_ERROR_STOP=1 -h postgres -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  -v migrator_pw="$migrator_pw" -v bot_pw="$bot_pw" \
  -v api_pw="$api_pw" -v access_pw="$access_pw" \
  -f /provision_roles.sql

# Дошли досюда — только если psql (ON_ERROR_STOP=1 + set -e) реально успешен:
# БД уже приняла ВСЕ 4 новых пароля ОДНОЙ транзакцией (BEGIN...COMMIT в
# provision_roles.sql). Переводим staging → live; каждый отдельный mv атомарен,
# но цикл из четырёх — НЕ атомарен как единое целое. Если процесс прервётся
# посередине, восстановление — НЕ доделывать вручную, а повторить весь прогон
# provision-roles целиком (ALTER ROLE ... PASSWORD и запись staging идемпотентны).
for role in migrate bot api access; do
  mv "/output/.env.${role}.staging" "/output/.env.${role}"
done

echo "provision_roles: done"
