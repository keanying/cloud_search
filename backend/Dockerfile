# 云搜浏览器后端（API 与 worker 共用镜像）。构建上下文为仓库根目录：
#   docker build -f backend/Dockerfile .
# 基础镜像自带与 playwright==1.63.0 匹配的 Chromium 及系统依赖。
FROM mcr.microsoft.com/playwright/python:v1.63.0-noble

ENV PYTHONUNBUFFERED=1 PYTHONUTF8=1 PYDANTIC_AI_NO_BANNER=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY backend ./backend
COPY config.example.yaml ./
RUN uv sync --frozen --no-dev
ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
CMD ["sh", "-c", "alembic -c backend/alembic.ini upgrade head && python -m cloudsearch.serve --host 0.0.0.0 --port 8000 --forwarded-allow-ips '*'"]
