# Руководство менеджера — UK Management

> Роль: `manager`. Роль хранится в `user.roles` (JSON-массив), активная роль — в
> `user.active_role`. Менеджер работает в двух интерфейсах: **веб-дашборд** (React, путь
> `/uk/`) и **Telegram-бот** (админ-панель). Часть функций контроля доступа доступна
> только системному администратору (`system_admin`) — см. `docs/guides/ADMIN_GUIDE.md`.

Гейты доступа менеджера в дашборде заданы в `frontend/src/App.tsx` (route guards
`ProtectedRoute allowedRoles`), а видимость пунктов меню — в
`frontend/src/layouts/DashboardLayout.tsx:71-106` (`NAV_ENTRIES`). Основной блок дашборда
`/dashboard/*` пускает роли `['admin', 'manager']` (`App.tsx:102`).

---

## Часть A. Веб-дашборд

Вход — по логину/паролю на `/login`. После входа менеджер попадает на канбан заявок
(`App.tsx:103`, индекс-маршрут `/dashboard`). Слева — сайдбар с разделами
(`DashboardLayout.tsx`), сверху — топбар с действиями страницы, переключателем языка
(RU/UZ) и темы (`DashboardLayout.tsx:273-285`). Смена пароля и профиль — в меню
пользователя внизу сайдбара (`DashboardLayout.tsx:367-401`).

Разделы меню (`NAV_ENTRIES`, `DashboardLayout.tsx:71-106`):

1. Аналитика — `/dashboard/analytics`
2. Заявки — `/dashboard` (канбан, индекс)
3. Персонал (группа) — Сотрудники / Смены / Шаблоны смен
4. Адреса — `/dashboard/addresses`
5. Табло жителей — `/dashboard/board-editor`
6. Обратная связь — `/dashboard/feedback`
7. Контроль доступа (группа) — Обзор / История проездов / База доступа / Оборудование
8. Склад — `/dashboard/materials`

### A.1. Заявки (канбан) — `/dashboard`

Файл: `frontend/src/pages/KanbanPage.tsx`.

- Доска заявок по статусам (`KanbanBoard`), карточка кликается и открывает деталь
  (`RequestDetailModal`, `KanbanPage.tsx:68-74`).
- Кнопка **«Создать по звонку»** в топбаре (`KanbanPage.tsx:51-60`) открывает
  `CallCenterModal` — заведение заявки менеджером от лица жителя (call-центр).
- Поддержан deep-link из админ-панели InfraSafe: `/dashboard?request=<номер>` открывает
  нужную заявку (`KanbanPage.tsx:31-49`). Ссылка работает только внутри
  `ProtectedRoute` (admin|manager) — иначе пользователь уходит на `/login` или
  `/resident-board`.
- Приёмка выполненных заявок за заявителя выполняется из детали заявки
  (`RequestDetailModal.tsx`) и через бот — см. раздел B.5.

Формат номера заявки — строка `YYMMDD-NNN` (`RequestNumberService`).

### A.2. Аналитика — `/dashboard/analytics`

Файл: `frontend/src/pages/AnalyticsPage.tsx`.

- Переключатель периода: 7 / 30 / 90 дней (`AnalyticsPage.tsx:157-161`).
- KPI-карточки: всего заявок, среднее время решения (ч), удовлетворённость, на смене
  сейчас (`AnalyticsPage.tsx:255-288`).
- График «Заявки по дням» (создано/закрыто), круговая диаграмма по категориям
  (`AnalyticsPage.tsx:291-395`).
- Распределение по статусам, топ-5 исполнителей, лента последних действий
  (`AnalyticsPage.tsx:398-535`).
- Часы в правом верхнем углу — время Ташкента (`AnalyticsPage.tsx:167-177`).

### A.3. Персонал → Сотрудники — `/dashboard/employees`

Файл: `frontend/src/pages/EmployeesPage.tsx`.

- Верхняя панель статистики: всего / на смене / ожидают верификации / верифицированы
  (`EmployeesPage.tsx:117-122`).
- Блок **«Ожидают одобрения»** (`PendingApprovalCard`) — кнопки **Одобрить** /
  **Отклонить** для каждого нового сотрудника (`EmployeesPage.tsx:164-186`,
  мутации `useApproveEmployee`/`useRejectEmployee`).
- Фильтры: роль (исполнитель/менеджер), статус (на смене/верифицирован),
  специализация; поиск в топбаре (`EmployeesPage.tsx:188-287`).
- Переключатель вида плитки/таблица, сохраняется в localStorage
  (`EmployeesPage.tsx:35-44`).
