# Address Management Feature - Full Review (2026-03-13)

## Files Reviewed
- Backend: `uk_management_bot/api/addresses/schemas.py`, `router.py`
- Backend integration: `uk_management_bot/api/main.py` (line 16, 64)
- Frontend: `frontend/src/hooks/useAddresses.ts`, `pages/AddressesPage.tsx`
- Frontend modals: `YardFormModal.tsx`, `BuildingFormModal.tsx`, `ApartmentFormModal.tsx`, `BulkCreateModal.tsx`
- Frontend: `ModerationPanel.tsx`, `App.tsx`, `DashboardLayout.tsx`
- ORM models: `yard.py`, `building.py`, `apartment.py`, `user_apartment.py`
- Types: `frontend/src/types/api.ts` (lines 140-212)

## Critical Bugs

### BUG-3: model_validate triggers lazy-load crash in async context
- Location: router.py lines 91, 122, 228, 266, 391, 448, 562
- Yard/Building/Apartment ORM models have @property (buildings_count, apartments_count, residents_count)
  that access lazy-loaded relationships
- YardOut/BuildingOut/ApartmentOut use from_attributes=True
- model_validate reads ORM property -> triggers lazy load -> MissingGreenlet in async
- Fix: convert to column dict before validation, or eagerly load, or exclude computed fields

## Medium Bugs

### BUG-1/SEC-1: LIKE injection in search_apartments
- Location: router.py line 605
- `f"%{q}%"` does not escape %, _, \ in user input
- Fix: add _escape_like() helper (same as shifts feature had)

### BUG-2: useApproveModeration sends no body
- Location: useAddresses.ts line 214
- Backend ModerationAction expects JSON body with optional comment
- axios POST with no body may not send Content-Type: application/json
- Fix: pass {} as second argument to apiClient.post

### BUG-8: Shared mutation state in ModerationPanel
- Location: ModerationPanel.tsx lines 124-125, 241-242
- approve.isPending is shared across all items
- Fix: track per-item loading state

### BUG-9: Deactivation cascade gap
- Location: router.py lines 167-192 vs 127-164
- delete_yard checks for active buildings, but update_yard allows is_active=False without cascade
- Result: active buildings under inactive yard

## Low Bugs

### BUG-5: Frontend sends is_active in create payloads
- YardFormModal line 102, BuildingFormModal line 121, ApartmentFormModal line 109
- Backend create schemas don't include is_active (silently ignored)

### BUG-7: Lexicographic apartment sorting
- router.py line 370: ORDER BY apartment_number (string sort)
- "10" before "2"

### BUG-10: Missing address-stats invalidation
- useUpdateYard, useUpdateBuilding, useUpdateApartment, delete mutations
  don't invalidate ['address-stats']

## Security

### SEC-2: Mass assignment via setattr
- router.py lines 152-153, 298-299, 540-541
- Relies on schema whitelist only; no explicit field list
- Same pattern as shifts (already flagged)

### SEC-3: No rate limiting on address endpoints
- slowapi configured but no @limiter.limit decorators

### SEC-4: No pagination on list endpoints
- list_yards, list_buildings, list_apartments return all rows

## Positive
- All endpoints properly guarded with require_roles("manager")
- Uniqueness checks before insert (yards by name, apartments by building+number)
- Cascading delete protection (check active children before soft-delete)
- Frontend types match backend schemas perfectly
- Bulk create capped at 500 items both frontend and backend
- Proper async/await throughout
