import { useMemo } from 'react'
import { useQueries } from '@tanstack/react-query'
import { apiClient } from '@/api/client'
import type { BalanceSnapshot } from '../types/paymentControl'

/** Потолок счетов в одном запросе — тот же, что у сервиса. */
const CHUNK = 200
const URL = '/api/v2/payment-control/accounts/balances'

export type BalancesState = 'off' | 'idle' | 'loading' | 'error' | 'ready'

export interface ApartmentBalances {
  /** Снимок по лицевому счёту. Отсутствие ключа = данных нет, НЕ ноль. */
  map: Record<string, BalanceSnapshot>
  state: BalancesState
  /** Самая свежая дата отчёта среди полученных снимков. */
  asOf: string | null
  source: string | null
  /** У части счетов дата отчёта отличается от `asOf`. */
  mixedDates: boolean
}

const EMPTY: ApartmentBalances = { map: {}, state: 'off', asOf: null, source: null, mixedDates: false }

export function paymentsEnabled(): boolean {
  return import.meta.env.VITE_PAYMENTS_ENABLED === 'true'
}

/**
 * Текущие балансы сразу по списку лицевых счетов — для таблиц, где строк
 * больше одной. По одиночной ручке `/apartments/{id}` дом на 140 квартир
 * стоил бы 140 запросов.
 *
 * Ключ запроса строится из ОТСОРТИРОВАННЫХ счетов, поэтому переупорядочивание
 * строк таблицы не роняет кэш.
 */
export function useApartmentBalances(accounts: (string | null | undefined)[]): ApartmentBalances {
  const enabled = paymentsEnabled()

  const chunks = useMemo(() => {
    if (!enabled) return []
    const unique = Array.from(new Set(accounts.filter((a): a is string => !!a && a.trim() !== '').map(a => a.trim())))
    unique.sort()
    const result: string[][] = []
    for (let i = 0; i < unique.length; i += CHUNK) result.push(unique.slice(i, i + CHUNK))
    return result
  }, [enabled, accounts])

  const queries = useQueries({
    queries: chunks.map(chunk => ({
      queryKey: ['apartment-balances', chunk],
      queryFn: async () => {
        const { data } = await apiClient.post(URL, { account_numbers: chunk })
        return (data?.balances ?? {}) as Record<string, BalanceSnapshot>
      },
      staleTime: 60_000,
      retry: false,
    })),
  })

  return useMemo(() => {
    if (!enabled) return EMPTY
    if (chunks.length === 0) return { ...EMPTY, state: 'idle' as BalancesState }
    if (queries.some(q => q.isError)) return { ...EMPTY, state: 'error' as BalancesState }
    if (queries.some(q => q.isPending)) return { ...EMPTY, state: 'loading' as BalancesState }

    const map: Record<string, BalanceSnapshot> = {}
    for (const query of queries) Object.assign(map, query.data ?? {})

    const dates = new Set<string>()
    let asOf: string | null = null
    let source: string | null = null
    for (const snapshot of Object.values(map)) {
      dates.add(snapshot.as_of)
      // Даты — `YYYY-MM-DD`, поэтому лексикографическое сравнение и есть
      // хронологическое; парсить в Date незачем.
      if (asOf === null || snapshot.as_of > asOf) {
        asOf = snapshot.as_of
        source = snapshot.source
      }
    }
    return { map, state: 'ready' as BalancesState, asOf, source, mixedDates: dates.size > 1 }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, chunks, queries.map(q => `${q.status}:${q.dataUpdatedAt}`).join('|')])
}
