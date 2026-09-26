"""
Имитационная модель работы роботов на объекте (п. 3.6 ТЗ).

Зачем нужна: расчёт количества роботов опирается на паспортную производительность.
Симуляция проверяет её независимо — через физику маршрута: расстояние, скорость,
время на захват и установку груза, зарядку. Если симуляция даёт меньше, чем
паспорт, значит парк недоукомплектован, и платформа обязана это показать.

Модель пошаговая, шаг 1 секунда. Робот последовательно проходит состояния:
ожидание задачи → едет к точке забора → грузит → едет к точке выгрузки →
разгружает → возвращается. Когда заряд заканчивается, уходит на зарядку.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict

IDLE, TO_PICK, LOADING, TO_DROP, UNLOADING, TO_CHARGE, CHARGING = (
    "idle", "to_pick", "loading", "to_drop", "unloading", "to_charge", "charging")


@dataclass
class SimConfig:
    robot_count: int
    speed_ms: float = 1.5
    route_length_m: float = 120.0          # средняя длина маршрута в одну сторону
    handling_s: float = 45.0               # захват или установка груза
    runtime_h: float = 6.0                 # автономность по паспорту
    charge_min: float = 18.0               # время зарядки
    charger_slots: int = 2
    arrival_rate_per_h: float = 136.0      # пиковая потребность из расчёта
    duration_h: float = 11.0               # длительность смены
    traffic_factor: float = 1.15           # замедление из-за расхождения роботов
    extra_leg_s: float = 0.0               # лифт, шлюз, ожидание на каждом плече


@dataclass
class Robot:
    id: int
    state: str = IDLE
    timer: float = 0.0
    energy_s: float = 0.0
    done: int = 0
    busy_s: float = 0.0
    idle_s: float = 0.0
    charge_s: float = 0.0
    charge_wait_s: float = 0.0             # ждёт свободную зарядную станцию
    waiting_charger: bool = False
    x: float = 0.0                          # положение на маршруте 0..1 для анимации


@dataclass
class SimResult:
    completed: int
    generated: int
    backlog: int
    utilization: float
    idle_share: float
    charging_share: float
    charge_wait_share: float
    avg_wait_s: float
    achieved_per_h: float
    required_per_h: float
    cycle_time_s: float
    theoretical_per_robot_h: float
    bottleneck: str
    verdict: str
    timeline: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


def cycle_time(cfg: SimConfig) -> float:
    """Полный цикл: путь к грузу, погрузка, путь к месту выгрузки, выгрузка."""
    return travel_leg(cfg) * 2 + cfg.handling_s * 2


def travel_leg(cfg: SimConfig) -> float:
    if cfg.route_length_m <= 0:
        return cfg.extra_leg_s
    return cfg.route_length_m / cfg.speed_ms * cfg.traffic_factor + cfg.extra_leg_s


def simulate(cfg: SimConfig) -> SimResult:
    robots = [Robot(i) for i in range(cfg.robot_count)]
    # заряд на начало смены распределён равномерно от 50 до 100%: парк не приходит
    # на смену полностью заряженным одновременно, иначе все роботы уходят на зарядку
    # в один момент и имитация показывает искусственное узкое место
    n = max(len(robots), 1)
    for r in robots:
        r.energy_s = cfg.runtime_h * 3600 * (1 - 0.5 * r.id / n)

    leg = travel_leg(cfg)
    total_s = int(cfg.duration_h * 3600)
    arrival_interval = 3600 / cfg.arrival_rate_per_h if cfg.arrival_rate_per_h else 1e9

    queue: list[float] = []          # моменты появления задач
    waits: list[float] = []
    charging_now = 0
    completed = generated = 0
    next_arrival = 0.0
    timeline: list[dict] = []

    for t in range(total_s):
        while next_arrival <= t:
            queue.append(next_arrival)
            generated += 1
            next_arrival += arrival_interval

        for r in robots:
            if r.state in (TO_PICK, TO_DROP, LOADING, UNLOADING):
                r.busy_s += 1
                r.energy_s -= 1
            elif r.state == CHARGING:
                r.charge_s += 1
            elif r.waiting_charger:
                r.charge_wait_s += 1
            else:
                r.idle_s += 1

            if r.timer > 0:
                r.timer -= 1
                if r.state in (TO_PICK, TO_DROP):
                    r.x = 1 - r.timer / leg if leg else 0
                continue

            if r.state == IDLE:
                if r.energy_s <= leg * 2 + cfg.handling_s * 2:
                    if charging_now < cfg.charger_slots:
                        charging_now += 1
                        r.waiting_charger = False
                        r.state, r.timer = CHARGING, cfg.charge_min * 60
                    else:
                        r.waiting_charger = True
                    continue
                if queue:
                    created = queue.pop(0)
                    waits.append(t - created)
                    r.state, r.timer = TO_PICK, leg
            elif r.state == TO_PICK:
                r.state, r.timer = LOADING, cfg.handling_s
            elif r.state == LOADING:
                r.state, r.timer = TO_DROP, leg
            elif r.state == TO_DROP:
                r.state, r.timer = UNLOADING, cfg.handling_s
            elif r.state == UNLOADING:
                r.done += 1
                completed += 1
                r.state = IDLE
            elif r.state == CHARGING:
                charging_now -= 1
                r.energy_s = cfg.runtime_h * 3600
                r.state = IDLE

        if t % 600 == 0:
            timeline.append({
                "minute": t // 60,
                "completed": completed,
                "queue": len(queue),
                "busy_robots": sum(1 for r in robots if r.state not in (IDLE, CHARGING)),
                "charging_robots": sum(1 for r in robots if r.state == CHARGING or r.waiting_charger),
            })

    busy = sum(r.busy_s for r in robots)
    idle = sum(r.idle_s for r in robots)
    charge_wait = sum(r.charge_wait_s for r in robots)
    charge = sum(r.charge_s for r in robots) + charge_wait
    total_robot_s = max(busy + idle + charge, 1)
    achieved = completed / cfg.duration_h
    cycle = cycle_time(cfg)
    theoretical = 3600 / cycle if cycle else 0

    if len(queue) > cfg.arrival_rate_per_h * 0.5:
        bottleneck = "Не хватает роботов: очередь задач растёт в течение смены"
    elif charge_wait / total_robot_s > 0.05:
        bottleneck = ("Узкое место — зарядные станции: роботы ждут свободную станцию "
                      "(%.0f%% времени парка)" % (charge_wait / total_robot_s * 100))
    elif charge / total_robot_s > 0.15:
        bottleneck = ("Существенная доля времени уходит на зарядку (%.0f%%) — "
                      "парк рассчитан с её учётом" % (charge / total_robot_s * 100))
    elif idle / total_robot_s > 0.3:
        bottleneck = ("Загрузка парка невысокая (простой %.0f%%): резерв из-за округления до "
                      "целого числа роботов и неравномерности пиков" % (idle / total_robot_s * 100))
    else:
        bottleneck = "Явного узкого места нет"

    coverage = achieved / cfg.arrival_rate_per_h if cfg.arrival_rate_per_h else 0
    if coverage >= 0.98:
        verdict = "Расчётная производительность подтверждается имитацией"
    elif coverage >= 0.9:
        verdict = ("Имитация закрывает %.0f%% потребности: нужен резерв или "
                   "увеличение парка на одну единицу" % (coverage * 100))
    else:
        verdict = ("Имитация закрывает лишь %.0f%% потребности: расчёт парка "
                   "занижен, требуется пересчёт" % (coverage * 100))

    return SimResult(
        completed=completed, generated=generated, backlog=len(queue),
        utilization=round(busy / total_robot_s, 3),
        idle_share=round(idle / total_robot_s, 3),
        charging_share=round(charge / total_robot_s, 3),
        charge_wait_share=round(charge_wait / total_robot_s, 3),
        avg_wait_s=round(sum(waits) / len(waits), 1) if waits else 0.0,
        achieved_per_h=round(achieved, 1),
        required_per_h=cfg.arrival_rate_per_h,
        cycle_time_s=round(cycle, 1),
        theoretical_per_robot_h=round(theoretical, 1),
        bottleneck=bottleneck, verdict=verdict, timeline=timeline,
    )


def fleet_by_simulation(cfg: SimConfig, max_robots: int = 120,
                        coverage_target: float = 0.98, start: int = 1) -> tuple[int, SimResult]:
    """Минимальный парк, при котором имитация закрывает потребность.

    Нужен, потому что паспортная производительность из каталога измеряется в
    типовой конфигурации зоны и не учитывает длину маршрутов конкретного объекта.
    Платформа берёт большее из двух значений и показывает расхождение.
    """
    last: SimResult | None = None
    for n in range(max(1, start), max_robots + 1):
        probe = SimConfig(**{**cfg.__dict__, "robot_count": n})
        result = simulate(probe)
        last = result
        if result.achieved_per_h >= cfg.arrival_rate_per_h * coverage_target:
            return n, result
    return max_robots, last


def reconcile(passport_fleet: int, simulated_fleet: int,
              passport_per_h: float, simulated_per_h: float) -> dict:
    """Сверка паспортной производительности с имитацией (п. 3.6.2)."""
    if simulated_fleet <= passport_fleet:
        return {
            "fleet": passport_fleet,
            "agreement": True,
            "message": "Имитация подтверждает расчёт по паспортной производительности.",
        }
    return {
        "fleet": simulated_fleet,
        "agreement": False,
        "message": (
            "Паспортная производительность %.0f оп./ч даёт парк %d ед., но на маршрутах "
            "этого объекта робот реально выполняет %.1f оп./ч, поэтому требуется %d ед. "
            "В расчёт принята имитационная оценка; паспортное значение относится к "
            "типовой конфигурации зоны и должно быть подтверждено вендором."
            % (passport_per_h, passport_fleet, simulated_per_h, simulated_fleet)
        ),
    }
