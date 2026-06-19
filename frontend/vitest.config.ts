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
          'src/twa/**',
          'src/pages/twa/**',
          'src/hooks/useTWAAuth.ts',
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
        // Breadcrumb/TabBar, shared EmptyState/LoadingSpinner). Floors sit a few
        // points under the achieved global so a regression trips them without
        // day-to-day flake.
        thresholds: {
          lines: 22,
          statements: 20,
          functions: 15,
          branches: 17,
        },
      },
    },
  }),
)
