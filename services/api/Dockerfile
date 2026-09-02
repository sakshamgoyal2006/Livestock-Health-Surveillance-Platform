FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY pyproject.toml alembic.ini ./
COPY app/__init__.py ./app/__init__.py
COPY scripts/__init__.py ./scripts/__init__.py
RUN --mount=type=cache,target=/root/.cache/pip \
    python -m pip install --upgrade pip && python -m pip install -e ".[dev]"
COPY alembic ./alembic
COPY app ./app
COPY scripts ./scripts
COPY tests ./tests

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
