# PENT-F14 — чек-лист владельцу: публикация `security.txt`

_Составлено 2026-07-26. Всё, что про profk, проверено запросами и чтением файлов
на самом хосте; про infrasafe.uz — см. предупреждение в задаче 2._

## Что не так сейчас

```
$ curl -s -o /dev/null -w '%{http_code} %{content_type}\n' https://profk.uz/.well-known/security.txt
200 text/html
```

Файла нет, но домен отвечает **успехом с HTML-страницей**: путь попадает в
catch-all корневого сайта (`location / { try_files $uri $uri/ /index.html; }`).
Для security-запроса это хуже, чем `404`: исследователь получает `200` и парсит
из ответа заглушку вместо контакта. Каталога `.well-known` на диске нет
(`/opt/infrasafe/public/.well-known` отсутствует).

Решение владельца — **публиковать настоящий файл** (вариант «отдавать 404» был
бы явно принятым риском, а не исправлением).

## Что публикуем

Дословно файл [`docs/security/security.txt`](../security/security.txt) из
репозитория:

```
Contact: https://t.me/infrasafe
Expires: 2027-07-01T00:00:00.000Z
Preferred-Languages: ru, uz, en
Canonical: https://profk.uz/.well-known/security.txt
Canonical: https://infrasafe.uz/.well-known/security.txt
```

Один файл на оба домена: RFC 9116 §2.5.5 допускает несколько `Canonical`, и оба
домена в нём перечислены — значит файл валиден на каждом. Правки вносить в
репозитории и переопубликовывать, а не редактировать на хосте: отредактированная
на месте копия через полгода станет неизвестного происхождения.

## Задача 1 — profk.uz (всё проверено, можно делать)

**Почему не просто «положить файл в docroot».** Server-блок profk.uz имеет
`root /usr/share/nginx/html` (`nginx.profk.conf:253`), и это каталог **внутри
образа** nginx: bind-mount'ами подключены только подкаталоги (`data`, `css`,
`public`). Файл, положенный в `/usr/share/nginx/html/.well-known/`, исчезнет при
пересоздании контейнера. Персистентный каталог, уже смонтированный в этот
контейнер, — `/opt/infrasafe/frontend-html` → `/srv/frontend-html`.

1. Положить файл (владелец `infrasafe`, режим `644` — файл публичный по смыслу):

```bash
mkdir -p /opt/infrasafe/frontend-html/.well-known
# содержимое — из docs/security/security.txt репозитория UK, дословно
install -m 644 -o infrasafe -g infrasafe /path/to/security.txt \
        /opt/infrasafe/frontend-html/.well-known/security.txt
```

2. В `/opt/infrasafe/nginx-config/nginx.profk.conf`, в HTTPS-server-блок
   `server_name profk.uz` (тот, что с `listen 443`), добавить:

```nginx
        # PENT-F14: RFC 9116. Точное совпадение (`location =`) имеет приоритет над
        # prefix- и regex-локациями, поэтому catch-all `location /` больше не
        # подменит файл SPA-заглушкой. root — персистентный bind-mount
        # (/opt/infrasafe/frontend-html), а не каталог образа.
        location = /.well-known/security.txt {
            root /srv/frontend-html;
            access_log off;
        }
```

⚠️ **Не добавлять сюда ни одного `add_header`.** В этом конфиге уже зафиксирована
грабля (комментарий у `location ~* \.(html|htm)$`): любой `add_header` на уровне
location убивает наследование ВСЕХ `add_header` из server-блока, включая
`always`. Без директив ответ унаследует security-заголовки как надо, а
`Content-Type: text/plain` придёт из `mime.types` по расширению `.txt`.

3. Применить и проверить:

```bash
docker exec infrasafe-nginx-1 nginx -t
docker exec infrasafe-nginx-1 nginx -s reload

curl -s -D- -o /tmp/s.txt https://profk.uz/.well-known/security.txt | grep -iE '^(HTTP/|content-type)'
# ожидаем: HTTP/2 200 и content-type: text/plain
cat /tmp/s.txt          # ровно 5 строк, начиная с Contact:
curl -s https://profk.uz/.well-known/nonexistent | head -c 40
# контроль: посторонний путь под .well-known по-прежнему отдаёт заглушку/404 —
# мы открыли ровно один файл, а не каталог
```

## Задача 2 — infrasafe.uz (тот же рецепт, но ДРУГОЙ хост)

⚠️ **Проверить на месте, не копировать наши выводы.** Установлено, что живой
nginx на profk запускается с единственным файлом
(`nginx -c /etc/nginx/custom/nginx.profk.conf`), а `infrasafe.uz` резолвится в
**95.46.96.105** — то есть его конфигурацию обслуживает другой хост, и лежащий
рядом `nginx.production.conf` на profk **не используется**. Проверить структуру
на .105 мы не смогли: хост отбивает наш ssh-ключ
(`Permission denied (publickey)`, повторно 2026-07-26).

Рецепт тот же (persistent-каталог + `location = /.well-known/security.txt` без
`add_header`), но пути и имя контейнера подтвердить на .105. Плюс infrasafe.uz —
домен партнёра: публикация нашего контакта на нём должна быть их согласованным
решением, а не следствием этого чек-листа.

## Срок действия — не «выставил и забыл»

`Expires: 2027-07-01` умышленно меньше года: по RFC 9116 §2.5.5 файл с истёкшим
сроком следует считать недействительным. Чтобы это не протухло молча, в
репозитории есть гейт `tests/services/test_security_txt.py` — он краснеет **за 30
дней до** срока с инструкцией продлить. Красный тест в этом месте не поломка, а
напоминание в единственный момент, когда оно полезно.

## Порядок

Задача 1 — независима, можно делать сразу. Задача 2 — после подтверждения доступа
и структуры на .105 (и согласия по домену партнёра). Пункт `PENT-F14` закрывается
только когда файл живой на обоих домах; если по infrasafe.uz решение будет
«не публиковать» — это фиксируется как явно принятый риск с обоснованием, а не
как закрытие.
