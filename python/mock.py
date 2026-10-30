import asyncio, json, multiprocessing, os, socket
from aiohttp import web
# Bodies are serialised once so the mock spends its CPU on I/O, not json.dumps.
DELAY = json.dumps({'value': 42}).encode()
DATA = json.dumps({'id': 7, 'blob': 'x' * 32768}).encode()
HEALTH = json.dumps({'ok': True}).encode()
def reply(body): return web.Response(body=body, content_type='application/json')
async def delay(request):
    await asyncio.sleep(.1)
    return reply(DELAY)
# /park holds a connection for PARK_MS so a candidate can be driven to thousands of in-flight calls.
PARK_SECONDS = int(os.getenv('PARK_MS', '1000')) / 1000
async def park(request):
    await asyncio.sleep(PARK_SECONDS)
    return reply(DELAY)
async def data(request): return reply(DATA)
async def health(request): return reply(HEALTH)
def serve():
    app = web.Application()
    app.router.add_get('/delay', delay)
    app.router.add_get('/park', park)
    app.router.add_get('/data', data)
    app.router.add_get('/health', health)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    if hasattr(socket, 'SO_REUSEPORT'): sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    sock.bind(('0.0.0.0', 8080))
    web.run_app(app, sock=sock, access_log=None, print=None)
if __name__ == '__main__':
    # MOCK_WORKERS processes share the port via SO_REUSEPORT (Linux). 1 keeps the old single-loop mock.
    workers = int(os.getenv('MOCK_WORKERS', '2'))
    procs = [multiprocessing.Process(target=serve) for _ in range(workers - 1)]
    for p in procs: p.start()
    try: serve()
    finally:
        for p in procs: p.terminate()
