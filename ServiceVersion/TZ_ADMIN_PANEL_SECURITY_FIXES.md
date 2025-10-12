# 🔒 TZ_ADMIN_PANEL - Critical Security & Architecture Fixes

**Дата**: 9 октября 2025
**Версия**: 1.0.0
**Приоритет**: 🔴 CRITICAL
**Статус**: Требуется немедленное исправление

---

## 📋 Executive Summary

Выявлено **4 критических проблемы** в спецификации Admin Panel, которые:
1. Противоречат принятой архитектуре безопасности (RS256 vs shared secret)
2. Создают недопустимые security риски (bulk data exfiltration)
3. Требуют несуществующей инфраструктуры (direct DB access)
4. Зависят от нерешенных бизнес-вопросов (multiple roles - Q1.2)

**Все 4 проблемы требуют исправления перед началом разработки Admin Panel.**

---

## 🔥 CRITICAL Issues

### Issue #1: JWT Secret Management Conflict

**Приоритет:** 🔴 CRITICAL (Security Architecture)

**Локация:** `TZ_ADMIN_PANEL.md:552`

**Проблема:**
```
│ 🔐 Security:                                           │
│ ┌──────────────────────────────────────────────┐     │
│ │ JWT Secret:      [••••••••••••] [🔄 Rotate]  │     │  ⬅️ ПРОБЛЕМА
│ │ Token expiry:    [24] hours                  │     │
```

Admin UI предполагает **rotatable shared JWT Secret** (symmetric HS256), в то время как Core Service архитектура требует **asymmetric RS256** с публичными/приватными ключами.

**Почему это критично:**
- ❌ Противоречит `TZ_CORE_SERVICE.md:236` ("JWT с RS256 подписью")
- ❌ Противоречит `SHARED_LIBRARY_SPECIFICATION.md:189-194` (RS256 по умолчанию)
- ❌ Ротация shared secret сломает верификацию токенов во всех сервисах
- ❌ Symmetric key требует распространения секрета между сервисами (security risk)

**Архитектурное противоречие:**

```
┌─────────────────────────────────────────────────────────┐
│ APPROVED ARCHITECTURE (RS256)                           │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  Core Service                                           │
│  ┌─────────────────┐                                    │
│  │ Private Key     │ ──> Подписывает JWT               │
│  │ (never exposed) │                                    │
│  └─────────────────┘                                    │
│                                                         │
│  Other Services                                         │
│  ┌─────────────────┐                                    │
│  │ Public Key      │ ──> Проверяют JWT                 │
│  │ (can be shared) │                                    │
│  └─────────────────┘                                    │
│                                                         │
│  ✅ Безопасно: private key только в Core Service       │
│  ✅ Ротация: заменить keypair, распространить public   │
└─────────────────────────────────────────────────────────┘

VS

┌─────────────────────────────────────────────────────────┐
│ ADMIN PANEL SPEC (HS256 - WRONG!)                       │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  All Services                                           │
│  ┌─────────────────┐                                    │
│  │ Shared Secret   │ ──> Подписывают И проверяют JWT   │
│  │ (all services)  │                                    │
│  └─────────────────┘                                    │
│                                                         │
│  ❌ Риск: shared secret в каждом сервисе               │
│  ❌ Ротация: требует синхронной замены везде           │
│  ❌ Утечка: компрометирует всю систему                 │
└─────────────────────────────────────────────────────────┘
```

**Исправление:**

**ДО (НЕПРАВИЛЬНО):**
```
│ 🔐 Security:                                           │
│ ┌──────────────────────────────────────────────┐     │
│ │ JWT Secret:      [••••••••••••] [🔄 Rotate]  │     │
│ │ Token expiry:    [24] hours                  │     │
│ │ Refresh expiry:  [30] days                   │     │
```

