"""
Сквозной расчёт по объекту: параметры → потребность → парк (паспорт + имитация) →
три сценария → чувствительность → рекомендация.

Все шаги возвращаются с трассировкой (формула, входы, источник), поэтому
интерфейс и отчёт показывают, откуда взялась каждая цифра (п. 3.5.8 ТЗ).
Модуль не зависит от FastAPI и БД.
"""
from __future__ import annotations

import math
from typing import Any

from app.core import economics as ec
from app.core import operations as ops
from app.core.selection import select
from app.core.simulation import SimConfig, fleet_by_simulation, reconcile, simulate

MODEL_VERSION = "1.2.0"

PAYBACK_BANDS = [
    (3, "good", "Рекомендуется",
     "Окупаемость до 3 лет: проект экономически обоснован, можно переходить к ТЭО и пилоту."),
    (5, "medium", "Целесообразно после пилота",
     "Окупаемость 3–5 лет: эффект есть, но чувствителен к допущениям — подтвердите "
     "производительность и цены пилотом."),
    (None, "bad", "Не рекомендуется в текущих условиях",
     "Окупаемость более 5 лет или эффект отрицательный: при текущих параметрах роботизация "
     "операции не окупается."),
]


def assumptions_with(overrides: dict[str, float] | None,
                     extra: dict[str, ec.Assumption] | None = None) -> dict[str, ec.Assumption]:
    data = {k: ec.Assumption(v.value, v.unit, v.source) for k, v in ec.DEFAULT_ASSUMPTIONS.items()}
    for k, v in (extra or {}).items():
        data[k] = v
    for key, value in (overrides or {}).items():
        if key in data and value is not None:
            data[key] = ec.Assumption(float(value), data[key].unit,
                                      "Изменено пользователем в интерфейсе "
                                      f"(по умолчанию {data[key].value})")
    return data


def selection_context(profile: ops.OperationProfile, params: dict) -> dict:
    aisle = ops.optional(profile, params, "aisle_param", 1000)
    budget = ops.optional(profile, params, "budget_param", 1_000_000)
    return {
        "object_type": profile.object_type,
        "profile_subtypes": profile.subtypes,
        "cargo_mass_kg": ops.cargo_mass(profile, params),
        "aisle_width_mm": aisle,
        "capex_budget_rub": budget,
        "industry": profile.raw.get("industry"),
    }


def run_selection(solutions: list[dict], profile: ops.OperationProfile, params: dict) -> dict:
    ctx = selection_context(profile, params)
    result = select(solutions, ctx)
    return {
        "context": ctx,
        "total": len(result),
        "fit": [c for c in result if c["verdict"] == "fit"],
        "check_needed": [c for c in result if c["verdict"] == "check_needed"],
        "excluded": [c for c in result if c["verdict"] == "excluded"],
    }


def _spec(sol: dict, key: str) -> Any:
    v = sol["specs"].get(key)
    return v.get("value") if isinstance(v, dict) else None


def robot_parameters(sol: dict, profile: ops.OperationProfile, A: dict,
                     throughput_override: float | None) -> dict:
    """Скорость, автономность, зарядка, производительность — с источником каждой."""
    out: dict[str, Any] = {}
    speed = _spec(sol, "speed_ms")
    out["speed_ms"] = (speed, "паспорт решения") if speed else (
        ec.a(A, "default_speed_ms"), "допущение: default_speed_ms")
    runtime = _spec(sol, "runtime_h")
    out["runtime_h"] = (runtime, "паспорт решения") if runtime else (
        ec.a(A, "default_runtime_h"), "допущение: default_runtime_h")
    charge = _spec(sol, "charge_min") or ((_spec(sol, "charge_h") or 0) * 60) or None
    out["charge_min"] = (charge, "паспорт решения") if charge else (
        ec.a(A, "default_charge_min"), "допущение: default_charge_min")

    thr = _spec(sol, "throughput_per_h")
    thr_unit = _spec(sol, "throughput_unit")
    spec_meta = sol["specs"].get("throughput_per_h") or {}
    if throughput_override:
        out["throughput"] = (float(throughput_override), "задано пользователем")
    elif thr and thr_unit in profile.throughput_units:
        src = "паспорт (подтверждено)" if spec_meta.get("confirmed") else \
            "типовое значение для подтипа (требует подтверждения)"
        out["throughput"] = (float(thr), src)
    elif profile.raw.get("throughput_default"):
        td = profile.raw["throughput_default"]
        out["throughput"] = (float(td["value"]), td["source"])
    elif profile.mode == "area":
        out["throughput"] = (800.0, "допущение команды: типовая производительность "
                                    "робота-уборщика 600–1000 м²/ч, в паспорте нет")
    else:
        out["throughput"] = (None, "в единицах операции нет — считается из цикла рейса")
    return out


