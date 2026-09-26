"""
Профили операций.

Зачем нужно: в датасете объекта потоки заданы в разных единицах (поддоны в сутки,
строки отбора в сутки, квадратные метры, рейсы), а производительность робота
в каталоге — в своих (паллет/ч, м²/ч, доставок/ч). Считать одно через другое нельзя.

Профиль операции связывает: откуда берётся объём работы, в каких единицах
измеряется производительность, какой персонал высвобождается и какие подтипы
решений операцию закрывают. Подбор и расчёт всегда идут внутри одного профиля.

Профили описаны декларативно в data/profiles.json: новая операция или новый тип
объекта добавляются записью в файл, ядро не меняется (п. 3.2.6, 4.2.6 ТЗ).
Каждое вычисленное значение возвращается вместе с шагом трассировки.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.core.economics import Step

PROFILES_PATH = Path(__file__).resolve().parents[2] / "data" / "profiles.json"


@dataclass
class OperationProfile:
    code: str
    title: str
    object_type: str
    unit: str
    mode: str
    note: str
    raw: dict = field(repr=False)

    @property
    def subtypes(self) -> list[str]:
        return self.raw.get("subtypes", [])

    @property
    def throughput_units(self) -> list[str]:
        return self.raw.get("throughput_units", [self.unit])

    def public(self) -> dict:
        r = self.raw
        return {
            "code": self.code, "title": self.title, "object_type": self.object_type,
            "unit": self.unit, "mode": self.mode, "note": self.note,
            "task_label": r.get("task_label", "операция"),
            "subtypes": self.subtypes, "layout": r.get("layout", "generic"),
            "risks": r.get("risks", []),
            "automation_share": r.get("automation_share"),
            "used_params": sorted(used_params(self)),
        }


@lru_cache(maxsize=1)
def _load() -> tuple[OperationProfile, ...]:
    data = json.loads(PROFILES_PATH.read_text(encoding="utf-8"))
    return tuple(OperationProfile(
        code=p["code"], title=p["title"], object_type=p["object_type"], unit=p["unit"],
        mode=p.get("mode", "mobile"), note=p.get("note", ""), raw=p)
        for p in data["profiles"])


def reload_profiles() -> None:
    _load.cache_clear()


def all_profiles() -> list[OperationProfile]:
    return list(_load())


def profiles_for(object_type: str) -> list[OperationProfile]:
    return [p for p in _load() if p.object_type == object_type]


def get_profile(code: str) -> OperationProfile:
    for p in _load():
        if p.code == code:
            return p
    raise KeyError(f"Профиль операции {code} не найден")


def used_params(profile: OperationProfile) -> set[str]:
    """Какие параметры объекта участвуют в расчёте — их форма помечает как обязательные."""
    r = profile.raw
    out: set[str] = set()
    for term in r.get("volume", []):
        out |= set(term.get("mul", [])) | set(term.get("div", []))
    hours = r.get("hours", {})
    for k in ("shifts_param", "shift_hours_param", "working_days_param"):
        if hours.get(k):
            out.add(hours[k])
    peak = r.get("peak", {})
    if peak.get("param"):
        out.add(peak["param"])
    if peak.get("ratio"):
        out |= {peak["ratio"]["peak_param"], peak["ratio"]["daily_param"]}
    hc = r.get("headcount", {})
    if hc.get("param"):
        out.add(hc["param"])
    for k in ("rate_param", "absence_param", "cap_param"):
        if hc.get("derive", {}).get(k):
            out.add(hc["derive"][k])
    for k in ("salary_param", "payroll_param", "budget_param", "horizon_param",
              "cargo_mass_param", "aisle_param"):
        if r.get(k):
            out.add(r[k])
    route = r.get("route", {})
    for k in ("param", "area_param"):
        if route.get(k):
            out.add(route[k])
    return out


# --------------------------------------------------------------------------
# вычисления по профилю
# --------------------------------------------------------------------------
class MissingParam(ValueError):
    pass


def num(params: dict[str, Any], label: str) -> float:
    value = params.get(label)
    if value is None or value == "":
        raise MissingParam(f"Не заполнен параметр «{label}»")
    try:
        return float(str(value).replace(",", ".").replace(" ", ""))
    except ValueError as exc:
        raise MissingParam(f"Параметр «{label}» должен быть числом, получено «{value}»") from exc


def daily_volume(profile: OperationProfile, params: dict) -> tuple[float, Step]:
    total, inputs, parts = 0.0, {}, []
    for term in profile.raw["volume"]:
        v = term.get("k", 1.0)
        text = []
        for label in term.get("mul", []):
            x = num(params, label)
            inputs[label] = x
            v *= x
            text.append(label)
        for label in term.get("div", []):
            x = num(params, label)
            inputs[label] = x
            v = v / x if x else 0.0
            text.append("/ " + label)
        if term.get("k", 1.0) != 1.0:
            inputs[f"коэффициент ({term.get('source') or 'допущение'})"] = term["k"]
        total += v
        parts.append(" × ".join(text))
    step = Step("Суточный объём операции", " + ".join(f"({p})" for p in parts),
                inputs, round(total, 1), profile.unit.replace("/ч", "/сут"))
    return total, step


def schedule(profile: OperationProfile, params: dict) -> tuple[dict, Step]:
    h = profile.raw["hours"]
    shifts = num(params, h["shifts_param"]) if h.get("shifts_param") else h["shifts"]
    shift_hours = num(params, h["shift_hours_param"]) if h.get("shift_hours_param") else h["shift_hours"]
    days = num(params, h["working_days_param"]) if h.get("working_days_param") else h["working_days"]
    out = {"shifts": shifts, "shift_hours": shift_hours, "working_days": days,
           "hours_per_day": shifts * shift_hours, "hours_per_year": shifts * shift_hours * days}
    src = h.get("source") or "Датасет объекта"
    step = Step("Режим работы", "смен × часов в смене × рабочих дней",
                {"смен": shifts, "часов в смене": shift_hours, "дней в году": days,
                 "источник": src},
                out["hours_per_year"], "ч/год")
    return out, step


def peak_factor(profile: OperationProfile, params: dict) -> tuple[float, Step]:
    p = profile.raw["peak"]
    if p.get("param"):
        v = num(params, p["param"])
        return v, Step("Пиковый коэффициент", "из параметров объекта",
                       {p["param"]: v}, v, "")
    if p.get("ratio"):
        r = p["ratio"]
        peak_h = num(params, r["peak_param"])
        avg_h = num(params, r["daily_param"]) / r["hours"]
        v = peak_h / avg_h if avg_h else 1.0
        return v, Step("Пиковый коэффициент", "пиковое значение в час / среднее в час",
                       {r["peak_param"]: peak_h, "среднее в час": round(avg_h, 2)},
                       round(v, 2), "")
    return p["value"], Step("Пиковый коэффициент", "допущение", {"источник": p["source"]},
                            p["value"], "")


def headcount(profile: OperationProfile, params: dict, daily: float,
              sched: dict) -> tuple[float, Step]:
    hc = profile.raw["headcount"]
    if hc.get("param"):
        v = num(params, hc["param"])
        return v, Step("Персонал целевой операции", "из параметров объекта",
                       {hc["param"]: v}, v, "чел.")
    d = hc["derive"]
    rate = num(params, d["rate_param"]) if d.get("rate_param") else d["rate"]
    if d.get("absence_param"):
        absence = num(params, d["absence_param"]) / 100
    else:
        absence = d.get("absence", 0.25)
    # человеко-часы в сутки -> ставки -> списочная численность с учётом потерь времени.
    # Ставки считаются на суточный режим объекта, поэтому делим на длину смены.
    person_hours = daily / rate if rate else 0.0
    staff = person_hours / sched["shift_hours"] * (1 + absence)
    staff = math.ceil(staff * 10) / 10
    inputs = {"объём в сутки": round(daily, 1), "выработка, ед./ч на чел.": rate,
              "длительность смены, ч": sched["shift_hours"], "потери времени": absence,
              "источник выработки": d.get("rate_source") or d.get("rate_param")}
    formula = "объём в сутки / выработка / длительность смены × (1 + потери времени)"
    if d.get("cap_param"):
        cap = num(params, d["cap_param"])
        inputs[f"не больше: {d['cap_param']}"] = cap
        if staff > cap:
            staff = cap
        formula += ", не больше численности из датасета"
    return staff, Step("Персонал целевой операции", formula, inputs, round(staff, 1), "чел.")


def salary(profile: OperationProfile, params: dict) -> tuple[float, str]:
    r = profile.raw
    if r.get("salary_param"):
        return num(params, r["salary_param"]), f"Датасет: {r['salary_param']}"
    return r["salary"]["value"], r["salary"]["source"]


def optional(profile: OperationProfile, params: dict, key: str, scale: float = 1.0) -> float | None:
    label = profile.raw.get(key)
    if not label:
        return None
    try:
        return num(params, label) * scale
    except MissingParam:
        return None


def cargo_mass(profile: OperationProfile, params: dict) -> float | None:
    if profile.raw.get("cargo_mass_param"):
        return optional(profile, params, "cargo_mass_param")
    cm = profile.raw.get("cargo_mass")
    return cm["value"] if cm else None


def route_length(profile: OperationProfile, params: dict) -> tuple[float, Step]:
    r = profile.raw.get("route", {"default": 100})
    if r.get("param"):
        v = num(params, r["param"])
        return v, Step("Длина маршрута в одну сторону", "из параметров объекта",
                       {r["param"]: v, "примечание": r.get("source", "")}, v, "м")
    if r.get("area_param"):
        area = num(params, r["area_param"])
        v = r["k"] * math.sqrt(area)
        return v, Step("Длина маршрута в одну сторону", "k × √площади зоны",
                       {r["area_param"]: area, "k": r["k"], "источник": r["source"]},
                       round(v, 1), "м")
    return r["default"], Step("Длина маршрута в одну сторону", "допущение",
                              {"источник": r.get("source", "")}, r["default"], "м")


def extra_delay(profile: OperationProfile) -> float:
    e = profile.raw.get("extra_delay_s")
    return e["value"] if e else 0.0


def automation_share(profile: OperationProfile) -> tuple[float, str]:
    a = profile.raw.get("automation_share") or {"value": 0.7, "source": "Допущение команды"}
    return a["value"], a["source"]