**ПОСЛЕ (ПРАВИЛЬНО):**
```
│ 🔐 Security (JWT):                                     │
│ ┌──────────────────────────────────────────────┐     │
│ │ ⚠️ Управление ключами выполняется через       │     │
│ │    Core Service API, не через Admin UI       │     │
│ │                                              │     │
│ │ Algorithm:       RS256 (asymmetric)          │     │
│ │ Token expiry:    [24] hours                  │     │
│ │ Refresh expiry:  [30] days                   │     │
│ │                                              │     │
│ │ 🔑 Keypair Management:                        │     │
│ │ Current keypair: kid=uk-core-2025-q4         │     │
│ │ Created:         01.10.2025                  │     │
│ │ Next rotation:   01.01.2026 (90 days)        │     │
│ │                                              │     │
│ │ [📋 View Public Key]                         │     │
│ │ [🔄 Schedule Rotation] (Requires 2FA)        │     │
│ └──────────────────────────────────────────────┘     │
│                                                        │
│ 🔐 Password & Account Security:                        │
│ ┌──────────────────────────────────────────────┐     │
│ │ Password policy:                             │     │
│ │   • Min length:  [8] characters              │     │
│ │   • Require:     ☑ Uppercase ☑ Number       │     │
│ │                  ☑ Special char              │     │
│ │ Failed login:    [5] attempts before lock    │     │
│ │ Lock duration:   [30] minutes                │     │
│ │ 2FA required:    ☐ For all users             │     │
│ │                  ☑ For admins                │     │
│ └──────────────────────────────────────────────┘     │
```

**API для ротации ключей:**
```http
POST /api/v1/admin/security/jwt/schedule-rotation
Authorization: Bearer <admin-token>
X-2FA-Code: 123456

{
  "rotation_date": "2026-01-01T03:00:00Z",
  "notification_recipients": ["admin@uk-app.com"],
  "grace_period_days": 7
}

Response:
{
  "rotation_id": "rot_abc123",
  "status": "scheduled",
  "current_keypair": {
    "kid": "uk-core-2025-q4",
    "created_at": "2025-10-01T00:00:00Z"
  },
  "new_keypair": {
    "kid": "uk-core-2026-q1",
    "will_be_created_at": "2026-01-01T03:00:00Z"
  },
  "grace_period": {
    "start": "2026-01-01T03:00:00Z",
    "end": "2026-01-08T03:00:00Z",
    "description": "Both keys valid during this period"
  }
}
```

**Важно:**
- ✅ Admin UI показывает статус ключей (read-only)
- ✅ Ротация через API Core Service с 2FA
- ✅ Никогда не показывает private key в UI
- ✅ Public key можно просмотреть (для отладки)
- ✅ Grace period для плавного перехода

---

### Issue #2: Bulk Backup Download/Restore Risk

**Приоритет:** 🔴 CRITICAL (Data Exfiltration Risk)

**Локация:** `TZ_ADMIN_PANEL.md:715-734`

**Проблема:**
```
│ 📦 Последние бэкапы:                                   │
│ ┌────────────────────────────────────────────────┐   │
│ │ ✓ 09.10.2025 03:00  152 GB  Manual            │   │
│ │   [📥 Download] [🔄 Restore] [🗑️ Delete]       │   │  ⬅️ ПРОБЛЕМА
```

Admin UI предлагает in-browser download/restore полных production бэкапов (~150 GB).

**Почему это критично:**
- 🚨 **Data Exfiltration**: Один скомпрометированный admin аккаунт = весь датасет
- 🚨 **Credential Exposure**: Требует long-lived S3/DB credentials в web app
- 🚨 **Network Limits**: 150 GB через browser = timeout/failure гарантирован
- 🚨 **Out of Scope**: Архитектура не предусматривала bulk transfers через UI
- 🚨 **Audit Gap**: Легко скачать backup незаметно

**Сравнение рисков:**

