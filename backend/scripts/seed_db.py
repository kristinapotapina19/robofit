"""Создание таблиц и загрузка seed-данных в PostgreSQL (идемпотентно).
Запуск: python scripts/seed_db.py. При старте API то же самое делается автоматически."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.repo import get_repo  # noqa: E402

repo = get_repo()
print(f"хранилище: {repo.kind}, решений в каталоге: {len(repo.solutions())}")
