import { defineConfig, mergeConfig } from 'vitest/config'
import viteConfig from './vite.config'

// Separate from vite.config.ts on purpose: tsconfig.node.json typechecks
// vite.config.ts via `tsc -b`, and vite's defineConfig type has no `test` field.
// mergeConfig reuses the Vite `base: '/uk/'` + `@`→./src alias.
export default mergeConfig(
  viteConfig({ command: 'serve', mode: 'test' }),
  defineConfig({
    test: {
      globals: true,
      environment: 'jsdom',
      // Sets window.location (for BrowserRouter basename="/uk/" and
      // window.location-dependent code). Does NOT set import.meta.env.BASE_URL.
      environmentOptions: { jsdom: { url: 'http://localhost/uk/' } },
      setupFiles: ['./src/test/setup.ts'],
      css: false,
      // api/client.ts uses VITE_API_URL ?? import.meta.env.BASE_URL; pin it so
      // axios uses an absolute base and MSW matches deterministically.
      env: { VITE_API_URL: 'http://localhost/uk' },
      coverage: {
        provider: 'v8',
        reporter: ['text', 'text-summary', 'html', 'lcov'],
        include: ['src/**/*.{ts,tsx}'],
        exclude: [
          // AUD6-P2-28: 'src/twa/**' и 'src/pages/twa/**' СНЯТЫ из исключений —
          // TWA прод-поверхность (экран контролёра раскатан с 2026-07-14) и
          // обязана быть в знаменателе; floor'ы перекалиброваны по факту ниже.
          'src/components/ui/**',
          'src/types/**',
          'src/main.tsx',
          'src/App.tsx',
          'src/i18n/index.ts',
          'src/test/**',
          '**/*.d.ts',
          '**/*.test.*',
        ],
        // TEST-068 ratchet — coverage floor raised per phase toward the 80%
        // target (see plan ratchet schedule). The pages/components denominator
        // is large, so the global is still low; each phase ratchets it up.
        //
        // Phase 2 (stores + hooks): hook coverage (useHasRole/usePageTitle/
        // useMediaQuery/useEmployees + MSW data-hook paths).
        // Phase 3 (components): presentational components (addresses StatsBar/
        // Breadcrumb/TabBar, shared EmptyState/LoadingSpinner).
        // Phase 5 (pages): LoginPage (password + MFA flow) + RegisterPage (resident
        // self-reg phases). Floors sit a few points under the achieved global so a
        // regression trips them without day-to-day flake.
        //
        // 2026-07-25: floor'ы подтянуты к фактическому замеру (lines 41.55,
        // statements 39.56, functions 30.72, branches 32.1) — отставали на
        // ~15 пунктов и уже не ловили регрессию.
        // AUD6-P2-28 (2026-07-31): twa включён в знаменатель; замер с ним —
        // lines 42.28 / statements 40.38 / functions 32.89 / branches 33.57.
        // Floor'ы на ~1 пункт ниже факта: регрессия ловится, flake — нет.
        // TEST-068: ratchet — только вверх, вслед за фактом (порция 3.1,
        // 2026-09-01: факт 50.8/48.8/40.7/41.1 после закрытия нулей
        // useAddresses/AddressesPage/DashboardLayout; floor = факт − ~1 п.п.).
        // TEST-068 порция 4 (2026-09-18, после волн 1–7 бэклога): факт 61.84 /
        // 59.65 / 50.89 / 53.11 (lines/statements/functions/branches) при 158
        // файлах / 1078 тестах; components/materials 3.5 % → 94.4 %.
        // Floor = факт − ~1 п.п.; до цели 80 % — ~18 п.п. (pages 56 %,
        // features/resource-accounting 35 %, components/employees 27 %).
        // Порция 5 (2026-09-18): components/employees 27 % → 85 %; факт
        // 62.96 / 60.67 / 52.02 / 54.15 при 163 файлах / 1091 тестах.
        // Порция 6 (2026-09-18): features/resource-accounting 35 % → 85 %; факт
        // 66.64 / 64.12 / 56.31 / 58.40 при 168 файлах / 1118 тестах.
        // Порция 7 (2026-09-18): components/addresses 44 % → 68 %, pages/materials,
        // AnalyticsPage, TemplatesPage 0 % → покрыты; факт 69.86 / 67.24 / 59.30 /
        // 62.90 при 170 файлах / 1139 тестах.
        // Порция 8 (2026-09-18): pages/access/AccessEquipmentPage 39 % → CRUD всех
        // панелей, pages/BoardEditorPage и twa/pages/inspector/CreatePage 0 % →
        // покрыты (попутно BUG-191); факт 73.69 / 71.42 / 64.13 / 65.46 при
        // 173 файлах / 1170 тестах.
        // Порция 9 (2026-09-18): twa/executor/TaskDetailPage + MediaGallery,
        // components/shifts/{CalendarHeatmap,ShiftTimeline,ShiftDetailModal},
        // pages/ShiftsPage 0 % → покрыты; факт 77.72 / 75.41 / 67.71 / 68.77
        // при 177 файлах / 1203 тестах.
        thresholds: {
          lines: 76,
          statements: 74,
          functions: 66,
          branches: 67,
        },
      },
    },
  }),
)