```
┌─────────────────────────────────────────────────────────┐
│ CURRENT SPEC (HIGH RISK)                                │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  Admin clicks [📥 Download]                             │
│          ↓                                              │
│  Browser получает signed S3 URL                         │
│          ↓                                              │
│  150 GB загружается на локальный диск                   │
│                                                         │
│  ❌ Риски:                                              │
│  • Credential exposure (S3 presigned URL)               │
│  • No audit trail (S3 logs ≠ app audit)                │
│  • Easy exfiltration (one click)                        │
│  • Network timeout (150 GB)                             │
│  • No approval workflow                                 │
└─────────────────────────────────────────────────────────┘

VS

┌─────────────────────────────────────────────────────────┐
│ RECOMMENDED APPROACH (LOW RISK)                         │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  Admin creates restore request                          │
│          ↓                                              │
│  Multi-step approval (2+ admins + 2FA)                  │
│          ↓                                              │
│  Ops team notified (Slack/PagerDuty)                    │
│          ↓                                              │
│  Restore job executed by infrastructure service         │
│          ↓                                              │
│  Full audit trail + notification                        │
│                                                         │
│  ✅ Преимущества:                                       │
│  • No credential exposure                               │
│  • Full audit trail                                     │
│  • Approval workflow                                    │
│  • Handled by infrastructure (not browser)              │
│  • Rate limiting / time windows                         │
└─────────────────────────────────────────────────────────┘
```

**Исправление:**

**ДО (НЕПРАВИЛЬНО):**
```
│ 📦 Последние бэкапы:                                   │
│ ┌────────────────────────────────────────────────┐   │
│ │ ✓ 09.10.2025 03:00  152 GB  Manual            │   │
│ │   [📥 Download] [🔄 Restore] [🗑️ Delete]       │   │
│ ├────────────────────────────────────────────────┤   │
│ │ ✓ 08.10.2025 03:00  151 GB  Auto              │   │
│ │   [📥 Download] [🔄 Restore] [🗑️ Delete]       │   │
│ └────────────────────────────────────────────────┘   │
│                                                        │
│ 🔄 Восстановление из бэкапа:                           │
│ ┌──────────────────────────────────────────────┐     │
│ │ ⚠️ ВНИМАНИЕ: Это необратимая операция!       │     │
│ │ Выберите бэкап: [09.10.2025 03:00 ▼]        │     │
│ │ Target DB:      [Production ⚠️]              │     │
│ │ [✗ Отменить]           [🔄 Восстановить]     │     │
│ └──────────────────────────────────────────────┘     │
```

