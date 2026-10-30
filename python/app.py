import asyncio, hashlib, json, os, sys
from aiohttp import web, ClientSession, ClientTimeout, TCPConnector
PARTNER = os.getenv('PARTNER_URL', 'http://mock:8080')
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
        elif path == '/meta': result = {'runtime': 'python', 'concurrency': 'asyncio', 'workers': 1, 'version': sys.version.split()[0], 'gil_enabled': getattr(sys, '_is_gil_enabled', lambda: True)()}
        elif path == '/partner': result = await fetch('/delay')
        elif path == '/park': result = await fetch('/park')
        elif path == '/fanout': result = {'total': sum(x['value'] for x in await asyncio.gather(*(fetch('/delay') for _ in range(3))))}
        elif path == '/payload':
            x = await fetch('/data'); result = {'id': x['id'], 'bytes': len(x['blob'])}
        elif path == '/cpu':
            for _ in range(100): digest = hashlib.sha256(DATA).hexdigest()
            result = {'digest': digest}
        elif path == '/membuf': result = membuf()
        elif path == '/memobj': result = memobj()
        else: raise web.HTTPNotFound()
        return web.json_response(result)
    except (asyncio.TimeoutError, OSError) as e:
        return web.json_response({'error': type(e).__name__}, status=502)
app = web.Application()
app.cleanup_ctx.append(lifecycle)
app.router.add_get('/{path:.*}', handle)
if __name__ == '__main__': web.run_app(app, port=8080, access_log=None, print=None)
