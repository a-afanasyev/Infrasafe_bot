import { describe, it, expect, beforeEach, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import { waitFor } from '@testing-library/react'
import { render, screen } from '../../test/test-utils'
import TopbarSearch from './TopbarSearch'

// Поле поиска, живущее в топбаре, обязано быть НЕконтролируемым.
//
// Дефект (`docs/bugs-2026-07-28.md`, BUG-2, найден в проде на profk): страница
// отдаёт узел поля не напрямую, а через состояние контекста `useTopbar`,
// которое обновляется в useEffect — то есть ВТОРЫМ коммитом. У контролируемого
// поля React в фазе обработки события сверяет DOM-значение с последним
// отрендеренным `value` (всё ещё старым) и откатывает DOM: «админ» → «амн», а
// при медленном вводе не остаётся ничего.
//
// ⚠ Честная граница: САМУ потерю символов jsdom не воспроизводит — `act()`
// схлопывает оба коммита в один. Реальные guard'ы здесь — отсутствие prop
// `value` на элементе (структурный признак неконтролируемости) и debounce,
// который на старой реализации падает, потому что та звала колбэк на каждое
// нажатие. Отсутствие потери символов проверяется вручную в браузере.

const onSearch = vi.fn()

beforeEach(() => {
  onSearch.mockClear()
  vi.useRealTimers()
})

describe('TopbarSearch', () => {
  it('поле неконтролируемое: React не владеет его значением', () => {
    render(<TopbarSearch placeholder="Поиск" onSearch={onSearch} />)
    const input = screen.getByPlaceholderText('Поиск') as HTMLInputElement

    // Контролируемому полю React проставляет проп `value`; здесь его быть не
    // должно — именно он и откатывал ввод.
    const props = Object.keys(input).find(k => k.startsWith('__reactProps$'))
    const reactProps = props
      ? (input as unknown as Record<string, { value?: unknown }>)[props]
      : undefined
    expect(reactProps?.value).toBeUndefined()
  })

  it('принимает ввод целиком', async () => {
    const user = userEvent.setup()
    render(<TopbarSearch placeholder="Поиск" onSearch={onSearch} />)
    const input = screen.getByPlaceholderText('Поиск') as HTMLInputElement

    await user.type(input, 'админ')
    expect(input.value).toBe('админ')
  })

  it('зовёт onSearch один раз после паузы, а не на каждое нажатие', async () => {
    const user = userEvent.setup()
    render(<TopbarSearch placeholder="Поиск" onSearch={onSearch} />)

    await user.type(screen.getByPlaceholderText('Поиск'), 'админ')
    expect(onSearch).not.toHaveBeenCalled()

    await waitFor(() => expect(onSearch).toHaveBeenCalledTimes(1))
    expect(onSearch).toHaveBeenCalledWith('админ')
  })

  it('очистка поля отдаёт пустую строку', async () => {
    const user = userEvent.setup()
    render(<TopbarSearch placeholder="Поиск" onSearch={onSearch} />)
    const input = screen.getByPlaceholderText('Поиск')

    await user.type(input, 'ким')
    await waitFor(() => expect(onSearch).toHaveBeenCalledWith('ким'))

    await user.clear(input)
    await waitFor(() => expect(onSearch).toHaveBeenLastCalledWith(''))
  })

  it('таймер снимается при размонтировании', async () => {
    const user = userEvent.setup()
    const { unmount } = render(<TopbarSearch placeholder="Поиск" onSearch={onSearch} />)

    await user.type(screen.getByPlaceholderText('Поиск'), 'ким')
    unmount()

    // Колбэк не должен выстрелить в размонтированный компонент.
    await new Promise(r => setTimeout(r, 400))
    expect(onSearch).not.toHaveBeenCalled()
  })
})