**ПОСЛЕ (ПРАВИЛЬНО):**
```
│ 📦 Backup Status (Read-Only Monitoring):               │
│ ┌────────────────────────────────────────────────┐   │
│ │ ✓ 09.10.2025 03:00  152 GB  Manual            │   │
│ │   Status: Completed | Verified: Yes           │   │
│ │   Retention: 30 days | Encrypted: AES-256     │   │
│ │   [📊 Details] [✓ Verify Integrity]           │   │
│ ├────────────────────────────────────────────────┤   │
│ │ ✓ 08.10.2025 03:00  151 GB  Auto              │   │
│ │   Status: Completed | Verified: Yes           │   │
│ │   [📊 Details] [✓ Verify Integrity]           │   │
│ └────────────────────────────────────────────────┘   │
│                                                        │
│ ⚠️ ВАЖНО: Операции Download/Restore/Delete выполняются │
│ только через инфраструктурные процедуры с multi-party │
│ approval. См. раздел "Disaster Recovery Workflow".    │
│                                                        │
│ 🔄 Disaster Recovery Request:                          │
│ ┌──────────────────────────────────────────────┐     │
│ │ ⚠️ Запрос восстановления из бэкапа           │     │
│ │                                              │     │
│ │ Backup:         [09.10.2025 03:00 ▼]        │     │
│ │ Target env:     [Staging ▼]                 │     │
│ │                 Production (requires CTO)    │     │
│ │                                              │     │
│ │ Reason:         [Disaster recovery test ▼]  │     │
│ │ Description:    [Required field]            │     │
│ │                                              │     │
│ │ Approvals required:                          │     │
│ │   ☐ Second Admin (pending)                  │     │
│ │   ☐ CTO (for production only)               │     │
│ │                                              │     │
│ │ Execution window:                            │     │
│ │   [2025-10-10 03:00] to [2025-10-10 06:00]  │     │
│ │                                              │     │
│ │ [✗ Cancel]           [📨 Submit Request]     │     │
│ └──────────────────────────────────────────────┘     │
│                                                        │
│ 📋 Pending Restore Requests (2):                       │
│ ┌────────────────────────────────────────────────┐   │
│ │ REQ-2025-1009-003 | Staging | Test            │   │
│ │ Requested by: admin@uk.com                     │   │
│ │ Status: ⏳ Awaiting 2nd admin approval         │   │
│ │ [✓ Approve] [✗ Reject] [💬 Comment]          │   │
│ └────────────────────────────────────────────────┘   │
│                                                        │
│ [💾 Create Manual Backup] [⚙️ Settings]               │
└────────────────────────────────────────────────────────┘

📖 Disaster Recovery Workflow:

1. BACKUP VERIFICATION (Admin UI):
   ✅ View backup metadata
   ✅ Verify backup integrity (checksum)
   ✅ View backup size & retention

2. RESTORE REQUEST (Admin UI):
   ✅ Submit restore request with justification
   ✅ Select target environment (staging/production)
   ✅ Define execution window

3. APPROVAL WORKFLOW:
   • Staging restore:  1 additional admin + 2FA
   • Production restore: 2 admins + CTO + 2FA

4. EXECUTION (Infrastructure Service):
   • Automated restore job (not through browser)
   • Progress notifications (Slack/Email)
   • Full audit trail
   • Rollback capability

5. VERIFICATION:
   • Post-restore health checks
   • Data integrity validation
   • Notification to all stakeholders

🚫 NEVER AVAILABLE VIA UI:
   ❌ Direct backup download (150 GB)
   ❌ One-click restore to production
   ❌ Backup deletion without approval
```

**API Workflow:**

```http
# 1. Создать restore request
POST /api/v1/admin/disaster-recovery/restore-requests
Authorization: Bearer <admin-token>
X-2FA-Code: 123456

{
  "backup_id": "backup_20251009_030000",
  "target_environment": "staging",
  "reason": "disaster_recovery_test",
  "description": "Testing restore procedure before Q4 DR drill",
  "execution_window": {
    "start": "2025-10-10T03:00:00Z",
    "end": "2025-10-10T06:00:00Z"
  }
}

Response:
{
  "request_id": "REQ-2025-1009-003",
  "status": "pending_approval",
  "required_approvals": [
    {
      "role": "admin",
      "count": 1,
      "status": "pending"
    }
  ],
  "created_by": "admin@uk.com",
  "created_at": "2025-10-09T12:00:00Z"
}

# 2. Второй админ одобряет
POST /api/v1/admin/disaster-recovery/restore-requests/REQ-2025-1009-003/approve
Authorization: Bearer <second-admin-token>
X-2FA-Code: 654321

{
  "comment": "Approved for DR test"
}

Response:
{
  "request_id": "REQ-2025-1009-003",
  "status": "approved",
  "scheduled_execution": "2025-10-10T03:00:00Z",
  "job_id": "restore_job_abc123"
}

# 3. Мониторинг через Admin UI
GET /api/v1/admin/disaster-recovery/jobs/restore_job_abc123

Response:
{
  "job_id": "restore_job_abc123",
  "status": "in_progress",
  "progress": 45,
  "stage": "restoring_database",
  "estimated_completion": "2025-10-10T04:30:00Z"
}
```

---

### Issue #3: Direct Database Operations Without Infrastructure

**Приоритет:** 🔴 CRITICAL (Operational Risk)

**Локация:** `TZ_ADMIN_PANEL.md:694` (VACUUM/REINDEX buttons)

**Проблема:**
```
│ [🔧 Run VACUUM] [📊 Reindex] [⚙️ Query Console]        │  ⬅️ ПРОБЛЕМА
```

