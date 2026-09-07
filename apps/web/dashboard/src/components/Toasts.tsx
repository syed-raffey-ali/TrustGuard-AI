import type { ToastItem } from '../types';

export default function Toasts({
  toasts,
  onDismiss,
}: {
  toasts: ToastItem[];
  onDismiss: (id: number) => void;
}) {
  if (toasts.length === 0) return null;
  return (
    <div className="toast-stack" role="status" aria-live="polite">
      {toasts.map((t) => (
        <button
          key={t.id}
          type="button"
          className={`toast toast-${t.kind}`}
          onClick={() => onDismiss(t.id)}
          title="Click to dismiss"
        >
          <strong className="toast-title">{t.title}</strong>
          {t.body && <span className="toast-body">{t.body}</span>}
        </button>
      ))}
    </div>
  );
}
