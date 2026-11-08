import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import { useBindRequestAddress } from '../../hooks/useRequestMutations'
import AddressLevelPicker from '../addresses/AddressLevelPicker'
import { addressLevelBody, EMPTY_ADDRESS_LEVEL, type AddressLevelValue } from '../addresses/addressLevel'

/**
 * Заявка с адресом-текстом (legacy) не уходит в работу — сервер отказывает в
 * назначении (решение владельца 2026-11-07). Блок в карточке: предупреждение и
 * привязка двора/дома/квартиры. Показывается только менеджеру (`requests.manage`).
 */
export default function RequestAddressBind({ requestNumber }: { requestNumber: string }) {
  const { t } = useTranslation()
  const [address, setAddress] = useState<AddressLevelValue>(EMPTY_ADDRESS_LEVEL)
  const bind = useBindRequestAddress(requestNumber)
  const body = addressLevelBody(address)

  return (
    <div className="bg-amber/8 border border-amber/20 rounded-[10px] px-3 py-2.5 space-y-2 text-[13px]">
      <p className="text-text-primary">⚠️ {t('kanban.addressNotBound')}</p>
      <AddressLevelPicker value={address} onChange={setAddress} idPrefix={`bind-${requestNumber}`} />
      <Button size="sm" disabled={body === null || bind.isPending} onClick={() => body && bind.mutate(body)}>
        {t('kanban.bindAddress')}
      </Button>
    </div>
  )
}
