import { useEffect, useState } from 'react'
import { api, setToken } from '../api.js'
import { fmt, rub, SPEC_LABELS, STATUS } from '../format.js'
import { ErrorBox, Loading, Modal } from './ui.jsx'

export function AuthModal({ onClose, onAuth }) {
  const [mode, setMode] = useState('login')
  const [username, setU] = useState('user@demo')
  const [password, setP] = useState('demo123')
  const [error, setError] = useState(null)
  const submit = async (e) => {
    e.preventDefault()
    setError(null)
    try {
      const r = await api.post(mode === 'login' ? '/auth/login' : '/auth/register', { username, password })
      setToken(r.token)
      onAuth(r.user)
      onClose()
    } catch (err) { setError(err) }
  }
  return (
    <Modal title={mode === 'login' ? 'Вход' : 'Регистрация'} onClose={onClose}>
      <form className="stack" onSubmit={submit}>
        <div className="seg" style={{ alignSelf: 'flex-start' }}>
          <button type="button" className={mode === 'login' ? 'on' : ''} onClick={() => setMode('login')}>Вход</button>
          <button type="button" className={mode === 'register' ? 'on' : ''} onClick={() => { setMode('register'); setU(''); setP('') }}>Регистрация</button>
        </div>
        <label className="field"><span>Логин (e-mail)</span><input type="text" value={username} onChange={e => setU(e.target.value)} autoFocus /></label>
        <label className="field"><span>Пароль (не короче 6 символов)</span><input type="password" value={password} onChange={e => setP(e.target.value)} /></label>
        {error && <ErrorBox error={error} />}
        <button className="btn primary" type="submit">{mode === 'login' ? 'Войти' : 'Зарегистрироваться'}</button>
        {mode === 'login' && <p className="muted" style={{ fontSize: 12.5 }}>Демо-учётки: пользователь <b>user@demo / demo123</b>, администратор <b>admin@demo / admin123</b>.</p>}
      </form>
    </Modal>
  )
}

export function ProjectsModal({ onClose, onOpen, notify }) {
  const [items, setItems] = useState(null)
  const [error, setError] = useState(null)
  const load = () => api.get('/projects').then(setItems).catch(setError)
  useEffect(() => { load() }, [])
  const act = async (fn, msg) => { try { await fn(); notify(msg); load() } catch (e) { notify(e.message, true) } }
  return (
    <Modal title="Мои проекты" onClose={onClose} wide>
      {error && <ErrorBox error={error} />}
      {!items && !error && <Loading />}
      {items && !items.length && <div className="empty">Проектов пока нет. Выполните расчёт и сохраните его на шаге «Сохранение и экспорт».</div>}
      {items && items.length > 0 && (
        <table className="t">
          <thead><tr><th>Проект</th><th>Объект</th><th className="r">Сценариев</th><th>Изменён</th><th /></tr></thead>
          <tbody>{items.map(p => (
            <tr key={p.id}>
              <td><b>{p.title}</b></td>
              <td>{{ warehouse: 'Склад', airport: 'Аэропорт', clinic: 'Медучреждение', custom: 'Другой объект' }[p.object_type]}</td>
              <td className="r">{p.scenarios}</td>
              <td className="muted">{new Date(p.updated_at + 'Z').toLocaleString('ru-RU')}</td>
              <td style={{ whiteSpace: 'nowrap' }}>
                <button className="btn primary small" onClick={async () => { onOpen(await api.get(`/projects/${p.id}`)); onClose() }}>Открыть</button>{' '}
                <button className="btn small" onClick={() => act(() => api.post(`/projects/${p.id}/copy`), 'Проект скопирован')}>Копия</button>{' '}
                <button className="btn small danger" onClick={() => window.confirm(`Удалить проект «${p.title}» со всеми сценариями?`) && act(() => api.del(`/projects/${p.id}`), 'Проект удалён')}>Удалить</button>
              </td>
            </tr>
          ))}</tbody>
        </table>
      )}
    </Modal>
  )
}

