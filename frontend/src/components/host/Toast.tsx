import { useEffect } from 'react'

export type ToastState = { id: number; text: string; tone?: 'ok' | 'plain' } | null

export default function Toast({ toast, onDone }: { toast: ToastState; onDone: () => void }) {
  useEffect(() => {
    if (!toast) return
    const t = setTimeout(onDone, 4200)
    return () => clearTimeout(t)
  }, [toast, onDone])

  if (!toast) return null
  return (
    <div className={`toast ${toast.tone ?? 'ok'}`} role="status" aria-live="polite">
      {toast.tone !== 'plain' && <span className="toast-check" aria-hidden="true" />}
      <span>{toast.text}</span>
      <button className="toast-x" onClick={onDone} aria-label="Dismiss">
        ×
      </button>
    </div>
  )
}
