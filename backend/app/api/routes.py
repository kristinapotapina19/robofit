"""REST API платформы. Полная спецификация — /docs (Swagger) и /openapi.json."""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from functools import lru_cache
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, UploadFile
from fastapi.responses import Response

from app import auth
from app.config import settings
from app.core import economics as ec
from app.core import operations as ops
from app.core import params as P
from app.core.pipeline import MODEL_VERSION, PAYBACK_BANDS, evaluate, run_selection
from app.core.report import build_pdf, build_xlsx
from app.core.selection import RULES_DOC, WEIGHTS
from app.core.simulation import SimConfig, simulate
from app.repo import get_repo, summary_of
from app.schemas import (AssumptionIn, CompareIn, Credentials, EvaluateIn, ParamsIn,
                         ProjectIn, ProjectPatch, ScenarioIn, SelectionIn, SolutionIn)

router = APIRouter()

OBJECT_TYPES = [
    {"code": "warehouse", "title": "Склад", "industry": "Торговля",
     "description": "Распределительный центр: приёмка, хранение, отбор и отгрузка"},
    {"code": "airport", "title": "Аэропорт", "industry": "Логистика",
     "description": "Терминал и перрон: багаж, внутренняя логистика, уборка"},
    {"code": "clinic", "title": "Медучреждение", "industry": "Социальная сфера",
     "description": "Многопрофильная больница: питание, бельё, медикаменты, пробы"},
    {"code": "custom", "title": "Другой объект", "industry": "Другое",
     "description": "Произвольный объект: параметры задаёт пользователь"},
]


# ---------------------------------------------------------------- доступ
def current_user(authorization: str | None = Header(None)) -> dict | None:
    token = authorization.split(" ", 1)[1] if authorization and " " in authorization else None
    return auth.read_token(token)


def require_user(user: dict | None = Depends(current_user)) -> dict:
    if not user:
        raise HTTPException(401, "Войдите, чтобы сохранять проекты. Гостю доступны каталог и "
                                 "демонстрационные расчёты.")
    return user


def require_admin(user: dict = Depends(require_user)) -> dict:
    if user["role"] != "admin":
        raise HTTPException(403, "Действие доступно только администратору")
    return user


# ---------------------------------------------------------------- справочные данные
@lru_cache(maxsize=1)
def presets() -> dict:
    return json.loads((settings.seed_dir / "object_presets.json").read_text(encoding="utf-8"))


def preset_or_404(code: str) -> dict:
    if code not in presets():
        raise HTTPException(404, f"Тип объекта «{code}» не найден")
    return presets()[code]


def profile_or_404(code: str) -> ops.OperationProfile:
    try:
        return ops.get_profile(code)
    except KeyError:
        raise HTTPException(404, f"Операция «{code}» не найдена")


def full_params(profile: ops.OperationProfile, values: dict) -> dict:
    """Пропущенные параметры берутся из демо-датасета — так гость может посчитать сразу."""
    base = {p["label"]: p["default"] for p in preset_or_404(profile.object_type)["parameters"]}
    base.update({k: v for k, v in values.items() if v is not None and v != ""})
    return base


def check_params(profile: ops.OperationProfile, values: dict) -> dict:
    res = P.validate(preset_or_404(profile.object_type), values, ops.used_params(profile))
    if not res["ok"]:
        raise HTTPException(422, {"message": "Параметры объекта заполнены с ошибками",
                                  "errors": res["errors"]})
    return res


def apply_admin_defaults() -> None:
    for key, v in get_repo().settings().items():
        if key.startswith("assumption:"):
            k = key.split(":", 1)[1]
            if k in ec.DEFAULT_ASSUMPTIONS:
                old = ec.DEFAULT_ASSUMPTIONS[k]
                ec.DEFAULT_ASSUMPTIONS[k] = ec.Assumption(v["value"], old.unit, v["source"])


@router.get("/meta", tags=["service"], summary="Версии, состояние хранилища, правила подбора")
def meta():
    repo = get_repo()
    return {
        "app": settings.app_name, "model_version": MODEL_VERSION,
        "catalog_version": repo.catalog_version(), "storage": repo.kind,
        "solutions": len(repo.solutions()),
        "selection_rules": [{"name": n, "rule": r, "effect": e} for n, r, e in RULES_DOC],
        "ranking_weights": WEIGHTS,
        "payback_bands": [{"up_to_years": b[0], "level": b[1], "verdict": b[2], "text": b[3]}
                          for b in PAYBACK_BANDS],
        "demo_accounts": [{"username": "user@demo", "role": "user"},
                          {"username": "admin@demo", "role": "admin"}],
    }


