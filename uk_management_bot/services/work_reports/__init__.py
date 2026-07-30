"""Сервис визуальных отчётов «до/после» (публичная витрина резидентов).

Функциональный пакет (не класс) — как `material_service.py`. ~9 функций:

* ``derive_public_address`` — чистый резолвер публичного адреса;
* ``sync_pending_drafts`` — автосинхронизация черновиков из завершённых заявок;
* ``autofill_media`` / ``validate_media_ids`` — автозаполнение и ручная
  валидация медиа;
* ``revoke_stale_publications`` — снятие публикации с заявок, переставших
  быть eligible;
* ``publish_report`` / ``unpublish_report`` / ``reject_report`` /
  ``reopen_report`` / ``reconcile_publication_locks`` — сага публикации,
  координирующая состояние между БД бота (`work_reports`) и отдельной БД
  media-service (`media_files`) БЕЗ two-phase commit. Именно эта пятёрка
  несёт основной риск модуля: баг здесь может либо опубликовать контент, не
  прошедший модерацию, либо навсегда «подвесить» медиа в залоченном
  состоянии. Порядок операций внутри каждой функции — часть контракта, не
  стилистика; см. docstring каждой функции.

Инварианты (см. также database/models/work_report.py):

* ``WorkReport.request_number`` — НЕ FK: заявку можно жёстко удалить, отчёт —
  бессрочный снапшот и обязан её пережить. Отсюда: синк — dialect-aware
  ``INSERT ... ON CONFLICT DO NOTHING`` (паттерн ``webhook_sender.
  _outbox_insert_stmt``), а не ORM-relationship; сверка публикаций — INNER
  JOIN к `requests`, где отсутствие строки-заявки — не сигнал к действию.
* Автозаполнение медиа (`autofill_media`) фильтрует молча — это автоматический
  подбор кандидатов, не выбор человека. Ручная валидация (`validate_media_ids`)
  на тех же условиях — REJECTS, потому что выбор сделал человек и тихий
  дроп был бы неверной реакцией на его ошибку.
* Сага публикации не использует two-phase commit между двумя БД: вместо
  этого — строго упорядоченные шаги с компенсацией (publish_report) и
  идемпотентная фоновая сверка (reconcile_publication_locks) как
  self-healing на случай крэша посреди саги.

Карта пакета (AUD6-P2-56, разноска бывшего work_report_service.py):

* ``errors.py`` — исключения + `_LOCK_HOLDING_STATUSES`;
* ``addressing.py`` — `derive_public_address`, `address_looks_like_apartment`;
* ``media_selection.py`` — fetch/apply/autofill/validate медиа;
* ``sync.py`` — `sync_pending_drafts` + `revoke_stale_publications`;
* ``saga.py`` — publish/unpublish/reject/reopen;
* ``previews.py`` — прогрев превью;
* ``autopublish.py`` — `autopublish_ready_drafts`;
* ``reconcile.py`` — `reconcile_publication_locks`.

Публичная точка входа — ПО-ПРЕЖНЕМУ фасад
`uk_management_bot.services.work_report_service`: колл-сайты и тесты импортируют
и monkeypatch-ят атрибуты по этому имени, поэтому межмодульные вызовы внутри
пакета тоже идут через фасад (см. `_svc()` в модулях).
"""
