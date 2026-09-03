import { describe, it, expect } from 'vitest'
import { renderHook } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from '../test/msw/server'
import { useRegistration } from './useRegistration'

// Спека 2026-09-03 §5.2: клиент регистрации — «голый» axios с Bearer-тикетом;
// каскад двор → дом → квартира и статус контакта; submit без phone.

function hook() {
  return renderHook(() => useRegistration()).result.current
}

describe('useRegistration cascade + contact client', () => {
  it('yards/buildings/apartments/contactStatus идут под тикетом', async () => {
    const seen: Record<string, string | null> = {}
    server.use(
      http.get('*/api/v2/registration/yards', ({ request }) => {
        seen.yards = request.headers.get('authorization')
        return HttpResponse.json([{ id: 1, name: 'Двор' }])
      }),
      http.get('*/api/v2/registration/yards/1/buildings', ({ request }) => {
        seen.buildings = request.headers.get('authorization')
        return HttpResponse.json([{ id: 5, address: 'Дом 1' }])
      }),
      http.get('*/api/v2/registration/buildings/5/apartments', ({ request }) => {
        seen.apartments = request.headers.get('authorization')
        return HttpResponse.json([{ id: 9, apartment_number: '12', floor: 2, entrance: 1 }])
      }),
      http.get('*/api/v2/registration/contact-status', ({ request }) => {
        seen.contact = request.headers.get('authorization')
        return HttpResponse.json({ phone: '+998901234567' })
      }),
    )
    const reg = hook()
    expect(await reg.yards('t1')).toEqual([{ id: 1, name: 'Двор' }])
    expect(await reg.buildings('t1', 1)).toEqual([{ id: 5, address: 'Дом 1' }])
    expect((await reg.apartments('t1', 5))[0].apartment_number).toBe('12')
    expect(await reg.contactStatus('t1')).toEqual({ phone: '+998901234567' })
    expect(Object.values(seen)).toEqual(Array(4).fill('Bearer t1'))
  })

  it('submit шлёт только full_name и apartment_id', async () => {
    let body: unknown = null
    server.use(
      http.post('*/api/v2/registration/applicant', async ({ request }) => {
        body = await request.json()
        return HttpResponse.json({ status: 'pending' })
      }),
    )
    const reg = hook()
    await reg.submit('t1', { full_name: 'Иван Иванов', apartment_id: 9 })
    expect(body).toEqual({ full_name: 'Иван Иванов', apartment_id: 9 })
  })
})
