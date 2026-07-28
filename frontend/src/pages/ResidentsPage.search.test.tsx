import { describe, it, expect, beforeEach, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import { waitFor } from '@testing-library/react'
import { render, screen } from '../test/test-utils'
import { TopbarProvider } from '../contexts/TopbarContext'
import { useTopbar } from '../contexts/topbar'
import ResidentsPage from './ResidentsPage'
import type { ResidentListResponse, ResidentStats } from '../types/api'

// Регрессия найдена прод-проверкой на profk: в поле поиска терялись символы
// («админ» → «амн», при медленном вводе — вообще ничего). Причина не в поле, а
// в маршруте доставки: узел уезжает в топбар через состояние контекста,
// обновляемое в useEffect, то есть ВТОРЫМ коммитом. У контролируемого поля
// React в фазе обработки события откатывает DOM к последнему отрендеренному
// `value` — всё ещё пустому.
//
// Обычный тест страницы это не ловит: там нет TopbarProvider, и поле поиска
// вообще не рендерится. Поэтому здесь топбар воспроизводится явно.
//
// ⚠ Честная граница: САМУ потерю символов jsdom не воспроизводит — `act()`
// схлопывает оба коммита в один, и контролируемая версия поля тест ниже
// проходит (проверено откатом реализации). Реальным guard'ом служит тест на
// debounce: он падает на старой реализации, потому что та слала запрос на
// каждое нажатие. Отсутствие потери символов проверяется вручную в браузере
// на проде — этим дефект и был найден.

const { listQuery, statsQuery, useResidentsSpy } = vi.hoisted(() => ({
  listQuery: {
    data: undefined as ResidentListResponse | undefined,
    isLoading: false,
    isError: false,
  },
  statsQuery: { data: undefined as ResidentStats | undefined },
  useResidentsSpy: vi.fn(),
}))

vi.mock('../hooks/useResidents', () => ({
  useResidents: (...args: unknown[]) => {
    useResidentsSpy(...args)
    return listQuery
  },
  useResidentStats: () => statsQuery,
}))

vi.mock('../hooks/useAddresses', () => ({
  useYards: () => ({ data: [] }),
  useAllBuildings: () => ({ data: [] }),
  useAllApartments: () => ({ data: [] }),
}))

/** Мини-топбар: рендерит ровно то, что страница отдала через useTopbar. */
function TopbarStub() {
  const { actions } = useTopbar()
  return <header>{actions}</header>
}

function renderWithTopbar() {
  return render(
    <TopbarProvider>
      <TopbarStub />
      <ResidentsPage />
    </TopbarProvider>,
  )
}

beforeEach(() => {
  listQuery.data = { items: [], total: 0, limit: 25, offset: 0 }
  listQuery.isLoading = false
  listQuery.isError = false
  statsQuery.data = undefined
  useResidentsSpy.mockClear()
})

describe('ResidentsPage — поиск в топбаре', () => {
  // Не регрессионный guard (см. оговорку выше), а базовая проверка, что поле
  // вообще принимает ввод после перевода на неконтролируемое.
  it('принимает ввод целиком', async () => {
    const user = userEvent.setup()
    renderWithTopbar()

    const input = screen.getByPlaceholderText(/ФИО или телефон/)
    await user.type(input, 'админ')

    expect((input as HTMLInputElement).value).toBe('админ')
  })

  it('шлёт запрос один раз после паузы, а не на каждое нажатие', async () => {
    const user = userEvent.setup()
    renderWithTopbar()
    const callsBefore = useResidentsSpy.mock.calls.length

    await user.type(screen.getByPlaceholderText(/ФИО или телефон/), 'админ')

    // До истечения debounce поисковый терм в запрос ещё не ушёл.
    const midCalls = useResidentsSpy.mock.calls.slice(callsBefore)
    expect(midCalls.every(c => c[1] === undefined)).toBe(true)

    await waitFor(() => {
      const last = useResidentsSpy.mock.calls[useResidentsSpy.mock.calls.length - 1]
      expect(last[1]).toBe('админ')
    })
  })

  it('новый поиск возвращает на первую страницу', async () => {
    listQuery.data = { items: [], total: 60, limit: 25, offset: 25 }
    const user = userEvent.setup()
    renderWithTopbar()

    await user.type(screen.getByPlaceholderText(/ФИО или телефон/), 'ким')

    await waitFor(() => {
      const last = useResidentsSpy.mock.calls[useResidentsSpy.mock.calls.length - 1]
      expect(last[2]).toEqual({ limit: 25, offset: 0 })
    })
  })
})
