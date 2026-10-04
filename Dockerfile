FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /srv

# Зависимости отдельным слоем: правки в коде не пересобирают pip install
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app

# Не запускаемся от root
RUN useradd --create-home --uid 10001 appuser && chown -R appuser:appuser /srv
USER appuser

EXPOSE 8000

# Схему накатывает alembic в compose, здесь только приём трафика
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]