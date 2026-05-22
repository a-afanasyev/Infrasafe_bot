# FIX-007 — Контракт inbound-webhook для InfraSafe-оператора

Документ для оператора **InfraSafe**. Описывает, как настроить sender
(`src/clients/ukApiClient.js`), чтобы вебхуки «InfraSafe → UK» принимались
новым приёмником на стороне UK.

Статус UK-side: Фаза 1 (security envelope) реализована, проходит 10/10 тестов.
Деплой `uk-management-api` — по согласованию (см. «Go-live» внизу).

---

## 1. Endpoint

```
POST  {UK_API_URL}/api/v2/webhooks/infrasafe/alert
```

- `{UK_API_URL}` — базовый URL UK API, уже сконфигурированный у вас
  (внутренний через `uk-network` либо внешний `https://infrasafe.uz/uk`).
- Внешний полный URL: `https://infrasafe.uz/uk/api/v2/webhooks/infrasafe/alert`
- `Content-Type: application/json`
- Аутентификации (Bearer/cookie) **нет** — подпись HMAC и есть аутентификация.

## 2. Подпись HMAC (критично)

Каждый запрос обязан нести заголовок:

```
x-webhook-signature: t=<unix_seconds>,v1=<hmac_hex>
```

- `<unix_seconds>` — текущее Unix-время в **секундах**.
- `<hmac_hex>` — `HMAC-SHA256(secret, message)` в hex, где
  **`message = "<unix_seconds>" + "." + <raw_request_body>`**
  (timestamp, литеральная точка, затем **ровно те байты тела**, что уходят в HTTP).
- `secret` — общий секрет `UK_WEBHOOK_SECRET` (см. §5).

**Важно:** подписывать нужно те же самые байты, что отправляются. Нельзя
сериализовать JSON повторно между подписанием и отправкой — иначе подпись
не сойдётся (UK получит 401).

### Пример (Node.js)

```js
const crypto = require('crypto');

const body = JSON.stringify(payload);          // ← отправляется КАК ЕСТЬ
const t = Math.floor(Date.now() / 1000);
const sig = crypto
  .createHmac('sha256', process.env.UK_WEBHOOK_SECRET)
  .update(`${t}.${body}`)
  .digest('hex');

await httpClient.post(`${UK_API_URL}/api/v2/webhooks/infrasafe/alert`, body, {
  headers: {
    'Content-Type': 'application/json',
    'x-webhook-signature': `t=${t},v1=${sig}`,
  },
});
```

## 3. Окно времени и replay

- **Timestamp window — 300 секунд.** UK отклоняет запрос (401), если
  `|now − t| > 300s`. Часы sender'а должны быть синхронизированы по NTP.
- **Replay-dedup по `event_id`.** UK хранит `event_id` принятых событий 600s.
  - Каждое **логическое** событие — уникальный `event_id`.
  - **Retry того же события** — тот же `event_id`. UK вернёт **409**.
  - **409 трактовать как success** (idempotent re-delivery — событие уже принято).

## 4. Тело запроса (Фаза 1)

JSON-объект, обязательные поля:

| Поле | Тип | Назначение |
|---|---|---|
| `event_id` | string | Уникальный id события (для подписи/dedup/audit) |
| `event` | string | Тип события, напр. `alert.created` |
| `timestamp` | string | Метка времени события (ISO-8601) |
| `alert` | object | Данные алерта (точные поля — согласуем под Фазу 2) |

Пример:

```json
{
  "event_id": "a1b2c3d4-...",
  "event": "alert.created",
  "timestamp": "2026-05-22T10:00:00Z",
  "alert": { "severity": "high", "message": "..." }
}
```

Невалидная схема (нет обязательного поля) → **422**.

## 5. Общий секрет

UK-verifier читает `UK_WEBHOOK_SECRET` и `UK_WEBHOOK_SECRET_NEXT`, принимает
**любой совпавший** (для бесшовной ротации). Sender InfraSafe должен подписывать
тем же значением `UK_WEBHOOK_SECRET`.

**Ротация** (по integration-plan §4.4): прописать `UK_WEBHOOK_SECRET_NEXT` в оба
`.env`, рестарт обоих сервисов (UK уже принимает OLD‖NEW), затем выставить
`UK_USE_NEXT_SECRET=true` на стороне InfraSafe-sender'а, рестарт. Через ≥1 сутки
перенести `_NEXT → основной`.

⚠️ Секрет, который сейчас на диске, подлежит ротации (UK FIX-002). Перед
go-live согласовать актуальное значение `UK_WEBHOOK_SECRET`.

## 6. Коды ответа — что должен делать sender

| Код | Значение | Действие sender'а |
|---|---|---|
| **202** | Принято | Успех |
| **401** | Нет/битая/просроченная подпись | Проверить алгоритм подписи и синхронизацию часов. Не ретраить вслепую |
| **409** | Дубликат `event_id` | Трактовать как **success** — событие уже принято |
| **422** | Невалидная схема тела | Исправить payload. Не ретраить как есть |
| **429** | Превышен rate-limit | Backoff и повтор позже |
| **503** | UK-приёмник не сконфигурирован | Сигнал UK-ops (нет секрета на UK-стороне) |

**Rate-limit:** 60 запросов в минуту с одного IP.

## 7. Go-live

- Сейчас (Фаза 1) endpoint **валидирует и подтверждает (202), но заявку из
  алерта пока не создаёт** — это Фаза 2.
- Для проверки самой связки (подпись, доставка) слать тестовые события можно
  после деплоя `uk-management-api` — UK ответит 202.
- **Боевую отправку алертов начинать после Фазы 2** на UK-стороне (создание
  заявки), иначе события будут подтверждены, но не обработаны.
- Сообщить UK, когда sender готов — согласуем окно деплоя и значение секрета.

---

## Чек-лист для оператора

- [ ] Endpoint в sender: `POST {UK_API_URL}/api/v2/webhooks/infrasafe/alert`
- [ ] Заголовок `x-webhook-signature: t=<unix>,v1=<hmac_hex>`
- [ ] HMAC-SHA256 над `"<t>." + raw_body`, секрет `UK_WEBHOOK_SECRET`
- [ ] Подписываются ровно отправляемые байты (без повторной сериализации)
- [ ] Часы sender'а синхронизированы по NTP (окно 300s)
- [ ] Уникальный `event_id` на событие; 409 = success
- [ ] Обработаны коды 401/409/422/429/503
- [ ] Согласованы значение `UK_WEBHOOK_SECRET` и окно go-live с UK
