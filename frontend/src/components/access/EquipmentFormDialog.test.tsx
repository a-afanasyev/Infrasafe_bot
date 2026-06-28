import { describe, it, expect, vi } from 'vitest'
import { screen, fireEvent } from '@testing-library/react'
import { render } from '@/test/test-utils'
import EquipmentFormDialog, { type FormField } from './EquipmentFormDialog'

// JSON-редакторы attributes (камеры) / config (шлагбаумы): валидный JSON → объект
// в payload; невалидный → ошибка под полем + submit заблокирован; пустое → не шлём;
// при редактировании — префилл pretty-JSON.

const fields: FormField[] = [
  { name: 'code', type: 'text', label: 'Код', required: true },
  { name: 'attributes', type: 'json', label: 'Атрибуты (JSON)' },
]

function renderDialog(onSubmit = vi.fn(), initial: Record<string, unknown> | null = null) {
  render(
    <EquipmentFormDialog
      open
      title="Камера"
      fields={fields}
      initial={initial}
      onClose={() => {}}
      onSubmit={onSubmit}
    />,
  )
  return onSubmit
}

describe('EquipmentFormDialog — JSON-поле', () => {
  it('валидный JSON парсится в объект и уходит в payload', () => {
    const onSubmit = renderDialog()
    fireEvent.change(screen.getByLabelText('Код'), { target: { value: 'CAM-1' } })
    fireEvent.change(screen.getByLabelText('Атрибуты (JSON)'), {
      target: { value: '{ "fps": 25 }' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Добавить' }))

    expect(onSubmit).toHaveBeenCalledTimes(1)
    expect(onSubmit.mock.calls[0][0]).toEqual({ code: 'CAM-1', attributes: { fps: 25 } })
  })

  it('пустой JSON → поле не отправляется', () => {
    const onSubmit = renderDialog()
    fireEvent.change(screen.getByLabelText('Код'), { target: { value: 'CAM-2' } })
    fireEvent.click(screen.getByRole('button', { name: 'Добавить' }))

    expect(onSubmit).toHaveBeenCalledTimes(1)
    expect(onSubmit.mock.calls[0][0]).toEqual({ code: 'CAM-2' })
  })

  it('невалидный JSON блокирует submit и показывает ошибку', () => {
    const onSubmit = renderDialog()
    fireEvent.change(screen.getByLabelText('Код'), { target: { value: 'CAM-3' } })
    fireEvent.change(screen.getByLabelText('Атрибуты (JSON)'), {
      target: { value: '{ not json' },
    })

    expect(screen.getByText('Невалидный JSON')).toBeInTheDocument()
    const btn = screen.getByRole('button', { name: 'Добавить' }) as HTMLButtonElement
    expect(btn.disabled).toBe(true)
    fireEvent.click(btn)
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('JSON-массив/примитив тоже считается невалидным (нужен объект)', () => {
    const onSubmit = renderDialog()
    fireEvent.change(screen.getByLabelText('Код'), { target: { value: 'CAM-4' } })
    fireEvent.change(screen.getByLabelText('Атрибуты (JSON)'), {
      target: { value: '[1, 2, 3]' },
    })
    expect(screen.getByText('Невалидный JSON')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Добавить' }))
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('режим редактирования префилит pretty-JSON', () => {
    renderDialog(vi.fn(), { id: 1, code: 'CAM-5', attributes: { fps: 30, hd: true } })
    const ta = screen.getByLabelText('Атрибуты (JSON)') as HTMLTextAreaElement
    expect(ta.value).toBe(JSON.stringify({ fps: 30, hd: true }, null, 2))
  })
})
