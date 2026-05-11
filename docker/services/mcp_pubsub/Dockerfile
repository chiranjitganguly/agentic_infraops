FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY mcp_servers/pubsub/pyproject.toml ./
RUN pip install --no-cache-dir hatchling && \
    pip install --no-cache-dir -e .

COPY mcp_servers/pubsub/ ./mcp_servers/pubsub/
COPY contracts/ ./contracts/

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

CMD ["python", "-m", "mcp_servers.pubsub.server"]
