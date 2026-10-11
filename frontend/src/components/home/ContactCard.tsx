import { useTranslation } from 'react-i18next'
import type { BoardConfigData } from '../../types/boardConfig'
import HomeIcon from './HomeIcon'
import QrCode from './QrCode'
import { botHandle, formatWorkingHours, telHref, type Lang } from './homeFormat'

interface ContactCardProps {
  config: BoardConfigData
  // Заголовок из редактора витрины; '' → i18n-дефолт.
  title: string
  lang: Lang
}

// «Мы на связи»: диспетчерская, бот (QR + кнопка), часы работы, аварийная.
// Всё из конфига витрины — правится в «Редакторе витрины».
export default function ContactCard({ config, title, lang }: ContactCardProps) {
  const { t } = useTranslation()
  const loc = (v: { ru: string; uz: string }) => v[lang] || v.ru
  const bot = botHandle(config.bot.username)
  const botUrl = `https://t.me/${bot}`
  const phone = config.contacts.dispatch_phone.trim()
  const emergency = loc(config.contacts.emergency)

  return (
    <aside className="rh-card rh-contact" aria-labelledby="rh-contact-heading">
      <div className="rh-contact-heading">
        <span className="rh-contact-icon"><HomeIcon name="phone" /></span>
        <div>
          <h2 id="rh-contact-heading">{title || t('home.stayInTouch')}</h2>
          <p>{t('home.contactSub')}</p>
        </div>
      </div>

      {phone && (
        <div className="rh-phone-row">
          <span className="rh-small-label">{loc(config.contacts.dispatch_label)}</span>
          <a className="rh-phone" href={telHref(phone)}>
            {phone}
            <HomeIcon name="upRight" />
          </a>
        </div>
      )}

      {bot && (
        <div className="rh-telegram-row">
          <a className="rh-qr" href={botUrl} target="_blank" rel="noopener noreferrer">
            <QrCode value={botUrl} label={t('home.qrAlt', { bot })} />
          </a>
          <div className="rh-telegram-copy">
            <span className="rh-small-label">{t('home.requestViaBot')}</span>
            <a className="rh-telegram-handle" href={botUrl} target="_blank" rel="noopener noreferrer">
              <span>@{bot}</span>
              <HomeIcon name="upRight" />
            </a>
            <p>{t('home.scanQr')}</p>
            <a className="rh-telegram-button" href={botUrl} target="_blank" rel="noopener noreferrer">
              <HomeIcon name="telegram" />
              <span>{t('home.openBot')}</span>
              <HomeIcon name="arrow" />
            </a>
          </div>
        </div>
      )}

      <div className="rh-contact-hours">
        <HomeIcon name="clock" />
        <div>
          <span>{formatWorkingHours(config.working_hours, t)}</span>
          {emergency && <span className="rh-emergency">{emergency}</span>}
        </div>
      </div>
    </aside>
  )
}
