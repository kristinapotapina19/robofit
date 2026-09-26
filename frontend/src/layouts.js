// 2D-схемы объектов для визуализации: зоны, маршруты, точки операций и зарядки.
// Схема условная (не чертёж объекта), но длина маршрута, время погрузки, лифт и
// зарядка берутся из параметров расчёта и задают тайминги анимации.

export const W = 960
export const H = 480

const C = {
  zone: '#1e293b', zoneLine: '#475569', text: '#94a3b8', rack: '#334155', rackLine: '#475569',
  road: 'rgba(51, 65, 85, .45)', pick: '#fbbf24', drop: '#22d3ee', charger: '#10b981', cell: '#1e293b',
  clean: 'rgba(16, 185, 129, .35)', wall: '#475569', box: '#0f172a', plane: '#475569',
  pickSoft: 'rgba(251, 191, 36, .15)', dropSoft: 'rgba(34, 211, 238, .15)', chargerSoft: 'rgba(16, 185, 129, .18)',
}

function poly(pts, k) {
  const segs = []
  let total = 0
  for (let i = 1; i < pts.length; i++) {
    const d = Math.hypot(pts[i].x - pts[i - 1].x, pts[i].y - pts[i - 1].y)
    segs.push(d)
    total += d
  }
  if (!total) return { ...pts[pts.length - 1] }
  let dist = Math.max(0, Math.min(1, k)) * total
  for (let i = 0; i < segs.length; i++) {
    if (dist <= segs[i] || i === segs.length - 1) {
      const f = segs[i] ? dist / segs[i] : 1
      return { x: pts[i].x + (pts[i + 1].x - pts[i].x) * f, y: pts[i].y + (pts[i + 1].y - pts[i].y) * f }
    }
    dist -= segs[i]
  }
  return { ...pts[pts.length - 1] }
}

function label(ctx, text, x, y, opts = {}) {
  ctx.fillStyle = opts.color || C.text
  ctx.font = `${opts.bold ? '600 ' : ''}${opts.size || 11}px Inter, Segoe UI, sans-serif`
  ctx.textAlign = opts.align || 'left'
  ctx.fillText(text, x, y)
  ctx.textAlign = 'left'
}

function box(ctx, x, y, w, h, fill, stroke, r = 6) {
  ctx.beginPath()
  ctx.roundRect(x, y, w, h, r)
  ctx.fillStyle = fill
  ctx.fill()
  if (stroke) { ctx.strokeStyle = stroke; ctx.lineWidth = 1; ctx.stroke() }
}

function chargersRow(n, x0, y) {
  return Array.from({ length: Math.max(n, 1) }, (_, i) => ({ x: x0 + i * 26, y }))
}

function drawChargers(ctx, pts) {
  pts.forEach((p, i) => {
    box(ctx, p.x - 10, p.y - 10, 20, 20, C.chargerSoft, C.charger, 4)
    label(ctx, '⚡', p.x, p.y + 4, { align: 'center', color: C.charger, size: 11 })
    if (i === 0) label(ctx, 'Зарядка', p.x - 10, p.y - 15, { size: 10 })
  })
}

function parkingGrid(x0, y0, cols) {
  return (i) => ({ x: x0 + (i % cols) * 18, y: y0 + Math.floor(i / cols) * 18 })
}

