import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useEffect, useRef, useState } from 'react'
import { useAuthStore } from '../stores/authStore'
import { useTopbar, TopbarProvider } from '../contexts/TopbarContext'
import { useTheme } from '../hooks/useTheme'
import { LayoutGrid, ListChecks, Users, Clock, Table2, BookOpen, Sun, Moon } from 'lucide-react'

// Topbar inner component (needs useTopbar inside provider)
function TopbarInner() {
  const { actions } = useTopbar()
  const { isDark, toggle } = useTheme()
  return (
    <header style={{
      position: 'fixed',
      top: 0,
      left: 'var(--sidebar-w)',
      right: 0,
      height: 'var(--topbar-h)',
      background: 'rgba(10,15,24,0.8)',
      backdropFilter: 'blur(20px)',
      borderBottom: '1px solid var(--border)',
      display: 'flex',
      alignItems: 'center',
      padding: '0 24px',
      gap: '12px',
      zIndex: 100,
    }}>
      <div style={{ flex: 1 }} />
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
        {actions}
        <button
          onClick={toggle}
          style={{
            background: 'var(--bg-surface)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius-sm)',
            padding: '8px',
            cursor: 'pointer',
            color: 'var(--text-secondary)',
            display: 'flex',
            alignItems: 'center',
          }}
          title={isDark ? 'Светлая тема' : 'Тёмная тема'}
        >
          {isDark ? <Sun size={16} /> : <Moon size={16} />}
        </button>
      </div>
    </header>
  )
}

const NAV_ITEMS = [
  { to: '/dashboard/analytics', label: 'Дашборд', Icon: LayoutGrid },
  { to: '/dashboard', label: 'Заявки', Icon: ListChecks, end: true },
  { to: '/dashboard/employees', label: 'Сотрудники', Icon: Users },
  { to: '/dashboard/shifts', label: 'Смены', Icon: Clock },
  { to: '/dashboard/templates', label: 'Шаблоны', Icon: Table2 },
]

