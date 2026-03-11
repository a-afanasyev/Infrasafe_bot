# 4. Регистрация, авторизация и верификация пользователей

## 4.1. Общая схема авторизации

Система использует **Telegram ID** в качестве основного идентификатора. JWT-токены описаны в openapi.yaml (BearerAuth) — для Web API. Аутентификация в боте работает через Telegram ID + middleware-цепочку.

### Цепочка авторизации (Middleware)

```mermaid
sequenceDiagram
    participant TG as Telegram
    participant MW1 as db_middleware
    participant MW2 as auth_middleware
    participant MW3 as role_mode_middleware
    participant MW4 as localization_middleware
    participant H as Handler

    TG->>MW1: Update (message/callback)
    MW1->>MW1: db = SessionLocal()
    MW1->>MW2: data["db"] = db
    MW2->>MW2: user = db.query(User).filter(telegram_id)
    MW2->>MW2: data["user"] = user
    MW2->>MW2: data["user_status"] = user.status
    alt user.status == "blocked"
        MW2-->>TG: "Ваш аккаунт заблокирован"
        Note over MW2: Ранний выход
    end
    MW2->>MW3: Пропускает дальше
    MW3->>MW3: roles = parse(user.roles)
    MW3->>MW3: active_role = user.active_role
    MW3->>MW3: data["roles"], data["active_role"]
    MW3->>MW4: Пропускает дальше
    MW4->>MW4: language = user.language || "ru"
    MW4->>MW4: data["language"] = language
    MW4->>H: Handler получает: db, user, user_status, roles, active_role, language
```

## 4.2. Регистрация по приглашению

### 4.2.1. Генерация invite-токена

Администратор/менеджер создаёт приглашение через бота. Формат токена:

```
invite_v1:{base64_payload}.{hmac_sha256_signature}
```

**Payload содержит:**
- `role` — роль (applicant/executor/manager)
- `expires_at` — Unix timestamp истечения (по умолчанию 24 часа)
- `nonce` — уникальный одноразовый ключ
- `created_by` — Telegram ID создателя
- `specialization` — специализация (для executor)

**Безопасность:**
- HMAC-SHA256 подпись на основе `INVITE_SECRET`
- Одноразовый nonce (защита от повторного использования)
- Rate limiting: 3 попытки / 10 минут на пользователя (Redis)

### 4.2.2. Процесс регистрации

```mermaid
sequenceDiagram
    actor Admin as Администратор
    actor User as Новый пользователь
    participant Bot as Telegram Bot
    participant IS as InviteService
    participant AS as AuthService
    participant DB as PostgreSQL

    Note over Admin,DB: Этап 1: Создание приглашения
    Admin->>Bot: /invite executor electric,plumbing
    Bot->>IS: generate_invite(role, specialization)
    IS->>IS: payload + HMAC подпись
    IS->>DB: AuditLog (invite_created)
    IS-->>Bot: token
    Bot->>Admin: Инвайт-ссылка + команда /join <token>

    Note over Admin,DB: Этап 2: Регистрация
    User->>Bot: /join <token>
    Bot->>IS: validate_invite(token)
    IS->>IS: Проверка HMAC, nonce, expires_at
    alt Токен невалидный
        IS-->>Bot: ValueError
        Bot->>User: "Недействительный/просроченный токен"
    end
    IS-->>Bot: invite_data (role, specialization)

    Note over User,DB: Этап 3: Пошаговая регистрация (FSM)
    Bot->>User: "Введите ФИО"
    Note over Bot: State: waiting_for_full_name
    User->>Bot: "Иванов Иван Иванович"
    Bot->>User: "Введите телефон"
    Note over Bot: State: waiting_for_phone
    User->>Bot: "+7 999 123 4567"
    Bot->>User: "Подтвердите данные" [Confirm/Cancel]
    Note over Bot: State: waiting_for_position_confirmation

    User->>Bot: Confirm (callback)
    Bot->>AS: get_or_create_user()
    AS->>DB: INSERT/UPDATE user (status=pending, role=...)
    Bot->>Admin: "Новая заявка на регистрацию" [Approve/Reject]
    Bot->>User: "Заявка отправлена на рассмотрение"

    Note over Admin,DB: Этап 4: Одобрение
    Admin->>Bot: [Approve]
    Bot->>AS: approve_user(telegram_id, role)
    AS->>DB: user.status = "approved"
    Bot->>User: "Вы одобрены! Добро пожаловать."
```

### 4.2.3. FSM-состояния регистрации

