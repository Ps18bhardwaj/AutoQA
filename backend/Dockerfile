# AutoQA backend — self-contained image with Chromium preinstalled.
#
# Build from THIS backend directory (everything it needs is vendored here):
#   docker build -t autoqa-api .
#
# Uses Microsoft's official Playwright Python image, which ships a matched
# Chromium + all system libs — so no `playwright install` browser download or
# `--with-deps` apt dance at build time. Needs GEMINI_API_KEY at runtime
# (see .env.example); LANGFUSE_* optional.
#
# NOTE: Chromium is memory-hungry — deploy on HF Spaces Docker (or any host
# with >=1GB RAM), NOT Render's 512MB free tier.
FROM mcr.microsoft.com/playwright/python:v1.61.0-noble

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code + the vendored shared router/tracing + the bundled axe.min.js and
# demo site (both live under app/, so they're copied with it).
COPY app ./app
COPY shared ./shared

EXPOSE 8003
CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8003"]
