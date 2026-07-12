import { NavLink, Outlet, useNavigate, useLocation } from 'react-router-dom'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useAuthStore } from '../stores/authStore'
import { ACCESS_MODULE_ROLES, ACCESS_MANAGER_ROLES, MATERIALS_MODULE_ROLES } from '../constants/roles'
import { TopbarProvider } from '../contexts/TopbarContext'
import { useTopbar } from '../contexts/topbar'
import { useTheme } from '../hooks/useTheme'
import { brand } from '../brand/brand'
import { useMediaQuery } from '../hooks/useMediaQuery'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import LanguageSwitcher from '@/components/shared/LanguageSwitcher'
import ChangePasswordModal from '@/components/shared/ChangePasswordModal'
import ChangeEmailModal from '@/components/shared/ChangeEmailModal'
import {
  LayoutGrid,
  ListChecks,
  Users,
  Clock,
  Table2,
  MapPin,
  MonitorPlay,
  MessageSquare,
  ShieldCheck,
  History,
  Database,
  Cpu,
  BookOpen,
  Sun,
  Moon,
  Menu,
  PanelLeftClose,
  PanelLeftOpen,
  User,
  LogOut,
  KeyRound,
  Mail,
  ChevronUp,
  ChevronDown,
  Package,
  Boxes,
} from 'lucide-react'

// ─── Types ──────────────────────────────────────────────────────────────────────

type IconType = React.ComponentType<{ size?: number }>
type SidebarState = 'expanded' | 'collapsed' | 'hidden'

interface NavLeaf {
  to: string
  labelKey: string
  Icon: IconType
  end?: boolean
  // Если задано — пункт виден только пользователю с одной из этих ролей.
  // Без поля пункт виден всем (текущее поведение остальных пунктов).
  allowedRoles?: readonly string[]
}

// Раскрываемая группа: заголовок-аккордеон, внутри — обычные пункты.
// Группа видна, если после role-фильтра остался хотя бы один дочерний пункт.
interface NavGroup {
  groupKey: string
  labelKey: string
  Icon: IconType
  children: NavLeaf[]
}

type NavEntry = NavLeaf | NavGroup

const isGroup = (e: NavEntry): e is NavGroup => 'children' in e

// ─── Navigation structure ───────────────────────────────────────────────────────

const NAV_ENTRIES: NavEntry[] = [
  { to: '/dashboard/analytics', labelKey: 'nav.analytics', Icon: LayoutGrid },
  { to: '/dashboard', labelKey: 'nav.requests', Icon: ListChecks, end: true },
  // Персонал: сотрудники + смены + шаблоны смен под единым раскрываемым пунктом.
  {
    groupKey: 'personnel',
    labelKey: 'nav.groupPersonnel',
    Icon: Users,
    children: [
      { to: '/dashboard/employees', labelKey: 'nav.employees', Icon: Users },
      { to: '/dashboard/shifts', labelKey: 'nav.shifts', Icon: Clock },
      { to: '/dashboard/templates', labelKey: 'nav.templates', Icon: Table2 },
    ],
  },
  { to: '/dashboard/addresses', labelKey: 'nav.addresses', Icon: MapPin },
  { to: '/dashboard/board-editor', labelKey: 'nav.boardEditor', Icon: MonitorPlay },
  { to: '/dashboard/feedback', labelKey: 'nav.feedback', Icon: MessageSquare },
  // Контроль доступа: обзор + история проездов + база доступа + оборудование.
  {
    groupKey: 'access',
    labelKey: 'nav.accessControl',
    Icon: ShieldCheck,
    children: [
      // access_control §9.6: обзор модуля — роли модуля доступа.
      { to: '/dashboard/access', labelKey: 'nav.accessOverview', Icon: ShieldCheck, end: true, allowedRoles: ACCESS_MODULE_ROLES },
      // access_control §6/§13.2: экраны менеджера (история проездов + база доступа).
      { to: '/dashboard/access/history', labelKey: 'nav.accessHistory', Icon: History, allowedRoles: ACCESS_MANAGER_ROLES },
      { to: '/dashboard/access/database', labelKey: 'nav.accessDatabase', Icon: Database, allowedRoles: ACCESS_MANAGER_ROLES },
      // «Оборудование» — manager/system_admin (камеры/шлагбаумы/контроллеры внутри
      // только для system_admin).
      { to: '/dashboard/access/equipment', labelKey: 'nav.accessEquipment', Icon: Cpu, allowedRoles: ACCESS_MANAGER_ROLES },
    ],
  },
  // Складской учёт материалов (manager/system_admin)
  { to: '/dashboard/materials', labelKey: 'nav.materials', Icon: Package, allowedRoles: MATERIALS_MODULE_ROLES },
  // «Учёт ресурсов» — внешний сервис в iframe. Пункт есть только когда задан
  // VITE_RESOURCES_URL (infrasafe вкл.; profk тёмный, пока партнёр не поддержит
  // его origin в своём frame-ancestors/parent-origin).
  ...(import.meta.env.VITE_RESOURCES_URL
    ? [{ to: '/dashboard/resource-accounting', labelKey: 'nav.resourceAccounting', Icon: Boxes, allowedRoles: ['admin', 'manager'] as const }]
    : []),
]

