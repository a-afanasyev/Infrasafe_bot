# frontend/CLAUDE.md — бренды (InfraSafe / PROFK)

- Одна кодовая база; бренд = build-arg `VITE_BRAND` (`infrasafe` дефолт / `profk`). Фичу пишешь один раз — оба бренда получают.
- Брендо-слой (только тут расходятся): `src/brand/brand.ts`, блок `html[data-brand="profk"]` в `src/index.css`, `public/profk-*` + `manifest.profk.json`, `transformIndexHtml` в `vite.config.ts`.
- **Только токены**: в компонентах никакого сырого бренд-hex/лого — `bg-accent`, `var(--accent)`, `rgba(var(--accent-rgb),α)`, `brand.logoMark`. Иначе PROFK молча разъедется; CI-гейт `npm run guard:brand` ловит нарушения (легитимные палитры помечать `// brand-allow`).
- Перед PR собирать обе ветви: `npm run build && npm run build:profk`. Локально: `npm run dev` / `npm run dev:profk`.