export function SolutionModal({ id, onClose }) {
  const [s, setS] = useState(null)
  const [error, setError] = useState(null)
  useEffect(() => { api.get(`/catalog/solutions/${id}`).then(setS).catch(setError) }, [id])
  return (
    <Modal title={s?.name || 'Решение'} onClose={onClose} wide>
      {error && <ErrorBox error={error} />}
      {!s && !error && <Loading />}
      {s && (
        <div className="stack">
          <div className="row"><span className="badge accent">{s.subtype || 'тип не указан'}</span><span className="badge">{STATUS[s.status]}</span>{s.trl && <span className="badge">УГТ {s.trl}</span>}<span className="badge">{s.country}</span></div>
          <p><b>{s.vendor}</b> · {rub(s.price_rub)} <span className="muted">— {s.price_note}</span></p>
          {s.description && <p className="muted" style={{ fontSize: 13 }}>{s.description.slice(0, 700)}{s.description.length > 700 ? '…' : ''}</p>}
          <div><b>Сценарии применения:</b> {(s.scenarios || []).join('; ')}</div>
          {s.cases && <div><b>Кейсы:</b> <span className="muted">{s.cases.slice(0, 400)}</span></div>}
          <table className="t">
            <thead><tr><th>Характеристика</th><th>Значение</th><th>Источник</th><th>Статус</th></tr></thead>
            <tbody>{Object.entries(s.specs).map(([k, v]) => (
              <tr key={k}><td>{SPEC_LABELS[k]?.[0] || k}</td><td className="num">{typeof v.value === 'number' ? fmt(v.value, 2) : v.value} {SPEC_LABELS[k]?.[1] || ''}</td>
                <td className="muted" style={{ fontSize: 12 }}>{String(v.source).startsWith('http') ? <a href={v.source} target="_blank" rel="noreferrer">сайт</a> : ({ parsed_from_name: 'извлечено из названия', parsed_from_description: 'извлечено из описания' }[v.source] || v.source)}</td>
                <td>{v.confirmed ? <span className="badge good">подтверждено</span> : <span className="badge warn">требует проверки</span>}</td></tr>
            ))}
              {!Object.keys(s.specs).length && <tr><td colSpan={4} className="muted">Характеристик в каталоге нет — нужен запрос вендору.</td></tr>}</tbody>
          </table>
          <p className="muted" style={{ fontSize: 12 }}>Источник карточки: {s.source_url ? <a href={s.source_url} target="_blank" rel="noreferrer">{s.data_source}</a> : s.data_source}; обновлено {s.updated_at}.</p>
        </div>
      )}
    </Modal>
  )
}

