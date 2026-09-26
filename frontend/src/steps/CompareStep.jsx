import { useEffect, useState } from 'react'
import { api } from '../api.js'
import { ErrorBox, Loading } from '../components/ui.jsx'
import { fmt, mln, rub, SPEC_LABELS, STATUS, VERDICT, VERDICT_CLASS, years } from '../format.js'

const SPEC_ROWS = ['payload_kg', 'speed_ms', 'runtime_h', 'charge_min', 'throughput_per_h', 'width_mm', 'length_mm', 'navigation', 'positioning_mm', 'min_aisle_mm']

function specCell(sol, key) {
  const s = sol?.specs?.[key]
  if (!s) return <span className="muted">нет данных</span>
  const unit = key === 'throughput_per_h' ? (sol.specs.throughput_unit?.value || '') : SPEC_LABELS[key]?.[1]
  return (
    <span title={s.source}>
      {typeof s.value === 'number' ? fmt(s.value, 2) : s.value} {unit}
      {s.confirmed ? <span className="badge good" style={{ marginLeft: 4 }}>паспорт</span> : <span className="badge warn" style={{ marginLeft: 4 }}>оценка</span>}
    </span>
  )
}

export default function CompareStep({ profileCode, params, ids, remove, onCalc, onBack }) {
  const [data, setData] = useState(null)
  const [details, setDetails] = useState({})
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)

  const load = () => {
    if (!ids.length) return
    setLoading(true)
    setError(null)
    Promise.all([
      api.post('/compare', { profile_code: profileCode, params, solution_ids: ids }),
      ...ids.map(id => api.get(`/catalog/solutions/${id}`)),
    ]).then(([cmp, ...sols]) => {
      setData(cmp)
      setDetails(Object.fromEntries(sols.map(s => [s.external_id, s])))
    }).catch(setError).finally(() => setLoading(false))
  }
  useEffect(load, [ids.join(','), profileCode, JSON.stringify(params)])  // eslint-disable-line react-hooks/exhaustive-deps

  if (!ids.length) return <div className="card"><div className="empty">Добавьте решения в сравнение на шаге подбора.</div><div className="stepfoot"><button className="btn" onClick={onBack}>← К подбору</button></div></div>
  if (loading) return <div className="card"><Loading text="Считаем экономику по каждому решению…" /></div>
  if (error) return <div className="card"><ErrorBox error={error} onRetry={load} /></div>
  if (!data) return null

  const ok = data.filter(d => !d.error)
  const best = (key, sc, dir = 1) => {
    const vals = ok.map(d => d[sc][key]).filter(v => v !== null && v !== undefined)
    if (!vals.length) return null
    return dir > 0 ? Math.min(...vals) : Math.max(...vals)
  }
  const econ = [
    ['Парк, шт.', d => fmt(d.fleet.count), null],
    ['CAPEX (покупка), млн ₽', d => mln(d.purchase.capex_total), ['capex_total', 'purchase', 1]],
    ['OPEX (покупка), млн ₽/год', d => mln(d.purchase.opex_year), ['opex_year', 'purchase', 1]],
    ['Годовой эффект (покупка), млн ₽', d => mln(d.purchase.annual_effect), ['annual_effect', 'purchase', -1]],
    ['Окупаемость (покупка)', d => years(d.purchase.payback_years), ['payback_years', 'purchase', 1]],
    ['TCO за горизонт (покупка), млн ₽', d => mln(d.purchase.tco), ['tco', 'purchase', 1]],
    ['Годовой эффект (RaaS), млн ₽', d => mln(d.raas.annual_effect), ['annual_effect', 'raas', -1]],
    ['TCO за горизонт (RaaS), млн ₽', d => mln(d.raas.tco), ['tco', 'raas', 1]],
  ]
  return (
    <div>
      <div className="card">
        <div className="card-head">
          <div>
            <h2>Шаг 4. Сравнение решений</h2>
            <p>Единые технические, эксплуатационные и экономические показатели на параметрах вашего объекта. Зелёным отмечено лучшее значение в строке. Наведите на характеристику, чтобы увидеть её источник.</p>
          </div>
        </div>
        <div className="tablewrap">
          <table className="t">
            <thead>
              <tr><th style={{ width: 220 }}>Показатель</th>{data.map(d => (
                <th key={d.solution_id}>
                  <div style={{ color: 'var(--text)', fontSize: 13 }}>{d.solution?.name || details[d.solution_id]?.name}</div>
                  <div className="row mt-s">
                    {d.verdict && <span className={`badge ${VERDICT_CLASS[d.verdict]}`}>{VERDICT[d.verdict]}</span>}
                    <button className="btn ghost small" onClick={() => remove(d.solution_id)}>убрать</button>
                  </div>
                </th>))}</tr>
            </thead>
            <tbody>
              <tr className="sub"><td colSpan={data.length + 1}><b>Идентификация</b></td></tr>
              <tr><td>Производитель</td>{data.map(d => <td key={d.solution_id}>{details[d.solution_id]?.vendor}</td>)}</tr>
              <tr><td>Тип решения</td>{data.map(d => <td key={d.solution_id}>{details[d.solution_id]?.subtype}</td>)}</tr>
              <tr><td>Статус / УГТ</td>{data.map(d => { const s = details[d.solution_id]; return <td key={d.solution_id}>{STATUS[s?.status]}{s?.trl ? ` / ${s.trl}` : ''}</td> })}</tr>
              <tr><td>Страна</td>{data.map(d => <td key={d.solution_id}>{details[d.solution_id]?.country}</td>)}</tr>
              <tr><td>Цена единицы</td>{data.map(d => <td key={d.solution_id} className="num">{rub(details[d.solution_id]?.price_rub)}</td>)}</tr>
              <tr className="sub"><td colSpan={data.length + 1}><b>Технические характеристики</b></td></tr>
              {SPEC_ROWS.map(k => (
                <tr key={k}><td>{SPEC_LABELS[k][0]}</td>{data.map(d => <td key={d.solution_id}>{specCell(details[d.solution_id], k)}</td>)}</tr>
              ))}
              <tr><td>Производительность в расчёте</td>{data.map(d => <td key={d.solution_id}>{d.robot ? <span title={d.robot.throughput.source}>{fmt(d.robot.throughput.value, 1)} <small>({d.robot.throughput.source.split(':')[0].slice(0, 40)})</small></span> : '—'}</td>)}</tr>
              <tr className="sub"><td colSpan={data.length + 1}><b>Экономика на вашем объекте</b></td></tr>
              {econ.map(([label, f, b]) => (
                <tr key={label}><td>{label}</td>{data.map(d => {
                  if (d.error) return <td key={d.solution_id} className="muted">{typeof d.error === 'string' ? d.error : 'ошибка расчёта'}</td>
                  const isBest = b && best(b[0], b[1], b[2]) === d[b[1]][b[0]] && ok.length > 1
                  return <td key={d.solution_id} className="num" style={isBest ? { background: 'var(--good-soft)', fontWeight: 700 } : null}>{f(d)}</td>
                })}</tr>
              ))}
              <tr><td>Вывод</td>{data.map(d => <td key={d.solution_id}>{d.recommendation && <span className={`badge ${d.recommendation.level === 'good' ? 'good' : d.recommendation.level === 'medium' ? 'warn' : 'bad'}`}>{d.recommendation.verdict}</span>}</td>)}</tr>
              <tr><td>Источник данных</td>{data.map(d => { const s = details[d.solution_id]; return <td key={d.solution_id} style={{ fontSize: 12 }}>{s?.source_url ? <a href={s.source_url} target="_blank" rel="noreferrer">{s.data_source}</a> : s?.data_source}{s?.updated_at ? `, ${s.updated_at}` : ''}</td> })}</tr>
              <tr><td /> {data.map(d => <td key={d.solution_id}><button className="btn primary small" onClick={() => onCalc(d.solution_id)}>Подробный расчёт</button></td>)}</tr>
            </tbody>
          </table>
        </div>
      </div>
      <div className="stepfoot">
        <button className="btn" onClick={onBack}>← К подбору</button>
      </div>
    </div>
  )
}