// ------------------------------------------------------------------ склад
function warehouse(cfg) {
  const docks = Array.from({ length: 8 }, (_, i) => ({ x: 70, y: 70 + i * 46 }))
  const aislesX = [330, 450, 570, 690, 810]
  const drops = []
  aislesX.forEach(x => { for (let j = 0; j < 6; j++) drops.push({ x, y: 95 + j * 58 }) })
  const chargers = chargersRow(cfg.charger_slots, 150, 455)
  const topY = 48
  const crossX = 180
  const inRacks = (p) => p.x > 250
  return {
    pickCount: docks.length, dropCount: drops.length,
    pickPoint: (i) => docks[i % docks.length],
    dropPoint: (j) => drops[j % drops.length],
    chargerPoint: (k) => chargers[Math.max(0, k) % chargers.length],
    parking: parkingGrid(150, 395, 5),
    path(a, b, k) {
      const pts = [a]
      if (inRacks(a)) pts.push({ x: a.x, y: topY })
      else pts.push({ x: crossX, y: a.y }, { x: crossX, y: topY })
      if (inRacks(b)) pts.push({ x: b.x, y: topY })
      else pts.push({ x: crossX, y: topY }, { x: crossX, y: b.y })
      pts.push(b)
      return poly(pts, k)
    },
    draw(ctx) {
      box(ctx, 20, 30, 110, 400, C.zone, C.zoneLine)
      label(ctx, 'Ворота', 30, 50, { bold: true })
      docks.forEach((d, i) => { box(ctx, 26, d.y - 14, 26, 28, C.box, C.zoneLine, 4); label(ctx, `${i + 1}`, 39, d.y + 4, { align: 'center', size: 10 }) })
      box(ctx, 140, 30, 800, 36, C.road, null, 6)
      label(ctx, 'Главный проезд', 520, 53, { align: 'center' })
      box(ctx, 164, 30, 32, 400, C.road, null, 6)
      for (let r = 0; r < 6; r++) {
        const x = 270 + r * 120
        box(ctx, x, 78, 40, 350, C.rack, C.rackLine, 3)
        for (let j = 1; j < 7; j++) { ctx.strokeStyle = C.rackLine; ctx.beginPath(); ctx.moveTo(x, 78 + j * 50); ctx.lineTo(x + 40, 78 + j * 50); ctx.stroke() }
      }
      label(ctx, 'Паллетные стеллажи (точки выгрузки — в проходах)', 520, 450, { align: 'center' })
      label(ctx, 'Стоянка', 150, 385, { size: 10 })
      drawChargers(ctx, chargers)
    },
    pickLabel: 'Ворота (забор паллеты)', dropLabel: 'Ячейка стеллажа',
  }
}

// ------------------------------------------------------------------ аэропорт
function airport(cfg) {
  const carousels = Array.from({ length: 6 }, (_, i) => ({ x: 150, y: 90 + i * 55 }))
  const stands = []
  for (let i = 0; i < 5; i++) stands.push({ x: 520 + i * 95, y: 120 })
  for (let i = 0; i < 5; i++) stands.push({ x: 520 + i * 95, y: 360 })
  const chargers = chargersRow(cfg.charger_slots, 60, 455)
  const roadY = 240
  return {
    pickCount: carousels.length, dropCount: stands.length,
    pickPoint: (i) => carousels[i % carousels.length],
    dropPoint: (j) => stands[j % stands.length],
    chargerPoint: (k) => chargers[Math.max(0, k) % chargers.length],
    parking: parkingGrid(270, 420, 8),
    path(a, b, k) {
      return poly([a, { x: a.x < 300 ? 250 : a.x, y: a.x < 300 ? a.y : roadY }, { x: a.x < 300 ? 250 : a.x, y: roadY },
        { x: b.x < 300 ? 250 : b.x, y: roadY }, { x: b.x < 300 ? 250 : b.x, y: b.x < 300 ? b.y : roadY }, b], k)
    },
    draw(ctx) {
      box(ctx, 20, 40, 210, 380, C.zone, C.zoneLine)
      label(ctx, 'Сортировка багажа', 32, 60, { bold: true })
      carousels.forEach((c, i) => { box(ctx, 40, c.y - 12, 120, 24, C.box, C.zoneLine, 12); label(ctx, `Накопитель ${i + 1}`, 100, c.y + 4, { align: 'center', size: 10 }) })
      box(ctx, 230, roadY - 16, 710, 32, C.road, null, 4)
      label(ctx, 'Сервисная дорога перрона', 585, roadY + 4, { align: 'center' })
      box(ctx, 236, 40, 28, 380, C.road, null, 4)
      stands.forEach((s, i) => {
        ctx.save(); ctx.translate(s.x, s.y + (i < 5 ? -55 : 55)); ctx.fillStyle = C.plane
        ctx.beginPath(); ctx.ellipse(0, 0, 9, 38, 0, 0, Math.PI * 2); ctx.fill()
        ctx.fillRect(-36, -6, 72, 12); ctx.fillRect(-14, 26, 28, 7); ctx.restore()
        box(ctx, s.x - 16, s.y - 10, 32, 20, C.box, C.zoneLine, 4)
        label(ctx, `С${i + 1}`, s.x, s.y + 4, { align: 'center', size: 10 })
      })
      label(ctx, 'Стоянки воздушных судов', 720, 30, { align: 'center', bold: true })
      drawChargers(ctx, chargers)
    },
    pickLabel: 'Накопитель багажа', dropLabel: 'Стоянка ВС',
  }
}

