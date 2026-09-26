from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "РобоФит — подбор роботизированных решений"
    # Основное хранилище — PostgreSQL. Если БД недоступна (или DATABASE_URL пуст),
    # сервис работает на файловом хранилище в data/runtime, чтобы демонстрация
    # не падала из-за внешней зависимости (п. 4.2.7, 4.3.4 ТЗ).
    database_url: str = "postgresql+psycopg://robofit:robofit@db:5432/robofit"
    seed_dir: Path = BASE_DIR / "data" / "seed"
    runtime_dir: Path = BASE_DIR / "data" / "runtime"
    cors_origins: list[str] = ["*"]
    secret_key: str = "change-me-in-production"
    token_ttl_hours: int = 12
    demo_user_password: str = "demo123"
    demo_admin_password: str = "admin123"


settings = Settings()
