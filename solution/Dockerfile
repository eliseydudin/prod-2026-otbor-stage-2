FROM python:3.12-slim

# Install uv.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

COPY ./solution ./app

ENV DEBUG=1

# Install the application dependencies.
WORKDIR /app
RUN uv sync --frozen --no-cache

RUN apt-get update
RUN apt-get install curl

ENV SERVER_PORT=8080

# Run the application.
CMD ["sh", "-c", "exec /app/.venv/bin/fastapi run app/main.py --port $SERVER_PORT --host 0.0.0.0"]
