FROM ghcr.io/berriai/litellm:main-latest

WORKDIR /app

COPY litellm_config.yaml /app/config.yaml

EXPOSE 4000

CMD ["--config", "/app/config.yaml", "--port", "4000"]
