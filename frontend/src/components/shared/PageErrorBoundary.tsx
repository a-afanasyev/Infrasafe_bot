import { Component, type ErrorInfo, type ReactNode } from 'react'
import { AlertTriangle } from 'lucide-react'

interface Props {
  children: ReactNode
}

interface State {
  hasError: boolean
}

export default class PageErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props)
    this.state = { hasError: false }
  }

  static getDerivedStateFromError(): State {
    return { hasError: true }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('[PageErrorBoundary]', error, info.componentStack)
  }

  render() {
    if (this.state.hasError) {
      return (
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            minHeight: '60vh',
            gap: '16px',
            color: 'var(--text-primary)',
            padding: '24px',
            textAlign: 'center',
          }}
        >
          <AlertTriangle size={40} style={{ color: 'var(--amber, #f59e0b)' }} />
          <h2 style={{ margin: 0, fontSize: '20px', fontWeight: 600 }}>
            Ошибка загрузки страницы
          </h2>
          <p style={{ margin: 0, color: 'var(--text-secondary)', maxWidth: '400px' }}>
            Не удалось загрузить содержимое. Попробуйте обновить.
          </p>
          <div style={{ display: 'flex', gap: '12px', marginTop: '8px' }}>
            <button
              onClick={() => this.setState({ hasError: false })}
              style={{
                padding: '10px 24px',
                border: 'none',
                borderRadius: 'var(--radius, 8px)',
                background: 'var(--accent)',
                color: '#fff',
                fontSize: '14px',
                fontWeight: 500,
                cursor: 'pointer',
              }}
            >
              Попробовать снова
            </button>
            <button
              onClick={() => { window.location.href = '/dashboard' }}
              style={{
                padding: '10px 24px',
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius, 8px)',
                background: 'transparent',
                color: 'var(--text-primary)',
                fontSize: '14px',
                fontWeight: 500,
                cursor: 'pointer',
              }}
            >
              На главную
            </button>
          </div>
        </div>
      )
    }

    return this.props.children
  }
}