# ---------------------------------------------------------------- авторизация
@router.post("/auth/login", tags=["auth"])
def login(c: Credentials):
    u = get_repo().user(c.username)
    if not u or not auth.verify_password(c.password, u["password_hash"]):
        raise HTTPException(401, "Неверный логин или пароль")
    return {"token": auth.issue_token(u["username"], u["role"]),
            "user": {"username": u["username"], "role": u["role"]}}


@router.post("/auth/register", tags=["auth"])
def register(c: Credentials):
    repo = get_repo()
    if repo.user(c.username):
        raise HTTPException(409, "Пользователь с таким логином уже есть — войдите или выберите другой логин")
    repo.create_user(c.username, c.password, "user")
    return {"token": auth.issue_token(c.username, "user"),
            "user": {"username": c.username, "role": "user"}}


@router.get("/auth/me", tags=["auth"])
def me(user: dict | None = Depends(current_user)):
    return {"user": {"username": user["sub"], "role": user["role"]} if user else None}


# ---------------------------------------------------------------- каталог
@router.get("/catalog/object-types", tags=["catalog"], summary="Типы объектов и их операции")
def object_types():
    return [{**o, "data_source": presets()[o["code"]]["data_source"],
             "profiles": [p.public() for p in ops.profiles_for(o["code"])]}
            for o in OBJECT_TYPES]


@router.get("/catalog/presets/{code}", tags=["catalog"], summary="Параметры объекта с демо-значениями")
def preset(code: str):
    return preset_or_404(code)


@router.get("/catalog/tree", tags=["catalog"],
            summary="Иерархия: отрасль → объект → процесс → тип решения → продукты")
def catalog_tree():
    sols = get_repo().solutions()
    tree = []
    for o in OBJECT_TYPES:
        processes = []
        for p in ops.profiles_for(o["code"]):
            types = []
            for st in p.subtypes:
                items = [s for s in sols if s["subtype"] == st
                         and (o["code"] == "custom" or o["code"] in s["object_types"])]
                if items:
                    types.append({"subtype": st, "count": len(items),
                                  "products": [{"id": s["external_id"], "name": s["name"]}
                                               for s in items]})
            processes.append({"code": p.code, "title": p.title, "types": types})
        tree.append({"industry": o["industry"], "object_type": o["code"], "title": o["title"],
                     "processes": processes})
    return tree


@router.get("/catalog/solutions", tags=["catalog"], summary="Каталог: фильтр, поиск, сортировка")
def solutions(object_type: str | None = None, subtype: str | None = None,
              status: str | None = None, profile: str | None = None,
              q: str | None = Query(None, description="поиск по названию, вендору, описанию"),
              sort: str = Query("name", pattern="^-?(name|price_rub|trl|vendor)$"),
              limit: int = Query(50, le=500), offset: int = 0):
    items = get_repo().solutions()
    if object_type:
        items = [s for s in items if object_type in s["object_types"]]
    if profile:
        subs = set(profile_or_404(profile).subtypes)
        items = [s for s in items if s["subtype"] in subs]
    if subtype:
        items = [s for s in items if s["subtype"] == subtype]
    if status:
        items = [s for s in items if s["status"] == status]
    if q:
        ql = q.lower()
        items = [s for s in items if ql in s["name"].lower() or ql in s["vendor"].lower()
                 or ql in (s.get("description") or "").lower()]
    key = sort.lstrip("-")
    items = sorted(items, key=lambda s: (s.get(key) is None, s.get(key) or 0 if key in
                                         ("price_rub", "trl") else str(s.get(key) or "").lower()),
                   reverse=sort.startswith("-"))
    facets = {"subtypes": sorted({s["subtype"] for s in items if s["subtype"]}),
              "statuses": sorted({s["status"] for s in items if s["status"]})}
    return {"total": len(items), "items": items[offset:offset + limit], "facets": facets}


@router.get("/catalog/solutions/{external_id}", tags=["catalog"])
def solution(external_id: str):
    s = get_repo().solution(external_id)
    if not s:
        raise HTTPException(404, "Решение не найдено")
    return s


