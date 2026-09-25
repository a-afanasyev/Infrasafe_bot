import { describe, it, expect, beforeAll } from 'vitest'
import i18n from '../../i18n'
import { getErrorMessage } from './errors'

const httpError = (status: number, detail?: unknown) => ({
  isAxiosError: true,
  response: { status, data: detail === undefined ? {} : { detail } },
})

describe('TWA getErrorMessage — сырой detail бэкенда пользователю не показываем', () => {
  beforeAll(async () => {
    await i18n.changeLanguage('ru')
  })

  it('английский detail (строка/422-список/{code,message}) → локализованный fallback вызывающего', () => {
    expect(getErrorMessage(httpError(422, 'Transition not allowed'), 'Не удалось изменить статус'))
      .toBe('Не удалось изменить статус')
    expect(getErrorMessage(httpError(422, [{ loc: ['body', 'description'], msg: 'too short' }]), 'Ошибка'))
      .toBe('Ошибка')
    expect(getErrorMessage(httpError(409, { code: 'x', message: 'Conflict' }), 'Ошибка'))
      .toBe('Ошибка')
  })

  it('без fallback — общий локализованный текст', () => {
    expect(getErrorMessage(httpError(400, 'Bad request'))).toBe('Произошла ошибка')
  })

  it('текст по статусу: сеть/408, 403, 413, 429, 5xx', () => {
    expect(getErrorMessage({ isAxiosError: true, message: 'Network Error' }, 'fb'))
      .toBe('Нет связи с сервером. Проверьте интернет и повторите')
    // не-HTTP исключение (баг в коде) — не «нет сети», а fallback
    expect(getErrorMessage(new Error('boom'), 'fb')).toBe('fb')
    expect(getErrorMessage(httpError(408), 'fb')).toBe('Нет связи с сервером. Проверьте интернет и повторите')
    expect(getErrorMessage(httpError(403, 'Forbidden'), 'fb')).toBe('Недостаточно прав для этого действия')
    expect(getErrorMessage(httpError(413), 'fb')).toBe('Файл слишком большой')
    expect(getErrorMessage(httpError(429), 'fb')).toBe('Слишком много запросов. Подождите немного и повторите')
    expect(getErrorMessage(httpError(502, 'Bad Gateway'), 'fb')).toBe('Сервер временно недоступен. Повторите позже')
  })

  it('uz: локализованный текст, не английский detail', async () => {
    await i18n.changeLanguage('uz')
    expect(getErrorMessage(httpError(500, 'Internal Server Error'))).not.toMatch(/Internal|[А-Яа-яЁё]/)
    await i18n.changeLanguage('ru')
  })
})
