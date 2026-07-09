import { describe, it, expect, vi } from 'vitest'
import { render as rtlRender, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { I18nextProvider, initReactI18next } from 'react-i18next'
import { MemoryRouter } from 'react-router-dom'
import i18next from 'i18next'
import { http, HttpResponse } from 'msw'
import { render } from '../../../test/test-utils'
import { server } from '../../../test/msw/server'
import ru from '../../../i18n/locales/ru.json'
import uz from '../../../i18n/locales/uz.json'

// PullToRefresh → useTelegramSDK: не трогаем реальный Telegram-рантайм.
vi.mock('../../hooks/useTelegramSDK', () => ({
  useTelegramSDK: () => ({ haptic: vi.fn(), showBackButton: () => () => {} }),
}))

import HomePage from './HomePage'

describe('TWA HomePage', () => {
  it('renders board_config announcements + multiline working hours (RU)', async () => {
    render(<HomePage />)
    // Новость и контактная карточка из MSW-фикстуры.
    expect(await screen.findByText('Новость')).toBeInTheDocument()
    expect(screen.getByText('Контакты')).toBeInTheDocument()
    // Часы работы — многострочные (whitespace-pre-line), иначе схлопнутся.
    const hours = await screen.findByText(/Пн–Пт/)
    expect(hours).toHaveClass('whitespace-pre-line')
    expect(hours.textContent).toContain('\n')
  })

  it('requests ?lang=uz and renders UZ content when language is uz', async () => {
    let capturedLang: string | null = null
    server.use(
      http.get('*/api/v2/announcements', ({ request }) => {
        capturedLang = new URL(request.url).searchParams.get('lang')
        return HttpResponse.json({
          announcements: [{ id: 'n1', type: 'info', title: 'Yangilik', body: 'Matn' }],
          working_hours: 'Du–Ya: 08:00–20:00',
          emergency_phones: ['+998783331971'],
        })
      }),
    )

    // Отдельный i18n-инстанс с RU+UZ на языке uz, чтобы не протекало состояние
    // языка через singleton testI18n (он ru-only).
    const uzI18n = i18next.createInstance()
    await uzI18n.use(initReactI18next).init({
      resources: { ru: { translation: ru }, uz: { translation: uz } },
      lng: 'uz',
      fallbackLng: 'ru',
      interpolation: { escapeValue: false },
    })
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })

    rtlRender(
      <QueryClientProvider client={queryClient}>
        <I18nextProvider i18n={uzI18n}>
          <MemoryRouter>
            <HomePage />
          </MemoryRouter>
        </I18nextProvider>
      </QueryClientProvider>,
    )

    expect(await screen.findByText('Yangilik')).toBeInTheDocument()
    await waitFor(() => expect(capturedLang).toBe('uz'))
  })
})