@router.get("/catalog/sources", tags=["catalog"], summary="Источники данных каталога")
def sources():
    items = get_repo().solutions()
    by = {}
    for s in items:
        key = s.get("source_url") or s["data_source"]
        by.setdefault(key, {"source": key, "count": 0, "updated_at": s.get("updated_at")})
        by[key]["count"] += 1
    return sorted(by.values(), key=lambda x: -x["count"])


# ---------------------------------------------------------------- параметры объекта
@router.post("/params/validate", tags=["params"], summary="Проверка параметров объекта")
def params_validate(body: ParamsIn, profile: str | None = None):
    required = ops.used_params(profile_or_404(profile)) if profile else set()
    return P.validate(preset_or_404(body.object_type), body.values, required)


@router.get("/params/template/{object_type}", tags=["params"], summary="Шаблон Excel/CSV")
def params_template(object_type: str, fmt: str = Query("xlsx", pattern="^(xlsx|csv)$")):
    pr = preset_or_404(object_type)
    if fmt == "csv":
        return Response(P.template_csv(pr), media_type="text/csv; charset=utf-8",
                        headers=_attachment(f"шаблон_{pr['title']}.csv"))
    return Response(P.template_xlsx(pr), media_type=XLSX_MIME,
                    headers=_attachment(f"шаблон_{pr['title']}.xlsx"))


@router.post("/params/upload", tags=["params"], summary="Загрузка параметров из Excel/CSV")
async def params_upload(object_type: str, file: UploadFile = File(...),
                        profile: str | None = None):
    pr = preset_or_404(object_type)
    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(413, "Файл больше 5 МБ — загрузите только лист с параметрами")
    try:
        parsed = P.parse_upload(file.filename or "file.xlsx", content, pr)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    except Exception:                                   # noqa: BLE001
        raise HTTPException(422, "Не удалось прочитать файл. Проверьте, что это .xlsx или .csv "
                                 "по шаблону платформы")
    required = ops.used_params(profile_or_404(profile)) if profile else set()
    check = P.validate(pr, parsed["values"], required)
    return {**parsed, "validation": check}


# ---------------------------------------------------------------- подбор и расчёт
@router.post("/selection", tags=["selection"],
             summary="Подбор: все кандидаты с вердиктом, причинами и вкладом факторов")
def selection(body: SelectionIn):
    profile = profile_or_404(body.profile_code)
    params = full_params(profile, body.params)
    check_params(profile, params)
    return run_selection(get_repo().solutions(), profile, params)


def _evaluate(body: EvaluateIn) -> tuple[dict, dict, ops.OperationProfile, dict]:
    profile = profile_or_404(body.profile_code)
    params = full_params(profile, body.params)
    check_params(profile, params)
    repo = get_repo()
    sol = repo.solution(body.solution_id)
    if not sol:
        raise HTTPException(404, "Решение не найдено в каталоге")
    sel = run_selection(repo.solutions(), profile, params)
    cand = next((c for group in ("fit", "check_needed", "excluded") for c in sel[group]
                 if c["solution_id"] == body.solution_id), None)
    try:
        result = evaluate(sol, profile, params, body.overrides, body.options, cand)
    except (ValueError, ops.MissingParam) as exc:
        raise HTTPException(422, str(exc))
    result["catalog_version"] = repo.catalog_version()
    result["calculated_at"] = datetime.now().isoformat(timespec="seconds")
    result["candidate"] = cand
    return result, params, profile, sel


@router.post("/evaluate", tags=["economics"],
             summary="Полный расчёт: парк, 3 сценария, трассировка, чувствительность, рекомендация")
def evaluate_route(body: EvaluateIn):
    result, _, _, _ = _evaluate(body)
    return result


@router.post("/compare", tags=["economics"], summary="Сравнение нескольких решений по единым показателям")
def compare(body: CompareIn):
    out = []
    for sid in body.solution_ids:
        try:
            r, *_ = _evaluate(EvaluateIn(profile_code=body.profile_code, params=body.params,
                                         solution_id=sid, options=body.options))
        except HTTPException as exc:
            out.append({"solution_id": sid, "error": exc.detail})
            continue
        buy = next(s for s in r["scenarios"] if s["code"] == "purchase")
        raas = next(s for s in r["scenarios"] if s["code"] == "raas")
        out.append({"solution_id": sid, "solution": r["solution"], "robot": r["robot"],
                    "fleet": r["fleet"], "verdict": (r["candidate"] or {}).get("verdict"),
                    "purchase": {k: buy[k] for k in ("capex_total", "opex_year", "annual_effect",
                                                     "payback_years", "roi_percent", "tco")},
                    "raas": {k: raas[k] for k in ("capex_total", "opex_year", "annual_effect",
                                                  "payback_years", "tco")},
                    "recommendation": r["recommendation"]})
    return out


