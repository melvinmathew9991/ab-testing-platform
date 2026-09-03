# Build from the repository root, for symmetry with the API image:
#   docker build -f services/ui/Dockerfile -t ab-ui .
#
# The UI is a thin client over the API, so this image carries neither the
# analysis library nor its scientific stack - it is a fraction of the size.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    ENVIRONMENT=production \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

WORKDIR /app

COPY services/ui/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY services/ui/.streamlit/ ./.streamlit/
COPY services/ui/ui/ ./ui/

RUN useradd --create-home --uid 10001 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request,os,sys; \
sys.exit(0 if urllib.request.urlopen(f'http://127.0.0.1:{os.getenv(\"PORT\",\"8501\")}/_stcore/health', timeout=4).status == 200 else 1)"

# Cloud Run supplies PORT. Streamlit holds a websocket per viewer, so the
# platform is configured with session affinity rather than more workers here.
CMD exec streamlit run ui/main.py \
    --server.port=${PORT:-8501} \
    --server.address=0.0.0.0 \
    --server.headless=true
