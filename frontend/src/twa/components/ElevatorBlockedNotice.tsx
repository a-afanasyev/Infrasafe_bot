import { useTranslation } from 'react-i18next'
import { useDispatchPhone } from '../hooks/useDispatchPhone'
import { formatStatusSince, telHref, type ElevatorUnderWorks } from './elevatorUnderWorks'

/**
 * Р18: блокирующий блок «по лифту идут работы» — на шаге «Лифт» (выбран лифт
 * в ремонте/на ТО) и на шаге подтверждения (сервер ответил 409 в гонке
 * статусов). Текст тот же, что в боте; телефон диспетчерской — ссылкой `tel:`
 * с той же санитизацией, что в публичном виджете.
 */
interface Props {
  info: ElevatorUnderWorks
  /** Подсказка «выберите другой лифт» — только на шаге выбора. */
  showPickAnother?: boolean
}

export default function ElevatorBlockedNotice({ info, showPickAnother = false }: Props) {
  const { t } = useTranslation()
  const phone = useDispatchPhone(true)
  const since = formatStatusSince(info.statusSince)
  const status = t(info.status ? `elevators.status.${info.status}` : 'elevators.status.none')

  return (
    <div
      role="alert"
      className="mt-2 px-3 py-2 rounded-xl bg-amber-50 dark:bg-amber-900/30 border border-amber-200 dark:border-amber-800 text-amber-900 dark:text-amber-100 text-[12px] space-y-1"
    >
      <div className="font-semibold">⛔ {t('twa.create.elevator.blockedTitle')}</div>
      {info.label && <div>{info.label}</div>}
      <div>
        {since
          ? t('twa.create.elevator.blockedBody', { status, since })
          : t('twa.create.elevator.blockedBodyNoSince', { status })}
      </div>
      {phone ? (
        <div>
          {t('twa.create.elevator.blockedCall')}{' '}
          <a href={telHref(phone)} className="underline font-medium">{phone}</a>
        </div>
      ) : (
        <div>{t('twa.create.elevator.blockedCallNoPhone')}</div>
      )}
      {showPickAnother && <div>{t('twa.create.elevator.blockedPickAnother')}</div>}
    </div>
  )
}
