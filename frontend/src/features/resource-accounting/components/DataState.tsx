import { useTranslation } from 'react-i18next';

export function Loading({ text }: { text?: string }) {
  const { t } = useTranslation();
  return <div className="state state-loading">{text ?? t('resourceAccounting.state.loading')}</div>;
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const { t } = useTranslation();
  const message =
    error instanceof Error ? error.message : t('resourceAccounting.state.unknownError');
  return (
    <div className="state state-error">
      <span>{t('resourceAccounting.state.error', { message })}</span>
      {onRetry && (
        <button className="btn btn-sm" onClick={onRetry}>
          {t('resourceAccounting.state.retry')}
        </button>
      )}
    </div>
  );
}

export function Empty({ text }: { text?: string }) {
  const { t } = useTranslation();
  return <div className="state state-empty">{text ?? t('resourceAccounting.state.empty')}</div>;
}
