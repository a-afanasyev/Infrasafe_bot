import { describe, it, expect, beforeEach, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import { Route, Routes, useLocation } from 'react-router'
import { render, screen, within } from '../test/test-utils'
import ResidentElevatorsPage from './ResidentElevatorsPage'
import {
  EMPTY_PUBLIC_DATA,
  makeTwoYardsData,
  servePublicElevators,
} from '../test/fixtures/publicElevators'

// T17 (Р17) — публичная страница /elevators: сводка, фильтры (URL-состояние),
// группы двор → дом → подъезд → лифт. Данные через msw; флаг — vi.stubEnv.

function LocationProbe() {
  const { search } = useLocation()
  return <div data-testid="location-search">{search}</div>
}

function renderPage(url = '/elevators') {
  return render(
    <>
      <ResidentElevatorsPage />
      <LocationProbe />
    </>,
    { routerEntries: [url] },
  )
}

function shownLabels() {
  return screen.getAllByTestId('public-elevator-row').map((r) => r.getAttribute('title'))
}

beforeEach(() => {
  vi.unstubAllEnvs()
  vi.stubEnv('VITE_ELEVATORS_ENABLED', 'true')
})

describe('ResidentElevatorsPage', () => {
  it('рендерит сводку, дворы, дома с мини-счётчиком, подъезды и строки лифтов', async () => {
    servePublicElevators(makeTwoYardsData())
    renderPage()

    expect(await screen.findByText('2 из 5 работают')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '← На табло' })).toHaveAttribute('href', '/resident-board')
    // Имя двора — и заголовок группы, и option в селекте.
    expect(screen.getAllByText('Двор 1')).toHaveLength(2)
    expect(screen.getAllByText('Двор 2')).toHaveLength(2)
    expect(screen.getByText('ул. Мира, д. 5')).toBeInTheDocument()
    expect(screen.getByText('ул. Садовая, д. 1')).toBeInTheDocument()
    expect(screen.getAllByText('1 из 2 работает')).toHaveLength(2) // д. 5 и Садовая
    expect(screen.getByText('0 из 1 работает')).toBeInTheDocument() // д. 3
    expect(screen.getAllByText('Подъезд 1')).toHaveLength(3)
    expect(shownLabels()).toHaveLength(5)
    expect(screen.getByText('с 01.09.2026')).toBeInTheDocument()
    expect(screen.getByText(/Диспетчерская: \+998 71 123-45-67/)).toBeInTheDocument()
    expect(screen.getByText(/Данные актуальны на \d{2}:\d{2}/)).toBeInTheDocument()
    // Селект двора — только при нескольких дворах.
    expect(screen.getByRole('combobox', { name: 'Двор' })).toBeInTheDocument()
    // Левая рамка строки: цвет статуса у любого нерабочего (в т.ч. синий у ТО), нейтральная у рабочего.
    expect(screen.getByTitle('ул. Садовая, д. 1, подъезд 1, лифт 1')).toHaveStyle({ borderLeftColor: '#2563eb' })
    expect(screen.getByTitle('ул. Мира, д. 3, подъезд 1, лифт 1')).toHaveStyle({ borderLeftColor: '#dc2626' })
    expect(screen.getByTitle('ул. Мира, д. 5, подъезд 1, лифт 1')).toHaveStyle({ borderLeftColor: 'rgba(0,0,0,0.12)' })
  })

  it('чип статуса сужает список и пишет ?status= в URL; «Все» снимает', async () => {
    servePublicElevators(makeTwoYardsData())
    renderPage()
    const user = userEvent.setup()
    await screen.findByText('2 из 5 работают')

    await user.click(screen.getByRole('button', { name: 'В ремонте 1' }))
    expect(shownLabels()).toEqual(['ул. Мира, д. 5, подъезд 1, лифт 2'])
    expect(screen.queryByText('ул. Садовая, д. 1')).not.toBeInTheDocument()
    expect(screen.getByTestId('location-search')).toHaveTextContent('?status=under_repair')
    // Чип статуса крупную строку НЕ меняет (масштаб строки = двор/поиск).
    expect(screen.getByText('2 из 5 работают')).toBeInTheDocument()
    // Мини-счётчик дома — по всем его лифтам, не по отфильтрованным.
    expect(screen.getByText('1 из 2 работает')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Все 5' }))
    expect(shownLabels()).toHaveLength(5)
    expect(screen.getByTestId('location-search')).toHaveTextContent('')
  })

  it('поиск по адресу без регистра пишет ?q= и сужает список; крупная строка и чипы — по найденному', async () => {
    servePublicElevators(makeTwoYardsData())
    renderPage()
    const user = userEvent.setup()
    await screen.findByText('2 из 5 работают')

    await user.type(screen.getByRole('searchbox'), 'САДОВ')
    expect(shownLabels()).toEqual(['ул. Садовая, д. 1, подъезд 1, лифт 1', 'ул. Садовая, д. 1, подъезд 2, лифт 1'])
    expect(screen.getByTestId('location-search')).toHaveTextContent(`?q=${encodeURIComponent('САДОВ')}`)
    expect(screen.getByRole('button', { name: 'Все 2' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'На ТО 1' })).toBeInTheDocument()
    // Крупная строка — в том же масштабе, что чипы: заголовок + мини-счётчик дома Садовая.
    expect(screen.getAllByText('1 из 2 работает')).toHaveLength(2)
    expect(screen.queryByText('2 из 5 работают')).not.toBeInTheDocument()
  })

  it('читает фильтры из URL при открытии по ссылке; селект двора', async () => {
    servePublicElevators(makeTwoYardsData())
    renderPage('/elevators?status=not_working')
    expect(await screen.findByText('ул. Мира, д. 3')).toBeInTheDocument()
    expect(shownLabels()).toEqual(['ул. Мира, д. 3, подъезд 1, лифт 1'])

    const user = userEvent.setup()
    await user.selectOptions(screen.getByRole('combobox', { name: 'Двор' }), '2')
    expect(screen.getByTestId('location-search')).toHaveTextContent('?status=not_working&yard=2')
    expect(screen.getByText('Ничего не найдено')).toBeInTheDocument()
    // Строка — по выбранному двору (без учёта чипа статуса), даже при пустом списке.
    expect(screen.getByText('1 из 2 работает')).toBeInTheDocument()
    expect(screen.queryByTestId('public-elevator-row')).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Сбросить фильтры' }))
    expect(shownLabels()).toHaveLength(5)
    expect(screen.getByTestId('location-search')).toHaveTextContent('')
  })

  it('пустой ответ → заголовок и заглушка без фильтров', async () => {
    servePublicElevators(EMPTY_PUBLIC_DATA)
    renderPage()
    expect(await screen.findByText('Данные о лифтах пока не опубликованы')).toBeInTheDocument()
    expect(within(screen.getByRole('banner')).getByText('Лифты')).toBeInTheDocument()
    expect(screen.queryByRole('searchbox')).not.toBeInTheDocument()
  })

  it('при выключенном флаге редиректит на /resident-board, не дёргая API', async () => {
    vi.stubEnv('VITE_ELEVATORS_ENABLED', '')
    const seen = { value: null as string | null }
    servePublicElevators(makeTwoYardsData(), seen)
    render(
      <Routes>
        <Route path="/elevators" element={<ResidentElevatorsPage />} />
        <Route path="/resident-board" element={<div>BOARD</div>} />
      </Routes>,
      { routerEntries: ['/elevators'] },
    )
    expect(await screen.findByText('BOARD')).toBeInTheDocument()
    expect(seen.value).toBeNull()
  })

  it('старый ответ API без summary → сводка досчитывается по yards', async () => {
    servePublicElevators({ ...makeTwoYardsData(), summary: undefined })
    renderPage()
    expect(await screen.findByText('2 из 5 работают')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Все 5' })).toBeInTheDocument()
  })
})
