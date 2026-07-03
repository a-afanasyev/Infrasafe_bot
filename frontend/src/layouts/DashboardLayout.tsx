import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useEffect, useRef, useState, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { useAuthStore } from '../stores/authStore'
import { ACCESS_MODULE_ROLES, ACCESS_MANAGER_ROLES } from '../constants/roles'
import { TopbarProvider } from '../contexts/TopbarContext'
import { useTopbar } from '../contexts/topbar'
import { useTheme } from '../hooks/useTheme'
import { useMediaQuery } from '../hooks/useMediaQuery'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import LanguageSwitcher from '@/components/shared/LanguageSwitcher'
import ChangePasswordModal from '@/components/shared/ChangePasswordModal'
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
  ChevronUp,
  ChevronDown,
} from 'lucide-react'

// ─── Types ──────────────────────────────────────────────────────────────────────

type SidebarState = 'expanded' | 'collapsed' | 'hidden'

interface NavItem {
  to: string
  labelKey: string
  Icon: React.ComponentType<{ size?: number }>
  end?: boolean
  // Если задано — пункт виден только пользователю с одной из этих ролей.
  // Без поля пункт виден всем (текущее поведение остальных пунктов).
  allowedRoles?: readonly string[]
}

// ─── Navigation items ───────────────────────────────────────────────────────────

const NAV_ITEMS: NavItem[] = [
  { to: '/dashboard/analytics', labelKey: 'nav.analytics', Icon: LayoutGrid },
  { to: '/dashboard', labelKey: 'nav.requests', Icon: ListChecks, end: true },
  { to: '/dashboard/employees', labelKey: 'nav.employees', Icon: Users },
  { to: '/dashboard/shifts', labelKey: 'nav.shifts', Icon: Clock },
  { to: '/dashboard/templates', labelKey: 'nav.templates', Icon: Table2 },
  { to: '/dashboard/addresses', labelKey: 'nav.addresses', Icon: MapPin },
  { to: '/dashboard/board-editor', labelKey: 'nav.boardEditor', Icon: MonitorPlay },
  { to: '/dashboard/feedback', labelKey: 'nav.feedback', Icon: MessageSquare },
  // access_control §9.6: контроль доступа — только роли модуля доступа.
  { to: '/dashboard/access', labelKey: 'nav.accessControl', Icon: ShieldCheck, end: true, allowedRoles: ACCESS_MODULE_ROLES },
  // access_control §6/§13.2: экраны менеджера (история проездов + база доступа).
  { to: '/dashboard/access/history', labelKey: 'nav.accessHistory', Icon: History, allowedRoles: ACCESS_MANAGER_ROLES },
  { to: '/dashboard/access/database', labelKey: 'nav.accessDatabase', Icon: Database, allowedRoles: ACCESS_MANAGER_ROLES },
  // access_control: «Оборудование» — manager/system_admin (камеры/шлагбаумы/
  // контроллеры внутри только для system_admin).
  { to: '/dashboard/access/equipment', labelKey: 'nav.accessEquipment', Icon: Cpu, allowedRoles: ACCESS_MANAGER_ROLES },
]

// ─── Simple tooltip for collapsed sidebar ───────────────────────────────────────

