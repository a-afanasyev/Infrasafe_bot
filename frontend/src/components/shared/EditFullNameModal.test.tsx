import { describe, it, expect, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import { render, screen } from '../../test/test-utils'
import EditFullNameModal from './EditFullNameModal'
import { MAX_FULL_NAME_LEN, validateFullName } from '@/utils/personName'

function setup(over: Partial<React.ComponentProps<typeof EditFullNameModal>> = {}) {
  const onSubmit = vi.fn()
  const onClose = vi.fn()
  render(
    <EditFullNameModal
      currentName="Иван Иванов"
      isPending={false}
      onSubmit={onSubmit}
      onClose={onClose}
      {...over}
    />,
  )
  return { onSubmit, onClose }
}

describe('EditFullNameModal', () => {
  it('шлёт ФИО одной строкой, схлопнув пробелы', async () => {
    const user = userEvent.setup()
    const { onSubmit } = setup()
    const field = screen.getByLabelText('ФИО')
    await user.clear(field)
    await user.type(field, 'Петров   Пётр  Петрович')
    await user.click(screen.getByRole('button', { name: 'Сохранить' }))
    expect(onSubmit).toHaveBeenCalledWith('Петров Пётр Петрович')
  })

  it('Enter сохраняет так же, как кнопка', async () => {
    const user = userEvent.setup()
    const { onSubmit } = setup()
    const field = screen.getByLabelText('ФИО')
    await user.clear(field)
    await user.type(field, 'Петров Пётр{Enter}')
    expect(onSubmit).toHaveBeenCalledWith('Петров Пётр')
  })

  it('пустое ФИО не уходит на сервер и объясняется на месте', async () => {
    const user = userEvent.setup()
    const { onSubmit } = setup()
    await user.clear(screen.getByLabelText('ФИО'))
    await user.click(screen.getByRole('button', { name: 'Сохранить' }))
    expect(onSubmit).not.toHaveBeenCalled()
    expect(screen.getByRole('alert')).toHaveTextContent('ФИО не может быть пустым')
  })

  it('ФИО без букв отклоняется', async () => {
    const user = userEvent.setup()
    const { onSubmit } = setup()
    const field = screen.getByLabelText('ФИО')
    await user.clear(field)
    await user.type(field, '12345')
    await user.click(screen.getByRole('button', { name: 'Сохранить' }))
    expect(onSubmit).not.toHaveBeenCalled()
    expect(screen.getByRole('alert')).toHaveTextContent('хотя бы одну букву')
  })

  it('неизменённое ФИО не шлётся', async () => {
    const user = userEvent.setup()
    const { onSubmit } = setup()
    await user.click(screen.getByRole('button', { name: 'Сохранить' }))
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('во время сохранения обе кнопки заблокированы', () => {
    setup({ isPending: true, currentName: 'Старое Имя' })
    expect(screen.getByRole('button', { name: /Сохранение/ })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Отмена' })).toBeDisabled()
  })

  it('«Отмена» закрывает без запроса', async () => {
    const user = userEvent.setup()
    const { onSubmit, onClose } = setup()
    await user.click(screen.getByRole('button', { name: 'Отмена' }))
    expect(onClose).toHaveBeenCalled()
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('поле физически не даёт превысить лимит бэкенда', () => {
    setup()
    expect(screen.getByLabelText('ФИО')).toHaveAttribute('maxlength', String(MAX_FULL_NAME_LEN))
  })
})

describe('validateFullName', () => {
  it.each([
    ['', 'empty'],
    ['   ', 'empty'],
    ['12345', 'noLetters'],
    ['-- ---', 'noLetters'],
    ['Я'.repeat(MAX_FULL_NAME_LEN + 1), 'tooLong'],
  ])('%s → %s', (value, code) => {
    expect(validateFullName(value)).toBe(code)
  })

  it.each([
    'Иванов',
    'Иванов Иван Иванович',
    "O'Brien Patrick",
    'Toshmatov Alisher',   // узбекская латиница
    'Gʻaniyev Anvar',      // с диакритикой — тоже буквы
  ])('принимает %s', value => {
    expect(validateFullName(value)).toBeNull()
  })
})
