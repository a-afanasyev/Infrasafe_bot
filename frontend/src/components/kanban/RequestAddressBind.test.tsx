import { describe, it, expect } from 'vitest'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { render, screen, waitFor } from '../../test/test-utils'
import { server } from '../../test/msw/server'
import RequestAddressBind from './RequestAddressBind'

// Заявка с адресом-текстом не уходит в работу (2026-11-07): менеджер
// привязывает двор/дом/квартиру из справочника прямо из карточки.

describe('RequestAddressBind', () => {
  it('предупреждает и отправляет выбранный уровень адреса', async () => {
    let body: unknown = null
    server.use(
      http.get('*/api/v2/addresses/yards', () =>
        HttpResponse.json([{ id: 3, name: 'Olmazor City Phase 3', is_active: true }])),
      http.patch('*/api/v2/requests/261107-013/address', async ({ request }) => {
        body = await request.json()
        return HttpResponse.json({ request_number: '261107-013', address_type: 'yard' })
      }),
    )
    const user = userEvent.setup()
    render(<RequestAddressBind requestNumber="261107-013" />)

    expect(screen.getByText(/нельзя взять в работу/)).toBeInTheDocument()
    const submit = screen.getByRole('button', { name: 'Привязать адрес' })
    expect(submit).toBeDisabled()
    await screen.findByRole('option', { name: 'Olmazor City Phase 3' })
    await user.selectOptions(screen.getByLabelText('Двор *'), '3')
    await user.click(submit)
    await waitFor(() => expect(body).toEqual({ yard_id: 3 }))
  })
})
