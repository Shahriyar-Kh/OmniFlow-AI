FROM python:3.13.15-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PATH="/home/tbos/.local/bin:${PATH}"

WORKDIR /workspace

RUN groupadd --gid 10001 tbos \
    && useradd --uid 10001 --gid tbos --create-home --shell /usr/sbin/nologin tbos

COPY pyproject.toml README.md compose.yaml ./
COPY apps/renderer/src ./apps/renderer/src
RUN pip install --no-cache-dir ".[dev]"

COPY --chown=tbos:tbos database ./database
COPY --chown=tbos:tbos config ./config
COPY --chown=tbos:tbos scripts/container-entrypoint.sh ./scripts/container-entrypoint.sh
COPY --chown=tbos:tbos apps/renderer/tests ./apps/renderer/tests
COPY --chown=tbos:tbos apps/renderer/Dockerfile ./apps/renderer/Dockerfile
COPY --chown=tbos:tbos tests ./tests
RUN chmod 0555 ./scripts/container-entrypoint.sh \
    && chown tbos:tbos /workspace

USER 10001:10001
EXPOSE 8080

CMD ["/workspace/scripts/container-entrypoint.sh"]