Admin UI предполагает прямое выполнение привилегированных операций БД (VACUUM, REINDEX, manual restore), но:
- ❌ Нет supporting infrastructure service в архитектуре
- ❌ Нет hardened workflow для таких операций
- ❌ Требует embedding superuser credentials в web app
- ❌ Out of scope для текущей архитектуры

**Почему это критично:**
- 🚨 **Credential Risk**: Superuser credentials в web application
- 🚨 **Operational Risk**: VACUUM/REINDEX на production без safeguards
- 🚨 **No Rollback**: Нет механизма отката при ошибках
- 🚨 **Scope Creep**: Требует нового infrastructure automation service

**Исправление:**

**ДО (НЕПРАВИЛЬНО):**
```
│ [🔧 Run VACUUM] [📊 Reindex] [⚙️ Query Console]        │
```

**ПОСЛЕ (ПРАВИЛЬНО):**
```
│ 🔧 Database Maintenance:                               │
│ ┌──────────────────────────────────────────────┐     │
│ │ ⚠️ Maintenance операции выполняются через     │     │
│ │    автоматизированные задачи (cron) или      │     │
│ │    инфраструктурные процедуры.               │     │
│ │                                              │     │
│ │ Доступно в Admin UI:                         │     │
│ │ • Просмотр статуса maintenance tasks         │     │
│ │ • Просмотр истории операций                  │     │
│ │ • Создание запросов на внеплановое           │     │
│ │   обслуживание (с approval workflow)         │     │
│ │                                              │     │
│ │ НЕ доступно в Admin UI:                      │     │
│ │ • Прямое выполнение VACUUM/REINDEX           │     │
│ │ • Query console с write access               │     │
│ │ • Прямой доступ к production БД              │     │
│ └──────────────────────────────────────────────┘     │
│                                                        │
│ 📅 Scheduled Maintenance:                              │
│ ┌────────────────────────────────────────────────┐   │
│ │ ✓ Auto-VACUUM      | Daily 03:00 UTC | Next:  │   │
│ │                    | 2025-10-10 03:00          │   │
│ │ ✓ REINDEX          | Weekly Sun 04:00 | Next: │   │
│ │                    | 2025-10-13 04:00          │   │
│ │ ✓ Analyze tables   | Daily 04:00 UTC | Next:  │   │
│ │                    | 2025-10-10 04:00          │   │
│ └────────────────────────────────────────────────┘   │
│                                                        │
│ 📋 Request Ad-hoc Maintenance:                         │
│ ┌──────────────────────────────────────────────┐     │
│ │ Operation:  [VACUUM ANALYZE ▼]               │     │
│ │ Table:      [requests ▼] or [All tables]     │     │
│ │ Window:     [2025-10-10 03:00 - 06:00]       │     │
│ │ Reason:     [Performance degradation]        │     │
│ │                                              │     │
│ │ ⚠️ Requires approval from DBA team           │     │
│ │                                              │     │
│ │ [✗ Cancel]      [📨 Submit Request]          │     │
│ └──────────────────────────────────────────────┘     │
└────────────────────────────────────────────────────────┘
```

**Рекомендации:**
1. **Automated Maintenance**: Все routine операции через cron/Kubernetes CronJob
2. **Infrastructure Service**: Создать отдельный maintenance service с proper auth
3. **Approval Workflow**: Ad-hoc операции через ticketing system (не прямо через UI)
4. **Read-Only Console**: Query console только с SELECT правами для debugging

---

### Issue #4: Multi-Role UI Depends on Unresolved Business Rules

**Приоритет:** 🟡 HIGH (Dependency on Open Question)

**Локация:** `TZ_ADMIN_PANEL.md:145-157`

**Проблема:**
```
│ 🎭 Роли и права:                                       │
│ ┌──────────────────────────────────────────────┐     │
│ │ ✓ Applicant   (с 15.01.2025)                 │     │  ⬅️ Multiple roles
│ │ ✓ Executor    (с 01.03.2025)                 │     │  ⬅️ baked in UI
│ │ [+ Добавить роль]  [✎ Изменить права]       │     │  ⬅️ ПРОБЛЕМА
│ └──────────────────────────────────────────────┘     │
```

