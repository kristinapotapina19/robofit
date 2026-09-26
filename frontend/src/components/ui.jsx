import { useEffect } from 'react'

export function Loading({ text = 'Загрузка…' }) {
  return <div className="loading"><div className="spin" />{text}</div>
}

export function Modal({ title, onClose, children, wide }) {
  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])
  return (
    <div className="overlay" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className={`modal ${wide ? 'wide' : ''}`} role="dialog" aria-label={title}>
        <div className="modal-head">
          <h3>{title}</h3>
          <div className="spacer" />
          <button className="btn ghost small" onClick={onClose} aria-label="Закрыть">✕</button>
        </div>
        {children}
      </div>
    </div>
  )
}

export function Toast({ toast, onDone }) {
  useEffect(() => {
    if (!toast) return
    const t = setTimeout(onDone, toast.bad ? 6000 : 3000)
    return () => clearTimeout(t)
  }, [toast, onDone])
  if (!toast) return null
  return <div className={`toast ${toast.bad ? 'bad' : ''}`} role="status">{toast.text}</div>
}

export function ErrorBox({ error, onRetry }) {
  if (!error) return null
  const list = error.detail?.errors
  return (
    <div className="alert bad">
      <b>{error.message}</b>
      {list && <ul style={{ margin: '6px 0 0', paddingLeft: 18 }}>
        {list.map((e) => <li key={e.label}>{e.label}: {e.message}. {e.fix}</li>)}
      </ul>}
      {onRetry && <div className="mt-s"><button className="btn small" onClick={onRetry}>Повторить</button></div>}
    </div>
  )
}

export function Info({ children, kind = 'info' }) {
  return <div className={`alert ${kind}`}>{children}</div>
}

export function ObjectIcon({ code, size = 26 }) {
  const c = 'var(--accent)'
  const icons = {
    warehouse: <path d="M3 10 12 4l9 6v10H3zM7 20v-6h10v6M7 17h10" stroke={c} strokeWidth="1.7" fill="none" strokeLinejoin="round" />,
    airport: <path d="M2 13.5 21 8l1 2-8 4 1 7-2 1-3-6-5 2-1 2-1-1 1-3z" stroke={c} strokeWidth="1.6" fill="none" strokeLinejoin="round" />,
    clinic: <g stroke={c} strokeWidth="1.7" fill="none"><rect x="4" y="4" width="16" height="17" rx="2" /><path d="M12 8v7M8.5 11.5h7" /></g>,
    custom: <g stroke={c} strokeWidth="1.7" fill="none"><rect x="4" y="9" width="16" height="10" rx="3" /><circle cx="9" cy="14" r="1.5" /><circle cx="15" cy="14" r="1.5" /><path d="M12 9V5m0 0h2" /></g>,
  }
  return <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true">{icons[code] || icons.custom}</svg>
}