function NavTooltip({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="group relative">
      {children}
      <div className="pointer-events-none absolute left-full top-1/2 z-50 ml-2 -translate-y-1/2 rounded-sm bg-bg-card px-2.5 py-1.5 text-xs font-medium text-text-primary opacity-0 shadow-lg ring-1 ring-border-default transition-opacity group-hover:opacity-100">
        {label}
      </div>
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
  const { isDark, toggle } = useTheme()
  const { t } = useTranslation()

  return (
    <header
      className={cn(
        'fixed top-0 right-0 z-[100] flex h-[var(--topbar-h)] items-center gap-3 border-b border-border-default px-6 backdrop-blur-[20px]',
        'bg-bg-sidebar/80',
        sidebarState === 'expanded' && 'left-[var(--sidebar-w)]',
        sidebarState === 'collapsed' && 'left-[var(--sidebar-w-collapsed)]',
        sidebarState === 'hidden' && 'left-0',
      )}
    >
      {/* Hamburger for hidden sidebar */}
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
        <Button
          variant="ghost"
          size="icon"
          onClick={toggle}
          aria-label={isDark ? t('theme.light') : t('theme.dark')}
          title={isDark ? t('theme.light') : t('theme.dark')}
        >
          {isDark ? <Sun size={16} /> : <Moon size={16} />}
        </Button>
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

        {/* Name + role (only when expanded) */}
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
    </div>
  )
}

// ─── Sidebar content (shared between desktop and mobile overlay) ────────────────

function SidebarContent({
  collapsed,
  onNavClick,
}: {
  collapsed: boolean
  onNavClick?: () => void
}) {
  const { t } = useTranslation()
  const userRoles = useAuthStore((s) => s.user?.roles)
  // Пункты с allowedRoles показываем только при совпадении роли (гард сайдбара).
  const navItems = NAV_ITEMS.filter(
    (item) =>
      !item.allowedRoles ||
      item.allowedRoles.some((r) => userRoles?.includes(r)),
  )
  return (
    <>
      {/* Logo */}
      <div className={cn('px-5 pt-5 pb-4', collapsed && 'flex justify-center px-3')}>
        <div className={cn('flex items-center gap-3', collapsed && 'flex-col gap-0')}>
          <img
            src={`${import.meta.env.BASE_URL}infrasafe-logo.svg`}
            alt="InfraSafe"
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
      <nav className={cn('flex-1 overflow-y-auto', collapsed ? 'px-2 py-2' : 'px-3 py-2')}>
        {!collapsed && (
          <div className="mb-1 px-2 py-1 text-[10px] font-semibold uppercase tracking-wider text-text-muted">
            {t('nav.main')}
          </div>
        )}
        {navItems.map(({ to, labelKey, Icon, end }) => {
          const label = t(labelKey)
          return collapsed ? (
            <NavTooltip key={to} label={label}>
              <NavLink
                to={to}
                end={end}
                onClick={onNavClick}
                className={({ isActive }) =>
                  cn(
                    'mb-0.5 flex items-center justify-center rounded-sm p-2.5 text-sm transition-all',
                    isActive
                      ? 'bg-accent-dim text-accent font-semibold'
                      : 'text-text-secondary hover:bg-bg-surface',
                  )
                }
              >
                <Icon size={18} />
              </NavLink>
            </NavTooltip>
          ) : (
            <NavLink
              key={to}
              to={to}
              end={end}
              onClick={onNavClick}
              className={({ isActive }) =>
                cn(
                  'mb-0.5 flex items-center gap-2.5 rounded-sm border-l-[3px] px-3 py-[9px] text-sm no-underline transition-all',
                  isActive
                    ? 'border-accent bg-accent-dim font-semibold text-accent'
                    : 'border-transparent text-text-secondary hover:bg-bg-surface',
                )
              }
            >
              <Icon size={16} />
              {label}
            </NavLink>
          )
        })}

        {/* External section */}
        {!collapsed && (
          <div className="mt-3 mb-1 px-2 py-1 text-[10px] font-semibold uppercase tracking-wider text-text-muted">
            {t('nav.external')}
          </div>
        )}
        {collapsed ? (
          <NavTooltip label={t('nav.residentBoard')}>
            <NavLink
              to="/resident-board"
              onClick={onNavClick}
              className={({ isActive }) =>
                cn(
                  'mt-2 flex items-center justify-center rounded-sm p-2.5 text-sm transition-all',
                  isActive
                    ? 'bg-accent-dim text-accent font-semibold'
                    : 'text-text-secondary hover:bg-bg-surface',
                )
              }
            >
              <BookOpen size={18} />
            </NavLink>
          </NavTooltip>
        ) : (
          <NavLink
            to="/resident-board"
            onClick={onNavClick}
            className={({ isActive }) =>
              cn(
                'flex items-center gap-2.5 rounded-sm border-l-[3px] px-3 py-[9px] text-sm no-underline transition-all',
                isActive
                  ? 'border-accent bg-accent-dim font-semibold text-accent'
                  : 'border-transparent text-text-secondary hover:bg-bg-surface',
              )
            }
          >
            <BookOpen size={16} />
            {t('nav.residentBoard')}
          </NavLink>
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

  // Manual toggle override: user can force collapsed/expanded
  const [manualToggle, setManualToggle] = useState<'expanded' | 'collapsed' | null>(null)
  // Mobile overlay
  const [mobileOpen, setMobileOpen] = useState(false)

  // Compute sidebar state
  const sidebarState: SidebarState = (() => {
    if (isMobile) return 'hidden'
    if (manualToggle) return manualToggle
    if (isDesktop) return 'expanded'
    return 'collapsed'
  })()

  // Reset manual toggle when crossing breakpoints
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- намеренный сброс ручного тумблера при смене брейкпоинта
    setManualToggle(null)
  }, [isDesktop, isTablet])

  // Close mobile overlay on navigation
  const closeMobileMenu = useCallback(() => setMobileOpen(false), [])

  // Close mobile menu on Escape
  useEffect(() => {
    if (!mobileOpen) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setMobileOpen(false)
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [mobileOpen])

  // Toggle between expanded/collapsed
  const toggleSidebar = () => {
    if (sidebarState === 'expanded') {
      setManualToggle('collapsed')
    } else {
      setManualToggle('expanded')
    }
  }

  return (
    <TopbarProvider>
      {/* ── Desktop/Tablet Sidebar ── */}
      {sidebarState !== 'hidden' && (
        <aside
          className={cn(
            'fixed top-0 left-0 z-[200] flex h-screen flex-col border-r border-border-default bg-bg-sidebar transition-[width] duration-200',
            sidebarState === 'expanded' ? 'w-[var(--sidebar-w)]' : 'w-[var(--sidebar-w-collapsed)]',
          )}
        >
          <SidebarContent collapsed={sidebarState === 'collapsed'} />

          {/* Toggle button */}
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

      {/* ── Mobile Sidebar Overlay ── */}
      {isMobile && mobileOpen && (
        <>
          {/* Backdrop */}
          <div
            className="fixed inset-0 z-[250] bg-black/50 backdrop-blur-sm transition-opacity"
            onClick={closeMobileMenu}
            aria-hidden="true"
          />
          {/* Sidebar panel */}
          <aside className="fixed top-0 left-0 z-[260] flex h-screen w-[280px] flex-col border-r border-border-default bg-bg-sidebar shadow-2xl">
            <SidebarContent collapsed={false} onNavClick={closeMobileMenu} />
          </aside>
        </>
      )}

      {/* ── Topbar ── */}
      <TopbarInner
        sidebarState={sidebarState}
        onToggleMobile={() => setMobileOpen(o => !o)}
      />

      {/* ── Main content ── */}
      <main
        className={cn(
          'mt-[var(--topbar-h)] min-h-[calc(100vh-var(--topbar-h))] bg-bg-root overflow-y-auto',
          sidebarState === 'expanded' && 'ml-[var(--sidebar-w)]',
          sidebarState === 'collapsed' && 'ml-[var(--sidebar-w-collapsed)]',
          sidebarState === 'hidden' && 'ml-0',
        )}
      >
        <Outlet />
      </main>
    </TopbarProvider>
  )
}