// ------------------------------------------------------------------ медучреждение
function clinic(cfg) {
  const floors = 9
  const fy = (f) => 440 - (f - 1) * 46
  const services = [{ x: 90, y: fy(1) - 8, name: 'Пищеблок' }, { x: 170, y: fy(1) - 8, name: 'Аптека' }, { x: 250, y: fy(1) - 8, name: 'Прачечная' }]
  const liftX = 340
  const wards = []
  for (let f = 2; f <= floors; f++) { wards.push({ x: 560, y: fy(f) - 8 }); wards.push({ x: 820, y: fy(f) - 8 }) }
  const chargers = chargersRow(cfg.charger_slots, 430, fy(1) - 8)
  return {
    pickCount: services.length, dropCount: wards.length,
    pickPoint: (i) => services[i % services.length],
    dropPoint: (j) => wards[j % wards.length],
    chargerPoint: (k) => chargers[Math.max(0, k) % chargers.length],
    parking: parkingGrid(40, fy(1) - 30, 3),
    path(a, b, k) { return poly([a, { x: liftX, y: a.y }, { x: liftX, y: b.y }, b], k) },
    draw(ctx) {
      for (let f = 1; f <= floors; f++) {
        const y = fy(f)
        box(ctx, 20, y - 36, 920, 40, f === 1 ? C.zone : C.box, C.zoneLine, 4)
        label(ctx, `${f} эт.`, 28, y - 20, { size: 10 })
        if (f > 1) { label(ctx, 'Отделение', 520, y - 22, { size: 10 }); label(ctx, 'Отделение', 780, y - 22, { size: 10 }) }
      }
      services.forEach(s => { box(ctx, s.x - 34, s.y - 12, 68, 22, C.pickSoft, C.pick, 4); label(ctx, s.name, s.x, s.y + 3, { align: 'center', size: 10 }) })
      box(ctx, liftX - 16, fy(floors) - 36, 32, fy(1) - fy(floors) + 40, C.zone, C.rackLine, 4)
      label(ctx, 'Лифты', liftX, fy(floors) - 42, { align: 'center', bold: true })
      drawChargers(ctx, chargers)
    },
    pickLabel: 'Пищеблок / аптека / прачечная', dropLabel: 'Отделение',
  }
}

// ------------------------------------------------------------------ уборка по участкам
function area(cfg) {
  const cols = 16
  const rows = 7
  const cw = 52
  const ch = 52
  const x0 = 60
  const y0 = 50
  const cells = []
  for (let r = 0; r < rows; r++) for (let c = 0; c < cols; c++) cells.push({ x: x0 + c * cw + cw / 2, y: y0 + r * ch + ch / 2, r, c })
  const cleaned = new Map()
  const chargers = chargersRow(cfg.charger_slots, 70, 455)
  return {
    area: true, cleaned,
    pickCount: cells.length, dropCount: 1,
    pickPoint: (i) => cells[i % cells.length],
    dropPoint: () => ({ x: 70, y: 430 }),
    chargerPoint: (k) => chargers[Math.max(0, k) % chargers.length],
    parking: parkingGrid(420, 440, 20),
    path: (a, b, k) => poly([a, b], k),
    cleanPos(i, p) {
      const c = cells[i % cells.length]
      const lanes = 4
      const lane = Math.min(lanes - 1, Math.floor(p * lanes))
      const f = p * lanes - lane
      const x = c.x - cw / 2 + 8 + (lane % 2 ? 1 - f : f) * (cw - 16)
      return { x, y: c.y - ch / 2 + 8 + lane * ((ch - 16) / (lanes - 1)) }
    },
    onDone(task) { cleaned.set(task.pick % cells.length, (cleaned.get(task.pick % cells.length) || 0) + 1) },
    draw(ctx) {
      cells.forEach((c, i) => {
        const n = cleaned.get(i) || 0
        box(ctx, c.x - cw / 2 + 2, c.y - ch / 2 + 2, cw - 4, ch - 4, n ? C.clean : C.cell, null, 4)
        if (n > 1) label(ctx, `×${n}`, c.x, c.y + 4, { align: 'center', size: 10, color: C.charger })
      })
      label(ctx, `Убираемая площадь: участки по ${cfg.task_size || 250} м², зелёным — убранные за смену`, x0, 36, { bold: true })
      drawChargers(ctx, chargers)
    },
    pickLabel: 'Участок уборки', dropLabel: '',
  }
}