- Действия по сотруднику (карточка `StaffCard` / строка `StaffTable`):
  - **Назначить заявку** (`AssignRequestModal`) — `onAssign`.
  - **Заблокировать / Разблокировать** с подтверждением (`handleBlockToggle`,
    `EmployeesPage.tsx:71-88`).
  - **Удалить** (`DeleteEmployeeModal`).
- Кнопка **Добавить** (`AddEmployeeModal`) и **Экспорт** в топбаре
  (`EmployeesPage.tsx:98-110`).
- Клик по сотруднику ведёт на карточку `/dashboard/employees/:id`
  (`EmployeeDetailPage.tsx`).

### A.4. Персонал → Смены — `/dashboard/shifts`

Файл: `frontend/src/pages/ShiftsPage.tsx`.

- Три режима просмотра: день / неделя / месяц (`ShiftViewToggle`,
  `ShiftsPage.tsx:108-128`). Навигация вперёд/назад/сегодня.
- Данные обновляются в реальном времени (WebSocket, `useShiftsWebSocket`,
  `ShiftsPage.tsx:54`).
- Карточки статистики: на смене, покрытие %, покрытие по специализациям, переводы
  смен, общая нагрузка (`ShiftsPage.tsx:158-164`).
- Кнопка **Создать смену** (`CreateShiftModal`) и переход к **Шаблонам**
  (`ShiftsPage.tsx:108-128`).
- Клик по смене открывает деталь (`ShiftDetailModal`), из неё — редактирование.
- Блок **Запросы на перевод смен** (`TransferRequestCard`, `ShiftsPage.tsx:268-289`) —
  согласование передачи смены между исполнителями.
- Тепловая карта покрытия (день) / календарная тепловая карта (месяц).

### A.5. Персонал → Шаблоны смен — `/dashboard/templates`

Файл: `frontend/src/pages/TemplatesPage.tsx`.

- Статистика: всего шаблонов, авто-создание, активных (`TemplatesPage.tsx:90-115`).
- Таблица шаблонов: имя, время (начало—конец с учётом перехода через полночь), тип
  смены, дни недели или **цикл** (N через M дней с якорной датой), специализации,
  диапазон исполнителей (min—max), тумблер авто-создания (`TemplatesPage.tsx:299-486`).
- Действия по строке: **Создать смену из шаблона**, **Редактировать**, **Удалить**
  (с подтверждением) (`TemplatesPage.tsx:461-483`).
- Кнопка **Создать шаблон** в топбаре (`CreateTemplateModal`).
- Тумблер **auto_create** включает автоматическое создание смен по расписанию шаблона
  (`handleToggleAutoCreate`, `TemplatesPage.tsx:122-124`).

### A.6. Адреса — `/dashboard/addresses`

Файл: `frontend/src/pages/AddressesPage.tsx`.

Трёхуровневый справочник адресов: **Двор (Yard) → Дом (Building) → Квартира
(Apartment)** (`AddressesPage.tsx:44-45`).

- Панель статистики с переходами: дворы / дома / квартиры / жители-модерация
  (`AddressStatsBar`, `AddressesPage.tsx:209-215`).
- Две вкладки: **Справочник** и **Модерация** (жители на подтверждение привязки,
  `ModerationPanel`, `AddressesPage.tsx:229-230`).
- Навигация по уровням через хлебные крошки (`AddressBreadcrumb`), плоские виды
  «все дома» / «все квартиры» с фильтрами по двору/дому
  (`AddressesPage.tsx:98-113`, `249-268`).
- Вид плитки/таблица; тумблер «показывать неактивные» (`showInactive`).
- Действия по объекту: создать, редактировать, включить/выключить (soft),
  удалить (soft) и **удалить навсегда** (purge) — с подтверждением
  (`AddressesPage.tsx:270-334`).
- Массовое создание квартир (`showBulkCreate`), профиль квартиры по клику
  (`profileApartmentId`).

### A.7. Табло жителей (редактор) — `/dashboard/board-editor`

Файл: `frontend/src/pages/BoardEditorPage.tsx`.

- Редактор публичной страницы-лендинга УК (`/resident-board`): секции, объявления,
  локализованные тексты (RU/UZ/EN), порядок блоков перетаскиванием (dnd-kit)
  (`BoardEditorPage.tsx:1-33`).
- Изменения сохраняются через `useUpdateBoardConfig`; предпросмотр — встроенный
  `ResidentBoardPage` (`BoardEditorPage.tsx:33`).

### A.8. Обратная связь — `/dashboard/feedback`

Файл: `frontend/src/pages/FeedbackPage.tsx`.

