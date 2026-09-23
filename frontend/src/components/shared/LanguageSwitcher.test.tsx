import { describe, it, expect, afterEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import i18n from '../../i18n'
import LanguageSwitcher from './LanguageSwitcher'

describe('LanguageSwitcher — A9-P2-31', () => {
  afterEach(async () => {
    await i18n.changeLanguage('ru')
  })

  it('при браузерном ru-RU первый клик переключает на uz', async () => {
    await i18n.changeLanguage('ru-RU')
    render(<LanguageSwitcher />)
    fireEvent.click(screen.getByRole('button'))
    expect(i18n.resolvedLanguage).toBe('uz')
  })
})
