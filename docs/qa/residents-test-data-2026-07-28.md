# Тестовые данные на profk.uz — прод-проверка модуля «Жители» (2026-07-28)

Создано мной при проверке раздела в проде. **Ничего из перечисленного не
удалено** — удаление выполняется только по отдельному подтверждению владельца.

Заполняется в момент создания, а не задним числом.

## Учётные записи

| Что | Идентификатор | Где создано | Зачем | Как удалить |
|---|---|---|---|---|
| Житель `ТЕСТ-QA Жителев` | `users.id = 9`, `telegram_id = 999000001`, username `qa_resident_delete_me` | SQL под `uk_admin` | подопытный для мутаций аккаунта и привязок | `DELETE FROM users WHERE id = 9` (после зависимых строк, см. ниже) |

`telegram_id` выбран **заведомо несуществующим**: это и защита от рассылки
чужому человеку, и попутная проверка деградации — уведомления обязаны падать
молча, не роняя запрос менеджера.

## Зависимые строки (создано по факту)

| Таблица | Признак | Что именно | Как удалить |
|---|---|---|---|
| `user_apartments` | `user_id = 9` | привязки к квартирам `id 10` (`ua=5`, основная) и `id 12` (`ua=6`); привязка к квартире `id 1` (`ua=4`) создана и **удалена** ходом проверки | `DELETE FROM user_apartments WHERE user_id = 9` |
| `audit_logs` | `telegram_user_id = 999000001` | ~12 записей: `user_approved`, `user_blocked`, `user_unblocked`, `resident_apartment_attached`, `resident_binding_approved`, `resident_binding_updated`, `resident_binding_removed` | `DELETE FROM audit_logs WHERE telegram_user_id = 999000001` |
| `user_verifications` | `user_id = 9` | пока не создавалось (будет на проверке PR-5) | `DELETE FROM user_verifications WHERE user_id = 9` |
| `user_documents` | `user_id = 9` | пока не создавалось | `DELETE FROM user_documents WHERE user_id = 9` |
| `webhook_outbox` | события `apartment_request.*` за время проверки | ⚠ **не чистить руками** — записей может не быть вовсе: у `apartment_request.*` в `_ROUTING` endpoint=None, строка в outbox не создаётся. Оставшееся подчистит штатная retention-задача |

**Квартиры, дома и дворы не создавались** — использованы существующие. Их
трогать нельзя.

## Готовый SQL для зачистки

Выполнять под `uk_admin` (роль `profk_bot` не видит часть таблиц). Порядок
важен: сначала зависимые строки, потом сам пользователь.

```sql
BEGIN;
DELETE FROM user_documents     WHERE user_id = 9;
DELETE FROM user_verifications WHERE user_id = 9;
DELETE FROM user_apartments    WHERE user_id = 9;
DELETE FROM audit_logs         WHERE telegram_user_id = 999000001;
DELETE FROM users              WHERE id = 9 AND telegram_id = 999000001;
COMMIT;
```

Перед `COMMIT` стоит убедиться, что затронуто ровно ожидаемое число строк —
`id = 9` проверяется вместе с `telegram_id`, чтобы промах по id не удалил
живого человека.

## Временные изменения, УЖЕ откаченные

* `users.roles` жителя `id = 9` временно менялись на `["applicant","executor"]`
  для проверки запрета блокировки мультиролевых (Т2) и **возвращены** к
  `["applicant"]` сразу после проверки. Текущее состояние в БД — исходное.

## Чужие данные — не трогались

Живые аккаунты (`Nazya`, `ULUGBEK`, `Mikhail Grafov`, `Администратор`) читались,
но **не изменялись**. Единственная попытка мутации по чужому id (`residents/8`)
была намеренной проверкой ownership и вернула 404, ничего не изменив.

## Что НЕ создавалось

* Файлы в Media Service и сообщения в TG-каналах — документы через бота не
  загружались (для этого нужна живая Telegram-сессия жителя).
* Записи на infrasafe.uz — туда ничего не деплоилось и не писалось.
