FROM python:3.12-slim AS build

ENV POETRY_VERSION=2.3.4 \
    POETRY_HOME=/opt/poetry \
    POETRY_VIRTUALENVS_IN_PROJECT=true \
    POETRY_NO_INTERACTION=1

RUN pip install --no-cache-dir "poetry==$POETRY_VERSION"
WORKDIR /app
COPY pyproject.toml poetry.lock ./
RUN poetry install --only main --no-root
COPY src ./src

FROM python:3.12-slim AS runtime
WORKDIR /app
COPY --from=build /app/.venv /app/.venv
COPY --from=build /app/src /app/src
ENV PATH="/app/.venv/bin:$PATH" PYTHONPATH=/app/src PYTHONUNBUFFERED=1
RUN useradd --create-home --uid 10001 appuser
USER appuser
EXPOSE 8080
CMD ["sh", "-c", "uvicorn customer_data_product.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
