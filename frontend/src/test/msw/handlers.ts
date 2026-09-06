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
  // Виджет лифтов на табло (T16): дефолт — «ничего не опубликовано».
  http.get('*/api/v2/public/elevators', () =>
    HttpResponse.json({
      yards: [],
      summary: { total: 0, working: 0, not_working: 0, under_repair: 0, maintenance: 0 },
      dispatch_phone: null,
      generated_at: '2026-09-06T00:00:00Z',
    }),
  ),
  http.get('*/api/v2/announcements', ({ request }) => {
    const lang = new URL(request.url).searchParams.get('lang') ?? 'ru'
    const isUz = lang.startsWith('uz')
    return HttpResponse.json({
      announcements: [
        { id: 'n1', type: 'info', title: isUz ? 'Yangilik' : 'Новость', body: isUz ? 'Matn' : 'Текст' },
        { id: 'contacts', type: 'contact', title: isUz ? 'Aloqa' : 'Контакты', body: 'Диспетчерская: +998783331971' },
      ],
      working_hours: isUz ? 'Du–Ju: 08:00–20:00' : 'Пн–Пт: 08:00–20:00\nСб: Выходной',
      emergency_phones: ['+998783331971'],
    })
  }),
]
