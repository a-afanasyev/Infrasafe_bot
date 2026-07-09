import { defineConfig, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

// Brand-зависимые шрифты/favicon/manifest в index.html. process.env.VITE_BRAND
// доступен на этапе сборки (build-arg → ENV в Dockerfile). Дефолт infrasafe →
// HTML не меняется; profk → Montserrat/Open Sans + PROFK favicon/manifest.
const PROFK_FONTS =
  '<link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@400;500;600;700;800&family=Open+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">'

function brandHtmlPlugin(): Plugin {
  const isProfk = process.env.VITE_BRAND === 'profk'
  return {
    name: 'brand-html',
    // order:'pre' — до инъекции base (/uk/) в href, иначе favicon/manifest уже
    // переписаны в /uk/... и наши замены по «/favicon.svg» не срабатывают.
    transformIndexHtml: {
      order: 'pre',
      handler(html) {
        if (!isProfk) return html
        return html
          .replace(/<!--BRAND_FONTS_START-->[\s\S]*?<!--BRAND_FONTS_END-->/, PROFK_FONTS)
          .replace('href="/favicon.svg"', 'href="/profk-favicon.svg"')
          .replace('href="/manifest.json"', 'href="/manifest.profk.json"')
      },
    },
  }
}

// SPA is mounted under /uk/ on the shared infrasafe.uz domain.
// Top-level `base` is the only public Vite knob (server.base is internal),
// so dev URLs are http://localhost:5173/uk/* and built assets reference /uk/assets/*.
export default defineConfig(({ mode }) => ({
  base: '/uk/',
  plugins: [react(), tailwindcss(), brandHtmlPlugin()],
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
