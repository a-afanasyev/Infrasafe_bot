#!/usr/bin/env bash
# Сборка PDF-инструкций контроля доступа из Markdown.
# Требует: pandoc + chrome-headless-shell (puppeteer/playwright) или Chrome for Testing.
# Запуск: docs/access-control/guides/build_pdf.sh
set -euo pipefail
cd "$(dirname "$0")"

# 1) Найти chrome-headless-shell (надёжнее системного Chrome для print-to-pdf на macOS).
CHS="${CHROME_HEADLESS_SHELL:-}"
if [[ -z "$CHS" ]]; then
  CHS="$(find "$HOME/.cache/puppeteer" "$HOME/Library/Caches/ms-playwright" \
        -maxdepth 7 -name 'chrome-headless-shell' -type f 2>/dev/null | sort -V | tail -1 || true)"
fi
if [[ -z "$CHS" ]]; then
  echo "chrome-headless-shell не найден. Задайте CHROME_HEADLESS_SHELL=/путь или установите:" >&2
  echo "  npx puppeteer browsers install chrome-headless-shell" >&2
  exit 1
fi
command -v pandoc >/dev/null || { echo "Нужен pandoc" >&2; exit 1; }

mkdir -p build pdf

render() { # md  title  outpdf
  pandoc "$1" -f gfm -t html5 --standalone --embed-resources \
    --metadata title="$2" --css build/style.css -o "build/${1%.md}.html"
  "$CHS" --no-sandbox --disable-gpu --no-pdf-header-footer --virtual-time-budget=20000 \
    --print-to-pdf="pdf/$3" "file://$PWD/build/${1%.md}.html" 2>/dev/null
  echo "  pdf/$3"
}

render README.md   "Контроль доступа — обзор" "00_Обзор.pdf"
render resident.md "Инструкция жителя"         "01_Житель.pdf"
render operator.md "Инструкция охраны"         "02_Охрана.pdf"
render manager.md  "Инструкция менеджера"       "03_Менеджер.pdf"

# Общий файл со сквозным оглавлением
pandoc README.md resident.md operator.md manager.md -f gfm -t html5 --standalone --embed-resources \
  --metadata title="Контроль доступа — полные инструкции" --toc --toc-depth=2 \
  --css build/style.css -o build/combined.html
"$CHS" --no-sandbox --disable-gpu --no-pdf-header-footer --virtual-time-budget=20000 \
  --print-to-pdf="pdf/Контроль_доступа_инструкции.pdf" "file://$PWD/build/combined.html" 2>/dev/null
echo "  pdf/Контроль_доступа_инструкции.pdf"
echo "Готово."
