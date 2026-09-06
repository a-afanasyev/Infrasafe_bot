import { useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { twaClient } from '../twaClient'
import { useApiLang } from '../../utils/apiLang'
import { ElevatorStatusDot } from '../../components/elevators/ElevatorStatusBadge'
import { elevatorsForBuildingPath, type ElevatorMiniOut, type ElevatorStatus } from '../../types/elevators'
import { EMPTY_ELEVATOR_SELECTION, isElevatorSelectionComplete, type ElevatorSelection } from './elevatorSelection'
import ElevatorBlockedNotice from './ElevatorBlockedNotice'

/**
 * Шаг «Лифт» мастера создания заявки (категория elevator, флаг включён):
 * список лифтов дома → выбор → «Лифт сейчас работает?» Да/Нет. Автовыбор при
 * единственном лифте в доме (подъезд квартиры API не отдаёт). Без лифтов в
 * доме заявку по лифту создать нельзя (Р11) — только назад к категории.
 * Значение/дефолт/resolveBuildingId — `elevatorSelection.ts`.
 *
 * Р18/Р18a: лифт «В ремонте»/«На ТО» в списке ВИДЕН (житель должен понимать,
 * что происходит). Запрещать ли по нему заявку, решает СЕРВЕР — вердикт
 * приходит полем `resident_request_blocked` (статус × тумблер менеджера
 * `allow_resident_requests_under_works`), клиент про конфиг не знает. Запрет
 * включён → блокирующий блок вместо вопроса «работает?», «Далее» недоступно
 * (сервер держит тот же запрет сам, 409). Запрет выключен → прежняя мягкая
 * подсказка и обычный поток.
 */
const SOFT_HINT: Partial<Record<ElevatorStatus, string>> = {
  under_repair: 'twa.create.elevator.hintUnderRepair',
  maintenance: 'twa.create.elevator.hintMaintenance',
}

const CARD = 'w-full bg-white dark:bg-gray-800 border rounded-xl p-3 text-[13px] text-left active:scale-[0.97] transition-transform flex items-center gap-2'
const PRIMARY = 'w-full mt-3 bg-emerald-500 text-white py-3 rounded-xl font-medium disabled:opacity-40'
const SECONDARY = 'w-full mt-3 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 py-3 rounded-xl font-medium text-[13px]'

interface Props {
  buildingId: number | null
  value: ElevatorSelection
  onChange: (next: ElevatorSelection) => void
  onNext: () => void
  onBackToCategory: () => void
  onBackToAddress: () => void
}

export default function ElevatorStep({ buildingId, value, onChange, onNext, onBackToCategory, onBackToAddress }: Props) {
  const { t } = useTranslation()
  const lang = useApiLang()
  const query = useQuery<ElevatorMiniOut[]>({
    queryKey: ['twa', 'elevators-for-building', buildingId, lang],
    queryFn: () => twaClient.get(elevatorsForBuildingPath(buildingId as number), { params: { lang } }).then((r) => r.data),
    enabled: buildingId !== null,
  })
  const elevators = query.data ?? []

  const select = (el: ElevatorMiniOut) =>
    onChange({ ...value, elevatorId: el.id, elevatorLabel: el.label, elevatorStatus: el.current_status })

  const selected = elevators.find((e) => e.id === value.elevatorId)

  // Автовыбор единственного лифта; выбор из черновика, которого в доме больше
  // нет (сменили адрес между сессиями), сбрасываем.
  useEffect(() => {
    if (!query.isSuccess) return
    const stillValid = value.elevatorId !== null && elevators.some((e) => e.id === value.elevatorId)
    if (value.elevatorId !== null && !stillValid) {
      onChange({ ...value, ...EMPTY_ELEVATOR_SELECTION, operational: value.operational })
      return
    }
    if (value.elevatorId === null && elevators.length === 1) select(elevators[0])
    // eslint-disable-next-line react-hooks/exhaustive-deps -- реагируем на загрузку списка и выбор, не на identity колбэков
  }, [query.isSuccess, elevators, value.elevatorId])

  if (buildingId === null) {
    return (
      <div>
        <h2 className="font-semibold text-[15px] mb-3">{t('twa.create.elevator.title')}</h2>
        <div className="text-[13px] text-gray-500 dark:text-gray-400">{t('twa.create.elevator.needBuilding')}</div>
        <button onClick={onBackToAddress} className={SECONDARY}>{t('twa.create.elevator.backToAddress')}</button>
      </div>
    )
  }

  if (query.isLoading) {
    return <div className="text-[13px] text-gray-500 dark:text-gray-400">{t('common.loading')}</div>
  }
  if (query.isError) {
    return (
      <div>
        <h2 className="font-semibold text-[15px] mb-3">{t('twa.create.elevator.title')}</h2>
        <div className="text-[13px] text-red-600 dark:text-red-400">{t('twa.create.elevator.loadError')}</div>
        <button onClick={() => query.refetch()} className={PRIMARY}>{t('twa.create.elevator.retry')}</button>
        <button onClick={onBackToAddress} className={SECONDARY}>{t('twa.create.elevator.backToAddress')}</button>
      </div>
    )
  }
  if (elevators.length === 0) {
    return (
      <div>
        <h2 className="font-semibold text-[15px] mb-3">{t('twa.create.elevator.title')}</h2>
        <div className="text-[13px] text-gray-500 dark:text-gray-400">{t('twa.create.elevator.noElevators')}</div>
        <button onClick={onBackToCategory} className={SECONDARY}>{t('twa.create.elevator.backToCategory')}</button>
      </div>
    )
  }

  const blocked = selected?.resident_request_blocked === true
  const hintKey = !blocked && value.elevatorStatus ? SOFT_HINT[value.elevatorStatus] : undefined

  return (
    <div className="space-y-2">
      <h2 className="font-semibold text-[15px] mb-3">{t('twa.create.elevator.selectElevator')}</h2>
      {elevators.map((el) => (
        <button
          key={el.id}
          onClick={() => select(el)}
          aria-pressed={el.id === value.elevatorId}
          className={`${CARD} ${el.id === value.elevatorId ? 'border-emerald-500' : 'border-gray-200 dark:border-gray-700'}`}
        >
          <ElevatorStatusDot status={el.current_status} />
          <span className="flex-1">{t('twa.create.elevator.item', { entrance: el.entrance_number, number: el.elevator_number })}</span>
          <span className="text-[11px] text-gray-500 dark:text-gray-400">
            {t(el.current_status ? `elevators.status.${el.current_status}` : 'elevators.status.none')}
          </span>
        </button>
      ))}

      {value.elevatorId !== null && blocked && (
        <ElevatorBlockedNotice
          showPickAnother
          info={{
            status: value.elevatorStatus,
            statusSince: selected?.status_since ?? null,
            label: value.elevatorLabel,
          }}
        />
      )}

      {value.elevatorId !== null && !blocked && (
        <div className="pt-3">
          <h3 className="font-semibold text-[14px] mb-2">{t('twa.create.elevator.operationalQuestion')}</h3>
          <div className="grid grid-cols-2 gap-2">
            {([true, false] as const).map((answer) => (
              <button
                key={String(answer)}
                onClick={() => onChange({ ...value, operational: answer })}
                aria-pressed={value.operational === answer}
                className={`${CARD} justify-center ${value.operational === answer ? 'border-emerald-500' : 'border-gray-200 dark:border-gray-700'}`}
              >
                {t(answer ? 'twa.create.elevator.yes' : 'twa.create.elevator.no')}
              </button>
            ))}
          </div>
          {hintKey && (
            <div className="mt-2 px-3 py-2 rounded-xl bg-amber-50 dark:bg-amber-900/30 text-amber-800 dark:text-amber-200 text-[12px]">
              {t(hintKey)}
            </div>
          )}
        </div>
      )}

      <button disabled={blocked || !isElevatorSelectionComplete(value)} onClick={onNext} className={PRIMARY}>
        {t('twa.create.next')}
      </button>
      {blocked && (
        <button onClick={onBackToCategory} className={SECONDARY}>{t('twa.create.elevator.backToCategory')}</button>
      )}
    </div>
  )
}
