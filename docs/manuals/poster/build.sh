#!/usr/bin/env bash
# Пересобирает листовку: resident-poster.html → resident-poster.pdf (A4, RU+UZ)
# → resident-poster-2xA5.pdf (обе страницы как A5 на альбомном A4, линия реза по центру).
set -euo pipefail
cd "$(dirname "$0")"
CHROME="${CHROME:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

"$CHROME" --headless=new --disable-gpu --no-pdf-header-footer --virtual-time-budget=8000 \
  --print-to-pdf="$PWD/resident-poster.pdf" "file://$PWD/resident-poster.html" 2>/dev/null

cat > "$TMP/cut.html" <<'EOF'
<!doctype html><html><head><style>@page{size:A4 landscape;margin:0}html,body{margin:0}
.c{position:absolute;left:50%;top:0;height:210mm;border-left:0.3mm dashed #9aa59d}
.s{position:absolute;left:calc(50% - 2.2mm);top:1.5mm;font-size:9pt;color:#9aa59d}</style></head>
<body><div class="c"></div><div class="s">✂</div></body></html>
EOF
"$CHROME" --headless=new --disable-gpu --no-pdf-header-footer \
  --print-to-pdf="$TMP/cut.pdf" "file://$TMP/cut.html" 2>/dev/null

uvx --from pypdf python - "$TMP/cut.pdf" <<'EOF'
import sys
from pypdf import PdfReader, PdfWriter, Transformation
src = PdfReader('resident-poster.pdf').pages
base = PdfReader(sys.argv[1]).pages[0]
W, H = float(base.mediabox.width), float(base.mediabox.height)
assert W > H and len(src) == 2, 'ожидается 2 страницы A4 и альбомная подложка'
k = H / float(src[0].mediabox.height)  # A4 -> A5
for i, pg in enumerate(src):
    base.merge_transformed_page(pg, Transformation().scale(k).translate(i * W / 2, 0))
out = PdfWriter()
out.add_page(base)
out.write('resident-poster-2xA5.pdf')
EOF
echo "ok: resident-poster.pdf, resident-poster-2xA5.pdf"
