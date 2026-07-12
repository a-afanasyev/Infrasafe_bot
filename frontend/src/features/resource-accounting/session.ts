import { api } from './api/client';

/**
 * Тихий вход в resource без iframe: mint (backend хоста) → exchange (resource-API) → cookie.
 * Хост вызывает ensureResourceSession(mint) при входе в раздел и в onUnauthorized.
 * Ticket/nonce НЕ кладём в URL/localStorage — только в теле POST.
 */

/** Обменять одноразовый launch-ticket на resource-сессию (httpOnly cookie). */
export async function exchangeTicket(ticket: string): Promise<void> {
  await api('/v1/auth/session/exchange', { method: 'POST', body: { ticket } });
}

/**
 * Гарантировать активную resource-сессию.
 * mint — функция хоста, дергающая его backend (напр. POST /api/v2/resource-accounting/ticket),
 * которая возвращает свежий ticket. При наличии сессии — no-op; иначе mint→exchange.
 */
export async function ensureResourceSession(mint: () => Promise<string>): Promise<void> {
  try {
    await api('/v1/auth/me');
    return; // сессия уже есть
  } catch {
    // нет сессии / 401 → выпускаем и обмениваем свежий ticket
  }
  const ticket = await mint();
  await exchangeTicket(ticket);
}
