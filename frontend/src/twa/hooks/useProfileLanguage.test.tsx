import { describe, it, expect, beforeEach, afterAll } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import type { ReactNode } from 'react'
import { server } from '../../test/msw/server'
import i18n from '../../i18n'
import { useProfileLanguage } from './useProfileLanguage'

// Язык TWA — из профиля пользователя (users.language: выбран в боте или в
// профиле TWA), а не из Telegram language_code. i18n стартует с языка
// Telegram (фолбэк до загрузки профиля), затем профиль его перекрывает.

function mockProfile(language: string | null) {
  server.use(
    http.get('*/api/v2/profile', () =>
      HttpResponse.json({ id: 1, telegram_id: 42, language, roles: ['executor'], active_role: 'executor' }),
    ),
  )
}

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>
}

beforeEach(async () => {
  // Telegram language_code = ru → i18n стартовал по-русски.
  await i18n.changeLanguage('ru')
})

afterAll(async () => {
  await i18n.changeLanguage('ru')
})

describe('useProfileLanguage', () => {
  it('applies profile language uz over Telegram ru', async () => {
    mockProfile('uz')
    renderHook(() => useProfileLanguage(), { wrapper })
    await waitFor(() => expect(i18n.language).toBe('uz'))
  })

  it('switches back to ru when profile says ru', async () => {
    await i18n.changeLanguage('uz')
    mockProfile('ru')
    renderHook(() => useProfileLanguage(), { wrapper })
    await waitFor(() => expect(i18n.language).toBe('ru'))
  })

  it('applies uz_cyrl as its own locale (Cyrillic simple mode, rest falls back to uz)', async () => {
    mockProfile('uz_cyrl')
    renderHook(() => useProfileLanguage(), { wrapper })
    await waitFor(() => expect(i18n.language).toBe('uz_cyrl'))
    expect(i18n.t('twa.simple.tabs.mine')).toBe('Меники')
    expect(i18n.t('twa.exec.shift.title')).toBe('Smena')
  })

  it('ignores unknown profile language', async () => {
    mockProfile('en')
    const { result } = renderHook(() => useProfileLanguage(), { wrapper })
    await waitFor(() => expect(result.current.isFetched).toBe(true))
    expect(i18n.language).toBe('ru')
  })
})
