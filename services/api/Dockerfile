# Build from the repository root: the image needs both the library in src/ and
# the service in services/api/.
#   docker build -f services/api/Dockerfile -t ab-api .
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DEMO_DATA_DIR=/app/data/raw \
    LOG_FORMAT=json \
    ENVIRONMENT=production

WORKDIR /app

# Dependencies first, so a code change does not reinstall the world.
COPY requirements.txt ./requirements.txt
COPY services/api/requirements.txt ./services/api/requirements.txt
RUN pip install --no-cache-dir -r services/api/requirements.txt

# The analysis library, installed as a package rather than copied onto the path.
COPY pyproject.toml README.md ./
COPY src/ ./src/
RUN pip install --no-cache-dir --no-deps .

# The demo dataset is fetched at build time: the landing page must work on a
# cold instance with no network egress and no writable disk.
COPY analysis/fetch_data.py ./analysis/fetch_data.py
RUN python analysis/fetch_data.py && test -s data/raw/cookie_cats.csv

COPY services/api/app/ ./app/

# Run unprivileged; nothing in the service writes outside /tmp.
RUN useradd --create-home --uid 10001 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,os,sys; \
sys.exit(0 if urllib.request.urlopen(f'http://127.0.0.1:{os.getenv(\"PORT\",\"8080\")}/health', timeout=4).status == 200 else 1)"

# Cloud Run supplies PORT; the default keeps local runs identical.
# One worker: the platform scales by adding instances, and a second worker in
# a 512 MiB container competes for the same memory.
CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080} --workers 1 --timeout-keep-alive 65