UI предполагает multi-role editing logic, но бизнес-правила для множественных ролей **не финализированы** (`OPEN_QUESTIONS_REGISTRY.md:23-41`, вопрос Q1.2).

**Почему это проблема:**
- ⚠️ **Premature Implementation**: UI built before business rules defined
- ⚠️ **Rework Risk**: Если бизнес выберет другую стратегию, весь UI + API нужно переделывать
- ⚠️ **Scope Uncertainty**: Неясно, какие комбинации ролей разрешены

**Blocking Question Q1.2:**
```markdown
### Q1.2 Множественные роли у одного пользователя

**Контекст:**
Может ли пользователь иметь несколько ролей одновременно?
Например: applicant + executor?

**Варианты:**
A. Да, без ограничений (любые комбинации)
B. Да, с ограничениями (executor + manager, но не applicant + executor)
C. Нет, строго одна роль на пользователя
D. Да, но через separate profiles (один Telegram account = multiple profiles)

**Влияние:**
- User model design
- Permission checking logic
- UI/UX (role switching)
- Request assignment rules
```

**Исправление:**

**ДО (НЕПРАВИЛЬНО - без disclaimer):**
```
│ 🎭 Роли и права:                                       │
│ ┌──────────────────────────────────────────────┐     │
│ │ ✓ Applicant   (с 15.01.2025)                 │     │
│ │ ✓ Executor    (с 01.03.2025)                 │     │
│ │ [+ Добавить роль]  [✎ Изменить права]       │     │
│ └──────────────────────────────────────────────┘     │
```

**ПОСЛЕ (ПРАВИЛЬНО - с версионированием):**
```
│ 🎭 Роли и права:                                       │
│ ┌──────────────────────────────────────────────┐     │
│ │ ⚠️ DRAFT SPEC - Зависит от Q1.2              │     │
│ │ (OPEN_QUESTIONS_REGISTRY.md)                 │     │
│ │                                              │     │
│ │ Current implementation (PROVISIONAL):        │     │
│ │                                              │     │
│ │ Primary Role: Executor                       │     │
│ │   • Может принимать заявки                   │     │
│ │   • Может обновлять статусы                  │     │
│ │   • Специализации: Сантехника, Электрика     │     │
│ │                                              │     │
│ │ Secondary Roles (TBD):                       │     │
│ │   ☐ Applicant (pending Q1.2 resolution)     │     │
│ │                                              │     │
│ │ [✎ Edit Primary Role]                        │     │
│ │ [⚠️ Manage Secondary Roles] (Disabled)       │     │
│ └──────────────────────────────────────────────┘     │
│                                                        │
│ 📋 Role Management Notes:                              │
│ • Multiple roles subject to business approval (Q1.2)  │
│ • UI будет обновлен после финализации правил          │
│ • Текущая версия поддерживает только primary role    │
```

**Альтернативные UI mockups для разных вариантов Q1.2:**

**Вариант A: Множественные роли без ограничений**
```
│ 🎭 Активные роли:                                      │
│ ┌──────────────────────────────────────────────┐     │
│ │ ✓ Applicant   (Primary)                      │     │
│ │ ✓ Executor    (Secondary)                    │     │
│ │ ✓ Manager     (Secondary)                    │     │
│ │                                              │     │
│ │ [+ Add Role] [✎ Set Primary] [✗ Remove]     │     │
│ └──────────────────────────────────────────────┘     │
```

**Вариант B: Роли с ограничениями**
```
│ 🎭 Роли (с ограничениями):                             │
│ ┌──────────────────────────────────────────────┐     │
│ │ Current: Executor                            │     │
│ │                                              │     │
│ │ Compatible roles:                            │     │
│ │   ✓ Manager (can add)                        │     │
│ │   ✗ Applicant (conflict - executor cannot   │     │
│ │      create requests for themselves)         │     │
│ │                                              │     │
│ │ [+ Add Compatible Role]                      │     │
│ └──────────────────────────────────────────────┘     │
```

