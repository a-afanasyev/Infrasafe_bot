# Applicant Registration — Dual Scheme (WebApp + Bot)

**Date:** 2026-05-30
**Status:** Design approved (user); spec revised after code-grounded second review
**Scope:** UK Management System — applicant (заявитель/resident) self-registration

## 1. Context & Problem

Today applicant registration exists only inside the bot (onboarding FSM): an
unknown user on `/start` → `get_or_create_user(status="pending")` → phone +
apartment selection (`AddressService.request_apartment` → `UserApartment`
status `pending`) → admins notified (`handlers/user_apartment_selection.py`) →
manager approves. Profile completeness = `user.phone` AND an approved
`UserApartment`.

A second, parallel registration surface is desired: a **web form** opened as a
**Telegram Mini App (WebApp)**, integrated into the React frontend. An orphaned
standalone service `uk-web-registration` (`uk_management_bot/web/`, host port
`:8000`) once served this but is dead: not linked anywhere, not proxied by the
edge nginx, visually broken (`https://uk-management.local/static/style.css`),
invite-mandatory, and it exposes host port `:8000` on `0.0.0.0` (security
finding).

## 2. Goals

1. Provide a **WebApp registration form** for applicants, integrated into the
   existing React frontend (same origin as the dashboard).
2. Keep the **bot registration** (onboarding) as the second parallel scheme —
   unchanged in behaviour.
3. Both schemes produce the **same artifacts** (pending user + pending
   `UserApartment` + manager notification) and use the **same approval flow** —
   no data-model divergence.
4. Retire the dead `uk-web-registration` service (also removes the `:8000`
   public-port exposure).

### Non-goals (YAGNI)
- **Invite tokens on the web form** — the WebApp form is open applicant
  self-registration ONLY. Invite-token registration (incl. executor/manager
  presets) stays **bot-only** and unchanged. (User decision 2026-05-30.)
- Executor/manager self-registration on the web — out of scope.
- Plain-browser (non-Telegram) registration — WebApp-only identity.
- Reworking the bot onboarding FSM.
- A new manager moderation surface — approval reuses existing actions.

## 3. Key Decisions

| Decision | Choice |
|---|---|
| Web form gating | **Open applicant self-reg, no invite token** |
| Web UI location | **New `/register` route in React frontend**; retire Python page |
| Identity | **Telegram WebApp only** — `telegram_id` from signed `initData` |
| Submit auth | **Short-lived registration ticket** (JWT), minted after initData check, to survive the 5-min initData window |
| Bot scheme | **Leave as-is** (existing onboarding = bot registration) |
| Apartment input (web) | **Select from catalog** (`UserApartment` → manager approve), parity with bot |
| WebApp entry point | **WebApp button** on the bot new-user welcome screen (opens `/uk/register`) |
| Approval | **Single manager action approves both** `user.status` and the pending `UserApartment` (composition of existing methods) |

## 4. Architecture

### 4.1 Shared backend — new async router on `uk-management-api`

New isolated module `uk_management_bot/api/registration/` registered under
`/api/v2/registration` in `api/main.py` (matches the existing
`include_router(..., prefix="/api/v2/...")` pattern). Async throughout
(`AsyncSession` from `get_db`). Kept separate from `api/auth/`.

**Endpoints:**

- **`POST /api/v2/registration/start`** — body `{ init_data }`.
  - Verify with `verify_twa_init_data(init_data, settings.BOT_TOKEN)`
    (`api/auth/service.py`); invalid/expired → `401`.
  - Resolve trusted `telegram_id` from the verified payload (NEVER from a body
    field).
  - Look up the user: `blocked` → `403`; `approved` → `409` (already
    registered → client redirects into the app); else proceed.
  - Mint a **registration ticket** via a dedicated
    `create_registration_ticket(telegram_id)` (JWT, `purpose="register"`,
    `sub=telegram_id`, ~30-min TTL), with a matching `verify_registration_ticket`.
    These REUSE THE PATTERN of `create_mfa_token` but are SEPARATE functions —
    the MFA token is `purpose="mfa"`, `sub=user_id`; the two must not be conflated.
  - Return `{ registration_ticket, prefill: {first_name, last_name, phone?},
    apartments: [...] }` — ticket + prefill + catalog in one round-trip. Name
    comes from the Telegram payload; `phone` ONLY if an existing pending user row
    already has one (Telegram `initData` carries no phone number).
  - **Rationale (initData expiry):** `verify_twa_init_data` enforces
    `AUTH_DATE_MAX_AGE_SECONDS = 300`. A user may dwell on the form past 5 min;
    binding submit to the ticket (not raw initData) avoids a spurious `401`.
  - Rate-limited (e.g. `10/minute`).

