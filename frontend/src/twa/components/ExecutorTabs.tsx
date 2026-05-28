import { useTranslation } from 'react-i18next'
import { useQuery } from '@tanstack/react-query'
import { ClipboardList, Clock, ShoppingCart, Archive, UserCircle } from 'lucide-react'
import BottomTabBar from './BottomTabBar'
import { twaClient } from '../twaClient'

export function ExecutorTabs() {
  const { t } = useTranslation()
  // Self-fetch purchase count (shared cache with PurchasePage/TasksPage).
  const { data: tasks = [] } = useQuery({
    queryKey: ['executor-tasks'],
    queryFn: () => twaClient.get('/api/v2/requests', { params: { scope: 'my', limit: 50 } }).then((r) => r.data),
    staleTime: 30_000,
  })
  const purchaseBadge = tasks.filter((r: { status: string }) => r.status === 'Закуп').length
  const tabs = [
    { path: '/twa/exec', icon: <ClipboardList size={20} />, label: t('twa.exec.tabs.tasks') },
    { path: '/twa/exec/shift', icon: <Clock size={20} />, label: t('twa.exec.tabs.shift') },
    { path: '/twa/exec/purchase', icon: <ShoppingCart size={20} />, label: t('twa.exec.tabs.purchase'), badge: purchaseBadge },
    { path: '/twa/exec/archive', icon: <Archive size={20} />, label: t('twa.exec.tabs.archive') },
    { path: '/twa/exec/profile', icon: <UserCircle size={20} />, label: t('twa.exec.tabs.profile') },
  ]
  return <BottomTabBar tabs={tabs} />
}
