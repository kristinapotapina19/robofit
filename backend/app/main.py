import logging
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.api.routes import apply_admin_defaults, router
from app.config import settings
from app.core.pipeline import MODEL_VERSION
from app.repo import get_repo

logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title=settings.app_name,
    version=MODEL_VERSION,
    description=(
        "Подбор роботизированных решений, расчёт экономики (CAPEX, OPEX, эффект, окупаемость, "
        "ROI, TCO) по трём сценариям, имитация работы парка и выгрузка отчёта.\n\n"
        "Доступ: гость — каталог и демонстрационные расчёты; пользователь — проекты; "
        "администратор — каталог и нормативы. Токен из `/api/auth/login` передаётся в "
        "заголовке `Authorization: Bearer <token>`. Демо-учётки: user@demo / demo123, "
        "admin@demo / admin123."),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)

app.include_router(router, prefix="/api")


@app.on_event("startup")
def startup() -> None:
    get_repo()
    apply_admin_defaults()


@app.get("/health", tags=["service"])
def health():
    return {"status": "ok", "storage": get_repo().kind}


# Собранный фронтенд можно отдавать из этого же процесса: так весь сервис
# разворачивается одним контейнером (см. Dockerfile в корне репозитория).
DIST = Path(os.environ.get("FRONTEND_DIST", Path(__file__).resolve().parents[2] / "frontend" / "dist"))
if DIST.exists():
    from fastapi.staticfiles import StaticFiles

    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        target = DIST / path
        if path and target.is_file():
            return FileResponse(target)
        return FileResponse(DIST / "index.html")
