interface EmptyStateProps {
  icon: string
  title: string
  subtitle?: string
}

export default function EmptyState({ icon, title, subtitle }: EmptyStateProps) {
  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      gap: '12px',
      padding: '48px 24px',
      color: 'var(--text-secondary)',
      textAlign: 'center',
    }}>
      <span style={{ fontSize: '48px', lineHeight: 1 }}>{icon}</span>
      <p style={{ margin: 0, fontFamily: 'var(--font-display)', fontSize: '16px', fontWeight: 600, color: 'var(--text-primary)' }}>{title}</p>
      {subtitle && <p style={{ margin: 0, fontSize: '14px', color: 'var(--text-muted)' }}>{subtitle}</p>}
    </div>
  )
}