```mermaid
stateDiagram-v2
    [*] --> waiting_for_full_name : /join <token> валиден
    waiting_for_full_name --> waiting_for_phone : ФИО введено (мин. 2 слова)
    waiting_for_phone --> waiting_for_position_confirmation : Телефон введён
    waiting_for_position_confirmation --> [*] : Подтверждено → user.status = pending
    waiting_for_position_confirmation --> [*] : Отменено → state.clear()
```

## 4.3. Вход для существующих пользователей

```mermaid
sequenceDiagram
    actor U as Пользователь
    participant Bot as Telegram Bot
    participant AS as AuthService

    U->>Bot: /start или "Войти"
    Bot->>AS: get_or_create_user(telegram_id)
    alt Новый пользователь
        AS-->>Bot: user (status=pending)
        Bot->>U: Онбординг / Предложение /join
    else Уже одобрен
        AS-->>Bot: user (status=approved)
        Bot->>U: Главное меню (по active_role)
    else Заблокирован
        Note over Bot: auth_middleware блокирует
        Bot->>U: "Аккаунт заблокирован"
    end
```

## 4.4. Переключение ролей

Пользователь с несколькими ролями может переключаться через кнопку "Сменить роль".

```mermaid
sequenceDiagram
    actor U as Пользователь (applicant + executor)
    participant Bot as Telegram Bot
    participant DB as PostgreSQL

    U->>Bot: "Сменить роль"
    Bot->>U: Inline keyboard с доступными ролями
    U->>Bot: Выбирает "Исполнитель"
    Bot->>DB: user.active_role = "executor"
    Bot->>U: Главное меню исполнителя
```

## 4.5. Привязка к квартире

```mermaid
sequenceDiagram
    actor U as Пользователь
    actor Admin as Администратор/Менеджер
    participant Bot as Telegram Bot
    participant DB as PostgreSQL

    U->>Bot: Выбор квартиры из справочника
    Bot->>U: Список дворов → Список домов → Список квартир
    U->>Bot: Выбирает квартиру
    Bot->>DB: UserApartment (status=pending)
    Bot->>Admin: "Заявка на привязку к квартире"
    Admin->>Bot: [Approve] или [Reject]
    Bot->>DB: UserApartment.status = approved/rejected
    Bot->>U: Результат модерации
```

## 4.6. Система верификации

### Типы документов

| Тип | Код | Описание |
|-----|-----|----------|
| Паспорт | `passport` | Основной документ |
| Свидетельство о собственности | `property_deed` | Подтверждение владения |
| Договор аренды | `rental_agreement` | Для арендаторов |
| Квитанция ЖКХ | `utility_bill` | Подтверждение проживания |
| Другое | `other` | Дополнительные документы |

### Процесс верификации

```mermaid
flowchart TD
    A[Пользователь загружает документы\nUserDocument] --> B[UserVerification\nstatus=pending]
    B --> C{Менеджер рассматривает}
    C -->|Одобрено| D[verification_status=verified\nverification_date заполнен]
    C -->|Отклонено| E[verification_status=rejected\nverification_notes заполнены]
    C -->|Нужны доп. документы| F[status=requested\nУведомление пользователю]
    F --> A
```

### Уровни доступа (AccessRights)

| Уровень | Код | Описание |
|---------|-----|----------|
| Квартира | `apartment` | Доступ на уровне квартиры (макс. 2 заявителя) |
| Дом | `house` | Доступ на уровне дома |
| Двор | `yard` | Доступ на уровне двора |

## 4.7. Декоратор проверки ролей

Хендлеры защищены декоратором `@require_role(['manager', 'admin'])`, который:

1. Получает роли из `data["roles"]` (middleware DI)
2. Если ролей нет — загружает из БД
3. Проверяет пересечение с требуемыми ролями
4. При отсутствии доступа — отправляет локализованное сообщение и останавливает обработку

## 4.8. Управление пользователями (Admin/Manager)

```mermaid
flowchart TD
    A[Менеджер открывает\nуправление пользователями] --> B{Действие}
    B --> C[Просмотр пользователя]
    B --> D[Блокировка пользователя\nstatus=blocked]
    B --> E[Разблокировка\nstatus=approved]
    B --> F[Изменение ролей\nroles JSON]
    B --> G[Изменение специализаций\nspecialization JSON]
    B --> H[Создание инвайта]
    H --> I[generate_invite_token\nроль + специализация]
    I --> J[Отправка пользователю]
```
