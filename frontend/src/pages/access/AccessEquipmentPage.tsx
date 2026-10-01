import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Cpu } from 'lucide-react'
import { usePageTitle } from '../../hooks/usePageTitle'
import AccessTabBar from '../../components/access/AccessTabBar'
import ZonesPanel from '../../components/access/equipment/ZonesPanel'
import SpotsPanel from '../../components/access/equipment/SpotsPanel'
import AssignmentsPanel from '../../components/access/equipment/AssignmentsPanel'
import GatesPanel from '../../components/access/equipment/GatesPanel'
import CamerasPanel from '../../components/access/equipment/CamerasPanel'
import BarriersPanel from '../../components/access/equipment/BarriersPanel'
import ControllersPanel from '../../components/access/equipment/ControllersPanel'
import { useHasRole } from '../../hooks/useHasRole'
import { useAccessZones, useAccessGates } from '../../hooks/useAccessEquipment'

/**
 * Экран «Оборудование» (управление точками въезда). Табы фильтруются по роли:
 *  - manager: Зоны, Въезды;
 *  - system_admin: + Камеры, Шлагбаумы, Контроллеры (бэкенд отдаёт их GET только
 *    system_admin; manager получил бы 403, поэтому эти табы для него скрыты).
 *
 * Route уже закрыт ACCESS_MANAGER_ROLES (App.tsx) — здесь дополнительный гейтинг
 * табов/действий по system_admin (useHasRole).
 */
type Tab = 'zones' | 'spots' | 'assignments' | 'gates' | 'cameras' | 'barriers' | 'controllers'

export default function AccessEquipmentPage() {
  const { t } = useTranslation()
  usePageTitle(t('accessControl.equipment.title'))
  const isAdmin = useHasRole('system_admin')
  const [tab, setTab] = useState<Tab>('zones')

  // Источники для select'ов (зоны/въезды) + таблицы своих табов.
  const zonesQuery = useAccessZones()
  const gatesQuery = useAccessGates()
  const zones = zonesQuery.data?.items ?? []
  const gates = gatesQuery.data?.items ?? []

  const tabs = [
    { key: 'zones', label: t('accessControl.equipment.tabs.zones') },
    { key: 'spots', label: t('accessControl.parking.tabs.spots') },
    { key: 'assignments', label: t('accessControl.parking.tabs.assignments') },
    { key: 'gates', label: t('accessControl.equipment.tabs.gates') },
    ...(isAdmin
      ? [
          { key: 'cameras', label: t('accessControl.equipment.tabs.cameras') },
          { key: 'barriers', label: t('accessControl.equipment.tabs.barriers') },
          { key: 'controllers', label: t('accessControl.equipment.tabs.controllers') },
        ]
      : []),
  ]

  // Защита: если неадмин как-то оказался на admin-табе — вернуть на «Зоны».
  const adminTabs: Tab[] = ['cameras', 'barriers', 'controllers']
  const activeTab: Tab = !isAdmin && adminTabs.includes(tab) ? 'zones' : tab

  return (
    <div className="p-6 flex flex-col gap-5">
      <div className="flex items-center gap-2.5">
        <Cpu className="text-accent" size={22} />
        <div>
          <h1 className="text-xl font-semibold text-text-primary">{t('accessControl.equipment.title')}</h1>
          <p className="text-[13px] text-text-muted">{t('accessControl.equipment.subtitle')}</p>
        </div>
      </div>

      <AccessTabBar tabs={tabs} active={activeTab} onChange={(k) => setTab(k as Tab)} />

      {activeTab === 'zones' && <ZonesPanel canManage />}
      {activeTab === 'spots' && <SpotsPanel canManage zones={zones} />}
      {activeTab === 'assignments' && <AssignmentsPanel canManage zones={zones} />}
      {activeTab === 'gates' && <GatesPanel canManage zones={zones} />}
      {activeTab === 'cameras' && isAdmin && <CamerasPanel gates={gates} />}
      {activeTab === 'barriers' && isAdmin && <BarriersPanel gates={gates} />}
      {activeTab === 'controllers' && isAdmin && <ControllersPanel zones={zones} gates={gates} />}
    </div>
  )
}
