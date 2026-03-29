# Code Debugger & Security - Project Memory

## Project: UK Management Bot

### Frontend Stack (as of 2026-03-10)
- React 18 + TypeScript + Vite + Tailwind CSS v4 (@tailwindcss/vite)
- State: Zustand (persisted), React Query (server state)
- Routing: react-router-dom v6
- DnD: @dnd-kit/core + @dnd-kit/sortable
- API: axios with interceptors
- TWA: Telegram WebApp integration via window.Telegram.WebApp

### Key Frontend Files
- `frontend/src/api/client.ts` -- axios instance with auth interceptors
- `frontend/src/stores/authStore.ts` -- Zustand auth store (persisted)
- `frontend/src/hooks/useWebSocket.ts` -- WS with reconnection (has stale closure bug)
- `frontend/src/hooks/useKanban.ts` -- Kanban data + WS integration
- `frontend/src/hooks/useTWAAuth.ts` -- TWA authentication hook
- `frontend/src/utils/isTWA.ts` -- Telegram WebApp detection

### Known Bug Patterns (Frontend) -- updated 2026-03-12
- **Stale closures FIXED**: useWebSocket now uses useRef(onMessage) pattern
- **401 thundering herd**: concurrent 401s each trigger refresh; only first succeeds
- **DnD disabled prop FIXED**: RequestCard uses `{ draggable: true, droppable: true }` object form
- **DnD collision detection**: `closestCenter` still resolves to card nodes; needs custom filter
- **TWA auth race OPEN**: TWARequestDetailPage queries fire before auth; need `enabled` guard
- **Form state persistence**: CallCenterModal FIXED (useEffect on isOpen); RequestDetailModal STILL broken
- **Optimistic update key mismatch**: KanbanBoard:99 `['kanban', {}]` never matches cache key
- **Stats from filtered data**: EmployeesPage totals computed from filtered array, misleading
- **useMemo anti-pattern**: EmployeesPage wraps controlled input in useMemo+context
- **AssignRequestModal scope**: Only shows "В работе" requests, not "Новая"
- **Timeline missing Отменена**: TWARequestDetailPage STATUS_ORDER omits it; renders all grey

### Security Notes
- Tokens stored in localStorage (acceptable for internal tool)
- WS token passed in URL query param (logged in server access logs)
- No CSRF protection needed (API uses Bearer tokens)

See: [frontend-review-2026-03-10.md](./frontend-review-2026-03-10.md) for full bug list

### Backend API Layer (added 2026-03-10)
- FastAPI app under `uk_management_bot/api/`
- Auth: JWT (python-jose) + Telegram Widget + TWA init_data
- DB sessions: `dependencies.py:get_db()` does NOT auto-commit (unlike `session.py:get_async_db()`)
- AsyncSessionLocal: Only created for PostgreSQL; is None for SQLite -- API crashes in dev
- JWT secret reuses INVITE_SECRET (semantic misuse, should have dedicated JWT_SECRET)
- Settings class is plain Python, NOT Pydantic -- annotations are decorative

### Known Bug Patterns (Backend API)
- Race condition on request_number gen (COUNT+increment, no lock) in requests/ and callcenter/
- **String(10) column ALWAYS overflows**: YYMMDD-NNNN = 11 chars > 10 limit -- production blocker
- Missing authz on update_request PATCH -- FIXED as of 2026-03-12 (now requires manager role)
- auth_date freshness check FIXED (24h window) in auth/service.py as of 2026-03-10
- WS handler: pubsub unbound in finally if Redis connect fails (UnboundLocalError)
- update_profile uses query params instead of JSON body
- publish_request_event swallows ALL exceptions silently
- `add_comment` does not verify parent request exists (orphan records or 500)
- `list_requests` never joins executor -- executor_name always None
- No request status transition validation (any status->any status allowed)
- `exclude_none=True` in update endpoints prevents clearing optional fields

See: [backend-api-review-2026-03-10.md](./backend-api-review-2026-03-10.md) for first review
See: [backend-api-review-2026-03-12.md](./backend-api-review-2026-03-12.md) for requests+shifts deep review