def _sim_config(profile, sol_params, route_m, peak_units, sched, A, fleet=1) -> tuple[SimConfig, float]:
    """Переводит операцию в задачи имитации. Возвращает конфиг и размер задачи в единицах
    операции (для уборки задача — участок 250 м², для остальных — 1 ед.)."""
    mode = profile.mode
    task_size = 1.0
    thr = sol_params["throughput"][0]
    if mode == "area":
        task_size = profile.raw.get("task_size_m2", {"value": 250})["value"]
        service = task_size / thr * 3600 if thr else 900
        cfg = SimConfig(robot_count=fleet, speed_ms=sol_params["speed_ms"][0], route_length_m=0,
                        handling_s=service / 2, runtime_h=sol_params["runtime_h"][0],
                        charge_min=sol_params["charge_min"][0],
                        charger_slots=max(1, math.ceil(fleet / ec.a(A, "robots_per_charger"))),
                        arrival_rate_per_h=peak_units / task_size,
                        duration_h=sched["shift_hours"], traffic_factor=1.0)
    elif mode == "stationary":
        service = 3600 / thr if thr else 10
        cfg = SimConfig(robot_count=fleet, speed_ms=1, route_length_m=0, handling_s=service / 2,
                        runtime_h=10_000, charge_min=0, charger_slots=1,
                        arrival_rate_per_h=peak_units, duration_h=sched["shift_hours"],
                        traffic_factor=1.0)
    else:
        cfg = SimConfig(robot_count=fleet, speed_ms=sol_params["speed_ms"][0],
                        route_length_m=route_m, handling_s=profile.raw.get("handling_s", 45),
                        runtime_h=sol_params["runtime_h"][0], charge_min=sol_params["charge_min"][0],
                        charger_slots=max(1, math.ceil(fleet / ec.a(A, "robots_per_charger"))),
                        arrival_rate_per_h=peak_units, duration_h=sched["shift_hours"],
                        traffic_factor=ec.a(A, "traffic_factor"),
                        extra_leg_s=ops.extra_delay(profile))
    return cfg, task_size


def _fleet_search(cfg: SimConfig, estimate: int, A: dict) -> tuple[int, Any]:
    """Минимальный парк по имитации. Поиск стартует рядом с аналитической оценкой,
    чтобы укладываться в требование ко времени расчёта (п. 4.3.2)."""
    def with_chargers(n: int) -> SimConfig:
        c = SimConfig(**{**cfg.__dict__, "robot_count": n})
        if cfg.charge_min > 0 and cfg.runtime_h < 10_000:
            c.charger_slots = max(1, math.ceil(n / ec.a(A, "robots_per_charger")))
        return c

    start = max(1, estimate - 2)
    res = simulate(with_chargers(start))
    target = cfg.arrival_rate_per_h * 0.98
    n = start
    if res.achieved_per_h >= target:
        while n > 1:
            probe = simulate(with_chargers(n - 1))
            if probe.achieved_per_h < target:
                break
            n, res = n - 1, probe
        return n, res
    while n < 150:
        n += 1
        res = simulate(with_chargers(n))
        if res.achieved_per_h >= target:
            return n, res
    return n, res


def recommendation(scenarios: list[dict], horizon: int) -> dict:
    robotic = [s for s in scenarios if s["code"] != "baseline"]
    viable = [s for s in robotic if s["payback_years"] is not None]
    best = min(viable, key=lambda s: (s["payback_years"], -s["annual_effect"])) if viable else None
    best_by_tco = min(robotic, key=lambda s: s["tco"]) if robotic else None
    pb = best["payback_years"] if best else None
    for limit, level, verdict, text in PAYBACK_BANDS:
        if pb is not None and limit is not None and pb <= limit:
            break
    if pb is not None and pb > horizon:
        level, verdict = "bad", "Не рекомендуется в текущих условиях"
        text = (f"Окупаемость {pb:.1f} года превышает горизонт расчёта {horizon} лет.")
    return {
        "level": level, "verdict": verdict, "interpretation": text,
        "best_scenario": best["code"] if best else None,
        "best_by_tco": best_by_tco["code"] if best_by_tco else None,
        "bands": [{"up_to_years": b[0], "level": b[1], "verdict": b[2]} for b in PAYBACK_BANDS],
    }


