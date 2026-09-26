FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

# DejaVu — кириллический шрифт для PDF-отчёта
RUN apt-get update && apt-get install -y --no-install-recommends fonts-dejavu-core curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --retries=10 CMD curl -fs http://localhost:8000/health || exit 1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
