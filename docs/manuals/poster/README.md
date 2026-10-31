# Листовка для жителей (расклейка)

> _Последнее редактирование: 2026-10-31_

Одностраничник по инструкции жителя: QR на `@profkbot`, 3 шага регистрации, документы,
что умеет бот, телефон диспетчера.

| Файл | Что это |
|---|---|
| `resident-poster.pdf` | A4, стр. 1 — RU, стр. 2 — UZ |
| `resident-poster-2xA5.pdf` | обе версии как A5 на одном альбомном A4, линия реза по центру |
| `resident-poster.html` | исходник (обе страницы) |
| `build.sh` | пересборка обоих PDF (Chrome headless + `uvx pypdf`) |

Печатать в масштабе 100% («Фактический размер»).

**Данные со стороны прода — сверять перед перепечаткой:** телефон диспетчера взят из
`GET https://profk.uz/uk/api/v2/public/board-config` → `contacts.dispatch_phone`; имя бота —
`VITE_BOT_USERNAME` в `docker-compose.profk.yml`.

Ассеты (всё локально — шрифты встраиваются в PDF как TrueType, иконки векторные):

- `profk-logo.png` — официальный логотип из брендбука (`ProFK/Big_logo.png`, обрезан);
- `qr.svg` — `https://t.me/profkbot`, сгенерирован `segno`;
- `fonts/` — Montserrat и Open Sans (SIL OFL 1.1, через @fontsource 5.0.19);
- `icons/` — [Twemoji](https://github.com/jdecked/twemoji) 15.1.0, CC-BY 4.0.
