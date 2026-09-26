"""
Хранилище данных.

Основной режим — PostgreSQL через SQLAlchemy (SqlRepo). Если база недоступна при
старте, сервис переключается на файловое хранилище в data/runtime (FileRepo) и
продолжает работать: каталог и нормативы берутся из seed-файлов, проекты пишутся
в JSON. Это страховка демонстрации (п. 4.2.7, 4.3.4 ТЗ), а не замена БД.

Интерфейс у обоих хранилищ одинаковый, маршруты API не знают, какое активно.
"""
from __future__ import annotations

import copy
import json
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from app.auth import hash_password
from app.config import settings

log = logging.getLogger("robofit.repo")


def _now() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat()


def _seed_solutions() -> list[dict]:
    return json.loads((settings.seed_dir / "solutions.json").read_text(encoding="utf-8"))


def _catalog_version() -> str:
    try:
        rep = json.loads((settings.seed_dir / "etl_report.json").read_text(encoding="utf-8"))
        return rep.get("catalog_version", "")
    except FileNotFoundError:
        return ""


class BaseRepo:
    kind = "base"
    _solutions_cache: list[dict] | None = None

    def catalog_version(self) -> str:
        return _catalog_version()

    def demo_users(self) -> list[tuple[str, str, str]]:
        return [("user@demo", settings.demo_user_password, "user"),
                ("admin@demo", settings.demo_admin_password, "admin")]

    def invalidate(self) -> None:
        self._solutions_cache = None


# ==========================================================================
# файловое хранилище
# ==========================================================================
class FileRepo(BaseRepo):
    kind = "file"

    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self.path = root / "store.json"
        if self.path.exists():
            self.data = json.loads(self.path.read_text(encoding="utf-8"))
        else:
            self.data = {"users": {}, "projects": {}, "seq": 0, "solutions": None,
                         "settings": {}}
        if self.data.get("solutions") is None:
            self.data["solutions"] = {s["external_id"]: s for s in _seed_solutions()}
        for username, password, role in self.demo_users():
            self.data["users"].setdefault(username, {
                "username": username, "password_hash": hash_password(password), "role": role})
        self._save()

    def _save(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, default=str), encoding="utf-8")
        tmp.replace(self.path)          # атомарная запись: сбой не портит сохранённое

    def _next_id(self) -> int:
        self.data["seq"] += 1
        return self.data["seq"]

    # каталог
    def solutions(self) -> list[dict]:
        return list(self.data["solutions"].values())

    def solution(self, external_id: str) -> dict | None:
        return self.data["solutions"].get(external_id)

    def save_solution(self, item: dict, by: str) -> dict:
        with self.lock:
            item = {**item, "updated_at": _now()[:10], "updated_by": by}
            self.data["solutions"][item["external_id"]] = item
            self._save()
        return item

    def delete_solution(self, external_id: str) -> bool:
        with self.lock:
            found = self.data["solutions"].pop(external_id, None) is not None
            self._save()
        return found

    def reload_catalog(self) -> int:
        with self.lock:
            self.data["solutions"] = {s["external_id"]: s for s in _seed_solutions()}
            self._save()
        return len(self.data["solutions"])

    # пользователи
    def user(self, username: str) -> dict | None:
        return self.data["users"].get(username)

    def create_user(self, username: str, password: str, role: str = "user") -> dict:
        with self.lock:
            u = {"username": username, "password_hash": hash_password(password), "role": role}
            self.data["users"][username] = u
            self._save()
        return u

    def users(self) -> list[dict]:
        return [{"username": u["username"], "role": u["role"]} for u in self.data["users"].values()]

    # проекты
    def projects(self, owner: str) -> list[dict]:
        items = [p for p in self.data["projects"].values() if p["owner"] == owner]
        return sorted(items, key=lambda p: p["updated_at"], reverse=True)

    def project(self, pid: int) -> dict | None:
        p = self.data["projects"].get(str(pid))
        return copy.deepcopy(p) if p else None

    def create_project(self, owner: str, payload: dict) -> dict:
        with self.lock:
            pid = self._next_id()
            p = {"id": pid, "owner": owner, "title": payload["title"],
                 "object_type": payload["object_type"],
                 "profile_code": payload.get("profile_code", ""),
                 "parameters": payload.get("parameters", {}), "notes": payload.get("notes", ""),
                 "created_at": _now(), "updated_at": _now(), "scenarios": []}
            self.data["projects"][str(pid)] = p
            self._save()
        return copy.deepcopy(p)

    def update_project(self, pid: int, payload: dict) -> dict:
        with self.lock:
            p = self.data["projects"][str(pid)]
            for k in ("title", "object_type", "profile_code", "parameters", "notes"):
                if payload.get(k) is not None:
                    p[k] = payload[k]
            p["updated_at"] = _now()
            self._save()
        return copy.deepcopy(p)

    def delete_project(self, pid: int) -> None:
        with self.lock:
            self.data["projects"].pop(str(pid), None)
            self._save()

    def add_scenario(self, pid: int, sc: dict) -> dict:
        with self.lock:
            p = self.data["projects"][str(pid)]
            sc = {**sc, "id": self._next_id(), "created_at": _now()}
            p["scenarios"].append(sc)
            p["updated_at"] = _now()
            self._save()
        return sc

    def delete_scenario(self, pid: int, sid: int) -> None:
        with self.lock:
            p = self.data["projects"][str(pid)]
            p["scenarios"] = [s for s in p["scenarios"] if s["id"] != sid]
            self._save()

    # нормативы
    def settings(self) -> dict:
        return dict(self.data.get("settings", {}))

    def save_setting(self, key: str, value: dict, by: str) -> None:
        with self.lock:
            self.data.setdefault("settings", {})[key] = {**value, "updated_by": by,
                                                         "updated_at": _now()}
            self._save()


