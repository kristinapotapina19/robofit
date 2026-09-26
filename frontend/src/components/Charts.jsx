import { useState } from 'react'
import { fmt, mln, SCEN_COLOR, SCEN_SHORT } from '../format.js'

// Накопленные затраты по годам: CAPEX в нулевой год, затем OPEX каждый год,
// замена компонентов — в год, заданный допущением. Точка пересечения с базовым
// сценарием — момент окупаемости.
export function cumulativeCosts(result) {
  const A = result.assumptions
  const horizon = Math.round(A.horizon_years.value)
  const repYear = Math.round(A.component_replacement_year.value)
  const repShare = A.component_replacement_share.value
  const eq = result.steps.find(s => s.name === 'Стоимость оборудования')?.result || 0
  return result.scenarios.map(sc => {
    const pts = [sc.capex_total]
    for (let y = 1; y <= horizon; y++) {
      let v = pts[y - 1] + sc.opex_year
      if (sc.code === 'purchase' && y === repYear) v += eq * repShare
      pts.push(v)
    }
    return { code: sc.code, pts }
  })
}

export function CostChart({ result, height = 240 }) {
  const [hover, setHover] = useState(null)
  const series = cumulativeCosts(result)
  const years = series[0].pts.length - 1
  const max = Math.max(...series.flatMap(s => s.pts)) * 1.08
  const W = 560
  const H = height
  const pad = { l: 56, r: 16, t: 14, b: 30 }
  const x = (i) => pad.l + (i / years) * (W - pad.l - pad.r)
  const y = (v) => H - pad.b - (v / max) * (H - pad.t - pad.b)
  const ticks = 4
  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label="Накопленные затраты по сценариям"
        onMouseLeave={() => setHover(null)}>
        {Array.from({ length: ticks + 1 }, (_, i) => {
          const v = (max / ticks) * i
          return <g key={i}>
            <line x1={pad.l} x2={W - pad.r} y1={y(v)} y2={y(v)} stroke="var(--line)" />
            <text x={pad.l - 6} y={y(v) + 4} fontSize="10.5" textAnchor="end" fill="var(--muted)">{mln(v, 0)}</text>
          </g>
        })}
        {Array.from({ length: years + 1 }, (_, i) => (
          <g key={i}>
            <text x={x(i)} y={H - 10} fontSize="10.5" textAnchor="middle" fill="var(--muted)">{i === 0 ? 'старт' : `${i} г.`}</text>
            <rect x={x(i) - 18} y={pad.t} width={36} height={H - pad.t - pad.b} fill="transparent"
              onMouseEnter={() => setHover(i)} />
          </g>
        ))}
        {series.map(s => (
          <g key={s.code}>
            <polyline fill="none" stroke={SCEN_COLOR[s.code]} strokeWidth={s.code === 'baseline' ? 2 : 2.5}
              strokeDasharray={s.code === 'baseline' ? '5 4' : ''} points={s.pts.map((v, i) => `${x(i)},${y(v)}`).join(' ')} />
            {s.pts.map((v, i) => <circle key={i} cx={x(i)} cy={y(v)} r={hover === i ? 4 : 2.5} fill={SCEN_COLOR[s.code]} />)}
          </g>
        ))}
        {hover !== null && <line x1={x(hover)} x2={x(hover)} y1={pad.t} y2={H - pad.b} stroke="var(--muted)" strokeDasharray="2 3" />}
        <text x={pad.l} y={10} fontSize="10.5" fill="var(--muted)">млн ₽</text>
      </svg>
      <div className="legend">
        {series.map(s => (
          <span key={s.code}><i className="dot" style={{ background: SCEN_COLOR[s.code] }} />{SCEN_SHORT[s.code]}
            {hover !== null && <b style={{ marginLeft: 4 }}>{mln(s.pts[hover])}</b>}</span>
        ))}
        {hover === null && <span>Наведите на год, чтобы увидеть значения</span>}
      </div>
    </div>
  )
}

export function Tornado({ rows, scenario = 'purchase' }) {
  const data = rows.filter(r => r.scenario === scenario && Math.abs(r.delta_percent) === 20)
  const factors = [...new Set(data.map(r => r.factor))]
  const maxAbs = Math.max(1, ...data.map(r => Math.abs(r.annual_effect_change)))
  return (
    <div className="stack" style={{ gap: 10 }}>
      {factors.map(f => {
        const lo = data.find(r => r.factor === f && r.delta_percent === -20)
        const hi = data.find(r => r.factor === f && r.delta_percent === 20)
        const bar = (r, color) => {
          const w = Math.abs(r.annual_effect_change) / maxAbs * 50
          const left = r.annual_effect_change < 0 ? 50 - w : 50
          return <i style={{ position: 'absolute', left: `${left}%`, width: `${w}%`, top: 0, bottom: 0, background: color, borderRadius: 3 }} />
        }
        return (
          <div key={f}>
            <div className="row" style={{ justifyContent: 'space-between', fontSize: 12.5 }}>
              <span>{f}</span>
              <span className="muted">−20%: {mln(lo.annual_effect_change)} · +20%: {mln(hi.annual_effect_change)} млн ₽/год</span>
            </div>
            <div style={{ position: 'relative', height: 14, background: 'var(--surface-2)', borderRadius: 3, marginTop: 4 }}>
              {bar(lo, '#818cf8')}{bar(hi, 'var(--accent)')}
              <span style={{ position: 'absolute', left: '50%', top: -2, bottom: -2, width: 1, background: 'var(--muted)' }} />
            </div>
          </div>
        )
      })}
      <div className="legend"><span><i className="dot" style={{ background: '#818cf8' }} />параметр −20%</span>
        <span><i className="dot" style={{ background: 'var(--accent)' }} />параметр +20%</span>
        <span>изменение годового эффекта относительно базового расчёта</span></div>
    </div>
  )
}

export function Spark({ history, total, key1 = 'completed', key2 = 'queue' }) {
  const W = 280
  const H = 90
  if (!history.length) return <svg viewBox={`0 0 ${W} ${H}`} width="100%" />
  const maxT = Math.max(total / 60, 1)
  const m1 = Math.max(1, ...history.map(h => h[key1]))
  const m2 = Math.max(1, ...history.map(h => h[key2]))
  const px = (h) => (h.minute / maxT) * (W - 8) + 4
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" aria-label="Динамика смены">
      <polyline fill="none" stroke="var(--accent)" strokeWidth="2" points={history.map(h => `${px(h)},${H - 6 - h[key1] / m1 * (H - 16)}`).join(' ')} />
      <polyline fill="none" stroke="var(--warn)" strokeWidth="1.6" points={history.map(h => `${px(h)},${H - 6 - h[key2] / m2 * (H - 16)}`).join(' ')} />
    </svg>
  )
}

export function Bars({ items }) {
  const max = Math.max(1, ...items.map(i => i.value))
  return (
    <div className="stack" style={{ gap: 8 }}>
      {items.map(i => (
        <div key={i.label}>
          <div className="row" style={{ justifyContent: 'space-between', fontSize: 12.5 }}><span>{i.label}</span><b className="num">{fmt(i.value / 1e6, 1)} млн ₽</b></div>
          <div className="progress"><i style={{ width: `${i.value / max * 100}%`, background: i.color }} /></div>
        </div>
      ))}
    </div>
  )
}
