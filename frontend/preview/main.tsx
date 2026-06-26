import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import '../src/i18n'
import i18n from '../src/i18n'
import '../src/index.css'

import Preview from './Preview'
import { manualReviewEvents } from './mockData'
import type { AccessPage, AccessEventRow } from '../src/types/access'

/**
 * Точка входа STANDALONE-превью. Никакой сети: QueryClient настроен не делать
 * рефетчи, а кэш предзаполнен мок-данными под тем же queryKey, что использует
 * реальный ManualReviewQueue (useAccessEvents({ decision: 'manual_review',
 * limit: 50 })). Так настоящий компонент рендерится на синтетике без бэкенда.
 */

// Русский язык принудительно (превью для скриншотов).
i18n.changeLanguage('ru')

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: false,
      refetchOnWindowFocus: false,
      refetchOnMount: false,
      refetchOnReconnect: false,
      staleTime: Infinity,
      gcTime: Infinity,
    },
  },
})

const queuePage: AccessPage<AccessEventRow> = {
  items: manualReviewEvents,
  total: manualReviewEvents.length,
  limit: 50,
  offset: 0,
}
// queryKey должен побайтово совпадать с useAccessEvents в ManualReviewQueue.
queryClient.setQueryData(['access-events', { decision: 'manual_review', limit: 50 }], queuePage)

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <Preview />
    </QueryClientProvider>
  </StrictMode>,
)
