import asyncio, hashlib, json, os, sys
from aiohttp import web, ClientSession, ClientTimeout, TCPConnector
PARTNER = os.getenv('PARTNER_URL', 'http://mock:8080')
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
async def lifecycle(app):
    app['client'] = ClientSession(timeout=ClientTimeout(total=3), connector=TCPConnector(limit=int(os.getenv('PARTNER_LIMIT', '256'))))
    yield
    await app['client'].close()
async def handle(request):
    path = request.path
    async def fetch(path):
        async with request.app['client'].get(PARTNER + path) as r:
            r.raise_for_status()
            return await r.json()
    try:
        if path == '/health': result = {'ok': True}
        elif path == '/meta': result = {'runtime': 'python', 'framework': 'aiohttp', 'concurrency': 'asyncio+threads', 'workers': 1, 'threads': THREADS, 'pid': os.getpid(), 'version': sys.version.split()[0], 'gil_enabled': GIL()}
        elif path == '/partner': result = await fetch('/delay')
        elif path == '/park': result = await fetch('/park')
        elif path == '/fanout': result = {'total': sum(x['value'] for x in await asyncio.gather(*(fetch('/delay') for _ in range(3))))}
        elif path == '/payload':
            x = await fetch('/data'); result = {'id': x['id'], 'bytes': len(x['blob'])}
        elif path == '/cpu':
            result = await asyncio.get_running_loop().run_in_executor(POOL, hashing)
        elif path == '/pycpu': result = await asyncio.get_running_loop().run_in_executor(POOL, burn)
        else: raise web.HTTPNotFound()
        return web.json_response(result)
    except (asyncio.TimeoutError, OSError) as e:
        return web.json_response({'error': type(e).__name__}, status=502)
app = web.Application()
app.cleanup_ctx.append(lifecycle)
app.router.add_get('/{path:.*}', handle)
if __name__ == '__main__': web.run_app(app, port=8080, access_log=None, print=None)