def evaluate(solution: dict, profile: ops.OperationProfile, params: dict,
             overrides: dict | None = None, options: dict | None = None,
             candidate: dict | None = None) -> dict:
    options = options or {}
    horizon_src = None
    extra: dict[str, ec.Assumption] = {}
    if profile.raw.get("horizon_param"):
        try:
            h = ops.num(params, profile.raw["horizon_param"])
            extra["horizon_years"] = ec.Assumption(h, "лет", "Датасет объекта: "
                                                   + profile.raw["horizon_param"])
            horizon_src = h
        except ops.MissingParam:
            pass
    payroll = ops.num(params, profile.raw["payroll_param"]) if profile.raw.get("payroll_param") else 1.302
    extra["payroll_factor"] = ec.Assumption(payroll, "коэффициент начислений на ФОТ",
                                            "Датасет объекта")
    A = assumptions_with(overrides, extra)
    steps: list[ec.Step] = []
    warnings: list[str] = []

    if not solution.get("price_rub"):
        raise ValueError("У решения нет цены — расчёт CAPEX невозможен. Укажите цену в каталоге.")

    daily, s = ops.daily_volume(profile, params)
    volume_k = float(options.get("volume_factor") or 1.0)
    if volume_k != 1.0:
        daily *= volume_k
        s.inputs["поправка what-if"] = volume_k
        s.result = round(daily, 1)
    steps.append(s)
    sched, s = ops.schedule(profile, params)
    steps.append(s)
    pf, s = ops.peak_factor(profile, params)
    steps.append(s)
    peak, s = ec.peak_hourly_demand(daily, sched["shifts"], sched["shift_hours"], pf)
    s.unit = profile.unit
    steps.append(s)

    route_m, s = ops.route_length(profile, params)
    if options.get("route_length_m"):
        route_m = float(options["route_length_m"])
        s.inputs["задано пользователем"] = route_m
        s.result = route_m
    if profile.mode == "mobile":
        steps.append(s)

    rp = robot_parameters(solution, profile, A, options.get("throughput_override"))
    sim_cfg, task_size = _sim_config(profile, rp, route_m, peak, sched, A)
    if rp["throughput"][0] is None:
        cycle = (2 * (route_m / rp["speed_ms"][0] * ec.a(A, "traffic_factor")
                      + ops.extra_delay(profile)) + 2 * sim_cfg.handling_s)
        rp["throughput"] = (round(3600 / cycle, 2), "расчёт из цикла рейса: путь, погрузка, "
                                                    "выгрузка, лифт (паспортного значения в "
                                                    "единицах операции нет)")
        steps.append(ec.Step("Производительность робота из цикла рейса",
                             "3600 / (2 × (маршрут / скорость × замедление + лифт) + 2 × погрузка)",
                             {"маршрут, м": round(route_m, 1), "скорость, м/с": rp["speed_ms"][0],
                              "замедление": ec.a(A, "traffic_factor"),
                              "лифт на плечо, с": ops.extra_delay(profile),
                              "погрузка/выгрузка, с": sim_cfg.handling_s},
                             rp["throughput"][0], profile.unit))
        sim_cfg, task_size = _sim_config(profile, rp, route_m, peak, sched, A)
    throughput = rp["throughput"][0]

    passport_count, robot_steps = ec.robots_needed(peak, throughput, A)
    robot_steps[0].inputs["источник производительности"] = rp["throughput"][1]
    robot_steps[0].unit = profile.unit
    steps += robot_steps

    fleet_mode = options.get("fleet_mode", "auto")
    sim_count, sim_res = _fleet_search(sim_cfg, passport_count, A)
    sim_per_robot_units = sim_res.theoretical_per_robot_h * task_size
    rec = reconcile(passport_count, sim_count, throughput, sim_per_robot_units)
    if not rec["agreement"]:
        reasons = []
        if profile.mode == "mobile" and sim_per_robot_units < throughput * 0.95:
            reasons.append(f"на маршрутах объекта ({route_m:.0f} м в одну сторону) робот делает "
                           f"{sim_per_robot_units:.1f} {profile.unit} против {throughput:g} по паспорту")
        if sim_res.charging_share > 0.1:
            reasons.append(f"{sim_res.charging_share * 100:.0f}% времени парка уходит на зарядку "
                           f"и ожидание станции")
        if not reasons:
            reasons.append("случайные пики очереди задач внутри смены не закрываются "
                           "паспортным парком с резервом")
        rec["message"] = (f"По паспорту нужно {passport_count} ед., имитация смены требует "
                          f"{sim_count} ед.: " + "; ".join(reasons) + ". В расчёт принята "
                          "имитационная оценка.")
    if fleet_mode == "manual" and options.get("manual_fleet"):
        count = int(options["manual_fleet"])
        basis = f"Парк задан пользователем: {count} ед."
    elif fleet_mode == "passport":
        count, basis = passport_count, "Парк по паспортной производительности"
    else:
        count, basis = rec["fleet"], rec["message"]
    if not rec["agreement"] and fleet_mode != "passport":
        warnings.append(rec["message"])
    final_cfg = SimConfig(**{**sim_cfg.__dict__, "robot_count": count})
    if final_cfg.charge_min > 0 and final_cfg.runtime_h < 10_000:
        final_cfg.charger_slots = max(1, math.ceil(count / ec.a(A, "robots_per_charger")))
    final_sim = simulate(final_cfg)
    steps.append(ec.Step("Парк роботов, принятый в расчёт",
                         "max(паспортный расчёт, минимальный парк по имитации)"
                         if fleet_mode == "auto" else basis,
                         {"по паспорту": passport_count, "по имитации": sim_count,
                          "режим": fleet_mode}, count, "шт."))

    # персонал и зарплаты
    staff, s = ops.headcount(profile, params, daily, sched)
    steps.append(s)
    sal, sal_src = ops.salary(profile, params)
    sal *= float(options.get("salary_factor") or 1.0)
    share_default, share_src = ops.automation_share(profile)
    share = float(options.get("automation_share") or share_default)
    released = staff * share
    steps.append(ec.Step("Высвобождаемая численность",
                         "персонал операции × доля автоматизации",
                         {"персонал, чел.": staff, "доля автоматизации": share,
                          "источник доли": share_src if share == share_default else "задано пользователем"},
                         round(released, 1), "чел."))

    price = solution["price_rub"] * float(options.get("price_factor") or 1.0)
    equipment_cost = count * price
    steps.append(ec.Step("Стоимость оборудования", "парк × цена единицы",
                         {"парк, шт.": count, "цена, руб.": price,
                          "источник цены": solution.get("price_note") or solution["data_source"]},
                         round(equipment_cost), "руб."))

    base = ec.baseline_scenario(staff, sal, payroll, A)
    buy = ec.build_scenario("purchase", "Покупка оборудования", equipment_cost, count, released,
                            sal, payroll, sched["hours_per_year"], A, headcount=staff)
    raas = ec.build_scenario("raas", "Роботы как услуга (RaaS)", equipment_cost, count, released,
                             sal, payroll, sched["hours_per_year"], A, raas=True, headcount=staff)
    scenarios = [base.as_dict(), buy.as_dict(), raas.as_dict()]

    budget = ops.optional(profile, params, "budget_param", 1_000_000)
    w = ec.budget_check(buy.capex_total, budget)
    if w:
        warnings.append(w)

    horizon = int(ec.a(A, "horizon_years"))
    sens = sensitivity(solution, profile, params, overrides, options, count, passport_count,
                       sim_count, staff, sal, payroll, share, sched, A, price)

    rec_block = recommendation(scenarios, horizon)
    risks = list(profile.raw.get("risks", []))
    if "допущ" in rp["throughput"][1] or "типовое" in rp["throughput"][1] or "цикла" in rp["throughput"][1]:
        risks.append(f"Производительность робота: {rp['throughput'][1]}. Запросить паспортное "
                     "значение у вендора для этой операции.")
    if solution.get("status") == "piloting":
        risks.append("Решение на стадии пилотирования — нужны подтверждённые кейсы и гарантия вендора.")
    if candidate and candidate.get("verdict") == "excluded":
        risks.insert(0, "Решение добавлено вручную, хотя не прошло автоматический подбор: "
                        + (candidate.get("decisive_reason") or ""))
        warnings.insert(0, "Решение не прошло автоматический подбор: "
                           + (candidate.get("decisive_reason") or ""))
    for row in sens:
        if row["scenario"] == "purchase" and row["crosses_band"]:
            risks.append(f"Результат чувствителен к параметру «{row['factor']}»: при изменении на "
                         f"{row['delta_percent']:+d}% окупаемость переходит в другой интервал.")
            break
    if w:
        risks.append("CAPEX превышает бюджет объекта.")

    return {
        "model_version": MODEL_VERSION,
        "profile": profile.public(),
        "solution": {k: solution.get(k) for k in (
            "external_id", "name", "vendor", "subtype", "price_rub", "price_note", "status",
            "data_source", "source_url")},
        "robot": {k: {"value": v[0], "source": v[1]} for k, v in rp.items()},
        "demand": {"daily_volume": round(daily, 1), "peak_per_hour": round(peak, 2),
                   "unit": profile.unit, "route_length_m": round(route_m, 1),
                   "shift_hours": sched["shift_hours"], "shifts": sched["shifts"]},
        "fleet": {"count": count, "passport": passport_count, "simulation": sim_count,
                  "basis": basis, "agreement": rec["agreement"], "mode": fleet_mode},
        "staff": {"headcount": staff, "released": round(released, 1),
                  "automation_share": share, "salary_month": sal, "salary_source": sal_src},
        "scenarios": scenarios,
        "steps": [st.as_dict() for st in steps],
        "assumptions": {k: v.as_dict() for k, v in A.items()},
        "sensitivity": sens,
        "recommendation": rec_block,
        "risks": risks,
        "warnings": warnings,
        "simulation": final_sim.as_dict() | {"task_size": task_size},
        "sim_config": final_cfg.__dict__ | {"task_size": task_size, "mode": profile.mode,
                                            "layout": profile.raw.get("layout", "generic"),
                                            "task_label": profile.raw.get("task_label", "задача"),
                                            "passport_fleet": passport_count,
                                            "sim_fleet": sim_count},
        "disclaimer": "Результат является предварительной оценкой и требует верификации "
                      "при обследовании объекта (п. 3.7.5 ТЗ).",
    }


