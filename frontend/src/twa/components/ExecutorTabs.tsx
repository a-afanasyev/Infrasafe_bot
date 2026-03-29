import { useTranslation } from 'react-i18next'
import { ClipboardList, Clock, ShoppingCart, Archive, UserCircle } from 'lucide-react'
import BottomTabBar from './BottomTabBar'

export function ExecutorTabs({ purchaseBadge = 0 }: { purchaseBadge?: number }) {
  const { t } = useTranslation()
  const tabs = [
    { path: '/twa/exec', icon: <ClipboardList size={20} />, label: t('twa.exec.tabs.tasks') },
    { path: '/twa/exec/shift', icon: <Clock size={20} />, label: t('twa.exec.tabs.shift') },
    { path: '/twa/exec/purchase', icon: <ShoppingCart size={20} />, label: t('twa.exec.tabs.purchase'), badge: purchaseBadge },
    { path: '/twa/exec/archive', icon: <Archive size={20} />, label: t('twa.exec.tabs.archive') },
    { path: '/twa/exec/profile', icon: <UserCircle size={20} />, label: t('twa.exec.tabs.profile') },
  ]
  return <BottomTabBar tabs={tabs} />
}
