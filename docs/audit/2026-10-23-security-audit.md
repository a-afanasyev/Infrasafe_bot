# Аудит безопасности UK Management + площадок profk.uz / infrasafe.uz — 2026-10-23 (аудит #10)

Read-only аудит безопасности: код, инфраструктура, два прод-хоста изнутри (SSH) и снаружи (разведка из интернета). Ничего не правилось, не перезапускалось, не удалялось; на хостах выполнялись только команды чтения.

**База кода — `origin/main` `55d395c6`** (раскатан на оба прода 2026-10-23, теги `*-2026-10-23`). Рабочий чекаут автора (`docs/backlog-close-606-607`, `31f5847e`) отставал от прода на 252 коммита, поэтому все находки перепроверены против прод-кода в отдельном worktree; строки цитируются по нему. Находки, которые main уже закрыл, в отчёт не попали (их сняли ~10: обход soft-delete в media, `_client_ip` = IP nginx, follow-redirects HIGH, Pillow 12.3 CVE, logout без `queryClient.clear()` и др.).

**Метод.** Пять параллельных ревьюеров (API 225 маршрутов, бот, сателлиты, инфра/CI/зависимости, фронт) + ручная проверка головных находок; хосты — скрипты чтения по SSH (`ss`, `docker inspect`, `nft`, `sshd -T`, `fail2ban-client`, `journalctl`, права файлов, версии образов); снаружи — DNS, TCP-скан 1–1024 + сервисные порты, `testssl.sh 3.2`, пробы заголовков/CORS/Host/методов/WS/rate-limit/публичных ручек. Инструменты: `pip-audit`, `npm audit`, `bandit`, `testssl.sh`. Значения секретов нигде не выводились (сравнение — по хэшам и длинам).

Предыдущие аудиты: #9 — `AUDIT_REPORT.md` (2026-09-22), #8 — `docs/audit/2026-09-19-full-review.md`, security-аудит 2026-05-29 — `docs/audit/security-audit-2026-05-29.md`. Открытые пункты бэклога (`AUD7-SEC-03`, `AUD8-ENG-02`, `PENT-F13`, `A9-P2-21`, `A9-P3-2`, `SEC-115` и др.) помечены KNOWN и повторно не заводились.

