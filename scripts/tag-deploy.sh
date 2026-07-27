#!/usr/bin/env bash
# Метка раскатки: annotated-тег на коммит, который реально уехал на прод.
#
# Зачем (AUD3-38 / AUD5-PRAC-3). Деплой здесь — это `git pull` на хосте, поэтому
# «что сейчас в проде» существует только как HEAD рабочей копии на машине. Тег
# один (`phase2b-deployment`, 2026-05), и вопрос «с чего откатываться» каждый раз
# решался через ssh. Память проекта отдельно фиксирует этот класс: прод-указатель
# дрейфует, проверять надо ssh, а не память.
#
# Использование (локально, ПОСЛЕ успешной раскатки и проверки):
#   scripts/tag-deploy.sh profk            # тег на текущий HEAD
#   scripts/tag-deploy.sh profk <commit>   # тег на конкретный коммит
#   scripts/tag-deploy.sh profk --push     # сразу отправить в origin
#
# Имя: <host>-YYYY-MM-DD, при второй раскатке за день добавляется .2, .3 …
# Тело: список коммитов от предыдущего тега этого же хоста — то есть ровно то,
# что уехало этой раскаткой.
set -euo pipefail

HOST="${1:-}"
if [[ -z "$HOST" || "$HOST" == -* ]]; then
    echo "usage: $0 <profk|infrasafe> [commit] [--push]" >&2
    exit 2
fi
shift

PUSH=false
COMMIT=HEAD
for arg in "$@"; do
    case "$arg" in
        --push) PUSH=true ;;
        *) COMMIT="$arg" ;;
    esac
done

SHA=$(git rev-parse --verify "$COMMIT^{commit}")
DATE=$(git show -s --format=%cd --date=format:%Y-%m-%d "$SHA")

# Дата берётся у КОММИТА, не «сегодня»: тег ставят и на следующий день после
# ночной раскатки, и тогда «сегодня» соврало бы о том, что уехало.
BASE="${HOST}-${DATE}"
NAME="$BASE"
n=2
while git rev-parse -q --verify "refs/tags/$NAME" >/dev/null; do
    NAME="${BASE}.${n}"
    n=$((n + 1))
done

PREV=$(git tag --list "${HOST}-*" --sort=-creatordate | head -1)
if [[ -n "$PREV" ]]; then
    RANGE="${PREV}..${SHA}"
    HEADER="Раскатано на ${HOST} (с ${PREV}):"
else
    RANGE="${SHA}~20..${SHA}"
    HEADER="Раскатано на ${HOST} (предыдущего тега нет, последние 20 коммитов):"
fi

BODY=$(git log --no-merges --format='  %h %s' "$RANGE" 2>/dev/null || echo "  (история недоступна)")

git tag -a "$NAME" "$SHA" -m "$HEADER" -m "$BODY"
echo "тег создан: $NAME → ${SHA:0:8}"

if $PUSH; then
    git push origin "$NAME"
    echo "отправлен в origin"
else
    echo "отправить: git push origin $NAME"
fi