- **`POST /api/v2/registration/applicant`** — gated by
  `Authorization: Bearer <registration_ticket>` (verify `purpose="register"`,
  not expired → else `401`). Body `{ full_name, phone, apartment_id }` (no
  `telegram_id` — from ticket). Rate-limited `3/minute` (parity with the old web
  endpoint).
  1. Validate `phone` (`Validator.validate_phone`), `full_name` non-empty,
     `apartment_id` exists in catalog → `400`/`422` otherwise.
  2. Re-check user state (blocked → `403`, approved → `409`).
  3. Ensure user: create if new, else update the pending row idempotently. Set
     `phone`, `first_name`/`last_name` from `full_name`, the MODERN role fields
     (`roles` contains `"applicant"`, `active_role="applicant"` — never the
     deprecated `user.role`, per CLAUDE.md), `status="pending"`. Commit.
  4. Create the apartment link by calling
     **`core.request_apartment(db, user_id=..., apartment_id=...)`**
     (`services/addresses/core.py:463`) on the request's `AsyncSession` — NOT
     `AddressService.request_apartment` (it opens its own session) and NOT a
     sync/threadpool path. This reuses the bot's exact policy: an existing
     pending/approved/rejected link raises `AddressConflict` (→ map to `409` /
     inline error), and `core` commits the apartment write itself.
  5. **Concurrency:** `core.request_apartment` pre-checks then inserts and does
     NOT catch the race where two concurrent submits both pass the pre-check and
     the second violates `UniqueConstraint(user_id, apartment_id)`. The endpoint
     MUST catch `IntegrityError` and map it to an idempotent no-op / `409` —
     never a `500`.
  6. **After the apartment write commits**, notify managers (so a failed write
     never leaves a ghost request). The bot's notifier is
     `handlers/user_apartment_selection.py:send_apartment_request_notification`
     (messages `settings.ADMIN_USER_IDS` via the aiogram bot). The async endpoint
     should send via a **direct Telegram `sendMessage`** (pattern in
     `api/auth/service.py:send_otp_via_bot`) rather than depending on the aiogram
     bot instance. Notification failure is non-fatal (logged) — the pending
     request is also visible in the existing pending-users / moderation lists.
  7. **Outcome is ALWAYS `status="pending"`.** No tokens issued. Response
     `{ "status": "pending" }`.

