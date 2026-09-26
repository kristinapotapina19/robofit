import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { saveBlob } from '../api.js'
import { Spark } from '../components/Charts.jsx'
import { makeLayout, H, W } from '../layouts.js'
import { S, Simulation } from '../sim.js'
import { fmt, pct } from '../format.js'

const ROBOT_COLORS = {
  [S.TO_PICK]: '#a78bfa', [S.TO_DROP]: '#d946ef', [S.LOADING]: '#fbbf24', [S.UNLOADING]: '#fbbf24',
  [S.CHARGING]: '#10b981', [S.IDLE]: '#64748b',
}
const SPEEDS = [30, 120, 600, 1800]

function hhmm(t) {
  const h = Math.floor(t / 3600)
  const m = Math.floor((t % 3600) / 60)
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`
}

export default function SimulationStep({ result, onBack, onNext }) {
  const canvasRef = useRef(null)
  const simRef = useRef(null)
  const rafRef = useRef(0)
  const [variant, setVariant] = useState('accepted')
  const [custom, setCustom] = useState(result?.fleet.count || 1)
  const [load, setLoad] = useState('peak')
  const [speed, setSpeed] = useState(600)
  const [running, setRunning] = useState(false)
  const [stats, setStats] = useState(null)
  const [version, setVersion] = useState(0)

  const cfg0 = result?.sim_config
  const fleet = variant === 'accepted' ? result?.fleet.count : variant === 'passport' ? cfg0?.passport_fleet : Math.max(1, custom)
  const cfg = useMemo(() => {
    if (!cfg0) return null
    const peakTasks = cfg0.arrival_rate_per_h
    const peakFactor = result.demand.peak_per_hour / (result.demand.daily_volume / (result.demand.shifts * result.demand.shift_hours))
    const rate = load === 'peak' ? peakTasks : peakTasks / (peakFactor || 1)
    const chargers = cfg0.charge_min > 0 && cfg0.runtime_h < 10000
      ? Math.max(1, Math.ceil(fleet / (result.assumptions.robots_per_charger?.value || 4))) : cfg0.charger_slots
    return { ...cfg0, robot_count: fleet, arrival_rate_per_h: rate, charger_slots: chargers }
  }, [cfg0, fleet, load, result])

  const draw = useCallback(() => {
    const canvas = canvasRef.current
    const sim = simRef.current
    if (!canvas || !sim) return
    const ctx = canvas.getContext('2d')
    const dpr = window.devicePixelRatio || 1
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    ctx.clearRect(0, 0, W, H)
    ctx.fillStyle = '#020617'
    ctx.fillRect(0, 0, W, H)
    ctx.strokeStyle = 'rgba(51, 65, 85, .5)'
    ctx.lineWidth = 0.5
    for (let x = 0; x < W; x += 40) { ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, H); ctx.stroke() }
    for (let y = 0; y < H; y += 40) { ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(W, y); ctx.stroke() }
    const L = sim.layout
    L.draw(ctx)
    // очередь задач у точек забора
    if (!L.area && !L.stationary) {
      const byPick = {}
      sim.queue.forEach(q => { byPick[q.pick] = (byPick[q.pick] || 0) + 1 })
      Object.entries(byPick).forEach(([i, n]) => {
        const p = L.pickPoint(Number(i))
        for (let k = 0; k < Math.min(n, 6); k++) { ctx.fillStyle = '#fbbf24'; ctx.fillRect(p.x + 16 + k * 7, p.y - 4, 5, 8) }
        if (n > 6) { ctx.fillStyle = '#b7791f'; ctx.font = '10px sans-serif'; ctx.fillText(`+${n - 6}`, p.x + 60, p.y + 4) }
      })
    }
    if (L.stationary) {
      sim.robots.forEach(r => {
        const st = L.parking(r.id)
        if (r.task) {
          const from = L.pickPoint(r.task.pick)
          const h = sim.cfg.handling_s || 1
          const k = r.state === S.LOADING ? 1 - r.timer / h : 1
          const p = L.path(from, st, k)
          ctx.fillStyle = '#fbbf24'; ctx.fillRect(p.x - 7, p.y - 7, 14, 14)
        }
      })
    }
    sim.robots.forEach(r => {
      const p = sim.position(r)
      if (L.stationary) {
        ctx.beginPath(); ctx.roundRect(p.x - 40, p.y - 16, 110, 32, 6)
        ctx.strokeStyle = r.task ? '#ec4899' : '#475569'; ctx.lineWidth = r.task ? 2.5 : 1; ctx.stroke()
        ctx.fillStyle = r.task ? '#ec4899' : '#64748b'; ctx.beginPath(); ctx.arc(p.x - 28, p.y, 6, 0, Math.PI * 2); ctx.fill()
        return
      }
      ctx.beginPath()
      ctx.arc(p.x, p.y, 8, 0, Math.PI * 2)
      ctx.fillStyle = ROBOT_COLORS[r.state]
      ctx.fill()
      ctx.lineWidth = r.waitingCharger ? 2.5 : 1.5
      ctx.strokeStyle = r.waitingCharger ? '#fb7185' : '#ffffff'
      ctx.stroke()
      if (r.state === S.TO_DROP) { ctx.fillStyle = '#fbbf24'; ctx.fillRect(p.x - 3, p.y - 3, 6, 6) }
    })
    ctx.fillStyle = 'rgba(30, 41, 59, .9)'
    ctx.beginPath(); ctx.roundRect(W - 200, H - 34, 190, 26, 6); ctx.fill()
    ctx.fillStyle = '#fff'; ctx.font = '600 12px Inter, sans-serif'
    ctx.fillText(`Время смены ${hhmm(sim.t)} / ${hhmm(sim.total)}`, W - 190, H - 17)
  }, [])

  // пересоздание модели при смене сценария
  useEffect(() => {
    if (!cfg) return
    cancelAnimationFrame(rafRef.current)
    const layout = makeLayout(cfg)
    simRef.current = new Simulation(cfg, layout)
    setStats(simRef.current.stats())
    setRunning(false)
    const canvas = canvasRef.current
    if (canvas) {
      const dpr = window.devicePixelRatio || 1
      canvas.width = W * dpr
      canvas.height = H * dpr
    }
    draw()
  }, [cfg, version, draw])

  useEffect(() => {
    if (!running) return
    let last = performance.now()
    let acc = 0
    let frame = 0
    const tick = (now) => {
      const sim = simRef.current
      const dt = Math.min(0.1, (now - last) / 1000)
      last = now
      acc += dt * speed
      let n = Math.floor(acc)
      acc -= n
      while (n-- > 0 && !sim.finished) sim.step()
      draw()
      if (++frame % 6 === 0 || sim.finished) setStats(sim.stats())
      if (sim.finished) { setRunning(false); setStats(sim.stats()); return }
      rafRef.current = requestAnimationFrame(tick)
    }
    rafRef.current = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(rafRef.current)
  }, [running, speed, draw])

  if (!result) return <div className="card"><div className="empty">Сначала выполните расчёт экономики.</div></div>
  const sim = simRef.current
  const unitK = cfg?.task_size || 1
  const required = (cfg?.arrival_rate_per_h || 0) * unitK
  const achieved = (stats?.achievedPerH || 0) * unitK
  const finished = sim?.finished
  const coverage = required ? achieved / required : 0
  const serverMatch = finished && variant === 'accepted' && load === 'peak'
    ? Math.abs(stats.achievedPerH - result.simulation.achieved_per_h) < 0.15 : null
  const unit = result.demand.unit

  const exportPng = () => canvasRef.current?.toBlob(b => saveBlob(b, `визуализация_${result.profile.code}_${fleet}_роботов.png`))

  return (
    <div>
      <div className="card">
        <div className="card-head">
          <div style={{ flex: 1 }}>
            <h2>Шаг 7. Имитация работы роботов на объекте</h2>
            <p>Модель прогоняет смену посекундно: задачи появляются с расчётной интенсивностью, роботы едут к точке забора, грузят, везут, выгружают и уходят на зарядку. Это та же модель, по которой сервер проверил парк, — анимация подтверждает расчёт, а не иллюстрирует его.</p>
          </div>
        </div>
        <div className="row">
          <span className="muted">Сценарий:</span>
          <div className="seg">
            <button className={variant === 'accepted' ? 'on' : ''} onClick={() => setVariant('accepted')}>Принятый парк · {result.fleet.count}</button>
            <button className={variant === 'passport' ? 'on' : ''} onClick={() => setVariant('passport')}>По паспорту · {cfg0.passport_fleet}</button>
            <button className={variant === 'custom' ? 'on' : ''} onClick={() => setVariant('custom')}>Свой</button>
          </div>
          {variant === 'custom' && <input type="number" min={1} max={200} value={custom} onChange={e => setCustom(Number(e.target.value) || 1)} style={{ width: 70 }} />}
          <div className="seg">
            <button className={load === 'peak' ? 'on' : ''} onClick={() => setLoad('peak')}>Пиковая нагрузка</button>
            <button className={load === 'avg' ? 'on' : ''} onClick={() => setLoad('avg')}>Средняя</button>
          </div>
          <div className="spacer" />
          <span className="muted">Скорость:</span>
          <div className="seg">{SPEEDS.map(s => <button key={s} className={speed === s ? 'on' : ''} onClick={() => setSpeed(s)}>×{s}</button>)}</div>
        </div>
        <div className="row mt">
          <button className="btn primary" onClick={() => setRunning(!running)} disabled={finished}>{running ? '❚❚ Пауза' : sim?.t ? '▶ Продолжить' : '▶ Запустить'}</button>
          <button className="btn" onClick={() => setVersion(v => v + 1)}>↺ Перезапустить</button>
          <button className="btn ghost" onClick={exportPng}>Сохранить кадр PNG</button>
        </div>
        <div className="simwrap mt">
          <div>
            <canvas ref={canvasRef} className="simcanvas" style={{ aspectRatio: `${W} / ${H}` }} aria-label="Схема объекта с роботами" />
            <div className="legend">
              <span><i className="dot" style={{ background: '#d946ef', borderRadius: 5 }} />едет с грузом</span>
              <span><i className="dot" style={{ background: '#a78bfa', borderRadius: 5 }} />едет за грузом</span>
              <span><i className="dot" style={{ background: '#fbbf24', borderRadius: 5 }} />{result.profile.mode === 'area' ? 'убирает участок' : 'погрузка / выгрузка'}</span>
              <span><i className="dot" style={{ background: '#10b981', borderRadius: 5 }} />на зарядке</span>
              <span><i className="dot" style={{ background: '#64748b', borderRadius: 5 }} />свободен</span>
              <span><i className="dot" style={{ border: '2px solid #fb7185' }} />ждёт зарядную станцию</span>
              {!['area', 'stationary'].includes(result.profile.mode) && <span><i className="dot" style={{ background: '#fbbf24' }} />задачи в очереди у точки забора</span>}
            </div>
          </div>
          <div className="card" style={{ padding: 14, boxShadow: 'none' }}>
            <h4>Показатели в реальном времени</h4>
            <div className="mt-s">
              <div className="progress"><i style={{ width: `${(stats?.t || 0) / (sim?.total || 1) * 100}%` }} /></div>
              <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>Смена {cfg.duration_h} ч · роботов {fleet} · зарядных станций {cfg.charger_slots}</div>
            </div>
            <div className="mt-s">
              <div className="metric"><span>Требуется</span><b>{fmt(required, 1)} {unit}</b></div>
              <div className="metric"><span>Выполняется (среднее)</span><b style={{ color: coverage >= 0.98 ? 'var(--good)' : coverage > 0.9 ? 'var(--warn)' : 'var(--bad)' }}>{fmt(achieved, 1)} {unit}</b></div>
              <div className="metric"><span>За последний час</span><b>{fmt((stats?.lastHour || 0) * unitK, 0)}</b></div>
              <div className="metric"><span>Выполнено задач</span><b>{fmt(stats?.completed)} из {fmt(stats?.generated)}</b></div>
              <div className="metric"><span>В очереди</span><b>{fmt(stats?.queue)}</b></div>
              <div className="metric"><span>Среднее ожидание задачи</span><b>{fmt((stats?.avgWait || 0) / 60, 1)} мин</b></div>
              <div className="metric"><span>Загрузка парка</span><b>{pct(stats?.utilization)}</b></div>
              <div className="metric"><span>Простой / зарядка</span><b>{pct(stats?.idle)} / {pct(stats?.charging)}</b></div>
              <div className="metric"><span>Сейчас в работе / на зарядке</span><b>{stats?.busyNow} / {stats?.chargingNow}</b></div>
            </div>
            <div className="mt-s"><Spark history={sim?.history || []} total={sim?.total || 1} /></div>
            <div className="legend"><span><i className="dot" style={{ background: 'var(--accent)' }} />выполнено</span><span><i className="dot" style={{ background: 'var(--warn)' }} />очередь</span></div>
          </div>
        </div>
        {finished && (
          <div className="mt">
            <div className={`alert ${coverage >= 0.98 ? 'info' : 'bad'}`}>
              <b>Итог смены: </b>парк из {fleet} роботов закрыл {fmt(coverage * 100)}% потребности ({fmt(achieved, 1)} из {fmt(required, 1)} {unit}).
              {coverage >= 0.98 ? ' Расчётная производительность подтверждается.' : ' Парка недостаточно: очередь растёт, нужно больше роботов или короче маршруты.'}
              {serverMatch !== null && <span> {serverMatch ? 'Результат совпадает с проверкой на сервере.' : 'Результат отличается от серверной проверки.'}</span>}
            </div>
          </div>
        )}
        {!finished && <p className="muted mt-s" style={{ fontSize: 12.5 }}>Серверная проверка принятого парка: {result.simulation.verdict}. {result.simulation.bottleneck}.</p>}
      </div>
      <div className="stepfoot">
        <button className="btn" onClick={onBack}>← Назад</button>
        <button className="btn primary" onClick={onNext}>Сохранение и отчёт →</button>
      </div>
    </div>
  )
}
