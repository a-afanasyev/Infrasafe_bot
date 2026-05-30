# Secret Rotation Checklist — 2026-05-29

Источник: `docs/security-audit-2026-05-29.md` (находки C-1, C-2, H-1).
Все перечисленные значения были закоммичены в git и присутствуют в **git history**
(затирание рабочего дерева в коммите `1248919` НЕ устраняет экспозицию).
**Каждый секрет ниже считается скомпрометированным и подлежит ротации.**

Утечка-источник в дереве (теперь вычищен): `docs/Archive/Old_Docs/main.file`
(+ `ADMIN_PASSWORD` дублировался в `docs/Archive/Deployment/*`, `docs/audit/2026-05-20-backlog.md`, `docs/SECURITY_AUDIT_FINAL.md`).

---

## 1. BOT_TOKEN — токен основного бота (`infrasafebot`)
- **Серьёзность:** CRITICAL — полный захват бота (чтение чатов, отправка от имени сервиса, смена webhook).
- **Где утекло:** git history (≈4 коммита), `docs/Archive/Old_Docs/main.file`.
- **Где используется:** прод `.env` → `BOT_TOKEN`; читается на старте бота (aiogram `Bot(token=...)`). Ссылки-плейсхолдеры: `.env.example`, `env.example`, `docker-compose*.unified.yml`, `media_service/docker-compose*.yml` (`${BOT_TOKEN}`).
- **Ротация:** @BotFather → выбрать бота → **API Token → Revoke current token** → получить новый → обновить `BOT_TOKEN` в прод `.env` → рестарт контейнера бота. Старый токен умирает мгновенно.

## 2. MEDIA_BOT_TOKEN — токен медиа-бота
- **Серьёзность:** CRITICAL — захват медиа-бота.
- **Где утекло:** git history, `main.file`.
- **Где используется:** прод `.env` → `MEDIA_BOT_TOKEN`; media-аплоады/скачивание через отдельного бота. Плейсхолдеры в `.env.example`, `docker-compose*.unified.yml`, `media_service/*`.
- **Ротация:** @BotFather для медиа-бота → Revoke → новый токен → обновить `.env`/compose медиа-сервиса → рестарт.

## 3. INVITE_SECRET — ключ подписи invite-токенов
## 4. JWT_SECRET — ключ подписи JWT дашборда (сейчас fallback на INVITE_SECRET)
- **Серьёзность:** CRITICAL — обход аутентификации веб-панели. Зная `INVITE_SECRET`, можно подделать JWT с `roles:["manager"]` для любого `user_id` (`api/auth/service.py:19` берёт `JWT_SECRET || INVITE_SECRET`) и подделать invite-токены.
- **Где утекло:** git history, `main.file` (`INVITE_SECRET`).
- **Где используется:** `uk_management_bot/config/settings.py`, `uk_management_bot/api/auth/service.py` (JWT HS256), `uk_management_bot/services/invite_service.py` (HMAC invite).
- **Ротация:** сгенерировать **два независимых** значения: `openssl rand -hex 32` (×2) → задать в прод `.env` **раздельно** `INVITE_SECRET=` и `JWT_SECRET=` (прекратить полагаться на fallback) → рестарт api+бота.
  **Побочный эффект (намеренный):** инвалидируются все активные access/refresh JWT (пользователи логинятся заново) и все ещё не использованные invite-ссылки.

## 5. ADMIN_PASSWORD — пароль админ/веб-аутентификации
- **Серьёзность:** HIGH — реальное значение слабое (8 символов после декодирования; см. SEC-083).
- **Где утекло:** git history + `main.file` + (вычищены) `docs/Archive/Deployment/{DEPLOYMENT_FIXES,SERVER_SETUP_GUIDE}.md`, `docs/audit/2026-05-20-backlog.md`, `docs/SECURITY_AUDIT_FINAL.md`.
- **Где используется:** `config/settings.py`, `handlers/health.py`, `api/auth` (`secrets.compare_digest`), `production.env.example`.
- **Ротация:** новый сильный пароль `openssl rand -base64 24` (≥16 символов) → обновить `ADMIN_PASSWORD` в прод `.env` → рестарт api. Дополнительно закрыть SEC-083 (декодировать `unquote()` до проверки длины, поднять минимум до 16).