**Catalog source (#6).** Do NOT call `AddressService`'s async-by-signature
methods blindly: several (`get_yard_by_id`, `get_all_yards`) are `async def`
but run synchronous `session.execute(...)` without `await`, and
`request_apartment` opens its own `_async_session()` and commits internally. The
new endpoint uses a **direct async query** (or a thin purpose-built async helper)
against the apartment model for the catalog, and a direct async insert for the
`UserApartment` link — avoiding the mixed-session pitfalls. Returns only the
fields the selector needs (id, building/house label, apartment number).

**Why no sync/async invite bridge.** Because the web form carries no invite
token (§3), there is no `InviteService` (sync `Session`) involvement and no
cross-session transaction problem. The whole write path is native async on the
request's `AsyncSession`.

### 4.2 Scheme 1 — WebApp (React `/register`)

- New **public** route `/register` in `frontend/src/App.tsx` →
  `pages/RegisterPage.tsx` (no `ProtectedRoute`), launched as a Telegram Mini App.
- On mount: read `window.Telegram.WebApp.initData`; if absent → "откройте форму
  через Telegram". POST it to `/registration/start` → store the
  `registration_ticket` in memory, prefill name, render the apartment selector
  from the returned catalog.
- Form fields: full name (prefilled from Telegram user), phone (prefilled ONLY
  from an existing pending `User.phone` if present — Telegram WebApp `initData`
  does not expose a phone number; otherwise the user types it), apartment
  (selector). On submit → `POST /registration/applicant` with
  `Authorization: Bearer <registration_ticket>`.
- Result handling:
  - `pending` (always, on success) → "заявка отправлена, ожидайте одобрения".
  - `409 already approved` → redirect into the app.
  - `401` (ticket expired) → re-run `/start` (re-reads fresh initData) and ask
    the user to resubmit; if initData itself is stale, prompt to reopen the form.
  - `400`/`422` validation → inline field errors.
- Hooks: `useRegistrationStart.ts` (ticket + catalog + prefill),
  `useRegisterApplicant.ts` (submit). i18n keys in
  `frontend/src/i18n/locales/{ru,uz}.json`.

Edge already proxies `/uk/` → `uk-frontend` and `/uk/api/` →
`uk-management-api`; the SPA serves `/register` and the API serves
`/api/v2/registration/*`. **No nginx changes required.**

### 4.3 Scheme 2 — Bot (unchanged + entry button)

- Existing onboarding FSM untouched.
- Single addition: a **WebApp button** ("Регистрация (форма)") on the new-user
  welcome screen (`handlers/base.py:handle_regular_start` / welcome keyboard)
  whose `web_app` URL is the frontend `/uk/register`. The WebApp button needs no
  start_param (the form carries no token); Telegram delivers signed `initData`
  on open, satisfying the WebApp-only identity decision. In-chat onboarding
  remains the alternative.

### 4.4 Approval flow (corrected)

The current system has THREE relevant flags: `user.status`
(pending/approved/blocked, gates login — `login_twa` requires `approved`),
`user.verification_status` (pending/verified/rejected), and
`UserApartment.status` (pending/approved). `AuthService.approve_user` flips only
`user.status`; `UserVerificationService.approve_verification` sets
`verification_status="verified"` and auto-approves pending `UserApartment`s — two
distinct actions today.

**Decision — approval is the EXISTING flow, unchanged.** A web-registered
applicant produces the SAME artifacts as bot onboarding (pending `user.status` +
pending `UserApartment` + manager notification) and is approved through the SAME
existing manager actions: apartment moderation
(`/api/v2/addresses/moderation/{id}/approve` and the bot apartment-approval
handlers) and user approval (the `approve_user` family). **This feature modifies
no approval entrypoint.**

The system's existing **two-status reality** — `user.status` (gates login) and
`UserApartment.status` (apartment access), approved by separate actions — already
applies to bot-onboarded residents today. The WebApp introduces nothing new: a
web-registered applicant becomes fully active exactly as a bot-onboarded one
does, via the same existing tools.

**Unifying user-approval and apartment-approval into a single manager action is a
pre-existing concern, explicitly OUT OF SCOPE** (§10). Doing it would mean
touching every approval entrypoint — `handle_approve_user`
(`user_management.py:749`), `handle_approve_user_from_notification`
(`user_management.py:227`), `admin_approve_apartment` (`user_apartments.py:557`),
the API moderation endpoint, and the dashboard — and is a separate ticket. We
therefore do NOT invent a "registration apartment" marker, a repoint rule, or an
approval helper. (Note: `UserApartment` has no `source`/`purpose` column, so such
a marker would require a migration — another reason to keep this out of scope.)

**Do NOT call `UserVerificationService.approve_verification` from this feature** —
it has destructive side-effects (sets `verification_status`, deletes
Media-Service documents and `UserDocument` rows,
`user_verification_service.py:149`); that belongs to the existing verification
flow, not registration.

### 4.5 Retire `uk-web-registration`

- Remove the `web` service (and its `:8000` publish) from `docker-compose.yml`.
- Delete `uk_management_bot/web/` (templates, `web/api/invite.py`, `web/main.py`,
  `web/limiter.py`, static).
- Tests cleanup (all under `uk_management_bot/tests/`):
  - Delete the web-endpoint-only tests: `test_invite_register.py`,
    `test_invite_register_role.py`, `test_web_debug_routes_guard.py`.
  - `test_invite_sec020.py` is **mixed** — it has web-endpoint tests AND a
    service-level test of `InviteService._use_nonce_atomically`
    (`test_validate_invite_raises_token_already_used_error_on_race_loser`).
    **Preserve** the service-level test (move it to a service test module);
    delete only the web-endpoint portions.
- Eliminates the public `:8000` exposure as a side effect.

## 5. Data Flow (WebApp scheme)

```
Bot new-user welcome
  └─ tap "Регистрация (форма)" (WebApp button → /uk/register)
       └─ Telegram opens Mini App with signed initData
            └─ POST /api/v2/registration/start { init_data }
                 ├─ verify initData → trusted telegram_id (blocked→403, approved→409)
                 └─ → { registration_ticket (JWT ~30m), prefill, apartments[] }
            └─ user fills ФИО / телефон / квартира → submit
                 └─ POST /api/v2/registration/applicant   (Bearer registration_ticket)
                      ├─ validate phone/full_name/apartment_id
                      ├─ ensure pending user (modern role fields) + pending UserApartment
                      ├─ notify managers
                      └─ → { status: "pending" } → "ожидайте одобрения"
       (manager completes the EXISTING approval steps — user approval AND apartment
        moderation → resident logs in via normal TWA/web login)
```

## 6. Components & Boundaries

**Backend**
- `api/registration/router.py` — two endpoints, thin; delegates to service.
- `api/registration/schemas.py` — `StartIn`, `StartOut`, `RegisterApplicantIn`, `ApartmentOut`, `RegistrationResult`.
- `api/registration/service.py` — `RegistrationService` (async): user upsert, apartment link, manager notification (direct Telegram `sendMessage`, cf. `send_otp_via_bot`).
- `api/registration/tickets.py` — `create_registration_ticket` / `verify_registration_ticket` (purpose=register, sub=telegram_id; reuse the MFA JWT *pattern*, not the MFA function).
- `api/main.py` — `include_router(registration_router, prefix="/api/v2/registration")`.

**Frontend**
- `pages/RegisterPage.tsx`, `hooks/useRegistrationStart.ts`,
  `hooks/useRegisterApplicant.ts`, route wiring in `App.tsx`, i18n keys.

**Bot**
- Welcome keyboard WebApp button (`handlers/base.py` + relevant keyboard module).

**Infra**
- `docker-compose.yml` (remove `web`), delete `uk_management_bot/web/`.

## 7. Error Handling

| Case | Behaviour |
|---|---|
| initData missing/invalid/expired (`/start`) | `401` → "откройте через Telegram" |
| Registration ticket missing/expired (`/applicant`) | `401` → client re-runs `/start` |
| User blocked | `403` |
| User already approved | `409` → client redirects into app |
| Invalid phone / empty name / unknown apartment | `400`/`422` field message |
| Manager notification failure | non-fatal; registration succeeds, logged server-side |
| Internal error | `500`, detail logged server-side, generic client message |

## 8. Testing

- **Backend (pytest, in container):** initData valid/invalid/expired at `/start`;
  blocked→403, approved→409; ticket mint/verify (purpose + expiry); `/applicant`
  rejects bad/expired ticket; pending user created with MODERN role fields (not
  legacy `role`); idempotent pending re-submit; phone validation; unknown
  apartment→400; `UserApartment(pending)` attached; rate-limit `3/min`.
- **Frontend (vitest):** initData-absent guard, start→prefill+catalog, form
  validation, submit states (pending / 409 / 401-re-start / field errors).
- **Manual:** Telegram WebApp walkthrough via telegram-qa MCP — open form (verify
  prefill + catalog), submit → pending; manager approves → resident logs in.

## 9. Edge Cases & Idempotency

1. **Re-submit** (sequential) → `core.request_apartment` finds the existing
   pending link and raises `AddressConflict` → map to `409` / idempotent;
   user-row fields update idempotently. **Concurrent submits** that both pass
   core's pre-check race on `UniqueConstraint(user_id, apartment_id)`; core does
   NOT catch this, so the **endpoint** must catch `IntegrityError` and map to a
   no-op / `409`, never `500`.
2. **User requests a *different* apartment** → same as the bot: a per-apartment
   request row. The WebApp does NOT invent a "single registration apartment" rule
   (the model has no marker for it); it follows the existing model — the manager
   approves the relevant request.
3. **Existing `rejected` UserApartment for that apartment** → the WebApp uses the
   SAME core, which currently raises a conflict ("предыдущая заявка была
   отклонена") rather than silently re-opening. Surfaced as `409` / field error —
   no behavior change vs the bot. (If rejected→re-apply is wanted later, change it
   in the shared core for both surfaces.)
4. **Telegram user without `last_name` / single-word `full_name`** → split safely.
5. **Opened outside Telegram** (no initData) → `401`, friendly message.
6. **Ticket expiry during a long session** → `/applicant` returns `401`; the
   client transparently re-runs `/start` (fresh initData) and resubmits.

## 10. Out of Scope (separate tickets)

- Invite-token / staff registration on the web (stays bot-only).
- Non-Telegram browser registration with phone/Login-Widget binding.
- Bot onboarding FSM rework.
- Unifying user-approval and apartment-approval into a single manager action
  (pre-existing two-step reality; registration reuses existing approval flows
  unchanged — see §4.4). Would touch all approval entrypoints + a model marker.
- Apartment catalog management UX changes.
