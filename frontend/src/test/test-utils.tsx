import type { ReactElement, ReactNode } from 'react'
import { render, renderHook, type RenderOptions } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { I18nextProvider, initReactI18next } from 'react-i18next'
import { MemoryRouter } from 'react-router-dom'
import i18next from 'i18next'
import ru from '../i18n/locales/ru.json'

// Test i18n instance built straight from ru.json — deliberately NOT importing
// src/i18n/index.ts (which wires LanguageDetector / localStorage).
export const testI18n = i18next.createInstance()
testI18n.use(initReactI18next).init({
  resources: { ru: { translation: ru } },
  lng: 'ru',
  fallbackLng: 'ru',
  interpolation: { escapeValue: false },
})

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  })
}

function AllProviders({ children }: { children: ReactNode }) {
  // Fresh QueryClient per mount so cache never leaks between tests.
  const queryClient = makeQueryClient()
  return (
    <QueryClientProvider client={queryClient}>
      <I18nextProvider i18n={testI18n}>
        <MemoryRouter>{children}</MemoryRouter>
      </I18nextProvider>
    </QueryClientProvider>
  )
}

function customRender(ui: ReactElement, options?: Omit<RenderOptions, 'wrapper'>) {
  return render(ui, { wrapper: AllProviders, ...options })
}

function customRenderHook<R>(callback: () => R) {
  return renderHook(callback, { wrapper: AllProviders })
}

export * from '@testing-library/react'
export { customRender as render, customRenderHook as renderHook }
