# The full interactive app: FastAPI + the built React console in one image.
#
# Two stages so the Node toolchain does not ship to production. The result is
# roughly 700 MB, most of it OR-Tools and the scientific stack — which is why
# this needs a container host (Render, Fly, Railway, Cloud Run) and not a
# serverless platform. Vercel and Netlify functions cap well below this, and
# their execution limits are shorter than a single solve.

FROM node:22-slim AS ui
WORKDIR /ui
COPY ui/package.json ui/package-lock.json ./
RUN npm ci
COPY ui/ ./
RUN npm run build

FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY sanchay/ ./sanchay/
COPY data/ ./data/
COPY --from=ui /ui/dist ./ui/dist

# A solve is CPU-bound and holds its result in memory, so one worker with
# several search threads beats several workers each fighting for the same core.
# See docs/build-notes.md §11 on the cache stampede this avoids.
ENV WEB_CONCURRENCY=1
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health',timeout=4).status==200 else 1)"

CMD ["sh", "-c", "uvicorn sanchay.api.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
