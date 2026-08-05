import { useQuery } from '@tanstack/react-query'

import { publicClient } from '../api/publicClient'
import { setDisplayTz } from '../utils/timezone'
import { DisplayTzContext, resolveDisplayTz } from './displayTz'

// ARCH-137 B6: зона показа развёртывания резолвится ДО того, как что-либо
// форматирующее время получит шанс отрисоваться. Провайдер гейтит детей до
// первого settle одного публичного запроса board-config и прибивает зону на
// сессию — поздний refetch, мутирующий module-level зону, не перерисовал бы
// уже смонтированных потребителей, поэтому его сознательно нет
// (staleTime: Infinity, без refetch).

// У publicClient нет дефолтного таймаута; без явного зависший запрос
// заблокировал бы за гейтом весь UI, включая логин и TWA.
const FETCH_TIMEOUT_MS = 4_000

interface DisplayTzProviderProps {
  children: React.ReactNode
  /** Рендерится, пока летит первый запрос (не дольше FETCH_TIMEOUT_MS). */
  fallback?: React.ReactNode
}

export function DisplayTzProvider({ children, fallback = null }: DisplayTzProviderProps) {
  // Ключ НАМЕРЕННО не ['board-config'] (useBoardConfig), хотя эндпоинт тот же
  // и это стоит одного лишнего GET за сессию на страницах витрины: общий ключ
  // означал бы, что 60-секундный observer useBoardConfig (и invalidate после
  // сохранения редактора) обновляет кэш-запись → провайдер ре-рендерится на
  // каждое обновление (лишний ре-рендер всего поддерева) и увидел бы «поздний
  // refetch», который этому провайдеру запрещён by design (см. шапку файла).
  const { data, isPending } = useQuery({
    queryKey: ['display-tz'],
    queryFn: () =>
      publicClient
        .get('/api/v2/public/board-config', { timeout: FETCH_TIMEOUT_MS })
        .then((r) => r.data as unknown),
    staleTime: Infinity,
    gcTime: Infinity,
    retry: false,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  })

  // Ошибка и таймаут тоже settle'ят запрос (retry: false), так что гейт держит
  // не дольше одной попытки и деградирует в дефолтную зону.
  if (isPending) return <>{fallback}</>

  const tz = resolveDisplayTz(data)
  // Установка в render-фазе намеренна: module-переменная должна быть финальной
  // до того, как render-функции детей её прочитают; значение — чистая функция
  // от settled-данных запроса, повторный рендер идемпотентен.
  setDisplayTz(tz)
  return <DisplayTzContext.Provider value={tz}>{children}</DisplayTzContext.Provider>
}
