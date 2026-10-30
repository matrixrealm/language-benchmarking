# One image, two interpreters: --build-arg PYVER=3.14 (GIL build) or 3.14t (free-threaded build). Same pure-asyncio stack for both:
# uvicorn runs with the stdlib loop and h11 so no compiled extension (uvloop/httptools) differs between builds.
FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim
ARG PYVER=3.14
WORKDIR /app
RUN uv venv /venv --python ${PYVER}
ENV PATH=/venv/bin:$PATH VIRTUAL_ENV=/venv
COPY requirements.txt .
RUN uv pip install -r requirements.txt
COPY app_aiohttp.py app_fastapi.py app_django.py mock.py ./
ENV APP=aiohttp THREADS=4
CMD ["sh", "-c", "case $APP in aiohttp) exec python app_aiohttp.py;; fastapi) exec uvicorn app_fastapi:app --host 0.0.0.0 --port 8080 --loop asyncio --http h11 --no-access-log;; django) exec uvicorn app_django:application --host 0.0.0.0 --port 8080 --loop asyncio --http h11 --no-access-log;; esac"]
