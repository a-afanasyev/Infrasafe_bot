import { http, HttpResponse } from 'msw'

// Wildcard prefixes (`*/api/v2/...`) so the host + `/uk` base don't matter.
// Phase 0 seeds the public endpoints; Phase 3 expands this set to every
// endpoint the data-hooks hit (derive from `grep "/api/v2/" src/hooks src/api`).
// onUnhandledRequest:'error' (setup.ts) makes any gap fail loudly.
export const handlers = [
  http.get('*/api/v2/public/board', () =>
    HttpResponse.json({ active: 0, completed_month: 0, specialists_on_shift: 0, avg_resolution_hours: null }),
  ),
  http.get('*/api/v2/public/board-config', () => HttpResponse.json({})),
]
