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

  return (
    <div style={{
      minHeight: '100vh',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      background: 'var(--bg-root)',
    }}>
      <div style={{
        background: 'var(--bg-card)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius)',
        padding: '40px 36px',
        width: '100%',
        maxWidth: 380,
        boxShadow: '0 24px 64px rgba(0,0,0,0.4)',
      }}>
        <h1 style={{
          fontFamily: 'var(--font-display)',
          fontSize: '22px',
          fontWeight: 700,
          color: 'var(--text-primary)',
          textAlign: 'center',
          marginBottom: '28px',
          margin: '0 0 28px',
        }}>
          UK Management
        </h1>

        <div
          id="telegram-login-widget"
          style={{ display: 'flex', justifyContent: 'center', marginBottom: '20px', minHeight: 48 }}
        />

        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '20px' }}>
          <div style={{ flex: 1, height: 1, background: 'var(--border)' }} />
          <span style={{ fontSize: '12px', color: 'var(--text-muted)', fontFamily: 'var(--font-body)' }}>или</span>
          <div style={{ flex: 1, height: 1, background: 'var(--border)' }} />
        </div>

        <form onSubmit={handleLogin} style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
          <input
            type="email"
            placeholder="Email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            style={{
              background: 'var(--bg-surface)',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius-sm)',
              padding: '10px 14px',
              fontSize: '14px',
              color: 'var(--text-primary)',
              fontFamily: 'var(--font-body)',
              outline: 'none',
            }}
          />
          <input
            type="password"
            placeholder="Пароль"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            style={{
              background: 'var(--bg-surface)',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius-sm)',
              padding: '10px 14px',
              fontSize: '14px',
              color: 'var(--text-primary)',
              fontFamily: 'var(--font-body)',
              outline: 'none',
            }}
          />
          {error && (
            <p style={{ fontSize: '13px', color: 'var(--red)', margin: 0 }}>{error}</p>
          )}
          <button
            type="submit"
            disabled={loading}
            style={{
              background: 'var(--accent)',
              border: 'none',
              borderRadius: 'var(--radius-sm)',
              padding: '11px',
              fontSize: '14px',
              fontWeight: 600,
              color: '#000',
              cursor: loading ? 'not-allowed' : 'pointer',
              fontFamily: 'var(--font-display)',
              opacity: loading ? 0.6 : 1,
              marginTop: 4,
            }}
          >
            {loading ? 'Вход...' : 'Войти'}
          </button>
        </form>
      </div>
    </div>
  )
}
