import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

// SPA is mounted under /uk/ on the shared infrasafe.uz domain.
// Top-level `base` is the only public Vite knob (server.base is internal),
// so dev URLs are http://localhost:5173/uk/* and built assets reference /uk/assets/*.
export default defineConfig(({ mode }) => ({
  base: '/uk/',
  plugins: [react(), tailwindcss()],
  build: {
    sourcemap: false,
    rollupOptions: {
      output: {
        // FE-042: split heavy vendors out of the entry chunk (was ~720 kB).
        // AnalyticsPage is already React.lazy'd; this carves shared libs into
        // cacheable vendor chunks so the main bundle drops < 400 kB.
        manualChunks: {
          'react-vendor': ['react', 'react-dom', 'react-router-dom'],
          'query-vendor': ['@tanstack/react-query'],
          'dnd-vendor': ['@dnd-kit/core', '@dnd-kit/sortable', '@dnd-kit/utilities'],
          'i18n-vendor': ['i18next', 'react-i18next'],
          'ui-vendor': ['lucide-react', 'sonner'],
        },
      },
    },
  },
  ...(mode === 'production' && {
    esbuild: {
      drop: ['console', 'debugger'],
    },
  }),
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    proxy: {
      '/uk/api': {
        target: 'http://localhost:8085',
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/uk\/api/, '/api'),
      },
      '/uk/ws': {
        target: 'ws://localhost:8085',
        ws: true,
        rewrite: (p) => p.replace(/^\/uk\/ws/, '/ws'),
      },
    },
  },
}))