export default function DashboardLayout() {
  const { user, logout } = useAuthStore()
  const navigate = useNavigate()
  const initials = user?.first_name ? user.first_name[0].toUpperCase() : 'U'
  const [menuOpen, setMenuOpen] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!menuOpen) return
    const handler = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [menuOpen])

  return (
    <TopbarProvider>
      {/* Sidebar */}
      <aside style={{
        position: 'fixed',
        top: 0,
        left: 0,
        width: 'var(--sidebar-w)',
        height: '100vh',
        background: 'var(--bg-sidebar)',
        borderRight: '1px solid var(--border)',
        display: 'flex',
        flexDirection: 'column',
        zIndex: 200,
      }}>
        {/* Logo */}
        <div style={{ padding: '20px 20px 16px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <div style={{
              width: '40px',
              height: '40px',
              background: 'linear-gradient(135deg, var(--accent), #0099aa)',
              borderRadius: '10px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontFamily: 'var(--font-display)',
              fontWeight: 700,
              fontSize: '16px',
              color: '#000',
            }}>УК</div>
            <div>
              <div style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '15px', color: 'var(--text-primary)' }}>УК Панель</div>
              <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>management system</div>
            </div>
          </div>
        </div>

        {/* Nav */}
        <nav style={{ flex: 1, padding: '8px 12px', overflowY: 'auto' }}>
          <div style={{ marginBottom: '4px', padding: '4px 8px', fontSize: '10px', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
            Основное
          </div>
          {NAV_ITEMS.map(({ to, label, Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              style={({ isActive }) => ({
                display: 'flex',
                alignItems: 'center',
                gap: '10px',
                padding: '9px 12px',
                borderRadius: 'var(--radius-sm)',
                marginBottom: '2px',
                textDecoration: 'none',
                fontSize: '14px',
                fontWeight: isActive ? 600 : 400,
                color: isActive ? 'var(--accent)' : 'var(--text-secondary)',
                background: isActive ? 'var(--accent-dim)' : 'transparent',
                borderLeft: isActive ? '3px solid var(--accent)' : '3px solid transparent',
                transition: 'all 0.15s',
              })}
            >
              <Icon size={16} />
              {label}
            </NavLink>
          ))}

          <div style={{ margin: '12px 0 4px', padding: '4px 8px', fontSize: '10px', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
            Внешнее
          </div>
          <NavLink
            to="/resident-board"
            style={({ isActive }) => ({
              display: 'flex',
              alignItems: 'center',
              gap: '10px',
              padding: '9px 12px',
              borderRadius: 'var(--radius-sm)',
              textDecoration: 'none',
              fontSize: '14px',
              fontWeight: isActive ? 600 : 400,
              color: isActive ? 'var(--accent)' : 'var(--text-secondary)',
              background: isActive ? 'var(--accent-dim)' : 'transparent',
              borderLeft: isActive ? '3px solid var(--accent)' : '3px solid transparent',
            })}
          >
            <BookOpen size={16} />
            Табло жителей
          </NavLink>
        </nav>

        {/* User block */}
        <div ref={menuRef} style={{ position: 'relative', padding: '8px 12px', borderTop: '1px solid var(--border)' }}>
          <button
            onClick={() => setMenuOpen(o => !o)}
            style={{
              width: '100%',
              background: menuOpen ? 'var(--bg-surface)' : 'none',
              border: 'none',
              borderRadius: 'var(--radius-sm)',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '10px',
              padding: '8px',
              transition: 'background 0.15s',
            }}
          >
            <div style={{
              width: '36px', height: '36px', flexShrink: 0,
              background: 'linear-gradient(135deg, var(--accent), #0099aa)',
              borderRadius: '50%',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '14px', color: '#000',
            }}>{initials}</div>
            <div style={{ overflow: 'hidden', flex: 1, textAlign: 'left' }}>
              <div style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                {user?.first_name ?? 'Пользователь'}
              </div>
              <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                {user?.roles?.[0] ?? 'manager'}
              </div>
            </div>
            <span style={{ fontSize: '10px', color: 'var(--text-muted)', flexShrink: 0 }}>
              {menuOpen ? '▲' : '▼'}
            </span>
          </button>

          {menuOpen && (
            <div style={{
              position: 'absolute',
              bottom: 'calc(100% - 4px)',
              left: 12,
              right: 12,
              background: 'var(--bg-card)',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius)',
              overflow: 'hidden',
              boxShadow: '0 -8px 24px rgba(0,0,0,0.3)',
              zIndex: 300,
            }}>
              <button
                onClick={() => { setMenuOpen(false); navigate(`/dashboard/employees/${user?.id}`) }}
                style={{
                  width: '100%', background: 'none', border: 'none', cursor: 'pointer',
                  padding: '10px 16px', textAlign: 'left',
                  fontSize: '13px', color: 'var(--text-primary)',
                  fontFamily: 'var(--font-display)',
                  display: 'flex', alignItems: 'center', gap: '10px',
                }}
                onMouseEnter={e => (e.currentTarget.style.background = 'var(--bg-surface)')}
                onMouseLeave={e => (e.currentTarget.style.background = 'none')}
              >
                <span>👤</span> Профиль
              </button>
              <div style={{ height: 1, background: 'var(--border)', margin: '0 12px' }} />
              <button
                onClick={async () => { setMenuOpen(false); await logout(); navigate('/login') }}
                style={{
                  width: '100%', background: 'none', border: 'none', cursor: 'pointer',
                  padding: '10px 16px', textAlign: 'left',
                  fontSize: '13px', color: 'var(--red)',
                  fontFamily: 'var(--font-display)',
                  display: 'flex', alignItems: 'center', gap: '10px',
                }}
                onMouseEnter={e => (e.currentTarget.style.background = 'var(--bg-surface)')}
                onMouseLeave={e => (e.currentTarget.style.background = 'none')}
              >
                <span>→</span> Выйти
              </button>
            </div>
          )}
        </div>
      </aside>

      {/* Topbar */}
      <TopbarInner />

      {/* Main content */}
      <main style={{
        marginLeft: 'var(--sidebar-w)',
        marginTop: 'var(--topbar-h)',
        minHeight: 'calc(100vh - var(--topbar-h))',
        background: 'var(--bg-root)',
        overflowY: 'auto',
      }}>
        <Outlet />
      </main>
    </TopbarProvider>
  )
}
