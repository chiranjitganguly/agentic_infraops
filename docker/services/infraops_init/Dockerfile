FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir asyncpg bcrypt httpx

COPY infrastructure/scripts/init_system.py /app/init_system.py
COPY infrastructure/db/migrations /app/migrations

# Override MIGRATIONS_DIR used inside the script via symlink
RUN mkdir -p /app/infrastructure/db && ln -s /app/migrations /app/infrastructure/db/migrations

CMD ["python", "/app/init_system.py"]
