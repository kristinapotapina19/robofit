"""
Подбор и ранжирование решений (п. 3.4 ТЗ).

Главное требование: для каждого решения показать причину соответствия,
ограничения и недостающие данные. Поэтому движок возвращает не список
подошедших продуктов, а список всех кандидатов с вердиктом:

    fit           — подходит, показывается в подборке
    check_needed  — не хватает данных для проверки, показывается с предупреждением
    excluded      — ключевое ограничение делает применение невозможным

Правила фильтрации вынесены в RULES: каждое правило — это функция, которая
возвращает вердикт и человеческую формулировку. Добавить правило = добавить
функцию, ядро менять не нужно.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Callable, Literal

Verdict = Literal["fit", "check_needed", "excluded"]


@dataclass
class RuleResult:
    verdict: Verdict
    reason: str

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class Candidate:
    solution: dict
    verdict: Verdict
    score: float
    reasons: list[str]
    warnings: list[str]
    missing_specs: list[str]
    decisive_reason: str | None = None
    breakdown: dict | None = None

    def as_dict(self) -> dict:
        return {
            "solution_id": self.solution["external_id"],
            "name": self.solution["name"],
            "vendor": self.solution["vendor"],
            "subtype": self.solution["subtype"],
            "price_rub": self.solution["price_rub"],
            "status": self.solution.get("status"),
            "trl": self.solution.get("trl"),
            "data_source": self.solution.get("data_source"),
            "verdict": self.verdict,
            "score": round(self.score, 3),
            "score_breakdown": self.breakdown,
            "reasons": self.reasons,
            "warnings": self.warnings,
            "missing_specs": self.missing_specs,
            "decisive_reason": self.decisive_reason,
        }


# --------------------------------------------------------------------------
# правила
# --------------------------------------------------------------------------
def rule_object_type(sol: dict, ctx: dict) -> RuleResult:
    scen = ", ".join(sol.get("scenarios") or [sol["scenario"]])
    if ctx["object_type"] == "custom":
        return RuleResult("fit", "Произвольный объект: применимость определяется операцией")
    if ctx["object_type"] in sol["object_types"]:
        return RuleResult("fit", f"Сценарий «{scen}» применим к объекту")
    return RuleResult("excluded",
                      f"Сценарий «{scen}» не относится к выбранному типу объекта")


def rule_status(sol: dict, ctx: dict) -> RuleResult:
    if sol["status"] == "operation":
        return RuleResult("fit", "Решение в эксплуатации, есть реализованные внедрения")
    if sol["status"] == "piloting":
        return RuleResult("check_needed", "Решение на стадии пилотирования — нужен запрос вендору")
    return RuleResult("excluded", "Решение на стадии НИОКР, к промышленному внедрению не готово")


def rule_payload(sol: dict, ctx: dict) -> RuleResult:
    required = ctx.get("cargo_mass_kg")
    spec = sol["specs"].get("payload_kg")
    if required is None:
        return RuleResult("fit", "Ограничение по массе груза не задано")
    if spec is None:
        return RuleResult("check_needed", "Нет данных о грузоподъёмности — требуется уточнение")
    if spec["value"] >= required:
        return RuleResult("fit",
                          f"Грузоподъёмность {spec['value']:.0f} кг покрывает груз {required:.0f} кг")
    return RuleResult("excluded",
                      f"Грузоподъёмность {spec['value']:.0f} кг меньше массы груза {required:.0f} кг")


def rule_aisle_width(sol: dict, ctx: dict) -> RuleResult:
    """Робот должен проходить в рабочих проходах объекта с запасом на манёвр."""
    aisle_mm = ctx.get("aisle_width_mm")
    spec = sol["specs"].get("width_mm")
    min_aisle = sol["specs"].get("min_aisle_mm")
    if aisle_mm is None:
        return RuleResult("fit", "Ограничение по ширине прохода не задано")
    if min_aisle:
        if min_aisle["value"] <= aisle_mm:
            return RuleResult("fit", f"Минимальный проход по паспорту {min_aisle['value']:.0f} мм "
                                     f"меньше прохода объекта {aisle_mm:.0f} мм")
        return RuleResult("excluded", f"Роботу нужен проход не менее {min_aisle['value']:.0f} мм, "
                                      f"на объекте {aisle_mm:.0f} мм")
    if spec is None:
        return RuleResult("check_needed", "Нет данных о габаритах — проходимость не проверена")
    clearance = ctx.get("clearance_mm", 400)
    if spec["value"] + clearance <= aisle_mm:
        return RuleResult("fit",
                          f"Ширина робота {spec['value']:.0f} мм проходит в проход "
                          f"{aisle_mm:.0f} мм с запасом {clearance} мм")
    return RuleResult("excluded",
                      f"Ширина робота {spec['value']:.0f} мм не оставляет запаса "
                      f"в проходе {aisle_mm:.0f} мм")


def rule_operation_profile(sol: dict, ctx: dict) -> RuleResult:
    """Решение должно закрывать выбранную операцию, а не просто относиться к объекту."""
    subtypes = ctx.get("profile_subtypes")
    if not subtypes:
        return RuleResult("fit", "Профиль операции не задан")
    if sol["subtype"] in subtypes:
        return RuleResult("fit", f"Подтип «{sol['subtype']}» закрывает выбранную операцию")
    return RuleResult("excluded",
                      f"Подтип «{sol['subtype']}» не выполняет выбранную операцию")


def rule_budget(sol: dict, ctx: dict) -> RuleResult:
    budget = ctx.get("capex_budget_rub")
    price = sol["price_rub"]
    if not budget or not price:
        return RuleResult("fit", "Бюджетное ограничение не проверялось")
    if price <= budget:
        return RuleResult("fit", "Стоимость единицы укладывается в бюджет проекта")
    return RuleResult("excluded",
                      "Стоимость одной единицы превышает весь заявленный бюджет CAPEX")


def rule_industry(sol: dict, ctx: dict) -> RuleResult:
    wanted = ctx.get("industry")
    if not wanted or wanted in (sol.get("industries") or [sol["industry"]]):
        return RuleResult("fit", "Отрасль решения совпадает с отраслью объекта")
    return RuleResult("check_needed",
                      f"Решение заявлено для отрасли «{sol['industry']}» — проверить переносимость")


def rule_price(sol: dict, ctx: dict) -> RuleResult:
    if sol.get("price_rub"):
        return RuleResult("fit", "Цена есть в каталоге")
    return RuleResult("check_needed", "Нет цены — CAPEX не рассчитать без запроса вендору")


RULES: list[Callable[[dict, dict], RuleResult]] = [
    rule_object_type, rule_operation_profile, rule_status, rule_payload,
    rule_aisle_width, rule_budget, rule_price, rule_industry,
]

RULES_DOC = [
    ("Тип объекта", "Сценарий решения должен относиться к выбранному объекту", "исключение"),
    ("Операция", "Подтип решения должен выполнять выбранную операцию", "исключение"),
    ("Статус", "НИОКР — исключение, пилот — требует проверки", "исключение / проверка"),
    ("Грузоподъёмность", "Не меньше массы грузовой единицы объекта", "исключение / нет данных"),
    ("Проходимость", "Ширина робота + 400 мм или паспортный минимальный проход ≤ ширины прохода", "исключение / нет данных"),
    ("Бюджет", "Цена одной единицы не больше всего бюджета CAPEX", "исключение"),
    ("Цена", "Без цены CAPEX не рассчитать", "проверка"),
    ("Отрасль", "Решение заявлено для другой отрасли — проверить переносимость", "проверка"),
]

WEIGHTS = {"has_cases": 0.2, "trl": 0.2, "capacity_price": 0.4, "specs_completeness": 0.2}
REQUIRED_SPECS = ("payload_kg", "speed_ms", "runtime_h", "throughput_per_h")


def score(sol: dict, ctx: dict, max_price: float) -> tuple[float, list[str], dict]:
    """Объяснимое ранжирование (п. 3.4.5): вклад каждого фактора виден."""
    notes = []
    has_cases = 1.0 if sol["cases"] else 0.0
    if has_cases:
        notes.append("есть описанные кейсы внедрения")
    trl = (sol["trl"] or 0) / 9
    completeness = sum(1 for k in REQUIRED_SPECS if k in sol["specs"]) / len(REQUIRED_SPECS)

    # удельная стоимость единицы производительности: чем дешевле закрыть один
    # паллет в час, тем выше ранг. Именно этот фактор определяет, сколько роботов
    # придётся купить, поэтому вес у него наибольший.
    thr = sol["specs"].get("throughput_per_h")
    capacity_price = 0.0
    if thr and thr["value"] and sol["price_rub"]:
        unit_cost = sol["price_rub"] / thr["value"]
        best = ctx.get("best_unit_cost") or unit_cost
        capacity_price = min(best / unit_cost, 1.0)
        notes.append(f"удельная стоимость {unit_cost:,.0f} руб. на единицу "
                     f"производительности".replace(",", " "))
    breakdown = {
        "Кейсы внедрения": round(WEIGHTS["has_cases"] * has_cases, 3),
        "Уровень готовности (УГТ)": round(WEIGHTS["trl"] * trl, 3),
        "Цена единицы производительности": round(WEIGHTS["capacity_price"] * capacity_price, 3),
        "Полнота ТТХ": round(WEIGHTS["specs_completeness"] * completeness, 3),
    }
    total = sum(breakdown.values())
    return total, notes, breakdown


def select(solutions: list[dict], ctx: dict) -> list[dict]:
    """
    ctx: object_type, cargo_mass_kg, capex_budget_rub, industry, scenarios (list | None)
    """
    prices = [s["price_rub"] for s in solutions if s["price_rub"]]
    max_price = max(prices) if prices else 0.0

    # лучшая удельная стоимость считается только среди решений той же операции,
    # иначе паллеты сравнивались бы с квадратными метрами
    pool = [s for s in solutions
            if not ctx.get("profile_subtypes") or s["subtype"] in ctx["profile_subtypes"]]
    unit_costs = [
        s["price_rub"] / s["specs"]["throughput_per_h"]["value"]
        for s in pool
        if s["price_rub"] and s["specs"].get("throughput_per_h")
        and s["specs"]["throughput_per_h"]["value"]
    ]
    ctx = {**ctx, "best_unit_cost": min(unit_costs) if unit_costs else None}
    out: list[Candidate] = []

    for sol in solutions:
        if ctx.get("scenarios") and not set(sol.get("scenarios") or [sol["scenario"]]) & set(ctx["scenarios"]):
            continue
        reasons, warnings = [], []
        verdict: Verdict = "fit"
        decisive = None
        for rule in RULES:
            res = rule(sol, ctx)
            if res.verdict == "excluded":
                verdict = "excluded"
                decisive = res.reason
                break
            if res.verdict == "check_needed":
                verdict = "check_needed" if verdict != "excluded" else verdict
                warnings.append(res.reason)
            else:
                reasons.append(res.reason)

        missing = [k for k in REQUIRED_SPECS if k not in sol["specs"]]
        value, notes, breakdown = score(sol, ctx, max_price)
        if verdict == "excluded":
            out.append(Candidate(sol, verdict, value, reasons, warnings, missing, decisive,
                                 breakdown))
        else:
            out.append(Candidate(sol, verdict, value, reasons + notes, warnings, missing,
                                 None, breakdown))

    order = {"fit": 0, "check_needed": 1, "excluded": 2}
    out.sort(key=lambda c: (order[c.verdict], -c.score))
    return [c.as_dict() for c in out]
