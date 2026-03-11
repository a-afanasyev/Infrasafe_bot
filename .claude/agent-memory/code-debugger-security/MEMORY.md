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

### Known Bug Patterns (Frontend)
- **Stale closures in hooks**: useWebSocket captures onMessage once; needs useRef or useCallback
- **Missing retry guards**: axios 401 interceptor can loop; needs `_retry` flag on config
- **DnD disabled prop**: `useSortable({ disabled: true })` boolean form ONLY disables draggable, NOT droppable in @dnd-kit/sortable@10. Must use `{ draggable: true, droppable: true }` object form.
- **DnD collision detection**: `closestCenter` resolves to card nodes (from SortableContext) more often than column nodes (from useDroppable). Use custom collision filter to block forbidden columns at collision level.
- **TWA auth race**: queries fire before async TWA auth completes; need `enabled` guard
- **Form state persistence**: CallCenterModal never resets state between open/close
- **localStorage.clear()**: used in both client.ts and authStore; nukes ALL localStorage

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
- Missing authz on update_request PATCH -- any user can modify any request
- No auth_date freshness check on Telegram Widget/TWA login (replay attacks)
- WS handler: pubsub unbound in finally if Redis connect fails (UnboundLocalError)
- update_profile uses query params instead of JSON body
- publish_request_event swallows ALL exceptions silently
- String(10) column overflow at >999 daily requests

See: [backend-api-review-2026-03-10.md](./backend-api-review-2026-03-10.md) for full bug list
