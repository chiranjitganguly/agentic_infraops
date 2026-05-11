FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/libs/*

COPY web/backend/pyproject.toml ./
RUN pip install --no-cache-dir hatchling && \
    pip install --no-cache-dir -e .

COPY web/backend/ ./web/backend/
COPY contracts/ ./contracts/

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

CMD ["python", "-m", "web.backend.notification_service.service"]
