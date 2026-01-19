FROM python:3.12-slim

# Install uv.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

COPY ./solution ./app

ENV DEBUG=1

# Install the application dependencies.
WORKDIR /app
RUN uv sync --frozen --no-cache

# Run the application.
CMD ["sh", "-c", "exec /app/.venv/bin/fastapi run app/main.py --port 8080 --host 0.0.0.0"]
