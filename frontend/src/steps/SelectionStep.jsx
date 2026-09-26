import { useState } from 'react'
import { ErrorBox, Loading } from '../components/ui.jsx'
import { fmt, rub, STATUS, VERDICT, VERDICT_CLASS } from '../format.js'

const FACTOR_COLORS = ['#5b2ea6', '#8f6ad6', '#1f8fb3', '#9fd0e1']

export function ScoreBar({ breakdown, score }) {
  const entries = Object.entries(breakdown || {})
  return (
    <div title={entries.map(([k, v]) => `${k}: ${v}`).join('\n')}>
      <div className="row" style={{ justifyContent: 'space-between', fontSize: 12 }}>
        <span className="muted">Рейтинг</span><b>{fmt(score * 100)} / 100</b>
      </div>
      <div className="scorebar mt-s">
        {entries.map(([k, v], i) => <i key={k} style={{ width: `${v * 100}%`, background: FACTOR_COLORS[i] }} />)}
      </div>
    </div>
  )
}

export function ScoreLegend({ weights }) {
  return (
    <div className="legend">
      {Object.keys({ 'Кейсы внедрения': 1, 'Уровень готовности (УГТ)': 1, 'Цена единицы производительности': 1, 'Полнота ТТХ': 1 }).map((k, i) => (
        <span key={k}><i className="dot" style={{ background: FACTOR_COLORS[i] }} />{k}{weights ? ` (вес ${Object.values(weights)[i] * 100}%)` : ''}</span>
      ))}
    </div>
  )
}

export default function SelectionStep({ selection, loading, error, retry, meta, compareIds, toggleCompare, solutionId, onCalc, onDetail, onBack, onNext }) {
  const [tab, setTab] = useState('fit')
  const [q, setQ] = useState('')
  const [sort, setSort] = useState('score')
  if (loading) return <div className="card"><Loading text="Подбираем решения по параметрам объекта…" /></div>
  if (error) return <div className="card"><ErrorBox error={error} onRetry={retry} /><div className="stepfoot"><button className="btn" onClick={onBack}>← К параметрам</button></div></div>
  if (!selection) return null
  const ctx = selection.context
  let list = selection[tab] || []
  if (q) list = list.filter(c => (c.name + c.vendor + c.subtype).toLowerCase().includes(q.toLowerCase()))
  if (sort === 'price') list = [...list].sort((a, b) => (a.price_rub ?? 1e12) - (b.price_rub ?? 1e12))
  const counts = { fit: selection.fit.length, check_needed: selection.check_needed.length, excluded: selection.excluded.length }

  return (
    <div>
      <div className="card">
        <div className="card-head">
          <div style={{ flex: 1 }}>
            <h2>Шаг 3. Подбор решений</h2>
            <p>Рассмотрено {selection.total} решений каталога. По каждому показано, почему оно подходит, что нужно проверить или что делает применение невозможным.</p>
          </div>
        </div>
        <div className="row" style={{ fontSize: 12.5 }}>
          <span className="muted">Ограничения объекта:</span>
          {ctx.cargo_mass_kg != null && <span className="badge">груз {fmt(ctx.cargo_mass_kg)} кг</span>}
          {ctx.aisle_width_mm != null && <span className="badge">проход {fmt(ctx.aisle_width_mm)} мм</span>}
          {ctx.capex_budget_rub != null && <span className="badge">бюджет {fmt(ctx.capex_budget_rub / 1e6)} млн ₽</span>}
          <span className="badge">типы: {ctx.profile_subtypes.join(', ')}</span>
        </div>
        <details className="mt-s"><summary className="muted" style={{ cursor: 'pointer', fontSize: 12.5 }}>Правила подбора и ранжирования</summary>
          <table className="t mt-s"><thead><tr><th>Правило</th><th>Условие</th><th>Если не выполнено</th></tr></thead>
            <tbody>{(meta?.selection_rules || []).map(r => <tr key={r.name}><td>{r.name}</td><td>{r.rule}</td><td>{r.effect}</td></tr>)}</tbody></table>
          <p className="muted mt-s" style={{ fontSize: 12.5 }}>Рейтинг — сумма четырёх факторов с весами; вклад каждого виден на полосе рейтинга.</p>
          <ScoreLegend weights={meta?.ranking_weights} />
        </details>
      </div>

      <div className="card">
        <div className="tabs">
          {['fit', 'check_needed', 'excluded'].map(k => (
            <button key={k} className={tab === k ? 'on' : ''} onClick={() => setTab(k)}>{VERDICT[k]} · {counts[k]}</button>
          ))}
          <div className="spacer" />
          <input type="text" placeholder="Поиск по названию или вендору" value={q} onChange={e => setQ(e.target.value)} style={{ maxWidth: 260 }} />
          <select value={sort} onChange={e => setSort(e.target.value)} style={{ maxWidth: 170 }}>
            <option value="score">По рейтингу</option><option value="price">По цене</option>
          </select>
        </div>
        {tab === 'excluded' && <p className="muted" style={{ marginBottom: 10 }}>Исключённое решение можно вручную добавить в сравнение — расчёт покажет предупреждение (п. 3.4.4 ТЗ).</p>}
        {!list.length && <div className="empty">В этой группе решений нет.</div>}
        {list.slice(0, 60).map(c => {
          const inCmp = compareIds.includes(c.solution_id)
          return (
            <div key={c.solution_id} className={`cand ${solutionId === c.solution_id ? 'sel' : ''}`}>
              <div>
                <div className="row">
                  <h4>{c.name}</h4>
                  <span className={`badge ${VERDICT_CLASS[c.verdict]}`}>{VERDICT[c.verdict]}</span>
                  {solutionId === c.solution_id && <span className="badge accent">выбрано для расчёта</span>}
                </div>
                <div className="muted" style={{ fontSize: 12.5, marginTop: 2 }}>
                  {c.vendor} · {c.subtype || 'тип не указан'} · {STATUS[c.status] || c.status}{c.trl ? ` · УГТ ${c.trl}` : ''}
                  {c.data_source?.startsWith('Открытые') && ' · из открытых источников'}
                </div>
                <ul>
                  {c.decisive_reason && <li className="x">{c.decisive_reason}</li>}
                  {c.reasons.slice(0, 5).map(r => <li key={r} className="ok">{r}</li>)}
                  {c.warnings.map(w => <li key={w} className="w">{w}</li>)}
                  {c.missing_specs.length > 0 && <li className="w">Нет данных: {c.missing_specs.map(m => ({ payload_kg: 'грузоподъёмность', speed_ms: 'скорость', runtime_h: 'автономность', throughput_per_h: 'производительность' }[m] || m)).join(', ')}</li>}
                </ul>
              </div>
              <div className="side">
                <div style={{ fontSize: 18, fontWeight: 700 }} className="num">{rub(c.price_rub)}</div>
                <ScoreBar breakdown={c.score_breakdown} score={c.score} />
                <button className="btn primary small" onClick={() => onCalc(c.solution_id)}>Рассчитать экономику</button>
                <button className={`btn small ${inCmp ? 'accent' : ''}`} onClick={() => toggleCompare(c)}>{inCmp ? '✓ В сравнении' : '+ В сравнение'}</button>
                <button className="btn ghost small" onClick={() => onDetail(c.solution_id)}>Характеристики</button>
              </div>
            </div>
          )
        })}
      </div>
      <div className="stepfoot">
        <button className="btn" onClick={onBack}>← Назад</button>
        <button className="btn primary" disabled={!compareIds.length} onClick={onNext}>Сравнить выбранные ({compareIds.length}) →</button>
      </div>
    </div>
  )
}
