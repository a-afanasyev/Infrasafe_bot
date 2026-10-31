import { describe, it, expect, vi } from 'vitest'
import { render, screen, within } from '../../test/test-utils'
import RequestMedia from './RequestMedia'

// Карточка заявки дашборда: фото «до работ» исполнителя — своя группа, не среди
// фото жителя и не во фотоотчёте.

vi.mock('../../hooks/useCan', () => ({ useCan: () => false }))
vi.mock('../../hooks/useRequestMediaUpload', () => ({
  useRequestMediaUpload: () => ({ mutate: vi.fn(), isPending: false }),
}))
vi.mock('../../hooks/useRequestMedia', () => ({
  useMediaBlob: () => ({ data: undefined, isError: false }),
  useRequestMediaList: () => ({
    data: [
      { id: 1, file_type: 'photo', category: 'request_photo' },
      { id: 2, file_type: 'photo', category: 'before_photo' },
      { id: 3, file_type: 'photo', category: 'before_photo' },
      { id: 4, file_type: 'photo', category: 'completion_photo' },
    ],
    isError: false,
  }),
}))

describe('RequestMedia — фото «до работ»', () => {
  it('отдельная группа «До работ» с двумя фото', () => {
    render(<RequestMedia requestNumber="260930-001" />)
    const group = screen.getByTestId('before-photos')
    expect(within(group).getByText('До работ')).toBeInTheDocument()
    expect(within(group).getAllByRole('button')).toHaveLength(2)
    // фото жителя (1) + «до» (2) + фотоотчёт (1) = 4 превью, «до» не задвоены
    expect(screen.getAllByRole('button')).toHaveLength(4)
  })
})