@router.post("/simulate", tags=["simulation"], summary="Прогон смены для заданного парка")
def run_simulation(payload: dict):
    fields = {k: v for k, v in payload.items() if k in SimConfig.__annotations__}
    fields.setdefault("robot_count", 1)
    return simulate(SimConfig(**fields)).as_dict()


# ---------------------------------------------------------------- отчёт
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _attachment(name: str) -> dict:
    return {"Content-Disposition": f"attachment; filename=\"report\"; filename*=UTF-8''{quote(name)}"}


def report_payload(result: dict, params: dict, profile: ops.OperationProfile, sel: dict) -> dict:
    pr = preset_or_404(profile.object_type)
    used = ops.used_params(profile)
    return {
        **result,
        "object": {"title": pr["title"], "data_source": pr["data_source"],
                   "parameters": [{"label": p["label"], "unit": p["unit"],
                                   "value": params.get(p["label"]),
                                   "source": ("используется в расчёте. " if p["label"] in used else "")
                                   + (p.get("source_note") or "")}
                                  for p in pr["parameters"]]},
        "operation": {"title": profile.title, "unit": profile.unit, "note": profile.note},
        "candidates": sel["fit"] + sel["check_needed"] + sel["excluded"],
    }


@router.post("/report/{fmt}", tags=["report"], summary="Отчёт PDF или Excel по расчёту")
def report(fmt: str, body: EvaluateIn):
    if fmt not in ("xlsx", "pdf"):
        raise HTTPException(404, "Формат отчёта: xlsx или pdf")
    result, params, profile, sel = _evaluate(body)
    payload = report_payload(result, params, profile, sel)
    stamp = datetime.now().strftime("%Y%m%d")
    if fmt == "xlsx":
        return Response(build_xlsx(payload), media_type=XLSX_MIME,
                        headers=_attachment(f"отчёт_роботизация_{stamp}.xlsx"))
    return Response(build_pdf(payload), media_type="application/pdf",
                    headers=_attachment(f"отчёт_роботизация_{stamp}.pdf"))


# ---------------------------------------------------------------- проекты
def own_project(pid: int, user: dict) -> dict:
    p = get_repo().project(pid)
    if not p or (p["owner"] != user["sub"] and user["role"] != "admin"):
        raise HTTPException(404, "Проект не найден")        # чужие проекты не раскрываем
    return p


@router.get("/projects", tags=["projects"])
def list_projects(user: dict = Depends(require_user)):
    return [{k: p[k] for k in ("id", "title", "object_type", "profile_code", "created_at",
                               "updated_at")} | {"scenarios": len(p["scenarios"])}
            for p in get_repo().projects(user["sub"])]


@router.post("/projects", tags=["projects"])
def create_project(body: ProjectIn, user: dict = Depends(require_user)):
    preset_or_404(body.object_type)
    return get_repo().create_project(user["sub"], body.model_dump())


@router.get("/projects/{pid}", tags=["projects"])
def get_project(pid: int, user: dict = Depends(require_user)):
    return own_project(pid, user)


@router.put("/projects/{pid}", tags=["projects"])
def update_project(pid: int, body: ProjectPatch, user: dict = Depends(require_user)):
    own_project(pid, user)
    return get_repo().update_project(pid, body.model_dump())


@router.post("/projects/{pid}/copy", tags=["projects"])
def copy_project(pid: int, user: dict = Depends(require_user)):
    p = own_project(pid, user)
    repo = get_repo()
    new = repo.create_project(user["sub"], {**p, "title": p["title"] + " (копия)"})
    for sc in p["scenarios"]:
        repo.add_scenario(new["id"], {k: v for k, v in sc.items() if k not in ("id", "created_at")})
    return repo.project(new["id"])


@router.delete("/projects/{pid}", tags=["projects"],
               summary="Удаление проекта со всеми сценариями и загруженными параметрами")
def delete_project(pid: int, user: dict = Depends(require_user)):
    own_project(pid, user)
    get_repo().delete_project(pid)
    return {"deleted": pid}


@router.post("/projects/{pid}/scenarios", tags=["projects"],
             summary="Сохранить расчёт как сценарий проекта (с версиями данных и модели)")
