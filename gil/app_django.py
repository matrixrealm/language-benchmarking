"""Minimal single-file Django (ASGI, async views). Run by uvicorn as app:application."""
import asyncio, hashlib, os, sys
import aiohttp, django
from django.conf import settings
settings.configure(DEBUG=False, SECRET_KEY='benchmark-only', ROOT_URLCONF=__name__, ALLOWED_HOSTS=['*'], MIDDLEWARE=[], USE_TZ=True)
from django.core.asgi import get_asgi_application
from django.http import HttpResponse, JsonResponse
from django.urls import re_path

PARTNER = os.getenv('PARTNER_URL', 'http://mock:8080')
LIMIT = int(os.getenv('PARTNER_LIMIT', '256'))
DATA = b'a' * (1024 * 1024)
from concurrent.futures import ThreadPoolExecutor

THREADS = int(os.getenv('THREADS', '4'))
PYCPU_ITERS = int(os.getenv('PYCPU_ITERS', '400000'))
def burn():
    # Pure-Python arithmetic: holds the GIL for its whole duration (unlike hashlib, which releases it on large buffers).
    x = 0
    for i in range(PYCPU_ITERS): x = (x * 31 + i) & 0xFFFFFFFF
    return {'ok': True, 'iters': PYCPU_ITERS}
def hashing():
    for _ in range(100): digest = hashlib.sha256(DATA).hexdigest()
    return {'digest': digest}
GIL = lambda: getattr(sys, '_is_gil_enabled', lambda: True)()
POOL = ThreadPoolExecutor(THREADS)
_client = None

def client():
    # Created lazily on first request so it belongs to this worker process's running event loop.
    global _client
    if _client is None:
        _client = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=3), connector=aiohttp.TCPConnector(limit=LIMIT))
    return _client

async def fetch(path):
    async with client().get(PARTNER + path) as r:
        r.raise_for_status()
        return await r.json()

async def handle(request, path):
    try:
        if path == 'health': result = {'ok': True}
        elif path == 'meta':
            result = {'runtime': 'python', 'framework': 'django', 'concurrency': 'asyncio', 'workers': int(os.getenv('WORKERS', '1')), 'pid': os.getpid(),
                      'version': sys.version.split()[0], 'django': django.get_version(), 'partner_limit': LIMIT,
                      'gil_enabled': GIL(), 'threads': THREADS}
        elif path == 'partner': result = await fetch('/delay')
        elif path == 'park': result = await fetch('/park')
        elif path == 'fanout': result = {'total': sum(x['value'] for x in await asyncio.gather(*(fetch('/delay') for _ in range(3))))}
        elif path == 'payload':
            x = await fetch('/data'); result = {'id': x['id'], 'bytes': len(x['blob'])}
        elif path == 'cpu':
            result = await asyncio.get_running_loop().run_in_executor(POOL, hashing)
        elif path == 'pycpu': result = await asyncio.get_running_loop().run_in_executor(POOL, burn)
        else: return HttpResponse(status=404)
        return JsonResponse(result)
    except (asyncio.TimeoutError, OSError, aiohttp.ClientError):
        return JsonResponse({'error': 'partner_failure'}, status=502)

urlpatterns = [re_path(r'^(?P<path>.*)$', handle)]
application = get_asgi_application()
