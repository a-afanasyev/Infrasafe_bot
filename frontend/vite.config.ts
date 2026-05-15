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