// Пункт «внешнего» блока (табло жителей) — вынесен отдельным листом.
const RESIDENT_BOARD_LEAF: NavLeaf = {
  to: '/resident-board',
  labelKey: 'nav.residentBoard',
  Icon: BookOpen,
}

// Виден ли пункт текущим ролям (без allowedRoles — виден всем).
const isVisibleTo = (item: { allowedRoles?: readonly string[] }, roles?: string[]) =>
  !item.allowedRoles || item.allowedRoles.some((r) => roles?.includes(r))

// ─── Single nav leaf (optional indent for group children) ───────────────────────

function NavLeafLink({
  leaf,
  indent = false,
  onClick,
}: {
  leaf: NavLeaf
  indent?: boolean
  onClick?: () => void
}) {
  const { t } = useTranslation()
  const { to, labelKey, Icon, end } = leaf

  return (
    <NavLink
      to={to}
      end={end}
      onClick={onClick}
      className={({ isActive }) =>
        cn(
          'mb-0.5 flex items-center gap-2.5 rounded-sm border-l-[3px] py-[9px] text-sm no-underline transition-all',
          indent ? 'pl-9 pr-3' : 'px-3',
          isActive
            ? 'border-accent bg-accent-dim font-semibold text-accent'
            : 'border-transparent text-text-secondary hover:bg-bg-surface',
        )
      }
    >
      <Icon size={16} />
      {t(labelKey)}
    </NavLink>
  )
}

function NavTooltip({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="group relative">
      {children}
      <div className="pointer-events-none absolute left-full top-1/2 z-50 ml-2 -translate-y-1/2 whitespace-nowrap rounded-sm bg-bg-card px-2.5 py-1.5 text-xs font-medium text-text-primary opacity-0 shadow-lg ring-1 ring-border-default transition-opacity group-hover:opacity-100">
        {label}
      </div>
    </div>
  )
}

function CollapsedNavLeafLink({ leaf }: { leaf: NavLeaf }) {
  const { t } = useTranslation()
  const { to, labelKey, Icon, end } = leaf

  return (
    <NavTooltip label={t(labelKey)}>
      <NavLink
        to={to}
        end={end}
        className={({ isActive }) =>
          cn(
            'mb-0.5 flex items-center justify-center rounded-sm p-2.5 text-sm transition-all',
            isActive
              ? 'bg-accent-dim font-semibold text-accent'
              : 'text-text-secondary hover:bg-bg-surface',
          )
        }
      >
        <Icon size={18} />
      </NavLink>
    </NavTooltip>
  )
}

// ─── Collapsible nav group (accordion header + indented children) ────────────────

function NavGroupBlock({
  group,
  open,
  onToggle,
  active,
  onNavClick,
}: {
  group: NavGroup
  open: boolean
  onToggle: () => void
  active: boolean
  onNavClick?: () => void
}) {
  const { t } = useTranslation()
  const label = t(group.labelKey)
  const { Icon } = group

  return (
    <div className="mb-0.5">
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        aria-controls={`nav-group-${group.groupKey}`}
        className={cn(
          'flex w-full items-center gap-2.5 rounded-sm border-l-[3px] border-transparent px-3 py-[9px] text-sm transition-all',
          active ? 'font-semibold text-accent' : 'text-text-secondary hover:bg-bg-surface',
        )}
      >
        <Icon size={16} />
        <span className="flex-1 text-left">{label}</span>
        <ChevronDown
          size={14}
          className={cn('shrink-0 transition-transform', open ? '' : '-rotate-90')}
        />
      </button>
      {open && (
        <div id={`nav-group-${group.groupKey}`} className="mt-0.5">
          {group.children.map((child) => (
            <NavLeafLink key={child.to} leaf={child} indent onClick={onNavClick} />
          ))}
        </div>
      )}
    </div>
  )
}

// ─── Topbar inner component (needs useTopbar inside provider) ───────────────────

