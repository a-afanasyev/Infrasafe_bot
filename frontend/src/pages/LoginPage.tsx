import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { apiClient } from '../api/client'
import { useAuthStore } from '../stores/authStore'
import { cn } from '@/lib/utils'
import LanguageSwitcher from '../components/shared/LanguageSwitcher'

const BOT_USERNAME = import.meta.env.VITE_BOT_USERNAME ?? 'infrasafebot'

export default function LoginPage() {
  const { t } = useTranslation()
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
        setError(t('login.telegramError'))
        toast.error(t('login.loginError'), { description: t('login.telegramError') })
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
      setError(t('login.error'))
      toast.error(t('login.loginError'), { description: t('login.error') })
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-bg-root relative overflow-hidden">
      {/* Language switcher */}
      <div className="absolute top-4 right-4 z-10">
        <LanguageSwitcher />
      </div>
      {/* Background grid */}
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          backgroundImage: `
            linear-gradient(rgba(0,212,170,0.03) 1px, transparent 1px),
            linear-gradient(90deg, rgba(0,212,170,0.03) 1px, transparent 1px)
          `,
          backgroundSize: '48px 48px',
        }}
      />

      {/* Accent glow */}
      <div
        className="absolute pointer-events-none"
        style={{
          top: '20%',
          left: '50%',
          transform: 'translateX(-50%)',
          width: 600,
          height: 300,
          background: 'radial-gradient(ellipse, rgba(0,212,170,0.07) 0%, transparent 70%)',
        }}
      />

      <div className="w-full max-w-[400px] px-4 relative">
        {/* Logo mark */}
        <div className="flex flex-col items-center mb-7">
          <div className="w-[52px] h-[52px] rounded-[14px] flex items-center justify-center font-[family-name:var(--font-display)] font-extrabold text-xl text-[#001a14] mb-3 shadow-[0_0_32px_rgba(0,212,170,0.3)]"
            style={{ background: 'linear-gradient(135deg, var(--accent), #0099aa)' }}
          >
            УК
          </div>
          <div className="font-[family-name:var(--font-display)] font-bold text-[22px] text-text-primary tracking-tight">
            UK Management
          </div>
          <div className="text-xs text-text-muted font-[family-name:var(--font-body)] mt-1">
            {t('login.subtitle')}
          </div>
        </div>

        {/* Card */}
        <div className="bg-bg-card border border-white/[.08] rounded-2xl p-8 px-7 shadow-[0_32px_80px_rgba(0,0,0,0.5),0_0_0_1px_rgba(0,212,170,0.05)]">

          {/* Telegram widget */}
          <div id="telegram-section">
            <div
              id="telegram-login-widget"
              className="flex justify-center mb-5 min-h-[48px]"
            />
            <div className="flex items-center gap-3 mb-5">
              <div className="flex-1 h-px bg-white/[.07]" />
              <span className="text-[11px] text-text-muted font-[family-name:var(--font-body)] tracking-wider uppercase">{t('login.or')}</span>
              <div className="flex-1 h-px bg-white/[.07]" />
            </div>
          </div>

          {/* Form */}
          <form onSubmit={handleLogin} className="flex flex-col gap-4">

            <div>
              <label className="block text-xs font-semibold text-text-secondary mb-1.5 font-[family-name:var(--font-display)] tracking-wide">
                Email
              </label>
              <input
                type="email"
                placeholder="admin@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                onFocus={() => setFocusedField('email')}
                onBlur={() => setFocusedField(null)}
                className={cn(
                  'w-full rounded-[10px] py-[11px] px-3.5 text-sm text-text-primary font-[family-name:var(--font-body)] outline-none transition-all box-border',
                  focusedField === 'email'
                    ? 'bg-accent/[.04] border-[1.5px] border-accent'
                    : 'bg-bg-root border-[1.5px] border-white/10'
                )}
                autoComplete="email"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-text-secondary mb-1.5 font-[family-name:var(--font-display)] tracking-wide">
                {t('login.password')}
              </label>
              <input
                type="password"
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                onFocus={() => setFocusedField('password')}
                onBlur={() => setFocusedField(null)}
                className={cn(
                  'w-full rounded-[10px] py-[11px] px-3.5 text-sm text-text-primary font-[family-name:var(--font-body)] outline-none transition-all box-border',
                  focusedField === 'password'
                    ? 'bg-accent/[.04] border-[1.5px] border-accent'
                    : 'bg-bg-root border-[1.5px] border-white/10'
                )}
                autoComplete="current-password"
              />
            </div>

            {error && (
              <div className="flex items-center gap-2 p-2.5 px-3 bg-red/10 border border-red/20 rounded-lg">
                <span className="text-[13px]">⚠</span>
                <span className="text-[13px] text-[#f87171] font-[family-name:var(--font-body)]">{error}</span>
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className={cn(
                'rounded-[10px] p-3 text-sm font-bold text-[#001a14] font-[family-name:var(--font-display)] tracking-wide transition-all mt-1 border-none',
                loading
                  ? 'bg-accent/50 cursor-not-allowed'
                  : 'bg-accent cursor-pointer hover:bg-[#00f0c0]'
              )}
            >
              {loading ? t('login.submitting') : t('login.submit')}
            </button>
          </form>
        </div>
      </div>
    </div>
  )
}
