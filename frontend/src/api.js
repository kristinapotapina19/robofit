// Клиент REST API. Адрес задаётся VITE_API_URL при сборке; по умолчанию /api
// того же хоста (в Docker его проксирует nginx, в разработке — Vite).
const BASE = (import.meta.env.VITE_API_URL || '/api').replace(/\/$/, '')

let token = null
try { token = localStorage.getItem('robofit_token') } catch { /* приватный режим */ }

export function setToken(t) {
  token = t
  try { t ? localStorage.setItem('robofit_token', t) : localStorage.removeItem('robofit_token') } catch { /* */ }
}

export class ApiError extends Error {
  constructor(status, detail) {
    const msg = typeof detail === 'string' ? detail
      : detail?.message || (Array.isArray(detail) ? detail.map(d => d.msg).join('; ') : 'Ошибка запроса')
    super(msg)
    this.status = status
    this.detail = detail
  }
}

async function request(method, path, body, { raw = false, form = false } = {}) {
  const headers = {}
  if (token) headers.Authorization = `Bearer ${token}`
  let payload
  if (form) payload = body
  else if (body !== undefined) { headers['Content-Type'] = 'application/json'; payload = JSON.stringify(body) }
  let res
  try {
    res = await fetch(BASE + path, { method, headers, body: payload })
  } catch {
    throw new ApiError(0, 'Сервер недоступен. Проверьте, что API запущен (docker compose up), и повторите.')
  }
  if (!res.ok) {
    let detail = res.statusText
    try { detail = (await res.json()).detail } catch { /* */ }
    throw new ApiError(res.status, detail)
  }
  if (raw) return res
  return res.json()
}

export const api = {
  get: (p) => request('GET', p),
  post: (p, b) => request('POST', p, b ?? {}),
  put: (p, b) => request('PUT', p, b),
  del: (p) => request('DELETE', p),
  upload: (p, file) => { const f = new FormData(); f.append('file', file); return request('POST', p, f, { form: true }) },
  async download(path, body, fallbackName) {
    const res = body === undefined ? await request('GET', path, undefined, { raw: true })
      : await request('POST', path, body, { raw: true })
    const blob = await res.blob()
    const cd = res.headers.get('Content-Disposition') || ''
    const m = cd.match(/filename\*=UTF-8''([^;]+)/)
    const name = m ? decodeURIComponent(m[1]) : fallbackName
    saveBlob(blob, name)
  },
}

export function saveBlob(blob, name) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = name
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
