# F-08/F-09 — чек-лист владельцу домена/edge (аудит profk 2026-07-11)

Наша (кодовая) часть F-08 закрыта отдельно: security-заголовки фронт-nginx
(HSTS, nosniff, Referrer-Policy, Permissions-Policy) едут с образом
`uk-frontend`. Пункты ниже находятся вне репозитория UK: DNS — у владельца
домена profk.uz, edge-nginx — зона InfraSafe (наши правки — только `/opt/uk`).

## Статус (2026-07-24, ответ владельца + наша независимая re-проверка)

1. **DNS-почта — ЗАКРЫТО с оговоркой.** SPF `"v=spf1 -all"` и DMARC
   `"v=DMARC1; p=reject"` проверены на живом DNS — без отклонений. MX: панель
   webspace.uz не принимает канонический RFC-7505 `0 .`, вместо него
   `0 0.` — таргет `0.` не резолвится (NXDOMAIN, проверено), практический
   эффект тот же: почта недоставляема. Оговорка зафиксирована; эскалация к
   регистратору за каноническим null MX — не требуется (анти-спуфинг несут
   SPF/DMARC, они развёрнуты полностью).
2. **www.profk.uz — ЗАКРЫТО.** Выбран вариант удаления алиаса: CNAME `www`
   удалён, имя не резолвится (проверено `dig` на живом DNS) — TLS-warning
   невозможен.
3. **Edge-nginx — В РАБОТЕ у владельца** (PR готов, `nginx -t` пройден,
   reload обещан «сегодня»): `frame-ancestors 'self' https://web.telegram.org`
   в CSP `/uk/*`; handshake-щит `limit_conn 10/IP + limit_req 10 burst` на
   `/uk/ws/v2/` (зеркало щита, стоящего на `/uk/ws/v1/access/` с июня —
   уточнение владельца: v1/access был защищён ранее, дыра касалась только
   management-WS v2). После их reload — наша re-проверка №3 ниже.

## 1. DNS-почта (F-09): анти-спуфинг

Сейчас: MX `0 profk.uz`, SMTP-порты закрыты, SPF/DMARC отсутствуют → домен
удобен для email-спуфинга, письма «от profk.uz» нечем отвергать.

**Вариант А — почта на домене НЕ используется (рекомендуемый, судя по закрытым
SMTP-портам):**

```
profk.uz.        MX   0 .                      ; null MX (RFC 7505)
profk.uz.        TXT  "v=spf1 -all"            ; никто не вправе слать от домена
_dmarc.profk.uz. TXT  "v=DMARC1; p=reject"     ; подделки — в reject
```

**Вариант Б — почта планируется:** MX почтового провайдера + его SPF include +
DKIM-ключи провайдера + DMARC (начать с `p=quarantine; rua=mailto:...`,
ужесточить до `p=reject` после недели чистых отчётов).

## 2. www.profk.uz (F-09): сертификат либо удаление алиаса

Сейчас: CNAME `www.profk.uz → profk.uz`, но сертификат содержит только SAN
`profk.uz` → у пользователей `https://www.profk.uz` TLS-warning.

Любой из двух вариантов, на выбор владельца:
- перевыпустить сертификат с SAN `www.profk.uz` (для certbot:
  `certbot --expand -d profk.uz -d www.profk.uz`) и добавить в edge-nginx
  301-redirect `www.profk.uz → profk.uz`; либо
- удалить CNAME `www` из DNS-зоны (если www-вариант не нужен).

## 3. Edge-nginx (F-08-хвост + F-05-хвост): два добавления в конфиг `/uk/*`

**(а) `frame-ancestors` в существующий CSP.** В нашем фронт-nginx X-Frame-Options
НЕ выставлен осознанно: Mini App (TWA) открывается в iframe `web.telegram.org`
в веб-версии Telegram, а XFO не умеет allowlist. Защита от clickjacking должна
жить в CSP на edge — добавить в существующий `Content-Security-Policy` для
`/uk/*` директиву:

```
frame-ancestors 'self' https://web.telegram.org;
```

**(б) Лимиты на WS-handshake** (`/uk/ws/`): приложение уже закрывает
неаутентифицированные соединения по таймауту 10 с (наша часть F-05), но
шторм handshake'ов дешевле резать на edge:

```nginx
limit_conn_zone $binary_remote_addr zone=uk_ws_conn:10m;
limit_req_zone  $binary_remote_addr zone=uk_ws_req:10m rate=10r/m;

location /uk/ws/ {
    limit_conn uk_ws_conn 10;
    limit_req  zone=uk_ws_req burst=10 nodelay;
    ...existing proxy config...
}
```

(числа — стартовые: 10 одновременных WS и 10 новых handshake/мин с одного IP
хватает дашборду с запасом; поднять, если появятся жалобы операторов).

## Re-проверка после исполнения (наша сторона)

```bash
# 1. DNS-почта
dig +short MX profk.uz                  # ожидаем: 0 .
dig +short TXT profk.uz                 # ожидаем: "v=spf1 -all"
dig +short TXT _dmarc.profk.uz          # ожидаем: "v=DMARC1; p=reject"

# 2. www-сертификат (если выбран вариант с SAN)
echo | openssl s_client -connect profk.uz:443 -servername www.profk.uz 2>/dev/null \
  | openssl x509 -noout -ext subjectAltName   # ожидаем www.profk.uz в SAN
# либо: dig +short CNAME www.profk.uz — пусто, если алиас удалён

# 3. frame-ancestors
curl -sI https://profk.uz/uk/ | grep -i content-security-policy | grep -o frame-ancestors
```