- Список обращений жителей: тип (жалоба/пожелание), статус (новое/на рассмотрении/
  решено), текст, автор (`FeedbackPage.tsx:14-20`, `92-131`).
- Фильтры по типу и статусу (`FeedbackPage.tsx:71-86`).
- Клик по строке открывает деталь (`FeedbackDetailModal`) для обработки; вложения
  помечены скрепкой (`FeedbackPage.tsx:120-123`).

### A.9. Контроль доступа (группа)

Модуль ANPR/шлагбаумов/пропусков. Роли модуля — `ACCESS_MODULE_ROLES` = manager,
system_admin, security_operator (`frontend/src/constants/roles.ts:47-51`). Экраны
менеджера (история/база/оборудование) — `ACCESS_MANAGER_ROLES` = manager, system_admin
(`roles.ts:59-62`); оператор охраны на них не допускается (`App.tsx:126-137`).

Подробная пошаговая инструкция уже есть — **не дублируется** здесь:
`docs/access-control/guides/manager.md`. Кратко:

- **Обзор** — `/dashboard/access` (`AccessControlPage`): live-панель модуля
  (`App.tsx:119-121`).
- **История проездов** — `/dashboard/access/history` (`AccessHistoryPage`): журнал
  проездов с фильтрами, деталь события (камера, достоверность, цепочка решений, команды
  шлагбаума, фото). Журналы append-only.
- **База доступа** — `/dashboard/access/database` (`AccessDatabasePage`): вкладки
  Автомобили / Пропуска / Заявки жителей. Менеджер добавляет/блокирует авто,
  создаёт taxi-пропуски, подтверждает/отклоняет заявки жителей на постоянный авто.
- **Оборудование** — `/dashboard/access/equipment` (`AccessEquipmentPage`): зоны и
  въезды доступны manager+system_admin; камеры, шлагбаумы, edge-контроллеры и
  device-ключи — **только system_admin** (гейтинг табов, `App.tsx:132-137`).

Границы: менеджер **не может** менять/удалять события/решения/аудит и открывать
шлагбаум «за оператора» без причины (`docs/access-control/guides/manager.md`, раздел 4).

Референс по продукту и данным: `docs/access-control/TECHNICAL_SPEC.md`,
`docs/access-control/DATA_MODEL_PILOT.md`.

### A.10. Склад материалов — `/dashboard/materials`

Файл: `frontend/src/pages/materials/MaterialsPage.tsx`. Гейт — `MATERIALS_MODULE_ROLES`
= manager, system_admin (`roles.ts:69-72`, `App.tsx:141-143`).

- Три вкладки: **Остатки** / **Журнал операций** / **На закуп**
  (`MaterialsPage.tsx:42`, `56-80`).
- Операции: приход (`ReceiptDialog`), расход/списание по заявке (`IssueDialog`),
  корректировка (`AdjustmentDialog`), сторно операции (`ReversalDialog`). Журнал
  **append-only** — исправления только через сторно (`MaterialsPage.tsx:35-39`).
- Карточка номенклатуры — создание/редактирование (`MaterialFormDialog`).
- Экспорт CSV операций и списка на закуп (`exportOperationsCsv`,
  `exportProcurementCsv`, `MaterialsPage.tsx:20-26`).
- Учёт партий FIFO и себестоимость по заявкам — см. `docs/MATERIALS_MODULE.md`.

Полное описание модели, статусов и бизнес-правил склада: `docs/MATERIALS_MODULE.md`.

---

## Часть B. Telegram-бот (админ-панель менеджера)

Клавиатура менеджера собирается в `uk_management_bot/keyboards/base.py:88-158`
(`get_main_keyboard_for_role`, ветка `active_role in ["admin","manager"]`). Кнопка
**«Панель администратора»** (`base.py:154-155`) открывает главное меню менеджера
(`uk_management_bot/keyboards/admin.py:8-22`, `get_manager_main_keyboard`).

> Важно: у менеджера/админа кнопка «Создать заявку» (applicant-flow) скрыта
> (`base.py:134`) — заявки менеджер заводит через call-центр в дашборде.

Главное меню бота (`admin.py:8-22`):

1. Новые заявки
2. Активные заявки
3. Исполненные заявки (подменю)
4. Закуп
5. Архив
6. Смены
7. Справочник адресов
8. Управление пользователями
9. Управление сотрудниками
10. Создать приглашение

### B.1. Работа с заявками в боте

- Списки заявок с пагинацией и карточками «#номер • Категория • Адрес»
  (`admin.py:36-76`, `get_manager_request_list_kb`). Статусные иконки — из
  `STATUS_EMOJI` (`admin.py:47-49`).
