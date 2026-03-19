# Enterprise UX Architect Memory

## Project: UK Management Frontend
- **Path**: `/Users/andreyafanasyev/Code/UK/frontend/`
- **Stack**: React 19, TypeScript 5.9, Vite 7, Tailwind CSS 4, Zustand 5, TanStack React Query 5, Recharts 3, @dnd-kit, lucide-react
- **UI Library**: None (all components hand-built); CVA + clsx + tailwind-merge already installed
- **Audit date**: 2026-03-19, report at `docs/ux-audit-report.md`
- **Design plan**: 2026-03-19, at `docs/modernization/design-plan.md`

## Key Architecture Notes
- Styling: Mix of inline styles (majority) and Tailwind CSS (CallCenterModal, TransitionModal, TWA pages) -- critical inconsistency
- Design tokens in `src/index.css` via CSS variables (dark default + body.light override)
- Topbar uses dynamic context pattern (TopbarProvider) for page-specific actions
- WebSocket for real-time Kanban and Shifts updates
- TWA (Telegram Web App) pages at `/twa/*` -- separate mobile UX, Tailwind-only
- Fonts declared in CSS vars but NOT loaded in index.html (critical gap)

## Critical UX Issues Found
1. No accessibility (ARIA, keyboard nav, focus management) -- WCAG non-compliant
2. `window.confirm()` / `window.alert()` for destructive actions and stubs (7+ locations)
3. Only 2 shared components (LoadingSpinner, EmptyState) -- no component library
4. CallCenterModal + TransitionModal break in dark theme (Tailwind hardcoded colors)
5. No pagination/virtualization for lists
6. No error boundaries
7. No toast/notification system
8. Contrast issue: --text-muted #5a6a7a on --bg-root #060a10 = 3.7:1 (below WCAG AA 4.5:1)
9. --border opacity too low (0.06) -- practically invisible

## Navigation Structure
- Sidebar: Analytics, Kanban(index), Employees, Shifts, Templates, Addresses, ResidentBoard
- Issue: "Dashboard" label maps to analytics but `/dashboard` route is Kanban
- Missing: Settings, Notifications, Help sections

## User Personas (inferred)
- **Manager/Dispatcher**: Primary user, manages requests via Kanban, reviews employees
- **Resident**: Uses TWA (Telegram) for request creation, or views ResidentBoard
- **Executor**: Not directly using this frontend (uses Telegram bot)

## Design Tokens (from index.css)
- Fonts: Outfit (display), DM Sans (body), IBM Plex Mono (mono)
- Accent: #00d4aa
- Radius: 12px / 8px
- Sidebar: 260px, Topbar: 64px (plan recommends 56px)

## Design Plan Key Decisions
- Strategy: Migrate ALL inline styles to Tailwind CSS + CSS vars
- cn() helper: twMerge(clsx(...)) at src/lib/utils.ts
- 19 shared UI components planned in src/components/ui/
- 4px spacing grid enforced
- Sonner recommended for toast notifications
- Responsive: 4 breakpoints (mobile <640, tablet 640-1023, desktop 1024-1279, wide >=1280)
- Sidebar: expanded/collapsed/overlay responsive behavior
- Full specs in `docs/modernization/design-plan.md`
