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

def membuf():
    n = 16 * 1024 * 1024
    b = bytearray([0xAB]) * n
    for i in range(0, n, 4096): b[i] = (i >> 12) & 0xFF
    return {'bytes': n, 'sum': sum(b[::4096])}
def memobj():
    n = 50000
    recs = [{'id': i, 'name': 'guest-%06d' % i, 'tags': [i + k for k in range(8)]} for i in range(n)]
    return {'records': n, 'sum': sum(len(r['name']) + sum(r['tags']) for r in recs)}
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
                      'gil_enabled': getattr(sys, '_is_gil_enabled', lambda: True)()}
        elif path == 'partner': result = await fetch('/delay')
        elif path == 'park': result = await fetch('/park')
        elif path == 'fanout': result = {'total': sum(x['value'] for x in await asyncio.gather(*(fetch('/delay') for _ in range(3))))}
        elif path == 'payload':
            x = await fetch('/data'); result = {'id': x['id'], 'bytes': len(x['blob'])}
        elif path == 'cpu':
            for _ in range(100): digest = hashlib.sha256(DATA).hexdigest()
            result = {'digest': digest}
        elif path == 'membuf': result = membuf()
        elif path == 'memobj': result = memobj()
        else: return HttpResponse(status=404)
        return JsonResponse(result)
    except (asyncio.TimeoutError, OSError, aiohttp.ClientError):
        return JsonResponse({'error': 'partner_failure'}, status=502)

urlpatterns = [re_path(r'^(?P<path>.*)$', handle)]
application = get_asgi_application()
