import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

/**
 * Конфиг STANDALONE-сборки превью экранов контроля доступа (для скриншотов).
 * НЕ влияет на боевую сборку (vite.config.ts). root = preview/, относительные
 * ассеты (base './') для статической отдачи из любой папки, отдельный outDir.
 * Плагины и alias '@' зеркалят основной конфиг, чтобы стили (Tailwind v4) и
 * импорты компонентов резолвились одинаково.
 */
export default defineConfig({
  root: path.resolve(__dirname, 'preview'),
  base: './',
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  build: {
    outDir: path.resolve(__dirname, 'dist-preview'),
    emptyOutDir: true,
    sourcemap: false,
  },
})