- Клик по заявке (`mview_`) открывает деталь с действиями (назначение исполнителя,
  просмотр отчёта/медиа) — хендлеры в `handlers/admin/*`.

### B.2. Исполненные заявки (подменю)

`admin.py:25-33` (`get_completed_requests_submenu`):

- **Ожидают приёмки**
- **Возвращённые**
- **Не принятые** — заявки, подтверждённые менеджером, но не принятые заявителем
  (см. B.5).

### B.3. Приглашения сотрудников/жителей

Кнопка **Создать приглашение** запускает FSM (`handlers/admin/invites.py`). Выбор роли
приглашения (`admin.py:79-88`): заявитель, исполнитель, менеджер, **обходчик
(inspector)**. Для исполнителя — выбор специализации (`admin.py:91-105`), затем срок
действия ссылки (1 час / 24 часа / 7 дней, `admin.py:108-116`) и подтверждение.

### B.4. Управление пользователями и ролями (бот)

- **Управление пользователями** — панель со статистикой и списком
  (`handlers/user_management/entry.py:17-36`, `open_user_management`).
- Верификация жителей, запрос документов, выдача/отзыв прав на подачу заявок —
  подробно в `docs/guides/ADMIN_GUIDE.md` и
  `uk_management_bot/VERIFICATION_SYSTEM_ADMIN_GUIDE.md` (доступ: admin и manager).
- Управление ролями пользователя: добавление/снятие ролей с обязательным комментарием,
  нельзя снять последнюю роль (`handlers/user_management/roles_specs.py:30-289`).
- Управление специализациями исполнителя (`roles_specs.py:294-508`).

> Права на управление ролями проверяются через `has_admin_access`
> (`roles_specs.py:37`, `has_admin_access`). Роль назначается/снимается через
> `AuthService.assign_role` / `remove_role` с записью комментария (`roles_specs.py:251-256`).

### B.5. Приёмка заявки за заявителя

Источник: `docs/TASK_17_MANAGER_ACCEPTANCE.md` (историческая структура — актуальные
хендлеры в `handlers/unaccepted_requests.py`).

Когда заявитель долго не принимает выполненную работу, заявка попадает в раздел
**«Не принятые»** (подтверждено менеджером `manager_confirmed=True`, статус
«Выполнена», `is_returned=False`). Менеджер может:

1. **Напомнить заявителю** — push-уведомление о необходимости принять/вернуть работу
   (`handlers/unaccepted_requests.py:handle_remind_applicant`).
2. **Принять за заявителя** — закрыть заявку с **обязательным комментарием**
   (минимум 10 символов, `handle_manager_accept_request` →
   `process_manager_acceptance_comment`). Заявка переходит в статус «Принято»,
   заполняются `manager_confirmed_by`, `manager_confirmed_at`,
   `manager_confirmation_notes`, с меткой «принята без оценки заявителя».

Отличие от приёмки жителем: житель ставит оценку 1-5 (таблица `ratings`), менеджер
оценку не ставит, но комментарий обязателен (`TASK_17_MANAGER_ACCEPTANCE.md`, таблица
различий).

> Проверить: workflow-переходы статусов заявки — `uk_management_bot/utils/request_workflow.py`
> и `uk_management_bot/database/models/request.py`.

---

## Что менеджер НЕ делает

- Не управляет камерами/шлагбаумами/edge-контроллерами и device-ключами модуля доступа
  — это `system_admin` (`App.tsx:132-137`, гейтинг табов «Оборудование»).
- Не работает на посту охраны (роль `security_operator`,
  `docs/access-control/guides/operator.md`).
- Не редактирует append-only журналы (события доступа, операции склада).

---

## Открытые вопросы (проверить у владельца продукта)

- ✅ **РЕШЕНО (2026-07-06):** `admin` — **отдельная действующая роль** (общий
  управленческий администратор ≈ manager), не легаси-синоним. Основной `/dashboard/*`
  пускает `['admin','manager']` (`App.tsx:102`). Нюанс: `admin` не в каноническом реестре
  `roles.ts`, а `system_admin` НЕ попадает на основной дашборд (только access/склад).
  Полная модель ролей и матрица доступа — [../tech/ROLES_AND_ACCESS.md](../tech/ROLES_AND_ACCESS.md).
- ⚠️ **[ТРЕБУЕТ УТОЧНЕНИЯ]** Узбекская локализация приёмки за заявителя помечена как
  нереализованная в `TASK_17_MANAGER_ACCEPTANCE.md` (2025). Проверить актуальный статус
  UZ-локализации этого сценария.

---

_Источник истины — код. При расхождении руководства и кода приоритет за кодом; отметки
«проверить» требуют подтверждения владельца продукта._
