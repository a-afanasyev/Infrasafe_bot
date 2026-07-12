export function Loading({ text = 'Загрузка…' }: { text?: string }) {
  return <div className="state state-loading">{text}</div>;
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const message = error instanceof Error ? error.message : 'Неизвестная ошибка';
  return (
    <div className="state state-error">
      <span>Ошибка: {message}</span>
      {onRetry && (
        <button className="btn btn-sm" onClick={onRetry}>
          Повторить
        </button>
      )}
    </div>
  );
}

export function Empty({ text = 'Нет данных' }: { text?: string }) {
  return <div className="state state-empty">{text}</div>;
}
