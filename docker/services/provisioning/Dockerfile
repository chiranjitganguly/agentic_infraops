FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY agents/provisioning/pyproject.toml ./
RUN pip install --no-cache-dir hatchling && \
    pip install --no-cache-dir -e .

COPY agents/provisioning/ ./agents/provisioning/
COPY contracts/ ./contracts/

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

CMD ["python", "-m", "agents.provisioning.agent"]
