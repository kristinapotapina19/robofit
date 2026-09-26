import { useState } from 'react'
import { api } from '../api.js'
import { Tornado } from '../components/Charts.jsx'
import { ErrorBox, Loading } from '../components/ui.jsx'
import { fmt, mln, years } from '../format.js'

function Slider({ label, value, min, max, step, onChange, format }) {
  return (
    <label className="field">
      <span className="row" style={{ justifyContent: 'space-between' }}><span>{label}</span><b style={{ color: 'var(--accent)' }}>{format(value)}</b></span>
      <input type="range" min={min} max={max} step={step} value={value} onChange={e => onChange(Number(e.target.value))} />
    </label>
  )
}

const signed = (v) => `${v > 0 ? '+' : ''}${fmt(v)}%`

export default function WhatIfStep({ result, request, onApply, onBack, onNext }) {
  const base = result
  const [salary, setSalary] = useState(0)
  const [volume, setVolume] = useState(0)
  const [price, setPrice] = useState(0)
  const [share, setShare] = useState(base?.staff.automation_share ?? 0.7)
  const [route, setRoute] = useState(base?.demand.route_length_m ?? 100)
  const [fleetMode, setFleetMode] = useState('auto')
  const [manual, setManual] = useState(base?.fleet.count ?? 1)
  const [wi, setWi] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [sensScen, setSensScen] = useState('purchase')

  if (!base) return <div className="card"><div className="empty">Сначала выполните расчёт экономики.</div></div>
  const mobile = base.profile.mode === 'mobile'
  const options = () => ({
    salary_factor: 1 + salary / 100, volume_factor: 1 + volume / 100, price_factor: 1 + price / 100,
    automation_share: share, ...(mobile ? { route_length_m: route } : {}),
    fleet_mode: fleetMode, ...(fleetMode === 'manual' ? { manual_fleet: manual } : {}),
  })
  const run = async () => {
    setBusy(true); setError(null)
    try { setWi(await api.post('/evaluate', { ...request, options: options() })) } catch (e) { setError(e) } finally { setBusy(false) }
  }
  const reset = () => { setSalary(0); setVolume(0); setPrice(0); setShare(base.staff.automation_share); setRoute(base.demand.route_length_m); setFleetMode('auto'); setWi(null) }

  const metrics = [
    ['Парк, шт.', (r, c) => fmt(r.scenarios.find(s => s.code === c).robot_count)],
    ['CAPEX, млн ₽', (r, c) => mln(r.scenarios.find(s => s.code === c).capex_total)],
    ['OPEX, млн ₽/год', (r, c) => mln(r.scenarios.find(s => s.code === c).opex_year)],
    ['Годовой эффект, млн ₽', (r, c) => mln(r.scenarios.find(s => s.code === c).annual_effect)],
    ['Окупаемость', (r, c) => c === 'baseline' ? '—' : years(r.scenarios.find(s => s.code === c).payback_years)],
    ['TCO, млн ₽', (r, c) => mln(r.scenarios.find(s => s.code === c).tco)],
  ]
  const cols = [['baseline', 'Без роботизации'], ['purchase', 'Покупка'], ['raas', 'RaaS']]
  const sensRows = base.sensitivity.filter(r => r.scenario === sensScen)
  const factors = [...new Set(sensRows.map(r => r.factor))]

  return (
    <div>
      <div className="card">
        <div className="card-head"><div><h2>Шаг 6. What-if анализ</h2>
          <p>Измените ключевые параметры и сравните базовый расчёт и сценарии роботизации в одной таблице.</p></div></div>
        <div className="grid g3">
          <Slider label="Стоимость труда" value={salary} min={-30} max={50} step={5} onChange={setSalary} format={signed} />
          <Slider label="Объём операций" value={volume} min={-50} max={100} step={10} onChange={setVolume} format={signed} />
          <Slider label="Стоимость оборудования" value={price} min={-30} max={50} step={5} onChange={setPrice} format={signed} />
          <Slider label="Доля автоматизации операции" value={share} min={0.2} max={1} step={0.05} onChange={setShare} format={v => `${fmt(v * 100)}%`} />
          {mobile && <Slider label="Длина маршрута в одну сторону" value={route} min={20} max={Math.max(600, Math.round(base.demand.route_length_m * 2))} step={10} onChange={setRoute} format={v => `${fmt(v)} м`} />}
          <label className="field"><span>Парк роботов</span>
            <div className="row">
              <div className="seg">
                {[['auto', 'Авто'], ['passport', 'По паспорту'], ['manual', 'Вручную']].map(([k, l]) => <button key={k} className={fleetMode === k ? 'on' : ''} onClick={() => setFleetMode(k)}>{l}</button>)}
              </div>
              {fleetMode === 'manual' && <input type="number" min={1} value={manual} onChange={e => setManual(Number(e.target.value))} style={{ width: 80 }} />}
            </div>
          </label>
        </div>
        <div className="row mt">
          <button className="btn primary" onClick={run} disabled={busy}>{busy ? 'Считаем…' : 'Пересчитать what-if'}</button>
          <button className="btn" onClick={reset}>Сбросить</button>
          {wi && <button className="btn ghost" onClick={() => onApply(options())}>Принять как основной расчёт</button>}
        </div>
        {error && <div className="mt"><ErrorBox error={error} /></div>}
        {busy && <Loading text="Пересчёт с имитацией парка…" />}
        {wi && !busy && (
          <div className="tablewrap mt">
            <table className="t">
              <thead>
                <tr><th rowSpan={2}>Показатель</th>{cols.map(([c, l]) => <th key={c} colSpan={2} className="r" style={{ textAlign: 'center' }}>{l}</th>)}</tr>
                <tr>{cols.map(([c]) => [<th key={c + 'b'} className="r">база</th>, <th key={c + 'w'} className="r">what-if</th>])}</tr>
              </thead>
              <tbody>{metrics.map(([l, f]) => (
                <tr key={l}><td>{l}</td>{cols.map(([c]) => [
                  <td key={c + 'b'} className="r num muted">{f(base, c)}</td>,
                  <td key={c + 'w'} className="r num"><b>{f(wi, c)}</b></td>])}</tr>
              ))}
                <tr><td>Вывод</td><td colSpan={6}><b>{wi.recommendation.verdict}</b> (было: {base.recommendation.verdict})</td></tr>
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="card">
        <div className="card-head">
          <div style={{ flex: 1 }}><h3>Чувствительность к трём параметрам</h3>
            <p>Как меняется годовой эффект и окупаемость при изменении стоимости оборудования, объёма операций и стоимости труда на ±10% и ±20% (п. 3.5.6 ТЗ).</p></div>
          <div className="seg">
            <button className={sensScen === 'purchase' ? 'on' : ''} onClick={() => setSensScen('purchase')}>Покупка</button>
            <button className={sensScen === 'raas' ? 'on' : ''} onClick={() => setSensScen('raas')}>RaaS</button>
          </div>
        </div>
        <div className="grid g2" style={{ alignItems: 'start' }}>
          <Tornado rows={base.sensitivity} scenario={sensScen} />
          <table className="t">
            <thead><tr><th>Параметр</th>{[-20, -10, 10, 20].map(d => <th key={d} className="r">{d > 0 ? '+' : ''}{d}%</th>)}</tr></thead>
            <tbody>{factors.map(f => (
              <tr key={f}><td>{f}<div className="muted" style={{ fontSize: 11.5 }}>окупаемость</div></td>
                {[-20, -10, 10, 20].map(d => {
                  const r = sensRows.find(x => x.factor === f && x.delta_percent === d)
                  return <td key={d} className="r num" style={r.crosses_band ? { background: 'var(--warn-soft)' } : null} title={r.crosses_band ? 'Окупаемость переходит в другой интервал' : ''}>{r.payback_years === null ? '—' : fmt(r.payback_years, 2)}</td>
                })}</tr>
            ))}</tbody>
          </table>
        </div>
        <p className="muted mt-s" style={{ fontSize: 12 }}>Жёлтым — изменение параметра переводит окупаемость в другой интервал (до 3 / 3–5 / более 5 лет). Значит, этот параметр нужно подтвердить в первую очередь.</p>
      </div>

      <div className="stepfoot">
        <button className="btn" onClick={onBack}>← Назад</button>
        <button className="btn primary" onClick={onNext}>Визуализация работы →</button>
      </div>
    </div>
  )
}
