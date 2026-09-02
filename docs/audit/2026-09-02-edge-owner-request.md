# Запрос владельцу edge (infrasafe-nginx / DNS) — 6 пунктов, оба домена

_Составлен 2026-09-02 по живым пробам с внешней машины. Все пункты — конфигурация
edge-nginx и DNS, вне каталога приложения УК. Подробные инструкции с точными
правками лежат в репозитории УК (пути в конце), здесь — что и зачем._

Привет! Просьба применить на edge-nginx и в DNS шесть правок для доменов
**profk.uz** и **infrasafe.uz**. Все проверены сегодня снаружи и открыты на обоих.
Пять из шести — правки одного nginx-конфига, удобно сделать одной правкой и одним
релоадом. Ниже по каждому: что видно, что поменять, как проверить.

## 1. Дублирующиеся security-заголовки на ответах API (PENT-F16)

**Что видно:** любой ответ API, дошедший до апстрима, несёт **два** `Strict-Transport-Security`
(с `preload` и без) и одновременно `X-Frame-Options: DENY` и `X-Frame-Options: SAMEORIGIN`.
Политика framing'а в итоге не определена, зависит от браузера.

```
curl -sD - -o /dev/null https://profk.uz/uk/api/v2/requests/__nope__ | grep -iE 'strict-transport|x-frame'
```

**Что сделать:** сделать edge единственным владельцем этих заголовков: в location'ах
`/uk/` снимать заголовки апстрима (`proxy_hide_header Strict-Transport-Security;`
`proxy_hide_header X-Frame-Options;`) и ставить свой канон один раз.
Наш фронт-nginx свои заголовки ставит корректно, дубль возникает на edge поверх них.

**Ожидаемо после:** ровно по одному `strict-transport-security` и `x-frame-options`.

## 2. Версия nginx на порту 80 (PENT-F15)

**Что видно:** `Server: nginx/1.31.2` (profk) и `nginx/1.29.3` (infrasafe) по HTTP.
По HTTPS версия уже скрыта.

**Что сделать:** `server_tokens off;` во всех server-блоках, включая `listen 80`
(проще на уровне `http {}`).

**Проверка:** `curl -sI http://profk.uz/ | grep -i server` → `Server: nginx` без версии.

## 3. Vhost принимает произвольный Host (PENT-F12)

**Что видно:** запрос с SNI домена и `Host: evil.example` обслуживается:
profk отвечает 302 на `https://profk.uz/uk/resident-board`, infrasafe отдаёт 200 со страницей.

**Что сделать:** `default_server` для 80 и 443, который отвечает `444` (или `421`);
рабочие vhost'ы только с явными `server_name profk.uz www.profk.uz` / `infrasafe.uz www.infrasafe.uz`.

**Проверка:** `curl -s -o /dev/null -w '%{http_code}\n' -H 'Host: evil.example' https://profk.uz/` → `421` или обрыв.

## 4. Открыть `/uk/api/health` в allowlist (PENT-F17)

**Что видно:** `https://profk.uz/uk/api/health` → `404 text/html` от самого nginx,
путь не входит в prefix-allowlist `/uk/api`. Из-за этого монитор «management-api жив»
(смотрит `/uk/api/v1/` с допуском 200–499) зелёный при мёртвом UK API: 404 отдаёт edge,
не касаясь апстрима.

**Что сделать (оба домена):** в `map $uri $uk_api_allowed` добавить одну строку
**точного** совпадения (не префикс, чтобы не открыть `/health/ratelimit` и `/health/outbox`):

```nginx
"~^/uk/api/health$"    1;
```

Затем перевести монитор Uptime Kuma «management-api жив» на `https://<домен>/uk/api/health`
с допуском только 200–299.

**Проверка:** `curl -s https://profk.uz/uk/api/health` → `{"ok":true}`, `content-type: application/json`;
`curl -s -o /dev/null -w '%{http_code}' https://profk.uz/uk/api/health/outbox` → `404`.

## 5. Опубликовать `/.well-known/security.txt` (PENT-F14)

**Что видно:** на обоих доменах путь отдаёт `200 text/html` (SPA-заглушку), файла нет.

**Что сделать:** положить файл ниже дословно и отдать его `location = /.well-known/security.txt`
из **персистентного** каталога (на profk это `/opt/infrasafe/frontend-html` → `/srv/frontend-html`;
`root /usr/share/nginx/html` живёт внутри образа и пропадёт при пересоздании контейнера).
В этот location **не добавлять `add_header`**: он отключит наследование всех заголовков server-блока.

```
Contact: https://t.me/infrasafe
Expires: 2027-07-01T00:00:00.000Z
Preferred-Languages: ru, uz, en
Canonical: https://profk.uz/.well-known/security.txt
Canonical: https://infrasafe.uz/.well-known/security.txt
```

Один файл на оба домена, RFC 9116 допускает несколько `Canonical`.

**Проверка:** `curl -sD - https://profk.uz/.well-known/security.txt | grep -iE '^(HTTP|content-type)'` → `200`, `text/plain`;
`curl -s https://profk.uz/.well-known/nonexistent` по-прежнему заглушка/404.

## 6. DNS: CAA, DNSSEC, OCSP stapling (PENT-F13)

**Что видно:** `dig +short CAA profk.uz` и `... infrasafe.uz` пусты.

**Что сделать:** минимум — CAA-запись на оба домена под текущий УЦ
(для Let's Encrypt: `0 issue "letsencrypt.org"`). По возможности DNSSEC у
регистратора и `ssl_stapling on; ssl_stapling_verify on;` в HTTPS-блоках.

**Проверка:** `dig +short CAA profk.uz` → непустая запись.

---

## Итоговая проверка одной командой (после релоада)

```bash
for d in profk.uz infrasafe.uz; do
  echo "== $d"
  curl -sD - -o /dev/null https://$d/uk/api/v2/requests/__nope__ | grep -ciE 'strict-transport|x-frame'   # ожидаем 2
  curl -sI http://$d/ | grep -i '^server'                                                                   # без версии
  curl -s -o /dev/null -w 'host: %{http_code}\n' -H 'Host: evil.example' https://$d/                       # 421/444/обрыв
  curl -s -o /dev/null -w 'health: %{http_code} %{content_type}\n' https://$d/uk/api/health              # 200 application/json
  curl -s -o /dev/null -w 'sec.txt: %{http_code} %{content_type}\n' https://$d/.well-known/security.txt  # 200 text/plain
  echo "caa: $(dig +short CAA $d)"
done
```

## Подробные инструкции (в репозитории УК)

- `docs/audit/2026-07-27-edge-owner-checklist.md` — пункты 1, 2, 3, 6
- `docs/audit/2026-07-26-pent-f17-owner-checklist.md` — пункт 4 (allowlist + монитор)
- `docs/audit/2026-07-26-pent-f14-owner-checklist.md` — пункт 5, с точным location-блоком
- `docs/security/security.txt` — сам файл для публикации
