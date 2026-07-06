FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir uv

# Installer les dépendances en premier pour bénéficier du cache Docker
COPY pyproject.toml uv.lock ./
ENV UV_HTTP_TIMEOUT=300
RUN uv sync --frozen --no-dev

# Copier le code applicatif
COPY . .

ENV VIRTUAL_ENV=/app/.venv
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

# Par défaut : API FastAPI (surchargé par chaque service worker dans docker-compose)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]