#!/bin/sh
# Перегенерировать initData (живёт минуты) и запустить сценарий записи.
set -e
J=/Users/andreyafanasyev/.claude/jobs/0653a80b/tmp
umask 077
docker exec -i -e DEMO_LANG="${DEMO_LANG:-ru}" uk-management-bot python - < "$J/initdata.py" > "$J/initdata.json"
cd "$J/pp"
node "$@"
