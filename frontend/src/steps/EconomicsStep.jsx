import { useState } from 'react'
import { CostChart } from '../components/Charts.jsx'
import { ErrorBox, Info, Loading } from '../components/ui.jsx'
import { ASSUMPTION_LABELS, fmt, mln, pct, SCEN_COLOR, years } from '../format.js'

function StepsTable({ steps }) {
  return (
    <table className="t">
      <thead><tr><th>Шаг</th><th>Формула</th><th>Входные данные</th><th className="r">Результат</th></tr></thead>
      <tbody>
        {steps.map((s, i) => (
          <tr key={i}>
            <td><b>{s.name}</b></td>
            <td><span className="formula">{s.formula}</span></td>
            <td style={{ fontSize: 12 }}>{Object.entries(s.inputs).map(([k, v]) => <div key={k}><span className="muted">{k}:</span> {typeof v === 'number' ? fmt(v, 3) : String(v)}</div>)}</td>
            <td className="r num" style={{ whiteSpace: 'nowrap' }}><b>{typeof s.result === 'number' ? fmt(s.result, 2) : s.result}</b> {s.unit}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

export function VerdictBox({ rec }) {
  return (
    <div className={`verdict ${rec.level}`}>
      <div style={{ fontSize: 26 }}>{rec.level === 'good' ? '✓' : rec.level === 'medium' ? '◐' : '✕'}</div>
      <div>
        <h3>{rec.verdict}</h3>
        <p className="mt-s">{rec.interpretation}</p>
        <p className="muted mt-s" style={{ fontSize: 12 }}>Интервалы: до 3 лет — рекомендуется; 3–5 лет — после пилота; более 5 лет или больше горизонта — не рекомендуется. Решение принимается не только по порогу: смотрите риски и чувствительность ниже.</p>
      </div>
    </div>
  )
}

export function ScenarioTable({ result }) {
  const sc = result.scenarios
  const rows = [
    ['Роботов, шт.', s => fmt(s.robot_count)],
    ['CAPEX, млн ₽', s => mln(s.capex_total)],
    ['Годовой OPEX, млн ₽', s => mln(s.opex_year)],
    ['Изменение OPEX к базовому, млн ₽', s => s.code === 'baseline' ? '—' : mln(s.opex_change)],
    ['Экономия ФОТ, млн ₽/год', s => s.code === 'baseline' ? '—' : mln(s.labor_saving_year)],
    ['Чистый годовой эффект, млн ₽', s => s.code === 'baseline' ? '—' : mln(s.annual_effect), true],
    ['Эффект с учётом амортизации, млн ₽', s => s.code === 'purchase' ? mln(s.annual_effect_after_depreciation) : '—'],
    ['Срок окупаемости', s => s.code === 'baseline' ? '—' : years(s.payback_years), true],
    ['ROI за горизонт', s => s.code === 'baseline' || s.roi_percent === null ? '—' : `${fmt(s.roi_percent)}%`],
    [`TCO за ${result.assumptions.horizon_years.value} лет, млн ₽`, s => mln(s.tco), true],
  ]
  return (
    <table className="t">
      <thead><tr><th>Показатель</th>{sc.map(s => <th key={s.code} className="r"><i className="dot" style={{ background: SCEN_COLOR[s.code], marginRight: 5 }} />{s.title}</th>)}</tr></thead>
      <tbody>{rows.map(([l, f, hl]) => <tr key={l} className={hl ? 'hl' : ''}><td>{l}</td>{sc.map(s => <td key={s.code} className="r num">{f(s)}</td>)}</tr>)}</tbody>
    </table>
  )
}

function Breakdown({ title, data }) {
  const items = Object.entries(data).filter(([k]) => k !== 'Итого')
  return (
    <div>
      <h4>{title}</h4>
      <table className="t mt-s"><tbody>
        {items.map(([k, v]) => <tr key={k}><td>{k}</td><td className="r num">{mln(v, 2)}</td></tr>)}
        <tr className="hl"><td><b>Итого</b></td><td className="r num"><b>{mln(data['Итого'], 2)}</b></td></tr>
      </tbody></table>
    </div>
  )
}

export default function EconomicsStep({ result, loading, error, retry, overrides, setOverrides, onRecalc, onBack, onNext }) {
  const [draft, setDraft] = useState({})
  if (loading) return <div className="card"><Loading text="Считаем парк, имитацию смены и три сценария…" /></div>
  if (error) return <div className="card"><ErrorBox error={error} onRetry={retry} /><div className="stepfoot"><button className="btn" onClick={onBack}>← Назад</button></div></div>
  if (!result) return <div className="card"><div className="empty">Выберите решение на шаге подбора и нажмите «Рассчитать экономику».</div><div className="stepfoot"><button className="btn" onClick={onBack}>← К подбору</button></div></div>

  const buy = result.scenarios.find(s => s.code === 'purchase')
  const raas = result.scenarios.find(s => s.code === 'raas')
  const d = result.demand
  const applyDraft = () => {
    const next = { ...overrides }
    Object.entries(draft).forEach(([k, v]) => { if (v !== '' && !Number.isNaN(Number(v))) next[k] = Number(v) })
    setDraft({})
    setOverrides(next)
    onRecalc(next)
  }
  const resetAll = () => { setDraft({}); setOverrides({}); onRecalc({}) }

  return (
    <div>
      <div className="card">
        <div className="card-head">
          <div style={{ flex: 1 }}>
            <h2>Шаг 5. Экономика: {result.solution.name}</h2>
            <p>{result.profile.title} · {result.solution.vendor} · цена {fmt(result.solution.price_rub)} ₽ за единицу. Расчёт от {result.calculated_at?.replace('T', ' ')}, каталог {result.catalog_version}, модель {result.model_version}.</p>
          </div>
        </div>
        <VerdictBox rec={result.recommendation} />
        <div className="kpis mt">
          <div className="kpi"><div className="k">Парк роботов</div><div className="v">{result.fleet.count} шт.</div><div className="s">паспорт {result.fleet.passport} · имитация {result.fleet.simulation}</div></div>
          <div className="kpi"><div className="k">CAPEX (покупка)</div><div className="v">{mln(buy.capex_total)} млн</div><div className="s">RaaS: {mln(raas.capex_total)} млн</div></div>
          <div className="kpi"><div className="k">Годовой эффект (покупка)</div><div className="v" style={{ color: buy.annual_effect > 0 ? 'var(--good)' : 'var(--bad)' }}>{mln(buy.annual_effect)} млн</div><div className="s">RaaS: {mln(raas.annual_effect)} млн</div></div>
          <div className="kpi"><div className="k">Окупаемость (покупка)</div><div className="v">{years(buy.payback_years)}</div><div className="s">ROI {buy.roi_percent === null ? '—' : `${fmt(buy.roi_percent)}%`}</div></div>
          <div className="kpi"><div className="k">Высвобождается</div><div className="v">{fmt(result.staff.released, 1)} чел.</div><div className="s">из {fmt(result.staff.headcount, 1)} · доля {pct(result.staff.automation_share)}</div></div>
        </div>
        {(result.warnings.length > 0) && <div className="mt">{result.warnings.map(w => <Info key={w} kind="warn">{w}</Info>)}</div>}
      </div>

      <div className="grid g2 mt" style={{ alignItems: 'start' }}>
        <div className="card" style={{ marginTop: 0 }}>
          <h3>Сравнение сценариев</h3>
          <div className="tablewrap mt-s"><ScenarioTable result={result} /></div>
          {raas.notes.map(n => <p key={n} className="muted mt-s" style={{ fontSize: 12 }}>{n}</p>)}
        </div>
        <div className="card" style={{ marginTop: 0 }}>
          <h3>Накопленные затраты по годам</h3>
          <p className="muted" style={{ fontSize: 12.5 }}>Где линия сценария опускается ниже пунктира «без роботизации» — вложения окупились.</p>
          <div className="mt-s"><CostChart result={result} /></div>
        </div>
      </div>

      <div className="card">
        <h3>Состав затрат и исходные данные расчёта</h3>
        <div className="grid g3 mt">
          <Breakdown title="CAPEX покупки, млн ₽" data={buy.capex_breakdown} />
          <Breakdown title="OPEX покупки, млн ₽/год" data={buy.opex_breakdown} />
          <Breakdown title="OPEX подписки RaaS, млн ₽/год" data={raas.opex_breakdown} />
        </div>
        <div className="grid g2 mt">
          <div>
            <h4>Потребность и парк</h4>
            <table className="t mt-s"><tbody>
              <tr><td>Суточный объём</td><td className="r num">{fmt(d.daily_volume, 1)} {d.unit.replace('/ч', '/сут')}</td></tr>
              <tr><td>Пиковая нагрузка</td><td className="r num">{fmt(d.peak_per_hour, 1)} {d.unit}</td></tr>
              {result.profile.mode === 'mobile' && <tr><td>Маршрут в одну сторону</td><td className="r num">{fmt(d.route_length_m)} м</td></tr>}
              <tr><td>Режим</td><td className="r">{d.shifts} × {d.shift_hours} ч</td></tr>
              <tr><td colSpan={2} style={{ fontSize: 12.5 }}>{result.fleet.basis}</td></tr>
            </tbody></table>
          </div>
          <div>
            <h4>Характеристики робота в расчёте</h4>
            <table className="t mt-s"><tbody>
              {[['throughput', 'Производительность', d.unit], ['speed_ms', 'Скорость', 'м/с'], ['runtime_h', 'Автономность', 'ч'], ['charge_min', 'Зарядка', 'мин']].map(([k, l, u]) => (
                <tr key={k}><td>{l}</td><td className="r num">{fmt(result.robot[k].value, 2)} {u}</td><td style={{ fontSize: 12 }} className="muted">{result.robot[k].source}</td></tr>
              ))}
              <tr><td>Зарплата</td><td className="r num">{fmt(result.staff.salary_month)} ₽/мес</td><td style={{ fontSize: 12 }} className="muted">{result.staff.salary_source}</td></tr>
            </tbody></table>
          </div>
        </div>
      </div>

      <div className="card">
        <div className="card-head">
          <div style={{ flex: 1 }}><h3>Допущения модели</h3><p>Каждый коэффициент — со значением, единицей и источником. Измените значение и пересчитайте: изменение фиксируется в расчёте и отчёте (п. 3.5.3–3.5.4 ТЗ).</p></div>
          <button className="btn" onClick={resetAll} disabled={!Object.keys(overrides).length}>Сбросить</button>
          <button className="btn primary" onClick={applyDraft} disabled={!Object.keys(draft).length}>Пересчитать</button>
        </div>
        <div className="tablewrap" style={{ maxHeight: 360, overflowY: 'auto' }}>
          <table className="t">
            <thead><tr><th>Допущение</th><th style={{ width: 130 }}>Значение</th><th>Ед. изм.</th><th>Источник</th></tr></thead>
            <tbody>{Object.entries(result.assumptions).map(([k, a]) => (
              <tr key={k} className={k in overrides ? 'hl' : ''}>
                <td>{ASSUMPTION_LABELS[k] || k}{k in overrides && <span className="badge accent" style={{ marginLeft: 6 }}>изменено</span>}</td>
                <td><input type="number" step="any" value={draft[k] ?? a.value} onChange={e => setDraft({ ...draft, [k]: e.target.value })} /></td>
                <td className="muted" style={{ fontSize: 12 }}>{a.unit}</td>
                <td className="muted" style={{ fontSize: 12 }}>{a.source}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      </div>

      <div className="card">
        <h3>Как посчитано</h3>
        <p className="muted">Все формулы, входные данные и источники. Эти же таблицы попадают в выгружаемый отчёт.</p>
        <details className="trace mt" open><summary>Потребность, парк и персонал</summary><div className="tablewrap"><StepsTable steps={result.steps} /></div></details>
        {result.scenarios.map(s => (
          <details className="trace" key={s.code}><summary>Сценарий: {s.title}</summary><div className="tablewrap"><StepsTable steps={s.steps} /></div></details>
        ))}
      </div>

      <div className="card">
        <h3>Риски и ограничения</h3>
        <ul style={{ margin: '8px 0 0', paddingLeft: 18 }}>{result.risks.map(r => <li key={r} style={{ marginTop: 4 }}>{r}</li>)}</ul>
        <p className="muted mt" style={{ fontSize: 12 }}>{result.disclaimer}</p>
      </div>

      <div className="stepfoot">
        <button className="btn" onClick={onBack}>← Назад</button>
        <button className="btn primary" onClick={onNext}>What-if анализ →</button>
      </div>
    </div>
  )
}