export function CatalogPage({ objectTypes, onDetail }) {
  const [filters, setFilters] = useState({ object_type: '', subtype: '', status: '', q: '', sort: 'name' })
  const [data, setData] = useState(null)
  const [tree, setTree] = useState(null)
  const [error, setError] = useState(null)
  useEffect(() => { api.get('/catalog/tree').then(setTree).catch(() => {}) }, [])
  useEffect(() => {
    const t = setTimeout(() => {
      const qs = new URLSearchParams(Object.entries(filters).filter(([, v]) => v)).toString()
      api.get(`/catalog/solutions?limit=500&${qs}`).then(setData).catch(setError)
    }, 250)
    return () => clearTimeout(t)
  }, [filters])
  const f = (k) => (e) => setFilters({ ...filters, [k]: e.target.value })
  return (
    <div>
      <div className="card">
        <div className="card-head"><div><h2>Каталог роботизированных решений</h2>
          <p>Каталог организатора (объединён по id, сценарии применения сохранены) и решения из открытых источников с указанием источника и даты. У каждой характеристики — источник и признак подтверждённости.</p></div></div>
        <div className="grid g4" style={{ gridTemplateColumns: '2fr 1fr 1fr 1fr 1fr' }}>
          <input type="text" placeholder="Поиск по названию, вендору, описанию" value={filters.q} onChange={f('q')} />
          <select value={filters.object_type} onChange={f('object_type')}><option value="">Все объекты</option>{objectTypes.filter(o => o.code !== 'custom').map(o => <option key={o.code} value={o.code}>{o.title}</option>)}</select>
          <select value={filters.subtype} onChange={f('subtype')}><option value="">Все типы</option>{(data?.facets.subtypes || []).map(s => <option key={s}>{s}</option>)}</select>
          <select value={filters.status} onChange={f('status')}><option value="">Любой статус</option>{Object.entries(STATUS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>
          <select value={filters.sort} onChange={f('sort')}><option value="name">По названию</option><option value="price_rub">Цена ↑</option><option value="-price_rub">Цена ↓</option><option value="-trl">УГТ ↓</option><option value="vendor">По вендору</option></select>
        </div>
      </div>
      {tree && (
        <div className="card">
          <h3>Иерархия: отрасль → объект → процесс → тип решения</h3>
          <div className="grid g4 mt-s">
            {tree.filter(t => t.object_type !== 'custom').map(t => (
              <div key={t.object_type}>
                <b>{t.industry}: {t.title}</b>
                {t.processes.map(p => (
                  <div key={p.code} style={{ marginTop: 6, fontSize: 12.5 }}>
                    <div>{p.title}</div>
                    <div className="muted">{p.types.length ? p.types.map(x => `${x.subtype} (${x.count})`).join(', ') : 'нет решений в каталоге'}</div>
                  </div>
                ))}
              </div>
            ))}
          </div>
        </div>
      )}
      <div className="card">
        {error && <ErrorBox error={error} />}
        {!data && !error && <Loading />}
        {data && <>
          <p className="muted" style={{ marginBottom: 8 }}>Найдено: {data.total}</p>
          <div className="tablewrap">
            <table className="t">
              <thead><tr><th>Решение</th><th>Производитель</th><th>Тип</th><th>Статус</th><th className="r">УГТ</th><th className="r">Цена</th><th>Объекты</th><th>Источник</th></tr></thead>
              <tbody>{data.items.map(s => (
                <tr key={s.external_id} style={{ cursor: 'pointer' }} onClick={() => onDetail(s.external_id)}>
                  <td><b>{s.name}</b></td><td>{s.vendor}</td><td>{s.subtype}</td><td>{STATUS[s.status]}</td><td className="r">{s.trl ?? '—'}</td>
                  <td className="r num">{rub(s.price_rub)}</td>
                  <td style={{ fontSize: 12 }}>{s.object_types.map(o => ({ warehouse: 'склад', airport: 'аэропорт', clinic: 'медучреждение' }[o])).join(', ') || '—'}</td>
                  <td className="muted" style={{ fontSize: 12 }}>{s.source_url ? 'открытый источник' : 'каталог организатора'}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        </>}
      </div>
    </div>
  )
}

const EMPTY = { name: '', vendor: '', subtype: 'AMR', scenarios: 'Внутрискладская логистика', object_types: 'warehouse', status: 'operation', trl: 9, price_rub: '', price_note: '', description: '', country: 'Россия', specs: '{\n  "payload_kg": {"value": 1000, "unit": "кг", "source": "https://…", "confirmed": true}\n}', source_url: '' }

export function AdminPage({ user, notify, onDetail }) {
  const [assumptions, setAssumptions] = useState(null)
  const [form, setForm] = useState(EMPTY)
  const [edit, setEdit] = useState({})
  const [users, setUsers] = useState([])
  const [q, setQ] = useState('')
  const [found, setFound] = useState([])
  const load = () => { api.get('/admin/assumptions').then(setAssumptions); api.get('/admin/users').then(setUsers).catch(() => {}) }
  useEffect(() => { if (user?.role === 'admin') load() }, [user])
  useEffect(() => { if (q.length > 1) api.get(`/catalog/solutions?q=${encodeURIComponent(q)}&limit=10`).then(r => setFound(r.items)) }, [q])
  if (user?.role !== 'admin') return <div className="card"><div className="empty">Раздел доступен администратору. Войдите как admin@demo / admin123.</div></div>

  const saveSolution = async () => {
    try {
      const specs = JSON.parse(form.specs || '{}')
      const body = { ...form, specs, trl: form.trl ? Number(form.trl) : null, price_rub: form.price_rub ? Number(form.price_rub) : null,
        scenarios: form.scenarios.split(';').map(s => s.trim()).filter(Boolean), object_types: form.object_types.split(',').map(s => s.trim()).filter(Boolean),
        source_url: form.source_url || null, data_source: form.source_url ? 'Открытые источники (добавлено администратором)' : 'Добавлено администратором' }
      const r = await api.post('/admin/solutions', body)
      notify(`Решение сохранено: ${r.name}`)
      setForm(EMPTY)
    } catch (e) { notify(e instanceof SyntaxError ? 'Характеристики должны быть в формате JSON' : e.message, true) }
  }
  const pick = (s) => setForm({ ...EMPTY, ...s, scenarios: (s.scenarios || []).join('; '), object_types: (s.object_types || []).join(', '), specs: JSON.stringify(s.specs, null, 2), price_rub: s.price_rub ?? '', source_url: s.source_url || '' })
  const saveAssumption = async (k) => {
    try { await api.put(`/admin/assumptions/${k}`, { value: Number(edit[k].value), source: edit[k].source }); notify('Норматив обновлён — применяется ко всем новым расчётам'); setEdit({ ...edit, [k]: undefined }); load() } catch (e) { notify(e.message, true) }
  }
  const reload = async () => { try { const r = await api.post('/admin/catalog/reload'); notify(`Каталог перезагружен: ${r.solutions} решений, версия ${r.catalog_version}`) } catch (e) { notify(e.message, true) } }

  return (
    <div>
      <div className="card">
        <div className="card-head"><div style={{ flex: 1 }}><h2>Администрирование</h2><p>Управление каталогом решений, источниками данных и расчётными нормативами по умолчанию.</p></div>
          <button className="btn" onClick={reload}>Перезагрузить каталог из ETL</button></div>
        <p className="muted" style={{ fontSize: 12.5 }}>Пользователи: {users.map(u => `${u.username} (${u.role})`).join(', ')}</p>
      </div>
      <div className="card">
        <h3>Добавить или изменить решение</h3>
        <div className="row mt-s"><input type="text" placeholder="Найти решение для редактирования…" value={q} onChange={e => setQ(e.target.value)} style={{ maxWidth: 360 }} />
          {found.slice(0, 6).map(s => <button key={s.external_id} className="btn small" onClick={() => pick(s)}>{s.name.slice(0, 30)}</button>)}</div>
        <div className="grid g3 mt">
          {[['name', 'Наименование'], ['vendor', 'Производитель'], ['subtype', 'Тип решения (подтип)'], ['scenarios', 'Сценарии (через ;)'], ['object_types', 'Объекты: warehouse, airport, clinic'], ['status', 'Статус: operation / piloting / rnd'], ['trl', 'УГТ'], ['price_rub', 'Цена, руб. с НДС'], ['price_note', 'Комментарий к цене'], ['country', 'Страна'], ['source_url', 'Ссылка на источник']].map(([k, l]) => (
            <label key={k} className="field"><span>{l}</span><input type="text" value={form[k] ?? ''} onChange={e => setForm({ ...form, [k]: e.target.value })} /></label>
          ))}
        </div>
        <div className="grid g2 mt">
          <label className="field"><span>Описание</span><textarea rows={6} value={form.description} onChange={e => setForm({ ...form, description: e.target.value })} /></label>
          <label className="field"><span>Характеристики (JSON: значение, единица, источник, подтверждено)</span><textarea rows={6} value={form.specs} onChange={e => setForm({ ...form, specs: e.target.value })} style={{ fontFamily: 'monospace', fontSize: 12 }} /></label>
        </div>
        <div className="row mt">
          <button className="btn primary" onClick={saveSolution} disabled={!form.name}>Сохранить решение</button>
          <button className="btn" onClick={() => setForm(EMPTY)}>Очистить</button>
          {form.external_id && <button className="btn ghost" onClick={() => onDetail(form.external_id)}>Карточка</button>}
          {form.external_id && <button className="btn danger" onClick={async () => { if (window.confirm('Удалить решение из каталога?')) { await api.del(`/admin/solutions/${form.external_id}`); notify('Решение удалено'); setForm(EMPTY) } }}>Удалить</button>}
        </div>
      </div>
      <div className="card">
        <h3>Расчётные нормативы по умолчанию</h3>
        <p className="muted">Изменение применяется ко всем новым расчётам и фиксируется с источником и автором.</p>
        {!assumptions ? <Loading /> : (
          <div className="tablewrap mt-s"><table className="t">
            <thead><tr><th>Ключ</th><th style={{ width: 110 }}>Значение</th><th>Ед.</th><th>Источник</th><th /></tr></thead>
            <tbody>{Object.entries(assumptions).map(([k, a]) => (
              <tr key={k}>
                <td><code>{k}</code>{a.changed && <div className="muted" style={{ fontSize: 11 }}>изменено: {a.changed.updated_by}</div>}</td>
                <td><input type="number" step="any" value={edit[k]?.value ?? a.value} onChange={e => setEdit({ ...edit, [k]: { value: e.target.value, source: edit[k]?.source ?? a.source } })} /></td>
                <td className="muted" style={{ fontSize: 12 }}>{a.unit}</td>
                <td>{edit[k] ? <input type="text" value={edit[k].source} onChange={e => setEdit({ ...edit, [k]: { ...edit[k], source: e.target.value } })} /> : <span className="muted" style={{ fontSize: 12 }}>{a.source}</span>}</td>
                <td>{edit[k] && <button className="btn small primary" onClick={() => saveAssumption(k)}>Сохранить</button>}</td>
              </tr>
            ))}</tbody>
          </table></div>
        )}
      </div>
    </div>
  )
}
