import { describe, it, expect } from 'vitest'
import { residentTone } from './residentTone'

const base = {
  status: 'approved',
  phone: '+998901234567',
  apartments_count: 1,
  verification_status: 'verified',
  documents_submitted: false,
  bot_blocked: false,
}

describe('residentTone', () => {
  it.each([
    ['одобрен — без цвета', {}, 'default'],
    ['ожидает — жёлтый', { status: 'pending', verification_status: 'pending' }, 'pending'],
    ['прислал документы — синий', { status: 'pending', verification_status: 'requested', documents_submitted: true }, 'submitted'],
    ['документы запрошены, но не присланы — жёлтый', { status: 'pending', verification_status: 'requested' }, 'pending'],
    ['не завершил регистрацию — красный контур', { status: 'pending', phone: null, apartments_count: 0 }, 'incomplete'],
    ['заблокировал бота — красный', { bot_blocked: true }, 'botBlocked'],
    ['заблокировал бота важнее незавершённой регистрации', { status: 'pending', phone: null, apartments_count: 0, bot_blocked: true }, 'botBlocked'],
  ] as const)('%s', (_name, patch, expected) => {
    expect(residentTone({ ...base, ...patch })).toBe(expected)
  })
})
