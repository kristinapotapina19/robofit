// Имитационная модель работы парка — та же логика, что в backend/app/core/simulation.py
// (шаг 1 секунда, те же состояния, та же зарядка), поэтому анимация воспроизводит
// ровно тот прогон, по которому бэкенд подтвердил парк. Визуализация не декоративная:
// каждое движение робота на схеме — это состояние модели в данный момент (п. 3.6.2 ТЗ).

export const S = {
  IDLE: 'idle', TO_PICK: 'to_pick', LOADING: 'loading', TO_DROP: 'to_drop',
  UNLOADING: 'unloading', CHARGING: 'charging',
}

function rng(seed) {
  let s = seed >>> 0
  return () => { s = (s * 1664525 + 1013904223) >>> 0; return s / 4294967296 }
}

export function travelLeg(cfg) {
  if (cfg.route_length_m <= 0) return cfg.extra_leg_s || 0
  return cfg.route_length_m / cfg.speed_ms * cfg.traffic_factor + (cfg.extra_leg_s || 0)
}

export class Simulation {
  constructor(cfg, layout) {
    this.cfg = { ...cfg }
    this.layout = layout
    this.leg = travelLeg(cfg)
    this.total = Math.floor(cfg.duration_h * 3600)
    this.interval = cfg.arrival_rate_per_h ? 3600 / cfg.arrival_rate_per_h : 1e9
    this.rand = rng(42)
    this.reset()
  }

  reset() {
    const n = Math.max(this.cfg.robot_count, 1)
    this.t = 0
    this.nextArrival = 0
    this.queue = []
    this.waits = []
    this.completed = 0
    this.generated = 0
    this.chargingNow = 0
    this.history = []
    this.recent = []
    this.robots = Array.from({ length: this.cfg.robot_count }, (_, i) => ({
      id: i, state: S.IDLE, timer: 0, done: 0, busy: 0, idle: 0, charge: 0, chargeWait: 0,
      waitingCharger: false,
      energy: this.cfg.runtime_h * 3600 * (1 - 0.5 * i / n),
      task: null, pos: this.layout.parking(i), from: null, charger: -1,
    }))
  }

  get finished() { return this.t >= this.total }

  newTask() {
    const L = this.layout
    return {
      created: this.nextArrival,
      pick: L.area ? this.generated % L.pickCount : Math.floor(this.rand() * L.pickCount),
      drop: Math.floor(this.rand() * L.dropCount),
    }
  }

  step() {
    if (this.finished) return
    const cfg = this.cfg
    const t = this.t
    while (this.nextArrival <= t) {
      this.queue.push(this.newTask())
      this.generated += 1
      this.nextArrival += this.interval
    }
    for (const r of this.robots) {
      if ([S.TO_PICK, S.TO_DROP, S.LOADING, S.UNLOADING].includes(r.state)) { r.busy += 1; r.energy -= 1 }
      else if (r.state === S.CHARGING) r.charge += 1
      else if (r.waitingCharger) r.chargeWait += 1
      else r.idle += 1

      if (r.timer > 0) {
        r.timer -= 1
        continue
      }
      if (r.state === S.IDLE) {
        if (r.energy <= this.leg * 2 + cfg.handling_s * 2) {
          if (this.chargingNow < cfg.charger_slots) {
            this.chargingNow += 1
            r.waitingCharger = false
            r.charger = this.freeCharger()
            r.state = S.CHARGING
            r.timer = cfg.charge_min * 60
          } else {
            r.waitingCharger = true
          }
          continue
        }
        if (this.queue.length) {
          const task = this.queue.shift()
          this.waits.push(t - task.created)
          r.task = task
          r.from = r.pos
          r.state = S.TO_PICK
          r.timer = this.leg
          r.legTotal = this.leg
        }
      } else if (r.state === S.TO_PICK) {
        r.state = S.LOADING; r.timer = cfg.handling_s
      } else if (r.state === S.LOADING) {
        r.state = S.TO_DROP; r.timer = this.leg; r.legTotal = this.leg
      } else if (r.state === S.TO_DROP) {
        r.state = S.UNLOADING; r.timer = cfg.handling_s
      } else if (r.state === S.UNLOADING) {
        r.done += 1
        this.completed += 1
        this.recent.push(t)
        if (this.layout.onDone) this.layout.onDone(r.task)
        r.pos = this.layout.area ? this.layout.pickPoint(r.task.pick) : this.layout.dropPoint(r.task.drop)
        r.task = null
        r.state = S.IDLE
      } else if (r.state === S.CHARGING) {
        this.chargingNow -= 1
        r.energy = cfg.runtime_h * 3600
        r.charger = -1
        r.pos = this.layout.parking(r.id)
        r.state = S.IDLE
      }
    }
    if (t % 600 === 0) {
      this.history.push({
        minute: t / 60, completed: this.completed, queue: this.queue.length,
        busy: this.robots.filter(r => r.state !== S.IDLE && r.state !== S.CHARGING).length,
      })
    }
    this.t += 1
    while (this.recent.length && this.recent[0] < this.t - 3600) this.recent.shift()
  }

  freeCharger() {
    const used = new Set(this.robots.map(r => r.charger))
    for (let i = 0; i < this.cfg.charger_slots; i++) if (!used.has(i)) return i
    return 0
  }

  /** Положение робота на схеме в текущий момент. */
  position(r) {
    const L = this.layout
    if (L.stationary) return L.parking(r.id)
    if (r.state === S.CHARGING) return L.chargerPoint(r.charger)
    if (L.area && r.task) {
      const h = this.cfg.handling_s || 1
      if (r.state === S.LOADING) return L.cleanPos(r.task.pick, 0.5 * (1 - r.timer / h))
      if (r.state === S.UNLOADING) return L.cleanPos(r.task.pick, 0.5 + 0.5 * (1 - r.timer / h))
      return L.pickPoint(r.task.pick)
    }
    if (r.state === S.TO_PICK) {
      const k = r.legTotal ? 1 - r.timer / r.legTotal : 1
      return L.path(r.from, L.pickPoint(r.task.pick), k, 'to_pick')
    }
    if (r.state === S.LOADING) return L.pickPoint(r.task.pick)
    if (r.state === S.TO_DROP) {
      const k = r.legTotal ? 1 - r.timer / r.legTotal : 1
      return L.path(L.pickPoint(r.task.pick), L.dropPoint(r.task.drop), k, 'to_drop')
    }
    if (r.state === S.UNLOADING) return L.dropPoint(r.task.drop)
    return r.pos
  }

  stats() {
    const b = this.robots.reduce((s, r) => s + r.busy, 0)
    const i = this.robots.reduce((s, r) => s + r.idle, 0)
    const cw = this.robots.reduce((s, r) => s + r.chargeWait, 0)
    const c = this.robots.reduce((s, r) => s + r.charge, 0) + cw
    const tot = Math.max(b + i + c, 1)
    const hours = Math.max(this.t / 3600, 1e-9)
    return {
      t: this.t,
      completed: this.completed,
      generated: this.generated,
      queue: this.queue.length,
      achievedPerH: this.completed / hours,
      lastHour: this.recent.length,
      utilization: b / tot,
      idle: i / tot,
      charging: c / tot,
      avgWait: this.waits.length ? this.waits.reduce((s, x) => s + x, 0) / this.waits.length : 0,
      busyNow: this.robots.filter(r => r.state !== S.IDLE && r.state !== S.CHARGING).length,
      chargingNow: this.robots.filter(r => r.state === S.CHARGING || r.waitingCharger).length,
    }
  }
}
