import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { apiClient } from '../api/client'
import { useAuthStore } from '../stores/authStore'

const BOT_USERNAME = 'infrasafebot'

export default function LoginPage() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [focusedField, setFocusedField] = useState<string | null>(null)
  const { login } = useAuthStore()
  const navigate = useNavigate()

  useEffect(() => {
    ;(window as any).onTelegramAuth = async (tgUser: Record<string, unknown>) => {
      setError('')
      setLoading(true)
      try {
        const { data } = await apiClient.post('/api/v2/auth/telegram-widget', tgUser)
        await login(data.access_token, data.refresh_token)
        navigate('/dashboard')
      } catch {
        setError('Аккаунт не найден или не одобрен')
      } finally {
        setLoading(false)
      }
    }

    const container = document.getElementById('telegram-login-widget')
    if (container) {
      while (container.firstChild) container.removeChild(container.firstChild)
      const script = document.createElement('script')
      script.src = 'https://telegram.org/js/telegram-widget.js?22'
      script.async = true
      script.setAttribute('data-telegram-login', BOT_USERNAME)
      script.setAttribute('data-size', 'large')
      script.setAttribute('data-onauth', 'onTelegramAuth(user)')
      script.setAttribute('data-request-access', 'write')

      script.onerror = () => {
        const wrapper = document.getElementById('telegram-section')
        if (wrapper) wrapper.style.display = 'none'
      }
      script.onload = () => {
        setTimeout(() => {
          const iframe = container.querySelector('iframe')
          if (!iframe || iframe.offsetHeight > 80) {
            const wrapper = document.getElementById('telegram-section')
            if (wrapper) wrapper.style.display = 'none'
          }
        }, 1500)
      }

      container.appendChild(script)
    }

    return () => {
      delete (window as any).onTelegramAuth
    }
  }, [login, navigate])

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const { data } = await apiClient.post('/api/v2/auth/login', { email, password })
      await login(data.access_token, data.refresh_token)
      navigate('/dashboard')
    } catch {
      setError('Неверные учётные данные')
    } finally {
      setLoading(false)
    }
  }

  const inputStyle = (field: string): React.CSSProperties => ({
    width: '100%',
    background: focusedField === field ? 'rgba(0,212,170,0.04)' : 'var(--bg-root)',
    border: `1.5px solid ${focusedField === field ? 'var(--accent)' : 'rgba(255,255,255,0.1)'}`,
    borderRadius: 10,
    padding: '11px 14px',
    fontSize: '14px',
    color: 'var(--text-primary)',
    fontFamily: 'var(--font-body)',
    outline: 'none',
    transition: 'border-color 0.2s, background 0.2s',
    boxSizing: 'border-box',
  })

  return (
    <div style={{
      minHeight: '100vh',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      background: 'var(--bg-root)',
      position: 'relative',
      overflow: 'hidden',
    }}>
      {/* Background grid */}
      <div style={{
        position: 'absolute',
        inset: 0,
        backgroundImage: `
          linear-gradient(rgba(0,212,170,0.03) 1px, transparent 1px),
          linear-gradient(90deg, rgba(0,212,170,0.03) 1px, transparent 1px)
        `,
        backgroundSize: '48px 48px',
        pointerEvents: 'none',
      }} />

      {/* Accent glow */}
      <div style={{
        position: 'absolute',
        top: '20%',
        left: '50%',
        transform: 'translateX(-50%)',
        width: 600,
        height: 300,
        background: 'radial-gradient(ellipse, rgba(0,212,170,0.07) 0%, transparent 70%)',
        pointerEvents: 'none',
      }} />

      <div style={{ width: '100%', maxWidth: 400, padding: '0 16px', position: 'relative' }}>
        {/* Logo mark */}
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', marginBottom: 28 }}>
          <div style={{
            width: 52,
            height: 52,
            background: 'linear-gradient(135deg, var(--accent), #0099aa)',
            borderRadius: 14,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontFamily: 'var(--font-display)',
            fontWeight: 800,
            fontSize: 20,
            color: '#001a14',
            marginBottom: 12,
            boxShadow: '0 0 32px rgba(0,212,170,0.3)',
          }}>УК</div>
          <div style={{
            fontFamily: 'var(--font-display)',
            fontWeight: 700,
            fontSize: 22,
            color: 'var(--text-primary)',
            letterSpacing: '-0.3px',
          }}>UK Management</div>
          <div style={{
            fontSize: 12,
            color: 'var(--text-muted)',
            fontFamily: 'var(--font-body)',
            marginTop: 4,
          }}>Система управления объектами</div>
        </div>

        {/* Card */}
        <div style={{
          background: 'var(--bg-card)',
          border: '1px solid rgba(255,255,255,0.08)',
          borderRadius: 16,
          padding: '32px 28px',
          boxShadow: '0 32px 80px rgba(0,0,0,0.5), 0 0 0 1px rgba(0,212,170,0.05)',
        }}>

          {/* Telegram widget */}
          <div id="telegram-section">
            <div
              id="telegram-login-widget"
              style={{ display: 'flex', justifyContent: 'center', marginBottom: 20, minHeight: 48 }}
            />
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 20 }}>
              <div style={{ flex: 1, height: 1, background: 'rgba(255,255,255,0.07)' }} />
              <span style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-body)', letterSpacing: '0.5px', textTransform: 'uppercase' }}>или</span>
              <div style={{ flex: 1, height: 1, background: 'rgba(255,255,255,0.07)' }} />
            </div>
          </div>

          {/* Form */}
          <form onSubmit={handleLogin} style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>

            <div>
              <label style={{
                display: 'block',
                fontSize: 12,
                fontWeight: 600,
                color: 'var(--text-secondary)',
                marginBottom: 6,
                fontFamily: 'var(--font-display)',
                letterSpacing: '0.3px',
              }}>Email</label>
              <input
                type="email"
                placeholder="admin@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                onFocus={() => setFocusedField('email')}
                onBlur={() => setFocusedField(null)}
                style={inputStyle('email')}
                autoComplete="email"
              />
            </div>

            <div>
              <label style={{
                display: 'block',
                fontSize: 12,
                fontWeight: 600,
                color: 'var(--text-secondary)',
                marginBottom: 6,
                fontFamily: 'var(--font-display)',
                letterSpacing: '0.3px',
              }}>Пароль</label>
              <input
                type="password"
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                onFocus={() => setFocusedField('password')}
                onBlur={() => setFocusedField(null)}
                style={inputStyle('password')}
                autoComplete="current-password"
              />
            </div>

            {error && (
              <div style={{
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                padding: '10px 12px',
                background: 'rgba(239,68,68,0.1)',
                border: '1px solid rgba(239,68,68,0.2)',
                borderRadius: 8,
              }}>
                <span style={{ fontSize: 13 }}>⚠</span>
                <span style={{ fontSize: 13, color: '#f87171', fontFamily: 'var(--font-body)' }}>{error}</span>
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              style={{
                background: loading ? 'rgba(0,212,170,0.5)' : 'var(--accent)',
                border: 'none',
                borderRadius: 10,
                padding: '12px',
                fontSize: '14px',
                fontWeight: 700,
                color: '#001a14',
                cursor: loading ? 'not-allowed' : 'pointer',
                fontFamily: 'var(--font-display)',
                letterSpacing: '0.3px',
                transition: 'background 0.2s, transform 0.1s',
                marginTop: 4,
              }}
              onMouseEnter={e => { if (!loading) (e.currentTarget as HTMLButtonElement).style.background = '#00f0c0' }}
              onMouseLeave={e => { if (!loading) (e.currentTarget as HTMLButtonElement).style.background = 'var(--accent)' }}
            >
              {loading ? 'Вход...' : 'Войти'}
            </button>
          </form>
        </div>
      </div>
    </div>
  )
}