def sensitivity(solution, profile, params, overrides, options, count, passport_count,
                sim_count, staff, sal, payroll, share, sched, A, price) -> list[dict]:
    """Чувствительность к трём параметрам (п. 3.5.6): стоимость оборудования, объём
    операций, стоимость труда. Пересчёт аналитический: при изменении объёма парк
    масштабируется пропорционально (паспорт и имитация линейны по потоку задач)."""
    rows = []
    base_codes = {}
    factors = [("Стоимость оборудования", "price"), ("Объём операций", "volume"),
               ("Стоимость труда", "salary")]

    def run(price_k=1.0, vol_k=1.0, sal_k=1.0):
        n = count if vol_k == 1.0 else max(1, math.ceil(count * vol_k))
        eq = n * price * price_k
        # объём влияет и на численность, если она считается от выработки
        st = staff if "derive" not in profile.raw["headcount"] else min(
            staff * vol_k, staff * 10)
        out = {}
        for code, raas in (("purchase", False), ("raas", True)):
            sc = ec.build_scenario(code, code, eq, n, st * share, sal * sal_k, payroll,
                                   sched["hours_per_year"], A, raas=raas, headcount=st)
            out[code] = sc
        return out

    base = run()
    for code in ("purchase", "raas"):
        base_codes[code] = base[code]

    def band(pb):
        if pb is None:
            return 2
        return 0 if pb <= 3 else 1 if pb <= 5 else 2

    for label, key in factors:
        for d in (-0.2, -0.1, 0.1, 0.2):
            kw = {"price": {"price_k": 1 + d}, "volume": {"vol_k": 1 + d},
                  "salary": {"sal_k": 1 + d}}[key]
            res = run(**kw)
            for code in ("purchase", "raas"):
                sc, b = res[code], base_codes[code]
                rows.append({
                    "factor": label, "key": key, "scenario": code,
                    "delta_percent": round(d * 100),
                    "annual_effect": sc.annual_effect,
                    "annual_effect_change": sc.annual_effect - b.annual_effect,
                    "payback_years": sc.payback_years, "tco": sc.tco,
                    "crosses_band": band(sc.payback_years) != band(b.payback_years),
                })
    return rows