function TopbarInner({
  sidebarState,
  onToggleMobile,
}: {
  sidebarState: SidebarState
  onToggleMobile: () => void
}) {
  const { actions } = useTopbar()
  const { isDark, toggle, canToggle } = useTheme()
  const { t } = useTranslation()

  return (
    <header
      className={cn(
        'fixed top-0 right-0 z-[100] flex h-[var(--topbar-h)] items-center gap-3 border-b border-border-default bg-bg-sidebar/80 px-3 backdrop-blur-[20px] sm:px-6',
        sidebarState === 'expanded' && 'left-[var(--sidebar-w)]',
        sidebarState === 'collapsed' && 'left-[var(--sidebar-w-collapsed)]',
        sidebarState === 'hidden' && 'left-0',
      )}
    >
      {sidebarState === 'hidden' && (
        <Button
          variant="ghost"
          size="icon"
          onClick={onToggleMobile}
          aria-label={t('sidebar.openMenu')}
        >
          <Menu size={20} />
        </Button>
      )}

      <div className="flex-1" />

      <div className="flex items-center gap-2">
        {actions}
        <LanguageSwitcher />
        {canToggle && (
          <Button
            variant="ghost"
            size="icon"
            onClick={toggle}
            aria-label={isDark ? t('theme.light') : t('theme.dark')}
            title={isDark ? t('theme.light') : t('theme.dark')}
          >
            {isDark ? <Sun size={16} /> : <Moon size={16} />}
          </Button>
        )}
      </div>
    </header>
  )
}

// ─── User dropdown menu ─────────────────────────────────────────────────────────

