# syntax=docker/dockerfile:1
#
# PhishermanAI verification API.
#
#   docker build -t phishermanai-api .
#   docker run -p 8000:8000 phishermanai-api
#
# The EMAIL path only. The image/OCR extras pull PaddlePaddle and add ~2GB, so
# they are not installed here -- core/ingest/image_pipeline.py probes for them
# and degrades cleanly when they are absent (/health reports image_support).

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TLDEXTRACT_CACHE=/opt/tldextract-cache

# fonts-dejavu-core -- core/actions.py renders the shareable warning card with
#   Pillow and looks for DejaVu on Linux. Without it every card silently falls
#   back to the fixed-size bitmap font and the PNG comes out unreadable.
# curl -- used by the HEALTHCHECK below.
RUN apt-get update \
 && apt-get install -y --no-install-recommends fonts-dejavu-core curl \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependencies before source, so editing code does not re-run the install.
COPY requirements.txt ./
RUN pip install -r requirements.txt

# Prime the public-suffix list. tldextract otherwise fetches it the first time
# a domain is parsed, which turns the first /verify of a cold container into a
# network round-trip -- or a silent fall back to its bundled snapshot.
#
# a+rwX, not a+rX: tldextract takes a filelock in this directory before it will
# even READ the cache, so a read-only cache dir makes every domain parse raise
# PermissionError and 500s the whole /verify path. It must stay writable by
# whatever uid ends up running the container -- 10001 below, but Spaces-style
# hosts substitute their own.
RUN python -c "import tldextract; tldextract.TLDExtract(cache_dir='/opt/tldextract-cache')('example.co.uk')" \
 && chmod -R a+rwX /opt/tldextract-cache

COPY . .

# Bake the corpus in. data.load_all is entirely offline -- it reads the
# committed data/cache/*.json -- so this needs no build-time network access and
# no request pays to build the database on a cold start.
RUN python -m data.load_all

# Non-root, but data/ stays writable: each verdict is appended to the SQLite
# database as it is served. /var/lib/phishermanai exists so that pointing
# DATABASE_URL at a mounted volume works without a root-owned-directory fight;
# core.db.init_db only creates the default path's parent, not a custom one.
RUN useradd --create-home --uid 10001 phisherman \
 && mkdir -p /var/lib/phishermanai \
 && chown -R phisherman:phisherman /app/data /var/lib/phishermanai
USER phisherman

ENV PORT=8000
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS "http://127.0.0.1:${PORT}/health" || exit 1

CMD ["python", "serve.py"]