**Исполнение (2026-10-24, решения владельца: ротация postgres не нужна; API-01 → аудит + уведомление; остальное на усмотрение).** Тем же PR закрыты: API-01 (аудит `staff.manager_*` + уведомление `ADMIN_USER_IDS`), API-02…08, INF-05, BOT-01…03, SAT-01/02/05/07/08/09, FE-02/04, INF-04/07 и `no-new-privileges` из INF-03 — бэклог `A10-API-01`, `A10-CODE-01`; гейт `tests/services/test_a10_compose_hardening.py`, пин-тесты `tests/api/test_a10_api_fixes.py`, `uk_management_bot/tests/test_a10_bot_fixes.py`, `media_service/test_a10_preview_bounds.py`, `access_control/tests/test_a10_plate_length.py`, `resource-accounting/backend/tests/test_a10_import_rows.py`. INF-06 (`--ignore-vuln`) на main уже отсутствовал — снят. Открытыми в бэклоге заведены `A10-HOST-01…11`, `A10-EXT-01/03`, `A10-FE-01/03/05`, `A10-SAT-03/04/10`, `A10-INF-03/08/09` (`docs/audit/2026-05-20-backlog.md`, раздел «Аудит #10»). **Хосты, 2026-10-24 (авторизация владельца):** HOST-01 закрыт на обоих продах — `.env` вычищен, прикладные контейнеры пересозданы через Doppler, суперюзер-пароля в их окружении нет, все healthy. HOST-03 частично: безопасный prune, диск 105 с 91 % до 58 %, profk до 41 %. HOST-04 частично: истории очищены, `HISTIGNORE`; токен подтверждён живым (`@profk_monitoring_bot`), ротация за владельцем. Обновление пакетов, рестарт хостов и `daemon.json` на 105 (HOST-02, остаток HOST-03) — руками владельца.

---

## 1. Executive summary

**P0 нет. P1 — одна, и она на хостах, а не в коде.** Пароль суперпользователя `uk-postgres` (переменная `POSTGRES_PASSWORD`, значение совпадает с живым контейнером БД по хэшу на обоих хостах) присутствует в окружении контейнеров `uk-management-api`, `uk-management-bot` и `uk-access-api`. Причина: сервисы грузят `env_file: .env` (`docker-compose.yml:33,124,192,293`), а `/opt/uk/.env` (profk) и `/home/infrasafe/uk/.env` (105) после перехода на Doppler так и не были вычищены. Это откатывает PR-7 (least-privilege роли, закрытие `PENT-F01`): любая RCE в боте/API/access даёт `docker inspect`-уровень доступа к суперпользователю PostgreSQL. Исправление — удалить строку из двух файлов и пересоздать контейнеры; ротация пароля — по решению владельца (значение не покидало хост).

**Внешний периметр — лучшая часть системы.** Снаружи открыты только 80/443 (на profk ещё SSH 32323 по ключам), TLS 1.2/1.3 с AEAD и forward secrecy без единой известной уязвимости, чужой `Host` → 421, default-server → 444, `TRACE/PUT/DELETE` → 405, `.map` → 404, `security.txt` опубликован. Edge-allowlist действительно режет всё лишнее (`/uk/api/v1/*` → 404), rate-limit на auth-путях срабатывает на 10-м запросе (429). Анонимно доступны только агрегаты табло и объявления — ПДн нет. CORS не отражает произвольный Origin.

**Код API/бота/сателлитов/фронта — зрелый, находки гигиенические.** 225 маршрутов API перебраны скриптом: каждый маршрут без auth-зависимости обоснован. RBAC A1 работает как единая точка (`require_action`, роли только из БД, `rbac.manage` недоступно ролям по построению). Единственное решение владельца — **API-01**: менеджер может выпустить инвайт на роль `manager` и сам активировать аккаунт, минуя суперадмина (второй, мягкий путь раздачи менеджерских прав). Остальное — P3: оракул email в `PATCH /profile`, два маршрута без rate-limit, IDOR на чтение деталей чужой передачи смены в боте, `/health` бота отдаёт инфраструктурные детали любому Telegram-аккаунту, Pillow без `MAX_IMAGE_PIXELS` в превью, media-service под ролью-владельцем БД с DDL.

**Хосты — главная зона роста.** Кроме P1: на обоих хостах 3+ недели ждёт перезагрузки ядро `6.1.0-54` (установлено, работает `-53`), ждут апгрейда docker-ce/containerd; на 105 диск заполнен на 91 % при ~5 ГБ мусора Docker и без ротации логов (`daemon.json` нет); в `~/.bash_history` на profk лежит строка с токеном Telegram-бота (`8914776478:…`), записанным в `/etc/profk-*`; стек InfraSafe на хостах крутится на образах возрастом 20–36 месяцев (PostGIS с PostgreSQL 15.4 от 2023 года, WireGuard `:latest` в privileged с `CAP_SYS_MODULE`, Mosquitto `:latest`). На 105 нет сети `uk-internal`: БД и Redis UK в одной сети с edge-nginx.

**Что сделано хорошо** (кратко, не разворачиваю): hash-locked зависимости на всех пяти Python-поверхностях и `--require-hashes` в образах; `pip-audit` = 0 по всем requirements, `npm audit --omit=dev` = 0, `bandit` на CI-пороге = 0; SHA-пины actions, `permissions: contents: read`, промоушен образов `ci-<sha>→sha-<sha>` write-once; все образы non-root; refresh-токены с хэшем, ротацией под `FOR UPDATE` и детекцией reuse; cookie-only auth для web (`HttpOnly`, `Secure`, `SameSite=Strict`); документы жителей — AES-256-GCM с AAD и crypto-shredding; `compare_digest` на всех межсервисных токенах; AST-гейты на `html.escape` и на возврат к `require_roles`; SPF `-all` + DMARC `p=reject` на profk.uz.

## 2. Scorecard

| Поверхность | Оценка | Обоснование |
|---|---|---|
| Внешний периметр (DNS/TLS/edge) | **9/10** | Чисто по всем пробам; минус за отсутствие SPF/DMARC у `infrasafe.uz` и CAA/DNSSEC у обоих (KNOWN). |
| Хосты (profk, 105) | **5/10** | Суперюзер-пароль в окружении приложений, не перезагруженное ядро, диск 91 %, токен в shell-истории, устаревшие образы InfraSafe. База при этом хорошая: ключи-only SSH на нестандартном порту, ufw default-deny, fail2ban, non-root контейнеры, unattended-upgrades. |
| API | **8/10** | Единая RBAC-точка, 19 анонимных маршрутов все обоснованы, экспорты/загрузки/SQL чисты; минус за API-01 (decision) и три маршрута без лимитов/валидации. |
| Бот | **8/10** | Гарды через `plan_transition` + RBAC-каталог, HTML-класс закрыт AST-гейтом, LLM-вывод валидируется по allowlist; три P3. |
| Сателлиты | **8/10** | `access_control` — образцовый edge-протокол; payment — `cap_drop ALL`; минус за media (роль-владелец с DDL, общий ключ без scope, бомба-картинка). |
| Фронт | **8/10** | Ни одного XSS-синка, prod-зависимости чисты, публичные страницы без ПДн; минус за SDK Telegram на всех страницах и dev-token-ветку в prod-бандле. |
| Supply chain / CI | **9/10** | Hash-lock, SHA-пины, write-once теги, паритет-гейты; минус за `pip install --upgrade pip` без пина и мёртвый `--ignore-vuln`. |

## 3. Внешняя разведка (факты)

| Проверка | profk.uz (95.46.96.224) | infrasafe.uz (95.46.96.105) |
|---|---|---|
| Открытые TCP-порты (скан 1–1024 + 40 сервисных) | 80, 443, 32323 (SSH) | 80, 443 (SSH 32323 работает, но в быстром скане не виден — лимит/фильтр) |
| UDP | — | 51820 (WireGuard, молчит на мусор — норма) |
| TLS | TLS 1.2/1.3 только, AEAD, FS, ECDSA LE до 2027-01-02; SAN: `assets.profk.uz` | то же, LE до 2026-12-18; SAN: `fountain.infrasafe.uz`, `infrasafe.aisolutions.uz` |
| testssl.sh | ни одной уязвимости (Heartbleed…LUCKY13 — not vulnerable) | то же; `gzip` на `/` → BREACH «potentially» (статика без секретов — неактуально) |
| Заголовки | HSTS preload, CSP, XFO, nosniff, Referrer-Policy, Permissions-Policy | то же |
| Чужой `Host` / прямой IP | 421 / unrecognized name | 421 / unrecognized name |
| `TRACE/PUT/DELETE` на `/uk/` | 405 | — |
| `/.env`, `/.git/HEAD`, `/metrics`, `/openapi.json` | 200 с SPA-заглушкой InfraSafe (не файлы) | 301 → `/` |
| `/uk/api/v1/*`, `/uk/api/docs` | 404 (allowlist) | 404 |
| Анонимные ручки UK | `/uk/api/health` `{"ok":true}`, `/uk/api/v2/public/board` (агрегаты), `/uk/api/v2/announcements` | то же |
| `POST /uk/api/v2/webhooks/infrasafe/alert` без подписи | 401 | — |
| Rate-limit `/uk/api/v2/auth/*` | 429 с 10-го запроса из 25 | (тот же конфиг) |
| CORS `Origin: https://evil.example` на `/api/*` (InfraSafe) | `allow-origin` не отражается, только `allow-credentials: true` без origin — безвредно | то же |
| WS без апгрейда на несматченный путь | 404 | — |
| `security.txt` | 200, 208 байт | 200, 208 байт |
| DNS: SPF / DMARC | `v=spf1 -all` / `p=reject` ✅ | **нет TXT вовсе**, MX указывает на сам домен (EXT-01) |
| DNS: CAA / DNSSEC | нет / нет (KNOWN `PENT-F13`) | нет / нет |
| Поддомены | `assets.profk.uz` 200 (asset-bot, CSP с `unsafe-inline`) | `infrasafe.aisolutions.uz` 200, `fountain.infrasafe.uz` без серт-имени, `monitor.infrasafe.uz` 503-заглушка; `www` → Wix (aisolutions.uz) |

## 4. Хосты изнутри (факты)

| Параметр | profk.uz | infrasafe105 |
|---|---|---|
| ОС / ядро | Debian 12, `6.1.0-53` работает, `-54` установлен, **reboot-required 3+ нед.** | то же |
| SSH | 32323, `PermitRootLogin no`, `PasswordAuthentication no`, fail2ban active | то же |
| sudo для `infrasafe` | **`NOPASSWD:ALL`** (`/etc/sudoers.d/90-infrasafe`); deploy-ключ также в `/root/.ssh/authorized_keys` | требует пароль |
| Firewall | ufw default-deny, allow 80/443/32323 | ufw active (правила без sudo не прочитать; снаружи подтверждено) |
| Docker | 29.6.2 (ждёт 29.9.2), `daemon.json` с ротацией 20m×5 | 29.6.2, **`daemon.json` нет** |
| Диск / RAM | 52 % / 5.9 ГБ | **91 % (1.8 ГБ свободно)** / 3.9 ГБ; reclaimable: images 1.38 ГБ, volumes 1.96 ГБ, build cache 1.69 ГБ |
| Сети UK | `uk_uk-internal` для БД/Redis/бота/API; `uk-network` общая с `infrasafe-nginx-1`, `asset-web`, `uk-payment-*` | **только `uk-network`**: uk-postgres, uk-redis, media в одной сети с `infrasafe-nginx-1`; postgres/redis опубликованы на `127.0.0.1` |
| Контейнеры UK | non-root, без privileged/docker.sock; `no-new-privileges` только у payment-api | то же |
| Контейнеры InfraSafe | `postgis/postgis:15-3.3` = **PostgreSQL 15.4 (2023-08)**, nginx 1.31.6 digest-pinned | то же + **`wireguard:latest` (20 мес.) privileged + `CAP_SYS_MODULE` + `label=disable`, 10 peers**, `mosquitto:latest` (2 года, auth включён), `alloy` как root с `docker.sock:ro` и `/:/rootfs:ro` |
| Секреты на диске | `/opt/uk/.env` (600, **содержит `POSTGRES_PASSWORD`**), `.env.bak.arch114-profk`, `.env.bak.arch106-rotate-*`, `.env.bak.resource-wire.*`, `/opt/infrasafe/.env.prod.bak*` ×2 | `/home/infrasafe/uk/.env` (600, 213 строк, `DATABASE_URL`+`POSTGRES_PASSWORD`), `env-backups/`, `hardening-backups/`, `obs/secrets/pg_*`/`redis_*` **644** |
| Shell-история | 144 строки; **`printf "8914776478:<token>" > /etc/profk-…`**, `sudo cat /etc/profk-…` | 2000 строк; `cat token.txt`, `cat password.txt` (файлов уже нет) |
| pg_hba | `trust` для local/127.0.0.1 внутри контейнера (дефолт образа), снаружи scram | + `host all uk_admin all reject` |
| Redis | `requirepass` задан (NOAUTH) | то же |
| Бэкапы | кросс-хост через restricted-key, retain 5 дней | то же; дампы в `~` незашифрованные (home 700) |
| auditd | inactive | inactive |
| Compose в работе | `docker-compose.yml` + `.profk.yml` + `.payments.yml` | `docker-compose.yml` + `.media.yml` |
| Git-чекауты | `/opt/uk` = `55d395c6` чисто; `/opt/infrasafe` **8 dirty** (`nginx.profk.conf` правлен на месте + 7 `.bak`) | `/home/infrasafe/uk` = `55d395c6` чисто; `/home/infrasafe/infrasafe` 5 untracked |

## 5. Находки

Серьёзность: **P0** критично / **P1** высокая / **P2** средняя / **P3** низкая. Труд: S < 1 ч, M < 1 дня, L > 1 дня. Все `путь:строка` — по `origin/main 55d395c6`.

### 5.1 Хосты и эксплуатация

| ID | Сер. | Категория | Где | Описание / вектор | Рекомендация | Труд | Статус |
|---|---|---|---|---|---|---|---|
| **HOST-01** | **P1** | Секреты / least privilege | `docker-compose.yml:33,124,192,293` (`env_file: .env` у app, group-intake, api, access-api); хосты: `/opt/uk/.env`, `/home/infrasafe/uk/.env` | Суперюзер-пароль `uk-postgres` в окружении трёх прикладных контейнеров на обоих хостах (sha256 значения = значению в `.env.postgres` = живому контейнеру БД). RCE в боте/API/access → `postgres` superuser → все БД на инстансе, включая `uk_media`. Отменяет PR-7/`PENT-F01`. Также в `.env` на 105 остался `DATABASE_URL` (перекрывается role-файлом, но лежит). | Удалить `POSTGRES_PASSWORD`/`DATABASE_URL` из обоих `.env` → `doppler run -- docker compose up -d app api access-api group-intake-bot`; проверить `docker inspect … | grep POSTGRES_PASSWORD` = пусто. Гейт в `tests/services`: `.env.example` без `POSTGRES_PASSWORD`; строка в SKILL uk-deploy «после Doppler-cutover ревизовать `.env`». Ротация пароля — решение владельца (утечки за пределы хоста не найдено). | S | NEW |
| **HOST-02** | **P2** | Патч-менеджмент | оба хоста: `/var/run/reboot-required`, `uname -r` = `6.1.0-53`, `/boot/vmlinuz-6.1.0-54` | Ядро с security-фиксами установлено, но не загружено 3+ недели (uptime 3 нед. 5 дн.). Ждут `docker-ce 29.6.2→29.9.2`, `containerd 2.2.6→2.4.2`, на 105 `libexpat1` security. | Плановое окно: `apt upgrade` + reboot обоих хостов (сначала 105, затем profk); проверить `expected-containers.tsv` после старта. Добавить алерт на `reboot-required` > 7 дней в `profk-observability`. | S | NEW |
| **HOST-03** | **P2** | Доступность / DoS диском | 105: `df /` = 91 %, `/etc/docker/daemon.json` отсутствует, `docker system df` reclaimable ≈ 5 ГБ; profk: лог-файл одного контейнера 257 МБ при лимите 20m×5 (контейнер создан до `daemon.json`) | Переполнение диска = остановка PostgreSQL/Redis/бота. json-file без лимита растёт бесконечно; weekly prune есть, но volumes/build-cache он не чистит (85 % volumes dangling). | На 105: `daemon.json` как на profk (20m×5) + `systemctl restart docker` в окне из HOST-02; `docker volume prune` (после проверки списка!), `docker builder prune`. На profk пересоздать контейнеры с большими логами. `x-logging` anchor в compose (см. INF-05). | S | NEW |
| **HOST-04** | **P2** | Секреты в shell-истории | profk `~/.bash_history` (144 строки): `sudo sh -c 'printf "%s" "8914776478:<35 симв.>" > /etc/profk-<…>'`, `sudo cat /etc/profk-<…>`, `cat <…>-webhook-secrets.txt`; 105: `cat token.txt`, `cat password.txt` | Полный токен Telegram-бота (bot id 8914776478) лежит открытым текстом в истории; любой, кто читает домашний каталог (бэкап `~`, компрометация deploy-ключа), получает управление ботом. Живость токена **не проверена** (проверка заблокирована политикой разрешений сессии). | Владельцу: `curl https://api.telegram.org/bot<token>/getMe` → если жив — ротировать через BotFather и в Doppler/`/etc/profk-*`; `history -c; > ~/.bash_history` на обоих хостах; `HISTIGNORE='*TOKEN*:*PASSWORD*:*SECRET*'` или `HISTCONTROL=ignorespace` в `~/.bashrc`. | S | NEW |
| **HOST-05** | **P2** | Устаревшие образы (стек InfraSafe на тех же хостах) | `infrasafe-postgres-1` = PostgreSQL 15.4 (2023-08-10; актуально 15.18 — пропущены фиксы CVE-2023-5868/5869/5870, CVE-2024-0985, CVE-2024-4317, CVE-2024-7348, CVE-2024-10976…10979, CVE-2025-1094, CVE-2025-8714/8715); 105: `lscr.io/linuxserver/wireguard:latest` создан 20 мес. назад, `privileged`, `CAP_SYS_MODULE`, `label=disable`, UDP 51820 в мир; `eclipse-mosquitto:latest` 2 года; `grafana/alloy:v1.10.0` 15 мес. с `docker.sock` | БД внутренняя (без host-порта), но это ядро InfraSafe + WireGuard — единственный privileged-контейнер на периметре: уязвимость в образе = root на хосте, где живут обе системы. `:latest` без digest — недетерминированно и не обновляется без `pull`. | В репо InfraSafe: `postgis/postgis:15-3.5`+ (минор 15.x) по digest, WireGuard — пин версии+digest, снять `label=disable`, рассмотреть `--cap-add NET_ADMIN` без `privileged` (kernel-модуль уже в ядре 6.1); Mosquitto — пин; Alloy — через docker-socket-proxy. Это зона репо `a-afanasyev/infrasafe`, здесь только фиксируется. | M | NEW (внешнее репо) |
| HOST-06 | P3 | Привилегии администратора | profk `/etc/sudoers.d/90-infrasafe`: `infrasafe ALL=(ALL) NOPASSWD:ALL`; `/root/.ssh/authorized_keys` содержит тот же deploy-ключ; `/etc/ssh/sshd_config:PermitRootLogin yes` (перекрыт `sshd_config.d/10-hardening.conf`) | Один ключ = root без пароля. Пользователь в группе `docker` и так root-эквивалентен, поэтому выигрыш от пароля ограничен, но на 105 пароль требуется — конфиги расходятся. Строка `PermitRootLogin yes` в основном файле — мина: пропадёт `Include` — root по ключу откроется. | Привести profk к 105 (`sudo` с паролем) или осознанно принять; убрать ключ из `/root/.ssh/authorized_keys`; заменить `PermitRootLogin yes` на `no` в основном файле. `X11Forwarding yes` → `no`. | S | NEW |
| HOST-07 | P3 | Сетевая изоляция | 105: `docker network inspect uk-network` — uk-postgres, uk-redis, uk-media-service вместе с `infrasafe-nginx-1`; `docker-compose.media.yml` не определяет `uk-internal` (в отличие от `.profk.yml:218`); profk: `uk-payment-postgres`/`uk-payment-api` в общей `uk-network` (`docker-compose.payments.yml:22,39,53`) | Компрометация edge-nginx или любого контейнера InfraSafe → прямой TCP до PostgreSQL/Redis UK (парольная auth остаётся). На profk эта изоляция уже сделана для основной БД, но не для payment. | На 105 добавить в `docker-compose.media.yml` (или отдельный `.infrasafe.yml`) `uk-internal` по образцу `.profk.yml:34-85,218`; на profk перевести `payment-postgres`/`payment-migrate` в `uk-internal`, `payment-api` — в обе. | S | NEW (= INF-02) |
| HOST-08 | P3 | Остатки секретов на диске | profk: `/opt/uk/.env.bak.arch114-profk`, `.env.bak.arch106-rotate-1784133693`, `.env.bak.resource-wire.1783880642`, `/opt/infrasafe/.env.prod.bak-from-current`, `.env.prod.bak.totp-issuer-20261011`; 105: `~/env-backups/`, `~/hardening-backups/`, `~/obs/secrets/{pg_monitoring_password_*,redis_password_*}` **644**; `/opt/infrasafe/.deploy/profk-initdb.sql` 644 с 23 вхождениями `password` (содержимое не читалось — **требует подтверждения**) | Старые (доротационные) и текущие секреты в нескольких копиях расширяют поверхность утечки через бэкап `~`/`/opt`. | `shred -u` бэкапов `.env*` после сверки с Doppler; `chmod 600 ~/obs/secrets/*` (Alloy читает под root — права не мешают); проверить `profk-initdb.sql` на хэши/пароли и убрать из 644. | S | NEW |
| HOST-09 | P3 | Детектирование | оба хоста: `auditd` inactive; profk `fail2ban-client get sshd journalmatch` = `_SYSTEMD_UNIT=sshd.service + _COMM=sshd` при юните Debian 12 `ssh.service` | fail2ban-jail для sshd на Debian 12 с `backend=systemd` может не видеть записи журнала (за 30 дней `journalctl -u ssh` показал 0 неудачных попыток, т.е. порт 32323 без перебора — эффект нулевой, но и защиты нет). Без auditd нет трассы `docker exec`/`sudo` вне journald. | `journalmatch = _SYSTEMD_UNIT=ssh.service + _COMM=sshd` в `jail.local`, проверить тестовым неудачным логином; auditd с правилами на `execve` для `docker`/`sudo` — по желанию. | S | NEW |
| HOST-10 | P3 | Конфиг-дрейф edge | profk `/opt/infrasafe`: `M nginx-config/nginx.profk.conf` + 7 файлов `nginx.profk.conf.bak-*` рядом с конфигом; 105: `nginx.production.conf.bak-*` ×2; `monitor.infrasafe.uz` отдаёт 503-заглушку | Живой конфиг edge (allowlist UK, редирект корня → `/uk/home`) не совпадает с репо InfraSafe — при следующем деплое InfraSafe правило может потеряться (память: правило корня в репо не внесено). `.bak` в каталоге, который монтируется в nginx (`/etc/nginx/custom:ro`), безвредны, но мусор. | Закоммитить живой `nginx.profk.conf` в репо InfraSafe, удалить `.bak`; зафиксировать `expected`-хэш конфига в observability. | S | NEW (внешнее репо) |
| HOST-11 | P3 | Стойкость секрета | 105: `ADMIN_PASSWORD` длиной 16 символов (profk — 64) | `/admin` в проде выключен (`ADMIN_COMMAND_ENABLED`), поэтому влияния нет; но один и тот же гейт на двух площадках с разной стойкостью — повод выровнять. | Сгенерировать 64-символьный в Doppler `infrasafe`. | S | NEW |

### 5.2 Внешний периметр

| ID | Сер. | Категория | Где | Описание / вектор | Рекомендация | Труд | Статус |
|---|---|---|---|---|---|---|---|
| EXT-01 | P3 | E-mail spoofing | DNS `infrasafe.uz`: TXT отсутствует, `_dmarc` отсутствует, MX `0 infrasafe.uz.` | Письма «от @infrasafe.uz» принимаются получателями без проверки — фишинг жителей/сотрудников от имени бренда. На profk.uz это закрыто (`PENT-F09`). | У регистратора: `TXT "v=spf1 -all"`, `_dmarc TXT "v=DMARC1; p=reject"`, MX → `0 .` (null MX, RFC 7505). | S | NEW |
| EXT-02 | P3 | DNS hardening | оба домена: CAA пуст, DNSSEC нет | — | — | S | KNOWN `PENT-F13` |
| EXT-03 | P3 | CSP поддомена | `assets.profk.uz`: `script-src 'self' 'unsafe-inline'` (`nginx.profk.conf:978`) | Статическая карта asset-bot; `unsafe-inline` открывает XSS при любой инъекции в её HTML/данные. | Вынести inline-скрипты в файлы, убрать `'unsafe-inline'`. | S | NEW (asset-bot) |
| EXT-04 | info | CSP `/uk/` | `img-src 'self' data: https:` (edge) | Широкий `img-src` — компромисс под Telegram; XSS-поверхность закрыта escaping'ом. | Сузить до `self data: https://*.telegram.org` при возможности. | S | KNOWN |
| EXT-05 | info | SPA-fallback | `https://profk.uz/.env`, `/.git/HEAD`, `/metrics` → 200 с `index.html` InfraSafe | Файлов нет (в образе только `dist/`), но сканеры видят ложные 200. | `location ~ /\. { return 404; }` в edge. | S | косметика |

### 5.3 API (FastAPI, 225 маршрутов)

| ID | Сер. | Категория | Где (`uk_management_bot/…`) | Описание / вектор | Рекомендация | Труд | Статус |
|---|---|---|---|---|---|---|---|
| **API-01** | **P2 (решение владельца)** | AuthZ / lateral privilege | `api/shifts/schemas.py:334-337` (`role: Literal["executor","manager"]`), `api/shifts/router/employees.py:126-135` (`create_invite`, гейт `staff.manage`), `:256-275` (`activate_staff` — «НЕ применяем `_ensure_not_privileged` намеренно») | Любой `manager` выпускает инвайт на роль **manager** и сам активирует новый аккаунт — без суперадмина и без аудита `rbac.user_roles.changed`, тогда как смена ролей в админке RBAC требует `rbac.manage`. Украденная сессия менеджера (cookie 60 мин / refresh 7 дн.) → «свой» менеджер, переживающий блокировку исходного аккаунта. Через edge достижимо (`/shifts/employees/…`). | Либо `role="manager"` в инвайте/активации требует `rbac.manage`, либо минимум `AuditLog` + уведомление в `ADMIN_USER_IDS` о создании/активации менеджера. Пин-тест. | M | NEW (намерение в докстринге — требует решения) |
| API-02 | P3 | AuthZ / scope | `api/shifts/router/employees.py:310-325` (`toggle_meter_entry`) vs `_ensure_staff_target` в `:328-379` | Капабилити `resource_meter_entry` выдаётся любому `user_id`, включая жителей и себя → доступ к вводу показаний в ресурс-сервисе. | `_ensure_staff_target` + запрет self-target, как у `simple-mode`. | S | NEW |
| API-03 | P3 | Валидация / оракул | `api/profile/router.py:82-99`, `api/profile/service.py:26-28`, `database/models/user.py:53` (`email unique`) | `PATCH /profile` любому аутентифицированному (в т.ч. `pending`) ставит непроверенный email — логин парольного входа; дубль → `IntegrityError` → 500. Оракул существования email (500 vs 200), без лимита (путь не в auth-префиксе edge); сквоттинг адреса до того, как его заведут владельцу. | Ловить `IntegrityError` → 409 единым текстом; `@limiter.limit`; подтверждение email кодом — по желанию. | S | NEW |
| API-04 | P3 | Rate limiting | `api/requests/router.py:843-888` (`GET/POST /{n}/comments`), `:889-915` (`remind-applicant`) — без `@limiter.limit` (PATCH `:424` имеет 30/мин) | Житель заваливает заявку комментариями до 2000 символов без ограничения. | `@limiter.limit("30/minute")` на POST, разумный на GET. | S | NEW |
| API-05 | P3 | Memory DoS | `api/feedback/router.py:131-132` (`await file.read()` до проверки размера), `api/webhooks/router.py:45` (`request.body()` до HMAC) | Тело читается в память целиком (класс A9-P3-4, закрытый в медиа-прокси `read(MAX+1)`). Edge режет `client_max_body_size 10M` — снаружи mitigated, внутри сети нет. | `file.read(MAX+1)`; для webhook — `Content-Length`/лимит чтения до верификации. | S | NEW (edge-mitigated) |
| API-06 | P3 | Валидация | `api/callcenter/schemas.py:34-42` (`description`, `caller_*`, `address` без `max_length`) vs `api/requests/schemas.py:180` | Заявка колл-центра без лимита длины → ломаные Telegram-уведомления (4096). Только менеджер. | Единый `MAX_DESCRIPTION_LENGTH`. | S | NEW |
| API-07 | P3 | JWT hygiene | `api/auth/service.py:104` (`jwt.decode` без `options={"require":[…]}`), `:153` (нет `iat`/`iss`/`jti` у access) | Токен без `exp` принимается HTTP-путём (WS компенсирует явно). Эксплуатируемо только при компрометации `JWT_SECRET`. | `options={"require": ["exp","sub"]}`, `iss`/`iat` в access-токен. | S | NEW |
| API-08 | P3 | Legacy | `api/dependencies.py:39-42` (фолбэк на cookie `access_token`, «remove after one release window») | Любая cookie `access_token` на общем домене (`Path=/`) затеняет Bearer TWA → спуриозные 401. Не эскалация. | Удалить фолбэк. | S | NEW |
| API-09 | P3 | Crypto / key mgmt | `database/models/user_verification.py:55-58`, `utils/document_crypto.py:1-10` | Ключ документа лежит рядом с метаданными; дамп БД + доступ к каналу = расшифровка. Осознанный дизайн (crypto-shredding), остаток — шифрование бэкапов. | — | M | KNOWN `AUD8-ENG-02` |
| API-10 | P3 | Межсервисный отзыв | `api/resource_accounting/router.py:105-113` | Сессия ресурс-сервиса не отзывается при блокировке в UK. | — | — | KNOWN `AUD7-SEC-03` |

Все 19 анонимных HTTP-маршрутов и 4 WS обоснованы: `auth/*` (вход, slowapi + fail-closed при деградации Redis + edge 20 r/m), `registration/start` (initData), `resource-accounting/twa-ticket` (initData + approved + действие), `webhooks/infrasafe/alert` (HMAC), `public/*`/`announcements` (агрегаты/опубликованное, без ПДн), `health` (liveness без версии), WS (Origin до `accept()`, запрет `?token=`, роль из БД, перепроверка каждые 60 с).

### 5.4 Telegram-боты

| ID | Сер. | Категория | Где (`uk_management_bot/…`) | Описание / вектор | Рекомендация | Труд | Статус |
|---|---|---|---|---|---|---|---|
| BOT-01 | P3 | Information disclosure | `handlers/health.py:123-126` («доступна всем пользователям»), `:52`, `:116-117`, `:191` (`f"{error_details}: {str(e)}"`) | `/health` любому Telegram-аккаунту (в т.ч. незарегистрированному): статус БД/Redis с таймингами, `DEBUG`, `LOG_LEVEL`, uptime; при сбое — `str(e)` с host/port/dbname из `OperationalError`. | Под `has_action_roles(roles, "admin_panel.use")` как `/health_detailed` (`:203`); `str(e)` → фиксированный ключ локали. | S | NEW |
| BOT-02 | P3 | IDOR (чтение) | `handlers/shift_transfer.py:250-265` (`action == "details"` → `get_transfer` без проверки участия) vs `_load_view_transfer:281-294` (гард есть) | Любой исполнитель перебирает `transfer_id` в callback_data и читает дату/причину/комментарий чужих передач смен. | Переиспользовать проверку участника из `_load_view_transfer`. | S | NEW |
| BOT-03 | P3 | Fail-open | `middlewares/auth.py:140-145` | При исключении загрузки пользователя (БД недоступна) → `user=None`, хендлер вызывается с `roles=["applicant"]`; проверка `blocked` пропускается. Практический impact низкий (хендлеры сами падают на БД), но FSM/Redis-пути и `/health` работают. | При исключении — `return None` (fail-closed). | S | NEW |
| BOT-04 | P3 | Rate limiting | `main.py:287`, `group_intake_main.py:59` — троттлинг только на `message` | `callback_query` без троттлинга → флуд `FOR UPDATE`/медиа-запросов от одного аккаунта. | `ThrottlingMiddleware` на `dp.callback_query`. | S | KNOWN `SEC-09` |

Чисто: callback_data → права (все назначения/статусы/вердикты/роли перепроверяются в БД, урок BUG-169 применён консистентно); HTML-инъекция (A9-P2-2 закрыт, AST-гейт `test_a9_p2_2_html_escape_gate.py`, 0 неэкранированных f-строк); Group Intake — LLM-вывод по `enum`-allowlist + повторная валидация, описание = исходный текст автора, чат-allowlist `MonitoredGroup`, Redis fail-closed; контакт `contact.user_id != from_user.id` → отказ; инвайты HMAC + nonce + expiry; deep-link только `join_<token>`; `/admin` за флагом + `compare_digest`; токены маскируются в логах.

### 5.5 Сателлиты

| ID | Сер. | Категория | Где | Описание / вектор | Рекомендация | Труд | Статус |
|---|---|---|---|---|---|---|---|
| SAT-01 | P3 | DoS / image bomb | `media_service/app/services/preview_cache.py:82-89`; `grep MAX_IMAGE_PIXELS media_service/app` = 0; `api/v1/media.py` `/previews/warm` (`gather` по пачке) | `MAX_IMAGE_PIXELS` не ужесточён, размер не проверяется до `convert`/`thumbnail`; однотонный PNG 13000×13000 (<1 МБ, проходит лимит 50 МБ) → 0.5–1 ГБ RAM на кадр, один воркер, `mem_limit` нет → OOM media. Условие: учётка исполнителя. `formats=` на main отрезал экзотику, но не бомбу в PNG. | `Image.MAX_IMAGE_PIXELS ≈ 40e6`, проверка `img.size` до convert, `img.draft` для JPEG, семафор, `mem_limit`. | S | NEW |
| SAT-02 | P3 | Ретеншн | `media_service/app/services/media_storage.py:422-547` (сага delete/archive без `preview_cache`), `preview_cache.py:116-136` | Превью остаётся на диске после удаления медиа до LRU-вытеснения (100 заявок). Отдача заблокирована. | `os.remove` превью в саге удаления. | S | NEW |
| SAT-03 | P3 | Least privilege БД | `media_service/app/db/database.py:91-96,112-120` (`create_all` на старте), `.claude/skills/uk-deploy/SKILL.md:163-166` (`OWNER`, `GRANT ALL`), один `MEDIA_DATABASE_URL` для сервиса и `media-migrate` (`docker-compose.media.yml:27,72`) | Рантайм media — владелец БД с DDL (класс `PENT-F01`, закрытый для остальных). Вместе с HOST-01 — вторая дыра в least-privilege. | Роль `uk_media_app` (DML) для сервиса; DDL только в `media-migrate` (с A9-P2-21). | M | NEW |
| SAT-04 | P3 | Архитектура доверия | `media_service/app/main.py:171-182`; `access_control/integrations/media.py:92-96,150-172` | Один общий `X-API-Key` без scope: access-api (принимает device-трафик) может `DELETE` любое медиа, читать `/search` и blob'ы документов. | Ключ на вызывающего + карта scope. | M | NEW (можно принять) |
| SAT-05 | P3 | Валидация | `access_control/api/camera_events.py:57`, `api/edge.py:102,108` (без `max_length`) vs `domain/events.py:76-77` (`String(32)`) | Номер >32 символов → `DataError` → 500 на горячем пути; `attributes` — произвольный JSON до 10 МБ. Условие: device-креды. | `Field(max_length=32)`, лимит `attributes`. | S | NEW |
| SAT-06 | P3 | AuthN ops-ручки | `access_control/api/metrics.py:34-56` (пустой `ACCESS_METRICS_TOKEN` → открыто) | Гейт opt-in, не fail-closed. **Проверено на проде: токен задан на обоих хостах (длина 43–44)** — риск только при потере переменной. | Сделать fail-closed как у UK `require_health_token`. | S | KNOWN `A9-P3-2` (конфиг подтверждён) |
| SAT-07 | P3 | Доступность | `resource-accounting/backend/app/api/auth.py:54-55`, `core/ratelimit.py:16` (`10/minute` по IP); UK `api/resource_accounting/router.py:68` без `X-Real-IP` | s2s-ручка `/v1/auth/tickets` лимитируется по IP, а клиент один (UK api) → один бакет 10/мин на всех менеджеров и контролёров → 429 → 502. Требует подтверждения нагрузкой. | Исключить s2s-ручку из IP-лимита (её гейтит токен). | S | NEW |
| SAT-08 | P3 | DoS / ресурсы | `resource-accounting/backend/app/services/imports.py:52-57,85-107` | Нет лимита строк импорта (payment имеет 10k): CSV 5 МБ ≈ 100k строк → `IN (...)` на 100k, `commit_token` на мегабайты. Роль `resource_operator`. | `MAX_ROWS` в `parse_file`. | S | NEW |
| SAT-09 | P3 | Гигиена сборки | `resource-accounting/backend/.dockerignore` (нет `.env`, `build/`), `Dockerfile:14` (`COPY . .`) | Локальный `.env` при сборке с рабочей машины попал бы в образ. Прод-образы из CI — потенциал. | Дополнить `.dockerignore`. | S | NEW |
| SAT-10 | P3 | PII в URL/логах | UK `api/payment_control/router.py:78-80` (`GET /account?account_number=`), `frontend/src/hooks/usePaymentControl.ts:45` (`?account=`) | Лицевой счёт в query-string → access-логи edge и история браузера (для batch `/balances` проект сам выбрал POST, `:89-91`). | POST с телом; `account` не в URL страницы. | S | NEW |

Чисто: `access_control` — per-device HMAC + anti-replay в Redis fail-closed + cap тела до парсинга + зона/гейт/шлагбаум от контроллера, а не из тела; все 60+ роутов под `require_action`; `payment_control` — `cap_drop ALL`, `payment_app` без DDL, ASCII-регэксп счёта, `no-store`; документы жителей — AES-256-GCM с AAD, узкая ручка `/upload-resident-document`, выдача только менеджеру, purge до смены статуса + триггер 026; magic-byte sniff на обеих границах; formula-injection и zip-bomb закрыты в resource/payment.

### 5.6 Фронт

| ID | Сер. | Категория | Где (`frontend/…`) | Описание / вектор | Рекомендация | Труд | Статус |
|---|---|---|---|---|---|---|---|
| FE-01 | P2 | Supply chain / third-party JS | `index.html:19` (`<script src="https://telegram.org/js/telegram-web-app.js">` без условия пути) | SDK Telegram грузится на `/uk/login` и всём дашборде, SRI невозможен (без версии). Компрометация `telegram.org` → same-origin код на дашборде: все API-вызовы с cookie, ПДн жителей, перехват логина/OTP. CSP `script-src 'self' https://telegram.org https://oauth.telegram.org` — другие источники закрыты. Низкая вероятность, высокий impact. | Динамическая загрузка из `main.tsx` только для `/uk/twa*`, `/uk/register` и при `tgWebAppData` в hash. | M | NEW |
| FE-02 | P3 | Dev-ветка в prod-бандле | `src/api/accessClient.ts:45-51,63,80`, `src/hooks/useAccessSecurityFeed.ts:72-79,123` | Cookieless dev-путь (`VITE_ACCESS_*_DEV_TOKEN`, `sessionStorage['access_api_dev_token']`) компилируется в прод; dev-JWT в build-env запёкся бы в публичный бандл. Сейчас переменные не задаются. | `import.meta.env.DEV ? … : null` → tree-shake. | S | NEW |
| FE-03 | P3 | Публичные данные | `src/hooks/useBoardConfig.ts:13-14` → `GET /api/v2/public/board-config`; `src/types/boardConfig.ts:78,142,156` | Анониму отдаётся весь конфиг витрины, включая операционные поля (`autopublish`, `work_reports.*`, `display_tz`). ПДн нет. | Публичный `PublicBoardConfigOut` только с полями рендера. | S | NEW (низкий) |
| FE-04 | P3 | Имя файла | `src/components/residents/ResidentDocuments.tsx:41-44` (`link.download = doc.file_name`) | Документ жителя сохраняется под именем из Telegram-загрузки без сверки расширения с MIME ответа («PDF под именем `акт.html`» на диске менеджера; исполнения нет). | Расширение из `loaded.type`, имя `document-${id}`. | S | NEW |
| FE-05 | P3 | Allowlist (ветка TV-табло, не main) | рабочее дерево `src/components/board/ResidentBoardTv.tsx:137` (`t.me/${username}` без регэкспа `botHandle`) | На main отсутствует; станет актуально при мерже ветки табло. | Переиспользовать `botHandle()` из `components/home/homeFormat.ts:121-123`. | S | NEW (pre-merge) |

Чисто: 0 `dangerouslySetInnerHTML`/`innerHTML`/`eval`; токены только в `HttpOnly` cookie (`uk_access` Path=/uk/, `uk_refresh` Path=/uk/api/), TWA refresh в памяти; Telegram Login Widget — ручной iframe с проверкой `origin`+`source`; `?next=` через `safeNextPath`; `sourcemap:false`, `console` вырезан; `npm audit --omit=dev` = 0 (lock main: axios 1.20.0, follow-redirects 1.16.1), CI-гейт `npm-audit` с пустым allowlist зелёный; публичные страницы (`/home`, `/resident-board`, `/elevators`, `/work-reports`) без имён/телефонов жителей и исполнителей; RBAC-админка — `can_edit`/`is_superadmin` с сервера, UI только скрывает; экспорты генерирует сервер с экранированием формул (`official_xlsx.py:212-233`, `csv_escape.py`).

### 5.7 Supply chain / CI / IaC

| ID | Сер. | Категория | Где | Описание / вектор | Рекомендация | Труд | Статус |
|---|---|---|---|---|---|---|---|
| INF-01 | — | — | — | = **HOST-01** (корневая причина `env_file: .env`). | см. HOST-01 | — | — |
| INF-02 | — | — | — | = **HOST-07**. | — | — | — |
| INF-03 | P3 | Контейнерный hardening | `docker-compose.yml` — 0 `cap_drop`/`read_only`/`no-new-privileges`/`pids_limit`; только `docker-compose.payments.yml:61-62` | Все сервисы кроме payment-api с дефолтными capabilities и возможностью privilege escalation. Non-root есть — это defence-in-depth при RCE. | Поэтапно `security_opt: [no-new-privileges:true]`, `cap_drop: [ALL]` (nginx: `CHOWN,SETUID,SETGID,NET_BIND_SERVICE`), `read_only` + `tmpfs` где можно; гейт по образцу `test_ci_service_coverage.py`. | M | NEW |
| INF-04 | P3 | Логи | `docker-compose*.yml` — 0 `logging:`; `docs/ops` без `daemon.json` | См. HOST-03: json-file без лимита на 105. | `x-logging` anchor в compose + `daemon.json` в `docs/ops/RUNBOOK.md`. | S | NEW |
| INF-05 | P3 | Аудит-лог входов | `api/auth/router.py:161` (`Invalid credentials` → 401 без записи); `api/auth/*.py` — 0 `AuditLog(` | Роли/инвайты/админ-действия аудируются, вход в дашборд (пароль/widget/initData/MFA) — нет; расследование перебора по БД невозможно. | `AuditLog(action="login_ok"/"login_failed", details={method, ip})`. | S | NEW |
| INF-06 | P3 | CI гигиена | `ci.yml` pip-audit: `--ignore-vuln PYSEC-2026-1325` (ecdsa) при удалённом python-jose | Мёртвый ignore маскирует будущие находки под тем же ID. | Убрать. | S | NEW |
| INF-07 | P3 | Детерминизм сборки | `Dockerfile:49` (`pip install --upgrade pip` без пина); `ci.yml:33,130,206,411` (инструменты по версии без `--hash`); корневой `requirements-dev.txt` без хэшей | pip «последний с PyPI» в момент сборки — недетерминированный слой. | Убрать `--upgrade pip`; инструменты CI через hash-locked `requirements-dev.txt`. | S | NEW |
| INF-08 | P3 | Секреты в argv | `docker-compose.yml:517` (`--requirepass ${REDIS_PASSWORD}`), `:529` (`redis-cli -a …`) | Пароль Redis в `docker inspect`/`ps`. Условие: доступ к хосту. | `REDISCLI_AUTH` env + конфиг-файл. | S | NEW |
| INF-09 | P3 | История git | `env.copy`/`env.copy.dev` в истории (`dfebe283`…`d2685b04`): реальные `BOT_TOKEN`, `MEDIA_BOT_TOKEN`, `ADMIN_PASSWORD`; `ssl/key.pem` (self-signed dev); `microservices/*/.env.*` с `JWT_SECRET_KEY`/`INTERNAL_API_TOKEN` (похожи на плейсхолдеры — **требует подтверждения**) | Репо публичное. Токены ротированы 2026-05-30, purge истории — WONTFIX владельца. Остаток: `.env.bak.pr7`, `env.copy*` на диске разработчика. | Подтвердить плейсхолдеры `microservices/*`; `shred` локальных `env.copy*`/`.env.bak.pr7`. | S | KNOWN (ротация) / NEW (хвост) |

Чисто: SHA-пины всех `uses:` в 4 workflow; `permissions` минимальны, `packages: write` только у `images-build/promote`; нет `pull_request_target`; PR-сборки не публикуют; GHA-cache per-branch; дрейф-гейты alembic в 4 джобах; digest-пины базовых образов и postgres/redis; `.dockerignore`/`.gitignore` покрывают `.env*`, `ssl/`, `.secrets/`; `tag-deploy.sh` `set -euo pipefail` без `eval`/`curl|sh`; `RATE_LIMIT_TRUSTED_PROXIES` и `FORWARDED_ALLOW_IPS` **заданы на проде** (проверено, длина 13) — `AUD3-35` подтверждён.

## 6. Top-10 quick wins

1. **HOST-01** — удалить `POSTGRES_PASSWORD`/`DATABASE_URL` из `/opt/uk/.env` и `/home/infrasafe/uk/.env`, пересоздать app/api/access-api/group-intake, проверить `docker inspect`. 15 минут, закрывает единственную P1.
2. **HOST-02 + HOST-03** — одно окно: `apt upgrade`, `daemon.json` на 105, `docker volume/builder prune`, reboot обоих хостов (105 → profk), сверка `expected-containers.tsv`.
3. **HOST-04** — `getMe` по токену из истории → ротация при необходимости; очистить `~/.bash_history` на обоих хостах; `HISTIGNORE`.
4. **EXT-01** — три DNS-записи для `infrasafe.uz` (SPF `-all`, DMARC `reject`, null MX).
5. **API-03** — `IntegrityError` → 409 + `@limiter.limit` на `PATCH /profile`.
6. **BOT-01 + BOT-02** — гейт на `/health`, проверка участника в `details` передачи.
7. **API-04 + API-02** — `@limiter.limit` на комментарии/remind, `_ensure_staff_target` на `meter-entry`.
8. **SAT-01** — `MAX_IMAGE_PIXELS` + проверка `img.size` в `preview_cache.py` + `mem_limit` для media.
9. **HOST-07** — `uk-internal` на 105 (`docker-compose.media.yml`) и для payment на profk.
10. **INF-06 + INF-07 + INF-05** — убрать мёртвый `--ignore-vuln`, `--upgrade pip`, добавить `AuditLog` на вход.

## 7. Roadmap

**Неделя 1 (P1 + P2 хостов).** HOST-01 (сначала 105, затем profk, затем гейт в `tests/services` и строка в SKILL uk-deploy) → HOST-02/HOST-03 в одном окне → HOST-04 → EXT-01. Решение владельца по **API-01** (суперадмин для инвайтов менеджера или аудит+уведомление) и по ротации пароля postgres.

**Неделя 2 (P3 кода, один PR на поверхность).** API-02…08 одним PR с пин-тестами; BOT-01…03; SAT-01/02/05/07/08/10; FE-02/03/04; INF-05/06/07/08. Все S, суммарно ~1 день.

**Неделя 3–4 (M-пункты).** SAT-03 (роль `uk_media_app`, вместе с A9-P2-21 alembic для media) → SAT-04 (ключи media по вызывающему) → INF-03 (`cap_drop`/`no-new-privileges`/`read_only` поэтапно с гейтом) → FE-01 (условная загрузка SDK Telegram) → HOST-06/08/09 (sudo/ключи/бэкапы/fail2ban/auditd).

**Внешнее репо InfraSafe (зафиксировать в его бэклоге).** HOST-05 (PostGIS 15.x минор по digest, WireGuard без `privileged`/`label=disable` и с пином, Mosquitto пин, Alloy через socket-proxy), HOST-10 (закоммитить живой `nginx.profk.conf`, убрать `.bak`), EXT-03 (CSP asset-bot), EXT-05 (404 на dotfiles).

**Процесс.** Аудит кода делать только по worktree `origin/main` (рабочее дерево отставало на 252 коммита — без этого ~10 ложных находок); проверку хостов (`reboot-required`, диск, `daemon.json`, `.env` без суперюзер-пароля) добавить в чек-лист деплоя SKILL uk-deploy.

## 8. Этап 2 — ревью внутренней защиты (2026-10-24, код `37b6fc91`)

Динамический пентест отменён владельцем; вместо него — защитное код-ревью по четырём зонам (владение объектами в 221 операции API, auth-потоки, бот, межсервисные границы), каждая находка перепроверена вручную по `файл:строка`. Эскалаций и IDOR через API/бота не найдено; канон `check_request_access` + `plan_transition`, роли и статус из БД на каждом запросе, `auth_middleware` fail-closed, все финалы бота через `run_command_sync` — подтверждены. На profk проверено наличие `RATE_LIMIT_TRUSTED_PROXIES`, `FORWARDED_ALLOW_IPS`, `USE_REDIS_RATE_LIMIT`, `MEDIA_API_KEY`, `ACCESS_METRICS_TOKEN`.

| ID | Сер. | Где | Что исправлено / что решить | Статус |
|---|---|---|---|---|
| INT-01 | P2 | `services/auth_service.py`, `api/shifts/router/_helpers.py` | Единый предикат `services/users/privileged.py:is_privileged_target`; `AuthService` отказывает в block/unblock/assign_role/remove_role/delete для привилегированной цели — бот выровнен с API. | ✅ PR этапа 2 |
| INT-02 | P2 | `config/locales/{ru,uz}.json` (`common.error_occurred`, `request_reports.handlers.error_occurred`, `request_status_mgmt.handlers.error_occurred`) | Плейсхолдер `{error}` убран — ответ бота жителю/исполнителю без текста исключения. | ✅ |
| INT-03 | P3 | `api/ws/router.py:232` | Legacy-cookie `access_token` больше не источник токена (как HTTP после A10-API-08). | ✅ |
| INT-04 | P2 | `docker-compose.payments.yml`; хост profk | payment-postgres/-migrate/-api только в `uk-internal` (были в общей с InfraSafe `uk-network`); ратчет в `test_a10_compose_hardening.py`. Часть A10-HOST-07. | ✅ код; хост — при раскатке |
| INT-05 | P3 | `handlers/user_management/fsm.py` | `has_admin_access` на финалах approve/block/unblock/delete. | ✅ |
| INT-06 | P3 | `api/auth/router.py:_set_auth_cookies` | Пин-тест атрибутов Set-Cookie. | ✅ |
| INT-07 | P3 | `api/auth/service.py:store_otp` | `attempts` через `hsetnx` — resend не возвращает попытки. | ✅ |
| INT-08 | P3 | `api/auth/router.py:login_password` | bcrypt против `DUMMY_PASSWORD_HASH` при неизвестном email. | ✅ |
| INT-09 | P3 | `services/webhook_sender.py:470` | timeout в конструкторе `httpx.AsyncClient`. | ✅ |
| INT-10 | P3 | `api/elevators/router.py:307-317,271`, `router_calendar.py:89` | `elevators.read` (executor+manager) открывает список заявок лифта с ФИО заявителей и смену статуса лифта; UI только у менеджера. Сузить до `elevators.manage` или фильтровать по назначению — меняет снимок прав. | ⏳ решение |
| INT-11 | P3 | `api/feedback/router.py:116` | Обращения без `approved_only` — завести `feedback.create`. | ⏳ решение |
| INT-12 | P3 | `api/routes/media_proxy.py:168-171` | `request_photo` доступен соседу по приёмке (закреплено комментарием к `requests.photos.attach`). | ⏳ решение |
| INT-13 | P3 | `services/request_service.py:285-291` | Same-status `notes`-append без проверки актора, вызывающих нет — удалить ветку. | ⏳ |
| INT-14 | P3 | `services/auth_service.py:214`, `handlers/admin/actions.py:373`, `assign_role("manager")` | Консистентность: pending-исполнитель по инвайту, гейт `mgr_delete_` по env мимо каталога, уведомление суперадминов при выдаче manager из бота. | ⏳ |
| INT-15 | P3 | `api/registration` | Нет теста на SEC-06 (привилегированный аккаунт не перетирается). | ⏳ |

Принятые риски: 404/403 по номеру заявки (пин-тест), access-JWT до `exp` после logout (статус из БД на каждом запросе), CSRF на поддоменах `*.infrasafe.uz` при SameSite=Strict (подтвердить отсутствие стороннего контента), `description` заявки в outbox по контракту.

### 8.4 Страницы profk.uz — сводка проверки защиты (2026-10-24)

| Проверка | Результат | Вердикт |
|---|---|---|
| Маршруты SPA (`App.tsx`) | Публичные: `/home`, `/resident-board`, `/work-reports`, `/elevators`, `/register`, `/login`, `/twa/*`. Остальные под `ProtectedRoute` с действием каталога: `dashboard.use` (manager, admin), `access.events.read`, `access.registry.manage`, `rbac.view`, `materials.manage`, `elevators.read`, `elevators.manage`, `resources.launch`; без входа → `/login?next=`, без права → `/home`. | OK |
| Заголовки страниц (`/uk/*`) | Единый SPA-shell: CSP `default-src 'self'` (+telegram.org для виджета), HSTS preload, nosniff, referrer-policy, permissions-policy, no-store; XFO намеренно нет (TWA); корень → 302 `/uk/home`. | OK |
| 221 операция API без входа | 195 → 401; 5 auth-ручек → 422 (валидация), 2 → 429 (лимит 20/мин); `POST /auth/logout` → 200 (идемпотентно); публичные 7 отвечают по дизайну (`/public/board-config` — A10-FE-03 открыт). | OK |
| 221 операция с невалидным Bearer | Те же статусы, ни одного 2xx у непубличных. | OK |
| Служебные пути через edge | `api/docs`, `openapi.json`, `redoc`, `api/health/*`, `health`, `api/v1/*`, `api/v2/rbac/*` → 404; `assets/` → 403; `metrics`, `.env`, `.git/*` → SPA-shell, не файлы. | OK |
| WebSocket `/uk/ws/v2/*` | Без cookie: 101, через 10 с только close 1008, данных нет; токен в query → 403; чужой Origin → 403. | OK |
| JS-бандл (95 чанков) | Нет sourcemap, dev-токенов, `import.meta.env.DEV`, ключей/токенов; `api_key` — поле ответа выпуска ключа контроллера. | OK |

Итог: страниц и ручек, отдающих данные без права, не найдено; анонимная поверхность совпадает с задуманной. Открытые решения — INT-10…12, A10-FE-03.
