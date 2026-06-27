import { describe, it, expect } from 'vitest'
import { screen, fireEvent, within } from '@testing-library/react'
import { render } from '@/test/test-utils'
import AccessPhotos from './AccessPhotos'

// Фото проезда: два подписанных блока (обзор авто + номер). Синтетические URI.

const OVERVIEW = 'data:image/svg+xml,<svg/>overview'
const PLATE = 'data:image/svg+xml,<svg/>plate'

describe('AccessPhotos', () => {
  it('рендерит оба фото при наличии url', () => {
    render(<AccessPhotos overviewUrl={OVERVIEW} plateUrl={PLATE} />)
    const vehicle = screen.getByRole('img', { name: 'Фото автомобиля' })
    const plate = screen.getByRole('img', { name: 'Фото номера' })
    expect(vehicle).toHaveAttribute('src', OVERVIEW)
    expect(plate).toHaveAttribute('src', PLATE)
    expect(vehicle).toHaveAttribute('loading', 'lazy')
  })

  it('показывает «Нет фото» когда url пуст/null', () => {
    render(<AccessPhotos overviewUrl={null} plateUrl="" />)
    expect(screen.queryByRole('img', { name: 'Фото автомобиля' })).not.toBeInTheDocument()
    expect(screen.getAllByText('Нет фото')).toHaveLength(2)
  })

  it('клик по фото открывает lightbox с увеличенной картинкой', () => {
    render(<AccessPhotos overviewUrl={OVERVIEW} plateUrl={PLATE} />)
    fireEvent.click(screen.getByRole('img', { name: 'Фото автомобиля' }))
    const dialog = screen.getByRole('dialog')
    const big = within(dialog).getByRole('img', { name: 'Увеличить фото' })
    expect(big).toHaveAttribute('src', OVERVIEW)
  })
})