**Вариант C: Строго одна роль**
```
│ 🎭 Роль:                                               │
│ ┌──────────────────────────────────────────────┐     │
│ │ Current Role: Executor                       │     │
│ │ Assigned:     01.03.2025                     │     │
│ │                                              │     │
│ │ [✎ Change Role] (requires admin approval)   │     │
│ │                                              │     │
│ │ ⚠️ Смена роли удалит текущие разрешения     │     │
│ └──────────────────────────────────────────────┘     │
```

**Вариант D: Separate profiles**
```
│ 🎭 Профили пользователя:                               │
│ ┌──────────────────────────────────────────────┐     │
│ │ Profile 1: Applicant                         │     │
│ │   • Квартиры: ЖК Центральный, кв. 42        │     │
│ │   • Заявки: 45 created                       │     │
│ │                                              │     │
│ │ Profile 2: Executor                          │     │
│ │   • Специализации: Сантехника                │     │
│ │   • Заявки: 89 completed                     │     │
│ │                                              │     │
│ │ [+ Add Profile] [🔄 Switch] [✎ Edit]        │     │
│ └──────────────────────────────────────────────┘     │
```

**Рекомендация:**
1. **Current Sprint**: Реализовать только Вариант C (single role) - это минимальный риск
2. **Resolver Q1.2**: Получить бизнес-решение по множественным ролям
3. **Refactor if needed**: После решения Q1.2 обновить UI/API под финальные правила
4. **Version TZ**: Пометить секцию multi-role как "v2.0 - pending Q1.2"

---

## 📊 Impact Summary

| Issue | Priority | Risk Type | Impact if Not Fixed | Effort to Fix |
|-------|----------|-----------|---------------------|---------------|
| #1 JWT Secret | 🔴 CRITICAL | Security Architecture | Token verification failure, security breach | Medium (2-3 days) |
| #2 Bulk Backup | 🔴 CRITICAL | Data Exfiltration | Easy data theft, compliance violation | High (5-7 days) |
| #3 Direct DB Ops | 🔴 CRITICAL | Operational Safety | Production outage, data corruption | High (5-7 days) |
| #4 Multi-Role UI | 🟡 HIGH | Technical Debt | Rework UI/API if Q1.2 resolved differently | Low (1 day) |

**Total Estimated Effort**: 13-18 days

---

## ✅ Action Items

### Immediate (Before Development Starts):
1. ⚠️ **Update TZ_ADMIN_PANEL.md** - Apply all 4 fixes
2. ⚠️ **Create ADMIN_PANEL_SECURITY_REQUIREMENTS.md** - Formalize security constraints
3. ⚠️ **Resolve Q1.2** - Get business decision on multiple roles
4. ⚠️ **Design Infrastructure Service** - For backup/restore/maintenance operations

### Short-term (Sprint 1-2):
5. Design proper disaster recovery workflow
6. Design JWT keypair rotation workflow
7. Create automated maintenance scheduler
8. Define approval workflows for privileged operations

### Mid-term (Sprint 3-4):
9. Implement infrastructure automation service
10. Implement multi-party approval system
11. Create full audit trail for all admin operations
12. Set up monitoring/alerting for admin actions

---

## 📚 Related Documents

- [TZ_ADMIN_PANEL.md](TZ_ADMIN_PANEL.md) - Original spec (needs update)
- [TZ_CORE_SERVICE.md](TZ_CORE_SERVICE.md) - RS256 requirement (line 236)
- [SHARED_LIBRARY_SPECIFICATION.md](SHARED_LIBRARY_SPECIFICATION.md) - JWT RS256 implementation
- [OPEN_QUESTIONS_REGISTRY.md](OPEN_QUESTIONS_REGISTRY.md) - Q1.2 (multiple roles)

---

**Prepared by:** Claude (Sonnet 4.5)
**Date:** 9 October 2025
**Status:** 🔴 CRITICAL - Requires immediate action
**Review Required:** Security Team, DevOps Lead, Product Owner
