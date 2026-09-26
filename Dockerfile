# Всё в одном контейнере — для развёртывания стенда на любом хостинге с Docker
# (Render, Railway, Amvera, VPS). Фронтенд собирается и отдаётся самим API.
# Без DATABASE_URL сервис работает на файловом хранилище; для PostgreSQL задайте
# DATABASE_URL=postgresql+psycopg://user:pass@host:5432/db
FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package.json ./
RUN npm install --no-audit --no-fund
COPY frontend/ .
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 FRONTEND_DIST=/app/frontend_dist DATABASE_URL=
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ .
COPY --from=web /web/dist /app/frontend_dist
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