# ==========================================================================
# PostgreSQL
# ==========================================================================
class SqlRepo(BaseRepo):
    kind = "postgresql"

    def __init__(self):
        from sqlalchemy import text

        from app.db import models  # noqa: F401  регистрирует таблицы
        from app.db.session import Base, SessionLocal, engine
        self.S = SessionLocal
        with engine.connect() as conn:
            conn.execute(text("select 1"))
        Base.metadata.create_all(engine)
        self.m = models
        with self.S() as db:
            if not db.query(models.Solution).first():
                self._load_seed(db)
            for username, password, role in self.demo_users():
                if not db.query(models.User).filter_by(username=username).first():
                    db.add(models.User(username=username, password_hash=hash_password(password),
                                       role=role))
            db.commit()

    def _load_seed(self, db) -> int:
        items = _seed_solutions()
        for s in items:
            db.add(self.m.Solution(external_id=s["external_id"], data=s, name=s["name"][:512],
                                   subtype=s["subtype"][:128], price_rub=s["price_rub"]))
        return len(items)

    # каталог
    def solutions(self) -> list[dict]:
        if self._solutions_cache is None:
            with self.S() as db:
                self._solutions_cache = [r.data for r in db.query(self.m.Solution).all()]
        return self._solutions_cache

    def solution(self, external_id: str) -> dict | None:
        with self.S() as db:
            r = db.query(self.m.Solution).filter_by(external_id=external_id).first()
            return r.data if r else None

    def save_solution(self, item: dict, by: str) -> dict:
        item = {**item, "updated_at": _now()[:10], "updated_by": by}
        with self.S() as db:
            r = db.query(self.m.Solution).filter_by(external_id=item["external_id"]).first()
            if not r:
                r = self.m.Solution(external_id=item["external_id"])
                db.add(r)
            r.data, r.name, r.subtype = item, item["name"][:512], item.get("subtype", "")[:128]
            r.price_rub, r.updated_by = item.get("price_rub"), by
            db.commit()
        self.invalidate()
        return item

    def delete_solution(self, external_id: str) -> bool:
        with self.S() as db:
            n = db.query(self.m.Solution).filter_by(external_id=external_id).delete()
            db.commit()
        self.invalidate()
        return bool(n)

    def reload_catalog(self) -> int:
        with self.S() as db:
            db.query(self.m.Solution).delete()
            n = self._load_seed(db)
            db.commit()
        self.invalidate()
        return n

    # пользователи
    def user(self, username: str) -> dict | None:
        with self.S() as db:
            u = db.query(self.m.User).filter_by(username=username).first()
            return {"username": u.username, "password_hash": u.password_hash,
                    "role": u.role} if u else None

    def create_user(self, username: str, password: str, role: str = "user") -> dict:
        with self.S() as db:
            db.add(self.m.User(username=username, password_hash=hash_password(password), role=role))
            db.commit()
        return {"username": username, "role": role}

    def users(self) -> list[dict]:
        with self.S() as db:
            return [{"username": u.username, "role": u.role} for u in db.query(self.m.User).all()]

    # проекты
    @staticmethod
    def _scenario(s) -> dict:
        return {"id": s.id, "title": s.title, "solution_external_id": s.solution_external_id,
                "profile_code": s.profile_code, "parameters": s.parameters,
                "overrides": s.overrides, "options": s.options, "summary": s.summary,
                "catalog_version": s.catalog_version, "model_version": s.model_version,
                "created_at": s.created_at.isoformat()}

    def _project(self, p) -> dict:
        return {"id": p.id, "owner": p.owner, "title": p.title, "object_type": p.object_type,
                "profile_code": p.profile_code, "parameters": p.parameters, "notes": p.notes,
                "created_at": p.created_at.isoformat(), "updated_at": p.updated_at.isoformat(),
                "scenarios": [self._scenario(s) for s in p.scenarios]}

    def projects(self, owner: str) -> list[dict]:
        with self.S() as db:
            rows = (db.query(self.m.Project).filter_by(owner=owner)
                    .order_by(self.m.Project.updated_at.desc()).all())
            return [self._project(p) for p in rows]

    def project(self, pid: int) -> dict | None:
        with self.S() as db:
            p = db.get(self.m.Project, pid)
            return self._project(p) if p else None

    def create_project(self, owner: str, payload: dict) -> dict:
        with self.S() as db:
            p = self.m.Project(owner=owner, title=payload["title"],
                               object_type=payload["object_type"],
                               profile_code=payload.get("profile_code", ""),
                               parameters=payload.get("parameters", {}),
                               notes=payload.get("notes", ""))
            db.add(p)
            db.commit()
            db.refresh(p)
            return self._project(p)

    def update_project(self, pid: int, payload: dict) -> dict:
        with self.S() as db:
            p = db.get(self.m.Project, pid)
            for k in ("title", "object_type", "profile_code", "parameters", "notes"):
                if payload.get(k) is not None:
                    setattr(p, k, payload[k])
            p.updated_at = datetime.utcnow()
            db.commit()
            db.refresh(p)
            return self._project(p)

    def delete_project(self, pid: int) -> None:
        with self.S() as db:
            p = db.get(self.m.Project, pid)
            if p:
                db.delete(p)
                db.commit()

    def add_scenario(self, pid: int, sc: dict) -> dict:
        with self.S() as db:
            row = self.m.Scenario(project_id=pid, **{k: sc[k] for k in (
                "title", "solution_external_id", "profile_code", "parameters", "overrides",
                "options", "summary", "catalog_version", "model_version")})
            db.add(row)
            p = db.get(self.m.Project, pid)
            p.updated_at = datetime.utcnow()
            db.commit()
            db.refresh(row)
            return self._scenario(row)

    def delete_scenario(self, pid: int, sid: int) -> None:
        with self.S() as db:
            db.query(self.m.Scenario).filter_by(project_id=pid, id=sid).delete()
            db.commit()

    # нормативы
    def settings(self) -> dict:
        with self.S() as db:
            return {s.key: {**s.value, "updated_by": s.updated_by,
                            "updated_at": s.updated_at.isoformat()}
                    for s in db.query(self.m.Setting).all()}

    def save_setting(self, key: str, value: dict, by: str) -> None:
        with self.S() as db:
            row = db.get(self.m.Setting, key) or self.m.Setting(key=key)
            row.value, row.updated_by = value, by
            db.merge(row)
            db.commit()


_repo: BaseRepo | None = None


def get_repo() -> BaseRepo:
    global _repo
    if _repo is None:
        try:
            if not settings.database_url:
                raise RuntimeError("DATABASE_URL не задан")
            _repo = SqlRepo()
            log.info("Хранилище: PostgreSQL")
        except Exception as exc:                       # noqa: BLE001
            log.warning("PostgreSQL недоступна (%s) — работаю на файловом хранилище", exc)
            _repo = FileRepo(settings.runtime_dir)
    return _repo


def summary_of(result: dict) -> dict[str, Any]:
    """Ключевые цифры расчёта для сохранения в проекте и сверки при повторном открытии."""
    return {
        "fleet": result["fleet"]["count"],
        "recommendation": result["recommendation"]["verdict"],
        "scenarios": {s["code"]: {k: s[k] for k in (
            "capex_total", "opex_year", "annual_effect", "payback_years", "roi_percent", "tco")}
            for s in result["scenarios"]},
        "solution_name": result["solution"]["name"],
    }