// ------------------------------------------------------------------ стационарная система (G2P)
function stationary(cfg) {
  const n = Math.max(cfg.robot_count, 1)
  const stations = Array.from({ length: n }, (_, i) => ({ x: 800, y: 60 + i * Math.min(48, 380 / n) }))
  const cells = []
  for (let r = 0; r < 8; r++) for (let c = 0; c < 12; c++) cells.push({ x: 120 + c * 44, y: 70 + r * 44 })
  return {
    stationary: true,
    pickCount: cells.length, dropCount: n,
    pickPoint: (i) => cells[i % cells.length],
    dropPoint: (j) => stations[j % stations.length],
    chargerPoint: () => ({ x: 0, y: 0 }),
    parking: (i) => stations[i % stations.length],
    path: (a, b, k) => poly([a, { x: 700, y: a.y }, b], k),
    draw(ctx) {
      box(ctx, 100, 48, 540, 360, C.zone, C.zoneLine)
      cells.forEach(c => box(ctx, c.x - 16, c.y - 16, 32, 32, C.box, C.zoneLine, 3))
      label(ctx, 'Система хранения (контейнеры с товаром)', 370, 40, { align: 'center', bold: true })
      stations.forEach((s, i) => { box(ctx, s.x - 40, s.y - 16, 110, 32, C.box, C.zoneLine, 6); label(ctx, `Станция ${i + 1}`, s.x + 30, s.y + 4, { size: 10 }) })
      label(ctx, 'Станции отбора', 830, 36, { align: 'center', bold: true })
    },
    pickLabel: 'Ячейка хранения', dropLabel: 'Станция отбора',
  }
}

// ------------------------------------------------------------------ произвольный объект
function generic(cfg) {
  const picks = Array.from({ length: 5 }, (_, i) => ({ x: 110, y: 90 + i * 70 }))
  const drops = Array.from({ length: 5 }, (_, i) => ({ x: 850, y: 90 + i * 70 }))
  const chargers = chargersRow(cfg.charger_slots, 400, 455)
  return {
    pickCount: picks.length, dropCount: drops.length,
    pickPoint: (i) => picks[i % picks.length],
    dropPoint: (j) => drops[j % drops.length],
    chargerPoint: (k) => chargers[Math.max(0, k) % chargers.length],
    parking: parkingGrid(420, 400, 10),
    path: (a, b, k) => poly([a, { x: a.x < 480 ? 200 : 760, y: a.y }, { x: a.x < 480 ? 200 : 760, y: 240 }, { x: b.x < 480 ? 200 : 760, y: 240 }, { x: b.x < 480 ? 200 : 760, y: b.y }, b], k),
    draw(ctx) {
      box(ctx, 40, 50, 140, 350, C.zone, C.zoneLine); label(ctx, 'Точки забора', 110, 70, { align: 'center', bold: true })
      box(ctx, 780, 50, 140, 350, C.zone, C.zoneLine); label(ctx, 'Точки выгрузки', 850, 70, { align: 'center', bold: true })
      box(ctx, 180, 224, 600, 32, C.road, null, 4); label(ctx, 'Маршрут', 480, 244, { align: 'center' })
      picks.forEach(p => box(ctx, p.x - 12, p.y - 12, 24, 24, C.pickSoft, C.pick, 4))
      drops.forEach(p => box(ctx, p.x - 12, p.y - 12, 24, 24, C.dropSoft, C.drop, 4))
      drawChargers(ctx, chargers)
    },
    pickLabel: 'Точка забора', dropLabel: 'Точка выгрузки',
  }
}

export function makeLayout(cfg) {
  if (cfg.mode === 'area') return area(cfg)
  if (cfg.mode === 'stationary') return stationary(cfg)
  return ({ warehouse, airport, clinic }[cfg.layout] || generic)(cfg)
}

export const COLORS = C
