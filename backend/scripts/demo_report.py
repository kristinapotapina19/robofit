"""Демонстрационный расчёт на данных организатора и выгрузка примеров отчёта.

Запуск (из каталога backend):  python scripts/demo_report.py [каталог_вывода]
По умолчанию отчёты кладутся в ../docs/examples. Для каждой операции печатается
сводка: подбор, парк (паспорт/имитация), три сценария и рекомендация.
"""
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

from app.core import operations as ops                     # noqa: E402
from app.core.pipeline import evaluate, run_selection      # noqa: E402
from app.core.report import build_pdf, build_xlsx          # noqa: E402

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else BASE.parent / "docs" / "examples"
OUT.mkdir(parents=True, exist_ok=True)
SEED = BASE / "data" / "seed"
solutions = json.loads((SEED / "solutions.json").read_text(encoding="utf-8"))
presets = json.loads((SEED / "object_presets.json").read_text(encoding="utf-8"))
version = json.loads((SEED / "etl_report.json").read_text(encoding="utf-8"))["catalog_version"]

EXPORT = {"pallet_transport": "Ronavi H1500", "baggage_tug": None, "small_delivery": None}

for profile in ops.all_profiles():
    preset = presets[profile.object_type]
    params = {p["label"]: p["default"] for p in preset["parameters"]}
    sel = run_selection(solutions, profile, params)
    pool = sel["fit"] + sel["check_needed"]
    if not pool:
        print(f"{profile.code}: подходящих решений нет")
        continue
    want = EXPORT.get(profile.code)
    cand = next((c for c in pool if want and want in c["name"]), pool[0])
    sol = next(s for s in solutions if s["external_id"] == cand["solution_id"])
    r = evaluate(sol, profile, params, candidate=cand)
    buy = next(s for s in r["scenarios"] if s["code"] == "purchase")
    print(f"{profile.object_type:9} {profile.code:18} подходят {len(sel['fit']):2}, проверка "
          f"{len(sel['check_needed']):2} | {sol['name'][:34]:34} | парк {r['fleet']['count']:3} "
          f"(паспорт {r['fleet']['passport']}) | CAPEX {buy['capex_total'] / 1e6:6.1f} млн | "
          f"эффект {buy['annual_effect'] / 1e6:6.1f} млн/год | {r['recommendation']['verdict']}")
    if profile.code in EXPORT:
        payload = {**r, "catalog_version": version,
                   "object": {"title": preset["title"], "data_source": preset["data_source"],
                              "parameters": [{"label": p["label"], "unit": p["unit"],
                                              "value": params[p["label"]], "source": p["source_note"]}
                                             for p in preset["parameters"]]},
                   "operation": {"title": profile.title, "unit": profile.unit, "note": profile.note},
                   "candidates": sel["fit"] + sel["check_needed"] + sel["excluded"]}
        (OUT / f"отчёт_{profile.code}.pdf").write_bytes(build_pdf(payload))
        (OUT / f"отчёт_{profile.code}.xlsx").write_bytes(build_xlsx(payload))

print("Примеры отчётов:", OUT)