def save_scenario(pid: int, body: ScenarioIn, user: dict = Depends(require_user)):
    own_project(pid, user)
    result, params, _, _ = _evaluate(body)
    return get_repo().add_scenario(pid, {
        "title": body.title, "solution_external_id": body.solution_id,
        "profile_code": body.profile_code, "parameters": params,
        "overrides": body.overrides, "options": body.options,
        "summary": summary_of(result), "catalog_version": result["catalog_version"],
        "model_version": result["model_version"]})


@router.post("/projects/{pid}/scenarios/{sid}/replay", tags=["projects"],
             summary="Воспроизвести сохранённый расчёт и сверить с сохранённым результатом")
def replay_scenario(pid: int, sid: int, user: dict = Depends(require_user)):
    p = own_project(pid, user)
    sc = next((s for s in p["scenarios"] if s["id"] == sid), None)
    if not sc:
        raise HTTPException(404, "Сценарий не найден")
    result, *_ = _evaluate(EvaluateIn(profile_code=sc["profile_code"], params=sc["parameters"],
                                      solution_id=sc["solution_external_id"],
                                      overrides=sc["overrides"], options=sc["options"]))
    now = summary_of(result)
    same = now["scenarios"] == sc["summary"]["scenarios"] and now["fleet"] == sc["summary"]["fleet"]
    return {"scenario": sc, "result": result, "matches_saved": same,
            "versions": {"saved": {"catalog": sc["catalog_version"], "model": sc["model_version"]},
                         "current": {"catalog": result["catalog_version"],
                                     "model": result["model_version"]}}}


@router.delete("/projects/{pid}/scenarios/{sid}", tags=["projects"])
def delete_scenario(pid: int, sid: int, user: dict = Depends(require_user)):
    own_project(pid, user)
    get_repo().delete_scenario(pid, sid)
    return {"deleted": sid}


# ---------------------------------------------------------------- администрирование
@router.post("/admin/solutions", tags=["admin"], summary="Добавить или изменить решение")
def admin_save_solution(body: SolutionIn, user: dict = Depends(require_admin)):
    repo = get_repo()
    item = body.model_dump()
    item["external_id"] = item["external_id"] or f"adm-{uuid.uuid4().hex[:10]}"
    old = repo.solution(item["external_id"]) or {}
    item = {**old, **item}
    item.setdefault("group", "Мобильные роботы")
    item["scenario"] = (item["scenarios"] or [""])[0]
    item.setdefault("industries", [item["industry"]])
    item.setdefault("kind", "brs")
    item.setdefault("region", "")
    item.setdefault("market_potential", None)
    for k, v in list(item["specs"].items()):
        if not isinstance(v, dict):
            item["specs"][k] = {"value": v, "unit": None, "confirmed": False,
                                "source": f"Введено администратором {user['sub']}"}
    return repo.save_solution(item, user["sub"])


@router.delete("/admin/solutions/{external_id}", tags=["admin"])
def admin_delete_solution(external_id: str, user: dict = Depends(require_admin)):
    if not get_repo().delete_solution(external_id):
        raise HTTPException(404, "Решение не найдено")
    return {"deleted": external_id}


@router.post("/admin/catalog/reload", tags=["admin"],
             summary="Перезагрузить каталог из seed-файлов (после ETL)")
def admin_reload(user: dict = Depends(require_admin)):
    n = get_repo().reload_catalog()
    ops.reload_profiles()
    presets.cache_clear()
    return {"solutions": n, "catalog_version": get_repo().catalog_version()}


@router.get("/admin/assumptions", tags=["admin"], summary="Нормативы модели по умолчанию")
def admin_assumptions():
    changed = get_repo().settings()
    return {k: v.as_dict() | {"changed": changed.get(f"assumption:{k}")}
            for k, v in ec.DEFAULT_ASSUMPTIONS.items()}


@router.put("/admin/assumptions/{key}", tags=["admin"], summary="Изменить норматив по умолчанию")
def admin_set_assumption(key: str, body: AssumptionIn, user: dict = Depends(require_admin)):
    if key not in ec.DEFAULT_ASSUMPTIONS:
        raise HTTPException(404, "Норматив не найден")
    get_repo().save_setting(f"assumption:{key}", body.model_dump(), user["sub"])
    apply_admin_defaults()
    return ec.DEFAULT_ASSUMPTIONS[key].as_dict()


@router.get("/admin/users", tags=["admin"])
def admin_users(user: dict = Depends(require_admin)):
    return get_repo().users()
