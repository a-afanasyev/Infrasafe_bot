import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { publicClient } from '../api/client'
import { isValidTelegramAuth } from '../utils/telegramAuth'
import { useAuthStore } from '../stores/authStore'
import { cn } from '@/lib/utils'
import LanguageSwitcher from '../components/shared/LanguageSwitcher'
import { safeNextPath } from '../utils/safeNextPath'
import { usePageTitle } from '../hooks/usePageTitle'
import { brand } from '../brand/brand'

// Telegram login-widget привязан к конкретному боту (data-telegram-login) и
// работает только на домене, зарегистрированном у этого бота в BotFather.
// Параметризуем через VITE_BOT_USERNAME (build-time), фолбэк — прод infrasafe.uz.
// Напр. profk.uz собирается с VITE_BOT_USERNAME=profkbot.
const BOT_USERNAME = import.meta.env.VITE_BOT_USERNAME ?? 'infrasafebot'

export default function LoginPage() {
  const { t } = useTranslation()
  usePageTitle(t('login.subtitle')) // QA-03: иначе document.title оставался от предыдущей страницы
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [focusedField, setFocusedField] = useState<string | null>(null)
  const [mfaToken, setMfaToken] = useState<string | null>(null)
  const [otpCode, setOtpCode] = useState('')
  const [otpTimer, setOtpTimer] = useState(0)
  const [canResend, setCanResend] = useState(false)
  const { login } = useAuthStore()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  // Deep-link return-to set by ProtectedRoute (e.g. /login?next=%2Fdashboard%3Frequest%3D...).
  const next = safeNextPath(searchParams.get('next'))

  useEffect(() => {
    ;(window as unknown as { onTelegramAuth?: (u: unknown) => void }).onTelegramAuth = async (tgUser: unknown) => {
      // FE-04: внешний payload от Telegram-виджета — валидируем до POST.
      if (!isValidTelegramAuth(tgUser)) {
        setError(t('login.telegramError'))
        return
      }
      setError('')
      setLoading(true)
      try {
        // FE-047: publicClient — без 401-interceptor (refresh→redirect стирал ошибку)
        await publicClient.post('/api/v2/auth/telegram-widget', tgUser)
        await login()
        navigate(next)
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
      delete (window as unknown as { onTelegramAuth?: (u: unknown) => void }).onTelegramAuth
    }
  }, [login, navigate, t, next])

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      // FE-047: publicClient — 401 (неверный логин) показывает inline-ошибку,
      // а не уходит в refresh→redirect, перетирающий setError.
      const { data } = await publicClient.post('/api/v2/auth/login', { email, password })
      if (data.mfa_required) {
        setMfaToken(data.mfa_token)
        setOtpTimer(300)
        setCanResend(false)
        setTimeout(() => setCanResend(true), 60000)
      } else {
        await login()
        navigate(next)
      }
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(detail || t('login.error'))
      toast.error(t('login.loginError'), { description: detail || t('login.error') })
    } finally {
      setLoading(false)
    }
  }

  const handleVerifyOtp = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await publicClient.post('/api/v2/auth/login/verify-otp', {
        mfa_token: mfaToken,
        code: otpCode,
      })
      await login()
      navigate('/dashboard')
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(detail || 'Invalid code')
    } finally {
      setLoading(false)
    }
  }

  const handleResendOtp = async () => {
    if (!canResend || !mfaToken) return
    try {
      await publicClient.post('/api/v2/auth/login/resend-otp', { mfa_token: mfaToken })
      setCanResend(false)
      setOtpTimer(300)
      setTimeout(() => setCanResend(true), 60000)
      toast.success('Код отправлен повторно')
    } catch {
      setError('Не удалось отправить код')
    }
  }

  useEffect(() => {
    if (otpTimer <= 0) return
    const interval = setInterval(() => {
      setOtpTimer(prev => {
        if (prev <= 1) {
          clearInterval(interval)
          return 0
        }
        return prev - 1
      })
    }, 1000)
    return () => clearInterval(interval)
  }, [otpTimer])

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
            linear-gradient(rgba(var(--accent-rgb),0.03) 1px, transparent 1px),
            linear-gradient(90deg, rgba(var(--accent-rgb),0.03) 1px, transparent 1px)
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
          background: 'radial-gradient(ellipse, rgba(var(--accent-rgb),0.07) 0%, transparent 70%)',
        }}
      />

      <div className="w-full max-w-[400px] px-4 relative">
        {/* Logo mark */}
        <div className="flex flex-col items-center mb-7">
          <img
            src={`${import.meta.env.BASE_URL}${brand.logoMark}`}
            alt={brand.displayName}
            className="w-[52px] h-[52px] mb-3 rounded-full shadow-[var(--auth-logo-shadow)]"
          />
          <div className="font-[family-name:var(--font-display)] font-bold text-[22px] text-text-primary tracking-tight">
            Сервисная панель
          </div>
          <div className="text-xs text-text-muted font-[family-name:var(--font-body)] mt-1">
            {t('login.subtitle')}
          </div>
        </div>

        {/* Card */}
        <div className="bg-bg-card border border-[color:var(--auth-card-border)] rounded-2xl p-8 px-7 shadow-[var(--auth-card-shadow)]">

          {/* Telegram widget */}
          <div id="telegram-section">
            <div
              id="telegram-login-widget"
              className="flex justify-center mb-5 min-h-[48px]"
            />
            <div className="flex items-center gap-3 mb-5">
              <div className="flex-1 h-px bg-border-default" />
              <span className="text-[11px] text-text-muted font-[family-name:var(--font-body)] tracking-wider uppercase">{t('login.or')}</span>
              <div className="flex-1 h-px bg-border-default" />
            </div>
          </div>

          {/* Form */}
          {mfaToken ? (
            <form onSubmit={handleVerifyOtp} className="flex flex-col gap-4">
              <div className="text-center mb-1">
                <div className="text-sm text-text-secondary font-[family-name:var(--font-body)]">
                  Код отправлен в Telegram
                </div>
                {otpTimer > 0 && (
                  <div className="text-xs text-text-muted font-[family-name:var(--font-body)] mt-1">
                    {String(Math.floor(otpTimer / 60)).padStart(2, '0')}:{String(otpTimer % 60).padStart(2, '0')}
                  </div>
                )}
              </div>

              <div>
                <label className="block text-xs font-semibold text-text-secondary mb-1.5 font-[family-name:var(--font-display)] tracking-wide">
                  Код подтверждения
                </label>
                <input
                  type="text"
                  inputMode="numeric"
                  pattern="[0-9]*"
                  maxLength={6}
                  placeholder="000000"
                  value={otpCode}
                  onChange={(e) => setOtpCode(e.target.value.replace(/\D/g, ''))}
                  onFocus={() => setFocusedField('otp')}
                  onBlur={() => setFocusedField(null)}
                  autoFocus
                  className={cn(
                    'w-full rounded-[10px] py-[11px] px-3.5 text-sm text-text-primary font-[family-name:var(--font-body)] outline-none transition-all box-border text-center tracking-[0.3em] text-lg',
                    focusedField === 'otp'
                      ? 'bg-accent/[.04] border-[1.5px] border-accent'
                      : 'bg-bg-root border-[1.5px] border-border-default'
                  )}
                />
              </div>

              {error && (
                <div className="flex items-center gap-2 p-2.5 px-3 bg-red/10 border border-red/20 rounded-lg">
                  <span className="text-[13px]">!</span>
                  <span className="text-[13px] text-red font-[family-name:var(--font-body)]">{error}</span>
                </div>
              )}

              <button
                type="submit"
                disabled={loading || otpCode.length < 6}
                className={cn(
                  'rounded-[10px] p-3 text-sm font-bold text-[color:var(--accent-contrast)] font-[family-name:var(--font-display)] tracking-wide transition-all mt-1 border-none',
                  loading || otpCode.length < 6
                    ? 'bg-accent/50 cursor-not-allowed'
                    : 'bg-accent cursor-pointer hover:bg-[var(--accent-hover)]'
                )}
              >
                {loading ? t('login.submitting') : 'Подтвердить'}
              </button>

              <div className="flex items-center justify-between text-xs font-[family-name:var(--font-body)]">
                <button
                  type="button"
                  onClick={() => { setMfaToken(null); setOtpCode(''); setError(''); setOtpTimer(0) }}
                  className="text-text-muted hover:text-text-secondary transition-colors cursor-pointer bg-transparent border-none p-0"
                >
                  Назад
                </button>
                <button
                  type="button"
                  onClick={handleResendOtp}
                  disabled={!canResend}
                  className={cn(
                    'bg-transparent border-none p-0 transition-colors',
                    canResend
                      ? 'text-accent hover:text-[var(--accent-hover)] cursor-pointer'
                      : 'text-text-muted cursor-not-allowed'
                  )}
                >
                  Отправить повторно
                </button>
              </div>
            </form>
          ) : (
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
                      : 'bg-bg-root border-[1.5px] border-border-default'
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
                      : 'bg-bg-root border-[1.5px] border-border-default'
                  )}
                  autoComplete="current-password"
                />
              </div>

              {error && (
                <div className="flex items-center gap-2 p-2.5 px-3 bg-red/10 border border-red/20 rounded-lg">
                  <span className="text-[13px]">!</span>
                  <span className="text-[13px] text-red font-[family-name:var(--font-body)]">{error}</span>
                </div>
              )}

              <button
                type="submit"
                disabled={loading}
                className={cn(
                  'rounded-[10px] p-3 text-sm font-bold text-[color:var(--accent-contrast)] font-[family-name:var(--font-display)] tracking-wide transition-all mt-1 border-none',
                  loading
                    ? 'bg-accent/50 cursor-not-allowed'
                    : 'bg-accent cursor-pointer hover:bg-[var(--accent-hover)]'
                )}
              >
                {loading ? t('login.submitting') : t('login.submit')}
              </button>
            </form>
          )}
        </div>
      </div>
    </div>
  )
}
