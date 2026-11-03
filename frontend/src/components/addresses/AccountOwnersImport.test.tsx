import { describe, it, expect, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import { render, screen, waitFor } from '../../test/test-utils'
import AccountOwnersImport from './AccountOwnersImport'
import { apiClient } from '../../api/client'

describe('AccountOwnersImport', () => {
  it('отправляет выбранный CSV как multipart-поле file', async () => {
    vi.spyOn(apiClient, 'get').mockResolvedValue({ data: { total: 0, linked: 0, imported_at: null } })
    const post = vi.spyOn(apiClient, 'post').mockResolvedValue({ data: { total: 2, skipped: 0, linked: 1 } })

    render(<AccountOwnersImport />)
    expect(await screen.findByText(/не загружены/)).toBeInTheDocument()

    const file = new File(['Лицевой счёт;ФИО\n1;Ali Valiyev\n'], 'owners.csv', { type: 'text/csv' })
    await userEvent.upload(screen.getByTestId('account-owners-file'), file)

    await waitFor(() => expect(post).toHaveBeenCalledOnce())
    const [url, body] = post.mock.calls[0]
    expect(url).toBe('/api/v2/addresses/account-owners/import')
    expect((body as FormData).get('file')).toBe(file)
  })
})