## 6. POSTGRES_PASSWORD — пароль БД роли `uk_bot` (основная БД)
- **Серьёзность:** HIGH — прямой доступ к проду БД при сетевой достижимости.
- **Где утекло:** в `main.file` значение было `uk_bot_password` (dev-плейсхолдер); деплой-доки связывали прод-пароль БД с `ADMIN_PASSWORD` (`Inf@$afe`). Точное прод-значение неизвестно (сервер сейчас не трогаем) — **ротировать независимо от того, какое из двух**.
- **Где используется:** `docker-compose*.yml` (`POSTGRES_PASSWORD`, `DATABASE_URL`), `alembic/env.py`, прод `.env`.
- **Ротация:** на проде `ALTER ROLE uk_bot WITH PASSWORD '<new>';` → обновить `POSTGRES_PASSWORD` и `DATABASE_URL` в прод `.env` → рестарт api+бота (требует согласованного рестарта). Спецсимволы в URL — URL-encode.

## 7. Медиа-сервис (если развёрнут) — БД/Redis/pgAdmin
- **Серьёзность:** MEDIUM/LOW (захардкоженные `media_password`, `admin123`; Redis без пароля).
- **Где утекло:** `media_service/docker-compose.yml` / `.dev.yml` (захардкожены), `media_service/.env.example`, README.
- **Где используется:** `media_service/docker-compose*.yml` — после хардненинга аудита требуют env-переменных: `POSTGRES_PASSWORD`/`MEDIA_DB_PASSWORD`, `REDIS_PASSWORD`, `PGADMIN_DEFAULT_PASSWORD`.
- **Ротация/установка:** завести **gitignored** `media_service/.env` с новыми значениями (`openssl rand -base64 24` каждое); без них compose теперь падает с явным сообщением. Если `media_password`/`admin123` когда-либо использовались в реальном деплое — сменить пароли в media-БД и pgAdmin.

## 8. WEBHOOK_SECRET / INFRASAFE HMAC (общий с InfraSafe) — ПРОВЕРИТЬ
- **Статус:** в аудированном утёкшем файле **не обнаружен**. Используется в `api/webhooks/{router,security,replay}.py`, `services/webhook_sender.py`.
- **Действие:** убедиться, что значение не попадало ни в один закоммиченный `.env`-дамп в истории. Если попадало — ротация **согласованно с InfraSafe** (оба конца HMAC должны обновиться одновременно), иначе webhook-интеграция отвалится.

## 9. Прочее — проверить
- `MEDIA_API_KEY` в утёкшем файле был **пустым** — не секрет, но задать осмысленное значение в проде.
- `GOOGLE_SHEETS_CREDENTIALS_FILE` — путь, не секрет; убедиться, что сам JSON-файл сервис-аккаунта **не закоммичен** (`git ls-files | grep -i credential`).

---

## История git (отдельный, деструктивный шаг — требует подтверждения)

Затирание дерева не убирает значения из истории. Полное удаление:

```bash
# на свежей зеркальной копии, НЕ на рабочем чекауте:
pip install git-filter-repo
git filter-repo --invert-paths --path docs/Archive/Old_Docs/main.file   # удалить файл целиком из истории
# либо точечно по строкам: git filter-repo --replace-text secrets.txt
git push --force --all origin && git push --force --tags origin
```

**ВНИМАНИЕ:**
- Перепишет ВСЕ SHA коммитов и требует `--force` пуша.
- Прод-чекаут `~/uk` (95.46.96.105) трекает `origin/main` — после force-push его `git pull` разойдётся; нужен `git fetch && git reset --hard origin/main` на проде, согласованно.
- **Прод сейчас тестируется другим агентом** — не выполнять force-push без координации.
- Ротация (п.1–8) — обязательна и первична: после неё значения в истории становятся бесполезными. History purge — гигиена поверх ротации.

## Порядок действий (рекомендуемый)
1. Ротировать токены ботов (@BotFather) — мгновенно, без даунтайма зависимостей.
2. Ротировать `INVITE_SECRET`+`JWT_SECRET` (раздельно) — предупредить о ре-логине.
3. Ротировать `ADMIN_PASSWORD` + закрыть SEC-083.
4. Ротировать пароль БД `uk_bot` (согласованный рестарт).
5. Завести `.env` для медиа-сервиса.
6. Проверить webhook-секрет и google-creds.
7. (Опц., по координации) purge git history + force-push + reset прод-чекаута.