### Shifts/Dashboard Feature (reviewed 2026-03-11, updated 2026-03-12)
- `shifts/router.py`: 18 endpoints, all require `manager` role via `require_roles`
- `ws/router.py`: kanban + shifts WS channels; auth but NO role check
- `redis_pubsub.py`: per-connection Redis clients leak (no `client.close()` in finally)
- `stats_router.py`: analytics aggregates with silent exception swallowing

### Known Bug Patterns (Shifts Feature)
- **Transfer approve+reject data corruption**: approve reassigns shift.user_id immediately, reject never reverts it
- **Mass assignment**: update_shift/update_template use setattr loop without field whitelisting
- **LIKE injection FIXED**: `_escape_like()` helper added as of 2026-03-12 review
- **CreateShiftBody validation IMPROVED**: max_requests>=1 and end_time>start_time validators added
- **Unbounded period FIXED**: stats endpoint now clamps days to max(1, min(365))
- **UpdateTemplateBody cross-validation gap**: min_executors/max_executors only validated when both in same request
- **Manager can block admins**: approve/reject/block endpoints don't check target user's role
- **get_schedule unbounded date range**: no max range validation on date_from/date_to
- **scalar_subquery() misuse**: has_active_shift filter uses scalar_subquery with IN, should use subquery
- **Frontend null crash**: AnalyticsPage `ex.name.trim()` crashes when name is null
- **Dual WS subscriptions**: ShiftsPage opens two WS connections to same /shifts channel
- **Modal stale state**: CreateShiftModal (same pattern as CallCenterModal)

See: [shifts-review-2026-03-11.md](./shifts-review-2026-03-11.md) for full bug list

### Address Management Feature (reviewed 2026-03-13)
- `addresses/router.py`: 15 endpoints (CRUD yards/buildings/apartments + search + moderation + stats)
- All endpoints require `manager` role -- authorization consistent
- Three-level hierarchy: Yards > Buildings > Apartments + UserApartment moderation
- Frontend: AddressesPage + 4 modals (YardForm, BuildingForm, ApartmentForm, BulkCreate) + ModerationPanel

### Known Bug Patterns (Addresses)
- **model_validate lazy-load crash**: ORM @property (buildings_count etc) triggers MissingGreenlet in async
- **LIKE injection OPEN**: search_apartments does not escape % and _ metacharacters
- **Mass assignment**: setattr loop without field whitelist (same pattern as shifts)
- **Approve sends no body**: useApproveModeration omits request body; may 422 on FastAPI
- **Frontend sends extra fields**: create modals send is_active:true, not in backend schema (silent ignore)
- **Shared mutation state**: ModerationPanel approve.isPending locks all buttons at once
- **Missing cache invalidation**: update/delete mutations don't invalidate ['address-stats']
- **Deactivation cascade gap**: Yard deactivation doesn't cascade to child buildings
- **Lexicographic apartment sort**: ORDER BY apartment_number sorts "10" before "2"
- **No pagination**: list endpoints return unbounded result sets

See: [addresses-review-2026-03-13.md](./addresses-review-2026-03-13.md) for full bug list

### SAST Security Audit (2026-03-21)
- **3 CRITICAL**: media_service zero auth, bot token in URLs, blocked user re-registration bypass
- **5 HIGH**: wildcard CORS on web app, mass assignment (6 endpoints), LIKE injection (media_service), info disclosure, request_number race
- **6 MEDIUM**: refresh no rate limit, hardcoded secrets/creds in media_service, WS token in URL, callcenter validation, nonce not consumed
- Media service: `app/api/v1/media.py` has `settings.api_keys` field but NEVER checks it
- Media service: `telegram_client.py:136` embeds bot token in file URLs returned to clients
- Web invite: `web/api/invite.py:107-124` resets blocked user status to "pending" with valid invite
- Web invite: nonce only consumed via `join_via_invite()`, bypassed on existing-user update paths
- No eval/exec/subprocess/unsafe deserialization found in project
- All DB queries use parameterized SQLAlchemy ORM (no raw SQL injection vectors)
