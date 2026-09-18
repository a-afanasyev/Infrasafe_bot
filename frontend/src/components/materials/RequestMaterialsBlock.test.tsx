import { describe, it, expect, beforeEach } from 'vitest'
import { http, HttpResponse } from 'msw'
import { render, screen } from '../../test/test-utils'
import { server } from '../../test/msw/server'
import { useAuthStore } from '../../stores/authStore'
import type { RequestMaterialsOut } from '../../types/materials'
import RequestMaterialsBlock from './RequestMaterialsBlock'

// TEST-068 (порция materials): блок «Материалы» в карточке заявки —
// только для ролей модуля, только при наличии списаний.

const DATA: RequestMaterialsOut = {
  request_number: '260918-001',
  total_cost: '5250.00',
  items: [
    { id: 1, material_id: 1, doc_type: 'request', qty: '10.500', total_cost: '5250.00', request_number: '260918-001',
      reason: null, material_name: 'Лампа', unit: 'pcs', created_by: 1, created_at: null },
    { id: 2, material_id: 2, doc_type: 'request', qty: '3', total_cost: '900.00', request_number: '260918-001',
      reason: null, material_name: 'Кабель', unit: 'm', created_by: 1, created_at: null, is_reversed: true },
  ],
}

function setRoles(roles: string[]) {
  useAuthStore.setState({ user: { id: 1, roles }, isAuthenticated: true, hydrating: false })
}

beforeEach(() => setRoles(['manager']))

describe('RequestMaterialsBlock', () => {
  it('исполнитель без роли модуля: ничего не рендерит и не ходит в API', () => {
    setRoles(['executor'])
    // Без handler'а: onUnhandledRequest="error" уронил бы тест при запросе.
    const { container } = render(<RequestMaterialsBlock requestNumber="260918-001" />)
    expect(container).toBeEmptyDOMElement()
  })

  it('менеджер: строки со списаниями, сторнированное зачёркнуто, итог себестоимости', async () => {
    server.use(http.get('*/api/v2/materials/by-request/:number', ({ params }) => {
      expect(params.number).toBe('260918-001')
      return HttpResponse.json(DATA)
    }))
    render(<RequestMaterialsBlock requestNumber="260918-001" />)

    expect(await screen.findByText('Материалы')).toBeInTheDocument()
    expect(screen.getByText(/Лампа — 10,5 шт/)).toBeInTheDocument()
    const reversed = screen.getByText(/Кабель — 3 м/).closest('li')
    expect(reversed).toHaveClass('line-through')
    expect(screen.getByText('(сторнировано)')).toBeInTheDocument()
    expect(screen.getByText(/Итого себестоимость: 5\s?250,00/)).toBeInTheDocument()
  })

  it('без списаний блок отсутствует', async () => {
    server.use(http.get('*/api/v2/materials/by-request/:number', () =>
      HttpResponse.json({ ...DATA, items: [], total_cost: '0.00' })))
    const { container } = render(<RequestMaterialsBlock requestNumber="260918-001" />)
    await new Promise((r) => setTimeout(r, 50))
    expect(container).toBeEmptyDOMElement()
  })
})
