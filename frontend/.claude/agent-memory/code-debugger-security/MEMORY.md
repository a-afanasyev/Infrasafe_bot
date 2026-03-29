# Frontend Code Debugger Memory

## dnd-kit Patterns (2026-03-11)
- **Version combo**: @dnd-kit/core@6.3.1 + @dnd-kit/sortable@10.0.0
- **Critical**: `useSortable({ disabled: true })` with boolean only disables draggable, NOT droppable.
  The `normalizeLocalDisabled` function in sortable@10 explicitly sets `droppable: false` for backwards compat.
  Must use `{ draggable: true, droppable: true }` object form to disable both.
- **Custom collision detection**: wrap `closestCenter` and filter `args.droppableContainers` to enforce transition rules at the collision level, not just in `onDragEnd`.
- **SortableContext**: registers every item as both draggable AND droppable. Cards inside it become collision targets for `closestCenter`, often resolving `over.id` to a card instead of a column.
- Use `useRef` alongside `useState` for drag state that needs synchronous access in collision detection callbacks.

## Kanban Architecture
- Files: `src/components/kanban/KanbanBoard.tsx`, `KanbanColumn.tsx`, `RequestCard.tsx`
- Hook: `src/hooks/useKanban.ts` — React Query with key `['kanban', filters]`
- Status flow: guards in `isTransitionAllowed()` — frozen statuses block all, "Новая" blocks inbound from other columns
- Optimistic update uses `queryClient.setQueryData(['kanban', {}], ...)` — must match hook's query key

## i18n Architecture (2026-03-21)
- Files: `src/i18n/index.ts`, `apiMaps.ts`, `formatters.ts`, `locales/ru.json`, `locales/uz.json`
- Pattern: Russian API values -> `apiMaps.ts` -> i18n keys -> translated text
- `constants.ts` holds raw API values (Russian for statuses/categories, English for shift types)
- Known gaps: `AnalyticsPage` pie chart shows raw Russian category names; `AssignRequestModal` shows raw category; `ShiftDetailModal` shows raw English shift status; `TemplatesPage` uses hardcoded `SHIFT_TYPE_LABELS`/`DAY_LABELS` from constants instead of t()
- DnD droppable IDs are raw Russian status strings (intentional, must NOT be translated)
- Pluralization: Russian uses `_one/_few/_many`, Uzbek uses `_other` only
- `formatters.ts` `formatDate()` has no Invalid Date guard

## Project Stack
- React 19, Vite 7, TailwindCSS 4, TypeScript 5.9
- React Query v5, Zustand v5, React Router v7
- TWA SDK for Telegram Web App integration
