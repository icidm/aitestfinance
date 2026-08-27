FROM python:3.13-slim AS builder
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libcairo2-dev libpango1.0-dev libgdk-pixbuf2.0-dev && rm -rf /var/lib/apt/lists/*
COPY requirements.txt pyproject.toml ./
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.13-slim
RUN apt-get update && apt-get install -y --no-install-recommends curl libcairo2 libpango-1.0-0 libgdk-pixbuf2.0-0 && rm -rf /var/lib/apt/lists/* \
    && groupadd -r app && useradd -r -g app app
COPY --from=builder /install /usr/local
WORKDIR /app
COPY --chown=app:app . .
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=10s --retries=3 --start-period=10s CMD curl -f http://localhost:8000/health || exit 1
CMD ["sh", "entrypoint.sh"]
