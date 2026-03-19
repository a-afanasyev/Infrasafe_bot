import { Component, type ErrorInfo, type ReactNode } from 'react'
import { AlertTriangle } from 'lucide-react'

interface Props {
  children: ReactNode
}

interface State {
  hasError: boolean
}

export default class GlobalErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props)
    this.state = { hasError: false }
  }

  static getDerivedStateFromError(): State {
    return { hasError: true }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('[GlobalErrorBoundary]', error, info.componentStack)
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
            minHeight: '100vh',
            gap: '16px',
            background: 'var(--color-bg-root)',
            color: 'var(--color-text-primary)',
            padding: '24px',
            textAlign: 'center',
          }}
        >
          <AlertTriangle size={48} style={{ color: 'var(--red, #ef4444)' }} />
          <h1 style={{ margin: 0, fontSize: '24px', fontWeight: 600 }}>
            Что-то пошло не так
          </h1>
          <p style={{ margin: 0, color: 'var(--color-text-secondary)', maxWidth: '420px' }}>
            Произошла непредвиденная ошибка. Попробуйте обновить страницу.
          </p>
          <button
            onClick={() => window.location.reload()}
            style={{
              marginTop: '8px',
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
            Обновить страницу
          </button>
        </div>
      )
    }

    return this.props.children
  }
}