function UserDropdown({ collapsed }: { collapsed: boolean }) {
  const { user, logout } = useAuthStore()
  const navigate = useNavigate()
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const [pwdOpen, setPwdOpen] = useState(false)
  const [emailOpen, setEmailOpen] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)
  const initials = user?.first_name ? user.first_name[0].toUpperCase() : 'U'

  // Close on click outside
  useEffect(() => {
    if (!open) return
    const handler = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  // Close on Escape
  useEffect(() => {
    if (!open) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [open])

  return (
    <div ref={menuRef} className="relative border-t border-border-default px-3 py-2">
      <button
        onClick={() => setOpen(o => !o)}
        aria-expanded={open}
        aria-haspopup="true"
        className={cn(
          'flex w-full items-center gap-2.5 rounded-sm p-2 transition-colors',
          open ? 'bg-bg-surface' : 'hover:bg-bg-surface',
          collapsed && 'justify-center',
        )}
      >
        {/* Avatar */}
        <div
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full font-[family-name:var(--font-display)] text-sm font-bold text-black"
          style={{ background: 'linear-gradient(135deg, var(--accent), #0099aa)' }}
        >
          {initials}
        </div>

        {!collapsed && (
          <>
            <div className="min-w-0 flex-1 text-left">
              <div className="truncate text-[13px] font-semibold text-text-primary">
                {user?.first_name ?? t('common.user')}
              </div>
              <div className="text-[11px] text-text-muted">
                {(['manager', 'executor', 'applicant'].find(r => user?.roles?.includes(r))) ?? 'manager'}
              </div>
            </div>
            <span className="shrink-0 text-text-muted">
              {open ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
            </span>
          </>
        )}
      </button>

      {/* Dropdown */}
      {open && (
        <div
          className="absolute bottom-[calc(100%-4px)] left-3 right-3 z-[300] overflow-hidden rounded-default border border-border-default bg-bg-card shadow-[0_-8px_24px_rgba(0,0,0,0.3)]"
          role="menu"
          aria-label={t('sidebar.userMenu')}
        >
          <button
            role="menuitem"
            onClick={() => {
              setOpen(false)
              navigate(`/dashboard/employees/${user?.id}`)
            }}
            className="flex w-full items-center gap-2.5 px-4 py-2.5 text-left text-[13px] text-text-primary font-[family-name:var(--font-display)] hover:bg-bg-surface transition-colors"
          >
            <User size={14} />
            {t('common.profile')}
          </button>
          <button
            role="menuitem"
            onClick={() => {
              setOpen(false)
              setPwdOpen(true)
            }}
            className="flex w-full items-center gap-2.5 px-4 py-2.5 text-left text-[13px] text-text-primary font-[family-name:var(--font-display)] hover:bg-bg-surface transition-colors"
          >
            <KeyRound size={14} />
            {t('changePassword.menuItem')}
          </button>
          <button
            role="menuitem"
            onClick={() => {
              setOpen(false)
              setEmailOpen(true)
            }}
            className="flex w-full items-center gap-2.5 px-4 py-2.5 text-left text-[13px] text-text-primary font-[family-name:var(--font-display)] hover:bg-bg-surface transition-colors"
          >
            <Mail size={14} />
            {t('changeEmail.menuItem')}
          </button>
          <div className="mx-3 h-px bg-border-default" />
          <button
            role="menuitem"
            onClick={async () => {
              setOpen(false)
              await logout()
              navigate('/login')
            }}
            className="flex w-full items-center gap-2.5 px-4 py-2.5 text-left text-[13px] text-red font-[family-name:var(--font-display)] hover:bg-bg-surface transition-colors"
          >
            <LogOut size={14} />
            {t('common.logout')}
          </button>
        </div>
      )}

      <ChangePasswordModal open={pwdOpen} onClose={() => setPwdOpen(false)} />
      <ChangeEmailModal open={emailOpen} onClose={() => setEmailOpen(false)} />
    </div>
  )
}

// ─── Sidebar content ─────────────────────────────────────────────────────────────

function SidebarContent({
  collapsed,
  onNavClick,
}: {
  collapsed: boolean
  onNavClick?: () => void
}) {
  const { t } = useTranslation()
  const location = useLocation()
  const userRoles = useAuthStore((s) => s.user?.roles)

  // Role-фильтр (гард сайдбара): группы отдают только видимых детей, пустые группы
  // скрываются; листья — как раньше.
  const entries: NavEntry[] = NAV_ENTRIES.map((entry) => {
    if (isGroup(entry)) {
      const children = entry.children.filter((c) => isVisibleTo(c, userRoles))
      return children.length ? { ...entry, children } : null
    }
    return isVisibleTo(entry, userRoles) ? entry : null
  }).filter((e): e is NavEntry => e !== null)

  // Активность дочернего пункта: end → точное совпадение, иначе — префикс пути.
  const isChildActive = (child: NavLeaf) =>
    child.end ? location.pathname === child.to : location.pathname.startsWith(child.to)
  const isGroupActive = (g: NavGroup) => g.children.some(isChildActive)

  // Открытость групп: явный тумблер пользователя, по умолчанию — открыта активная.
  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>({})
  // При навигации авто-раскрываем группу с активным маршрутом, даже если её ранее
  // свернули вручную (render-time adjust вместо effect — паттерн FE-034). Без этого
  // сохранённый false «залипает» и активный пункт остаётся скрытым после перехода.
  const [seenPath, setSeenPath] = useState(location.pathname)
  if (location.pathname !== seenPath) {
    setSeenPath(location.pathname)
    const activeGroup = entries.find((e): e is NavGroup => isGroup(e) && isGroupActive(e))
    if (activeGroup) setOpenGroups((s) => ({ ...s, [activeGroup.groupKey]: true }))
  }
  const toggleGroup = (g: NavGroup) => {
    const currentlyOpen = openGroups[g.groupKey] ?? isGroupActive(g)
    setOpenGroups((s) => ({ ...s, [g.groupKey]: !currentlyOpen }))
  }

  return (
    <>
      {/* Logo */}
      <div className={cn('px-5 pt-5 pb-4', collapsed && 'flex justify-center px-3')}>
        <div className={cn('flex items-center gap-3', collapsed && 'justify-center')}>
          <img
            src={`${import.meta.env.BASE_URL}${brand.logoMark}`}
            alt={brand.displayName}
            className="h-10 w-10 shrink-0"
          />
          {!collapsed && (
            <div>
              <div className="font-[family-name:var(--font-display)] text-[15px] font-bold text-text-primary">
                {t('sidebar.title')}
              </div>
              <div className="text-[11px] text-text-muted">{t('sidebar.subtitle')}</div>
            </div>
          )}
        </div>
      </div>

      {/* Nav */}
      <nav className={cn('flex-1 overflow-y-auto py-2', collapsed ? 'px-2' : 'px-3')}>
        {!collapsed && (
          <div className="mb-1 px-2 py-1 text-[10px] font-semibold uppercase tracking-wider text-text-muted">
            {t('nav.main')}
          </div>
        )}
        {entries.map((entry) => {
          if (collapsed) {
            return isGroup(entry)
              ? entry.children.map((child) => <CollapsedNavLeafLink key={child.to} leaf={child} />)
              : <CollapsedNavLeafLink key={entry.to} leaf={entry} />
          }

          return isGroup(entry) ? (
            <NavGroupBlock
              key={entry.groupKey}
              group={entry}
              open={openGroups[entry.groupKey] ?? isGroupActive(entry)}
              onToggle={() => toggleGroup(entry)}
              active={isGroupActive(entry)}
              onNavClick={onNavClick}
            />
          ) : (
            <NavLeafLink key={entry.to} leaf={entry} onClick={onNavClick} />
          )
        })}

        {/* External section */}
        {!collapsed && (
          <div className="mt-3 mb-1 px-2 py-1 text-[10px] font-semibold uppercase tracking-wider text-text-muted">
            {t('nav.external')}
          </div>
        )}
        {collapsed ? (
          <CollapsedNavLeafLink leaf={RESIDENT_BOARD_LEAF} />
        ) : (
          <NavLeafLink leaf={RESIDENT_BOARD_LEAF} onClick={onNavClick} />
        )}
      </nav>

      {/* User block */}
      <UserDropdown collapsed={collapsed} />
    </>
  )
}

// ─── Main DashboardLayout ───────────────────────────────────────────────────────

export default function DashboardLayout() {
  const { t } = useTranslation()
  const isDesktop = useMediaQuery('(min-width: 1280px)')
  const isTablet = useMediaQuery('(min-width: 1024px)')
  const isMobile = !isTablet
  const [manualToggle, setManualToggle] = useState<'expanded' | 'collapsed' | null>(null)
  const [mobileOpen, setMobileOpen] = useState(false)

  const sidebarState: SidebarState = isMobile
    ? 'hidden'
    : manualToggle ?? (isDesktop ? 'expanded' : 'collapsed')

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- reset the explicit state after a breakpoint change
    setManualToggle(null)
  }, [isDesktop, isTablet])

  const closeMobileMenu = useCallback(() => setMobileOpen(false), [])

  useEffect(() => {
    if (!mobileOpen) return
    const handler = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setMobileOpen(false)
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [mobileOpen])

  const toggleSidebar = () => {
    setManualToggle(sidebarState === 'expanded' ? 'collapsed' : 'expanded')
  }

  return (
    <TopbarProvider>
      <div className="h-dvh overflow-hidden bg-bg-root">
        {sidebarState !== 'hidden' && (
          <aside
            className={cn(
              'fixed top-0 left-0 z-[200] flex h-dvh flex-col border-r border-border-default bg-bg-sidebar transition-[width] duration-200',
              sidebarState === 'expanded'
                ? 'w-[var(--sidebar-w)]'
                : 'w-[var(--sidebar-w-collapsed)]',
            )}
          >
            <SidebarContent collapsed={sidebarState === 'collapsed'} />

            <div className={cn('border-t border-border-default px-3 py-2', sidebarState === 'collapsed' && 'flex justify-center')}>
              <Button
                variant="ghost"
                size={sidebarState === 'collapsed' ? 'icon' : 'sm'}
                onClick={toggleSidebar}
                aria-label={sidebarState === 'expanded' ? t('sidebar.collapseMenu') : t('sidebar.expandMenu')}
                className={cn(
                  'text-text-muted hover:text-text-primary',
                  sidebarState === 'expanded' && 'w-full justify-start gap-2',
                )}
              >
                {sidebarState === 'expanded' ? (
                  <>
                    <PanelLeftClose size={16} />
                    <span className="text-xs">{t('sidebar.collapse')}</span>
                  </>
                ) : (
                  <PanelLeftOpen size={16} />
                )}
              </Button>
            </div>
          </aside>
        )}

        {isMobile && mobileOpen && (
          <>
            <div
              className="fixed inset-0 z-[250] bg-black/50 backdrop-blur-sm"
              onClick={closeMobileMenu}
              aria-hidden="true"
            />
            <aside className="fixed top-0 left-0 z-[260] flex h-dvh w-[min(280px,85vw)] flex-col border-r border-border-default bg-bg-sidebar shadow-2xl">
              <SidebarContent collapsed={false} onNavClick={closeMobileMenu} />
            </aside>
          </>
        )}

        <TopbarInner
          sidebarState={sidebarState}
          onToggleMobile={() => setMobileOpen((open) => !open)}
        />

        <main
          className={cn(
            'fixed right-0 bottom-0 top-[var(--topbar-h)] overflow-auto bg-bg-root',
            sidebarState === 'expanded' && 'left-[var(--sidebar-w)]',
            sidebarState === 'collapsed' && 'left-[var(--sidebar-w-collapsed)]',
            sidebarState === 'hidden' && 'left-0',
          )}
        >
          <Outlet />
        </main>
      </div>
    </TopbarProvider>
  )
}
