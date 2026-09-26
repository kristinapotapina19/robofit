"""
Экономическая модель (п. 3.5 ТЗ).

Принцип: ни одного «магического» числа. Любой коэффициент — это Assumption
со значением, единицей измерения и текстом источника. Результат расчёта
возвращает не только цифры, но и трассировку: какая формула, какие входы,
какой источник. Именно эта трассировка показывается пользователю в интерфейсе
и попадает в выгружаемый отчёт (п. 3.5.8).

Модуль не зависит от FastAPI и БД — его можно запускать и тестировать отдельно.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any

MONTHS = 12


@dataclass
class Assumption:
    """Одно допущение расчёта."""
    value: float
    unit: str
    source: str

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class Step:
    """Шаг расчёта для объяснения пользователю."""
    name: str
    formula: str
    inputs: dict[str, Any]
    result: float
    unit: str

    def as_dict(self) -> dict:
        return asdict(self)


# --------------------------------------------------------------------------
# Допущения по умолчанию.
# Значения, взятые из демо-датасета организатора, помечены источником «датасет».
# Значения, выбранные командой, помечены как допущение — их обязательно
# показывать пользователю и давать менять (п. 3.5.3).
# --------------------------------------------------------------------------
DEFAULT_ASSUMPTIONS: dict[str, Assumption] = {
    # инфраструктура и внедрение считаются долями от стоимости оборудования
    "infrastructure_share": Assumption(
        0.15, "доля от стоимости оборудования",
        "Допущение команды: зарядные станции, сеть, разметка. Диапазон 10-20% по "
        "публичным кейсам внедрения AMR"),
    "software_share": Assumption(
        0.10, "доля от стоимости оборудования",
        "Допущение команды: лицензии системы управления парком роботов"),
    "integration_share": Assumption(
        0.12, "доля от стоимости оборудования",
        "Допущение команды: интеграция с WMS/ERP, разработка коннекторов"),
    "commissioning_share": Assumption(
        0.05, "доля от стоимости оборудования",
        "Допущение команды: пусконаладка и приёмочные испытания"),
    "training_share": Assumption(
        0.02, "доля от стоимости оборудования",
        "Допущение команды: обучение персонала"),
    "contingency_share": Assumption(
        0.10, "доля от суммы прочих статей CAPEX",
        "Допущение команды: резерв на непредвиденные работы"),

    # эксплуатация
    "service_share": Assumption(
        0.08, "доля от стоимости оборудования в год",
        "Допущение команды: сервисный контракт, типовая ставка 5-10% в год"),
    "spares_share": Assumption(
        0.03, "доля от стоимости оборудования в год",
        "Допущение команды: расходные материалы и ремонт"),
    "license_share": Assumption(
        0.15, "доля от стоимости ПО в год",
        "Допущение команды: подписка на ПО управления парком"),
    "power_price": Assumption(
        7.0, "руб./кВт·ч",
        "Допущение команды: средний тариф для промышленных потребителей"),
    "robot_power_kw": Assumption(
        0.5, "кВт среднего потребления на робота",
        "Допущение команды: усреднение по классу AMR, уточняется по ТТХ решения"),

    # эксплуатационный персонал вместо выбывающих операций
    "operators_per_10_robots": Assumption(
        1.0, "чел. на 10 роботов",
        "Допущение команды: оператор-диспетчер парка"),
    "operator_salary_month": Assumption(
        130_000, "руб./мес. gross",
        "Допущение команды: выше з/п оператора погрузчика из датасета"),

    "payroll_factor": Assumption(
        1.302, "коэффициент начислений на ФОТ",
        "Датасет организатора: страховые взносы 30,2%"),

    # производительность
    "utilization": Assumption(
        0.85, "коэффициент загрузки",
        "Допущение команды: доля полезного времени робота в смене"),
    "availability": Assumption(
        0.95, "коэффициент технической готовности",
        "Допущение команды: простои на зарядку и обслуживание"),
    "reserve": Assumption(
        0.10, "резерв парка",
        "Допущение команды: подменный фонд на пики и обслуживание"),

    "traffic_factor": Assumption(
        1.15, "коэффициент замедления на маршруте",
        "Допущение команды: расхождения, перекрёстки и пропуск людей добавляют 15% ко времени пути"),
    "default_speed_ms": Assumption(
        1.2, "м/с",
        "Допущение команды: скорость, если в паспорте решения её нет (нижняя граница класса AMR)"),
    "default_runtime_h": Assumption(
        8, "ч",
        "Допущение команды: автономность, если в паспорте её нет"),
    "default_charge_min": Assumption(
        60, "мин",
        "Допущение команды: время зарядки, если в паспорте его нет"),
    "robots_per_charger": Assumption(
        4, "роботов на одну зарядную станцию",
        "Допущение команды: типовое соотношение для AMR с оппортунистической зарядкой"),

    # финансы
    "depreciation_years": Assumption(
        7, "лет",
        "Допущение команды: линейная амортизация, срок службы робототехники"),
    "horizon_years": Assumption(
        5, "лет",
        "Датасет организатора: горизонт расчёта окупаемости, базовое значение 5 лет"),
    "component_replacement_year": Assumption(
        4, "год замены основных компонентов",
        "Допущение команды: замена батарей на 4-й год, 20% от стоимости оборудования"),
    "component_replacement_share": Assumption(
        0.20, "доля от стоимости оборудования",
        "Допущение команды: стоимость замены батарей и износных узлов"),

    # RaaS
    "raas_monthly_share": Assumption(
        0.035, "доля от стоимости оборудования в месяц",
        "Допущение команды: ставка подписки RaaS включает аренду, сервис, ремонт и ПО; "
        "3,5% в месяц ≈ окупаемость оборудования для вендора за 2,4 года, уточняется у вендора"),
    "raas_onboarding_share": Assumption(
        0.10, "доля от стоимости оборудования",
        "Допущение команды: разовый платёж за подключение и интеграцию"),
}


def a(assumptions: dict[str, Assumption], key: str) -> float:
    return assumptions[key].value


# --------------------------------------------------------------------------
# потребность в роботах
# --------------------------------------------------------------------------
def robots_needed(
    peak_operations_per_hour: float,
    robot_throughput_per_hour: float,
    assumptions: dict[str, Assumption],
) -> tuple[int, list[Step]]:
    """п. 3.5.2: пиковая потребность / эффективная производительность робота."""
    util = a(assumptions, "utilization")
    avail = a(assumptions, "availability")
    reserve = a(assumptions, "reserve")

    effective = robot_throughput_per_hour * util * avail
    raw = peak_operations_per_hour / effective if effective else 0.0
    count = int(-(-raw * (1 + reserve) // 1))  # округление вверх

    steps = [
        Step("Эффективная производительность робота",
             "паспортная × коэффициент загрузки × коэффициент готовности",
             {"паспортная, оп./ч": robot_throughput_per_hour,
              "загрузка": util, "готовность": avail},
             round(effective, 2), "оп./ч"),
        Step("Расчётное количество роботов",
             "пиковая потребность / эффективная производительность × (1 + резерв)",
             {"пиковая потребность, оп./ч": peak_operations_per_hour,
              "эффективная, оп./ч": round(effective, 2), "резерв": reserve},
             count, "шт."),
    ]
    return count, steps


def peak_hourly_demand(
    daily_operations: float,
    shifts_per_day: float,
    shift_hours: float,
    peak_factor: float,
) -> tuple[float, Step]:
    working_hours = shifts_per_day * shift_hours
    average = daily_operations / working_hours if working_hours else 0.0
    peak = average * peak_factor
    step = Step("Пиковая часовая нагрузка",
                "операций в сутки / рабочих часов × пиковый коэффициент",
                {"операций в сутки": daily_operations,
                 "рабочих часов в сутки": working_hours,
                 "пиковый коэффициент": peak_factor},
                round(peak, 1), "оп./ч")
    return peak, step


# --------------------------------------------------------------------------
# CAPEX / OPEX
# --------------------------------------------------------------------------
def capex(equipment_cost: float, assumptions: dict[str, Assumption]) -> tuple[dict, list[Step]]:
    infra = equipment_cost * a(assumptions, "infrastructure_share")
    software = equipment_cost * a(assumptions, "software_share")
    integration = equipment_cost * a(assumptions, "integration_share")
    commissioning = equipment_cost * a(assumptions, "commissioning_share")
    training = equipment_cost * a(assumptions, "training_share")
    subtotal = equipment_cost + infra + software + integration + commissioning + training
    contingency = subtotal * a(assumptions, "contingency_share")
    total = subtotal + contingency

    breakdown = {
        "Оборудование": round(equipment_cost),
        "Инфраструктура": round(infra),
        "ПО": round(software),
        "Интеграция": round(integration),
        "Пусконаладка": round(commissioning),
        "Обучение": round(training),
        "Резерв": round(contingency),
        "Итого": round(total),
    }
    step = Step("CAPEX",
                "оборудование + инфраструктура + ПО + интеграция + пусконаладка + обучение + резерв",
                breakdown, round(total), "руб.")
    return breakdown, [step]


def opex(
    equipment_cost: float,
    software_cost: float,
    robot_count: int,
    working_hours_year: float,
    assumptions: dict[str, Assumption],
) -> tuple[dict, list[Step]]:
    service = equipment_cost * a(assumptions, "service_share")
    spares = equipment_cost * a(assumptions, "spares_share")
    licenses = software_cost * a(assumptions, "license_share")
    power = (robot_count * a(assumptions, "robot_power_kw")
             * working_hours_year * a(assumptions, "power_price"))
    operators = (robot_count / 10 * a(assumptions, "operators_per_10_robots"))
    operators_cost = (operators * a(assumptions, "operator_salary_month") * MONTHS
                      * a(assumptions, "payroll_factor"))
    total = service + spares + licenses + power + operators_cost

    breakdown = {
        "Сервисный контракт": round(service),
        "Расходники и ремонт": round(spares),
        "Лицензии ПО": round(licenses),
        "Электроэнергия": round(power),
        "Персонал эксплуатации": round(operators_cost),
        "Итого": round(total),
    }
    step = Step("Годовой OPEX",
                "сервис + расходники + лицензии + электроэнергия + персонал эксплуатации",
                breakdown | {"операторов, чел.": round(operators, 1)},
                round(total), "руб./год")
    return breakdown, [step]


# --------------------------------------------------------------------------
# сценарии
# --------------------------------------------------------------------------
@dataclass
class ScenarioResult:
    code: str
    title: str
    robot_count: int
    capex_total: float
    capex_breakdown: dict
    opex_year: float
    opex_breakdown: dict
    opex_change: float
    labor_saving_year: float
    annual_effect: float
    annual_effect_after_depreciation: float
    payback_years: float | None
    roi_percent: float | None
    tco: float
    steps: list[Step] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        d = asdict(self)
        d["steps"] = [s.as_dict() for s in self.steps]
        return d


def labor_cost(headcount: float, salary_month: float, payroll_factor: float) -> float:
    return headcount * salary_month * MONTHS * payroll_factor


def labor_saving(
    released_headcount: float,
    salary_month: float,
    payroll_factor: float,
) -> tuple[float, Step]:
    value = labor_cost(released_headcount, salary_month, payroll_factor)
    step = Step("Экономия фонда оплаты труда",
                "высвобождаемая численность × з/п × 12 × коэффициент начислений",
                {"высвобождается, чел.": round(released_headcount, 1),
                 "з/п, руб./мес.": salary_month,
                 "коэффициент начислений": payroll_factor},
                round(value), "руб./год")
    return value, step


def tco(capex_total: float, opex_year: float, equipment_cost: float,
        assumptions: dict[str, Assumption]) -> tuple[float, Step]:
    horizon = int(a(assumptions, "horizon_years"))
    replacement = equipment_cost * a(assumptions, "component_replacement_share")
    replacement_year = int(a(assumptions, "component_replacement_year"))
    replacement = replacement if horizon >= replacement_year else 0
    value = capex_total + opex_year * horizon + replacement
    step = Step("TCO",
                "CAPEX + OPEX × горизонт + замена основных компонентов",
                {"CAPEX": round(capex_total), "OPEX в год": round(opex_year),
                 "горизонт, лет": horizon, "замена компонентов": round(replacement)},
                round(value), "руб.")
    return value, step


def build_scenario(
    code: str,
    title: str,
    equipment_cost: float,
    robot_count: int,
    released_headcount: float,
    salary_month: float,
    payroll_factor: float,
    working_hours_year: float,
    assumptions: dict[str, Assumption],
    raas: bool = False,
    headcount: float | None = None,
) -> ScenarioResult:
    """Сценарий роботизации.

    OPEX сценария включает оставшийся персонал операции, чтобы OPEX и TCO всех
    сценариев были сопоставимы с базовым (п. 3.5.2: «годовой OPEX и изменение
    OPEX относительно базового сценария»). Годовой эффект = OPEX базового −
    OPEX сценария = экономия ФОТ − дополнительный OPEX роботов.
    """
    headcount = released_headcount if headcount is None else headcount
    remaining_cost = labor_cost(max(headcount - released_headcount, 0), salary_month,
                                payroll_factor)
    baseline_cost = labor_cost(headcount, salary_month, payroll_factor)
    steps: list[Step] = []
    saving, saving_step = labor_saving(released_headcount, salary_month, payroll_factor)
    steps.append(saving_step)

    if raas:
        onboarding = equipment_cost * a(assumptions, "raas_onboarding_share")
        capex_breakdown = {"Подключение и интеграция": round(onboarding),
                           "Итого": round(onboarding)}
        capex_total = onboarding
        rent_year = equipment_cost * a(assumptions, "raas_monthly_share") * MONTHS
        base_opex, _ = opex(0, 0, robot_count, working_hours_year, assumptions)
        robot_opex = rent_year + base_opex["Электроэнергия"] + base_opex["Персонал эксплуатации"]
        opex_breakdown = {"Подписка (аренда + сервис + ПО)": round(rent_year),
                          "Электроэнергия": base_opex["Электроэнергия"],
                          "Персонал эксплуатации": base_opex["Персонал эксплуатации"]}
        steps.append(Step("Подписка RaaS",
                          "стоимость оборудования × месячная ставка × 12",
                          {"оборудование": round(equipment_cost),
                           "ставка в месяц": a(assumptions, "raas_monthly_share")},
                          round(rent_year), "руб./год"))
        steps.append(Step("CAPEX (RaaS)", "стоимость оборудования × доля разового платежа",
                          {"оборудование": round(equipment_cost),
                           "доля": a(assumptions, "raas_onboarding_share")},
                          round(onboarding), "руб."))
        depreciation = 0.0
    else:
        capex_breakdown, capex_steps = capex(equipment_cost, assumptions)
        capex_total = capex_breakdown["Итого"]
        opex_breakdown, opex_steps = opex(
            equipment_cost, capex_breakdown["ПО"], robot_count, working_hours_year, assumptions)
        robot_opex = opex_breakdown.pop("Итого")
        steps += capex_steps + opex_steps
        depreciation = capex_total / a(assumptions, "depreciation_years")

    opex_breakdown["Оставшийся персонал операции"] = round(remaining_cost)
    opex_year = robot_opex + remaining_cost
    opex_breakdown["Итого"] = round(opex_year)

    annual_effect = baseline_cost - opex_year          # = saving - robot_opex
    payback = capex_total / annual_effect if annual_effect > 0 else None
    horizon = int(a(assumptions, "horizon_years"))
    roi = (annual_effect * horizon / capex_total * 100) if capex_total else None
    tco_value, tco_step = tco(capex_total, opex_year, 0 if raas else equipment_cost, assumptions)

    steps.append(Step("Годовой OPEX сценария",
                      "OPEX роботов + ФОТ оставшегося персонала операции",
                      {"OPEX роботов": round(robot_opex), "оставшийся ФОТ": round(remaining_cost)},
                      round(opex_year), "руб./год"))
    steps.append(Step("Чистый годовой эффект",
                      "OPEX базового сценария − OPEX сценария "
                      "(= экономия ФОТ − дополнительный OPEX роботов)",
                      {"OPEX базового": round(baseline_cost), "OPEX сценария": round(opex_year)},
                      round(annual_effect), "руб./год"))
    if not raas:
        steps.append(Step("Годовой эффект с учётом амортизации",
                          "годовой эффект − CAPEX / срок амортизации (линейный метод)",
                          {"эффект": round(annual_effect), "CAPEX": round(capex_total),
                           "срок, лет": a(assumptions, "depreciation_years")},
                          round(annual_effect - depreciation), "руб./год"))
    steps.append(Step("Срок окупаемости", "CAPEX / годовой эффект",
                      {"CAPEX": round(capex_total), "эффект": round(annual_effect)},
                      round(payback, 2) if payback else 0, "лет"))
    steps.append(Step("ROI", "накопленный эффект за горизонт / CAPEX × 100%",
                      {"эффект за горизонт": round(annual_effect * horizon),
                       "CAPEX": round(capex_total)},
                      round(roi, 1) if roi else 0, "%"))
    steps.append(tco_step)

    notes: list[str] = []
    if raas:
        notes.append(
            "Модель RaaS: ежемесячная подписка включает аренду, сервис, ремонт и ПО; "
            "разовый платёж за подключение — единственный CAPEX; срок контракта равен "
            "горизонту расчёта, выкуп не предусмотрен. ROI по формуле ТЗ считается к CAPEX "
            "и при минимальных капитальных затратах получается неинформативно высоким, "
            "поэтому покупку и подписку сравнивают по годовому эффекту и TCO.")
    if annual_effect <= 0:
        notes.append("Годовой эффект отрицательный: затраты на роботов превышают экономию, "
                     "сценарий не окупается.")

    return ScenarioResult(
        code=code, title=title, robot_count=robot_count,
        capex_total=round(capex_total), capex_breakdown=capex_breakdown,
        opex_year=round(opex_year), opex_breakdown=opex_breakdown,
        opex_change=round(opex_year - baseline_cost),
        labor_saving_year=round(saving), annual_effect=round(annual_effect),
        annual_effect_after_depreciation=round(annual_effect - depreciation),
        payback_years=round(payback, 2) if payback else None,
        roi_percent=round(roi, 1) if roi is not None else None,
        tco=round(tco_value), steps=steps, notes=notes,
    )


def baseline_scenario(
    headcount: float, salary_month: float, payroll_factor: float,
    assumptions: dict[str, Assumption],
) -> ScenarioResult:
    """Текущий процесс без роботизации — база для сравнения (п. 3.5.5)."""
    cost = labor_cost(headcount, salary_month, payroll_factor)
    horizon = int(a(assumptions, "horizon_years"))
    step = Step("Годовые затраты на персонал целевой операции",
                "численность × з/п × 12 × коэффициент начислений",
                {"численность, чел.": headcount, "з/п, руб./мес.": salary_month,
                 "коэффициент начислений": payroll_factor},
                round(cost), "руб./год")
    return ScenarioResult(
        code="baseline", title="Без роботизации", robot_count=0,
        capex_total=0, capex_breakdown={"Итого": 0},
        opex_year=round(cost), opex_breakdown={"Персонал целевой операции": round(cost),
                                               "Итого": round(cost)},
        opex_change=0, labor_saving_year=0, annual_effect=0,
        annual_effect_after_depreciation=0, payback_years=None, roi_percent=None,
        tco=round(cost * horizon), steps=[step],
    )


def sensitivity(
    base_value: float,
    factor_name: str,
    recompute,
    deltas: tuple[float, ...] = (-0.2, -0.1, 0.1, 0.2),
) -> list[dict]:
    """Чувствительность результата к параметру (п. 3.5.6)."""
    out = []
    for d in deltas:
        value = recompute(base_value * (1 + d))
        out.append({"factor": factor_name, "delta_percent": round(d * 100),
                    "value": round(value, 2) if value is not None else None})
    return out


def budget_check(capex_total: float, budget: float | None) -> str | None:
    """Сверка расчётного CAPEX с бюджетом объекта из датасета."""
    if not budget:
        return None
    if capex_total <= budget:
        return None
    return (f"Расчётный CAPEX {capex_total/1e6:,.1f} млн руб. превышает заявленный бюджет "
            f"{budget/1e6:,.1f} млн руб. Варианты: поэтапное внедрение, "
            f"сокращение доли автоматизации операции или переход на RaaS.").replace(",", " ")
