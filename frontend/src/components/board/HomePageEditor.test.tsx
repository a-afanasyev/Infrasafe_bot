import { describe, it, expect, afterEach, vi } from 'vitest'
import { fireEvent, render, screen, within } from '../../test/test-utils'
import { defaultHomeConfig } from '../../types/boardConfig'
import type { HomeCfg } from '../../types/boardConfig'
import HomePageEditor from './HomePageEditor'

afterEach(() => vi.unstubAllEnvs())

function renderEditor(home: HomeCfg = defaultHomeConfig) {
  const onChange = vi.fn()
  render(<HomePageEditor home={home} onChange={onChange} />)
  return onChange
}

function ruInput(container: HTMLElement, label: string): HTMLInputElement {
  return within(within(container).getByText(label).parentElement as HTMLElement).getByPlaceholderText('RU') as HTMLInputElement
}

describe('HomePageEditor', () => {
  it('название комплекса уходит новым объектом, исходный не мутирует', () => {
    const onChange = renderEditor()
    fireEvent.change(ruInput(document.body, 'Название жилого комплекса (в шапке)'), { target: { value: 'ЖК Olmazor' } })
    const [next] = onChange.mock.calls[0]
    expect(next.complex_name).toEqual({ ru: 'ЖК Olmazor', uz: '' })
    expect(defaultHomeConfig.complex_name.ru).toBe('')
  })

  it('блок: скрыть и задать свой заголовок', () => {
    const onChange = renderEditor()
    const works = screen.getByTestId('home-block-works')
    fireEvent.click(within(works).getByRole('checkbox'))
    expect(onChange.mock.calls[0][0].blocks.find((b: { id: string }) => b.id === 'works').visible).toBe(false)

    fireEvent.change(ruInput(works, 'Свой заголовок'), { target: { value: 'План работ' } })
    expect(onChange.mock.calls[1][0].blocks.find((b: { id: string }) => b.id === 'works').title.ru).toBe('План работ')
  })

  it('у блоков с живыми данными — откуда данные и ссылка, где ими управлять', () => {
    vi.stubEnv('VITE_ELEVATORS_ENABLED', 'true')
    vi.stubEnv('VITE_WORK_REPORTS_ENABLED', 'true')
    renderEditor()
    const requests = screen.getByTestId('home-block-requests')
    expect(within(requests).getByText(/Считается автоматически по всем заявкам комплекса/)).toBeInTheDocument()
    expect(within(requests).getByRole('link', { name: /Заявки/ })).toHaveAttribute('href', '/dashboard')
    expect(within(screen.getByTestId('home-block-elevators')).getByRole('link', { name: /Лифты/ }))
      .toHaveAttribute('href', '/dashboard/elevators')
    expect(within(screen.getByTestId('home-block-workreports')).getByRole('link', { name: /Отчёты о работах/ }))
      .toHaveAttribute('href', '/dashboard/work-reports')
  })

  it('модуль выключен — блок виден, но не настраивается', () => {
    vi.stubEnv('VITE_ELEVATORS_ENABLED', '')
    renderEditor()
    const elevators = screen.getByTestId('home-block-elevators')
    expect(within(elevators).getByRole('checkbox')).toBeDisabled()
    expect(within(elevators).getByText('Модуль выключен на этой площадке')).toBeInTheDocument()
    expect(within(elevators).queryByPlaceholderText('RU')).not.toBeInTheDocument()
  })
})
