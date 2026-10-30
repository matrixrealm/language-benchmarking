import asyncio, hashlib, os, sys
from contextlib import asynccontextmanager
import aiohttp, fastapi, uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse
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

@asynccontextmanager
async def lifespan(app):
    # One client per worker process, created on that process's event loop.
    app.state.client = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=3), connector=aiohttp.TCPConnector(limit=LIMIT))
    yield
    await app.state.client.close()

app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

async def fetch(path):
    async with app.state.client.get(PARTNER + path) as r:
        r.raise_for_status()
        return await r.json()

def partner_failure(fn):
    async def wrapper():
        try: return await fn()
        except (asyncio.TimeoutError, OSError, aiohttp.ClientError): return JSONResponse({'error': 'partner_failure'}, status_code=502)
    wrapper.__name__ = fn.__name__
    return wrapper

@app.get('/health')
async def health(): return {'ok': True}

@app.get('/meta')
async def meta():
    loop = type(asyncio.get_running_loop()).__module__
    return {'runtime': 'python', 'framework': 'fastapi', 'concurrency': 'asyncio', 'workers': int(os.getenv('WORKERS', '1')), 'pid': os.getpid(),
            'version': sys.version.split()[0], 'fastapi': fastapi.__version__, 'uvicorn': uvicorn.__version__, 'loop': loop, 'partner_limit': LIMIT,
            'gil_enabled': getattr(sys, '_is_gil_enabled', lambda: True)()}

@app.get('/partner')
@partner_failure
async def partner(): return await fetch('/delay')

@app.get('/park')
@partner_failure
async def park(): return await fetch('/park')

@app.get('/fanout')
@partner_failure
async def fanout(): return {'total': sum(x['value'] for x in await asyncio.gather(*(fetch('/delay') for _ in range(3))))}

@app.get('/payload')
@partner_failure
async def payload():
    x = await fetch('/data'); return {'id': x['id'], 'bytes': len(x['blob'])}

@app.get('/cpu')
async def cpu():
    # Deliberately synchronous like the baseline: it blocks this worker's event loop.
    for _ in range(100): digest = hashlib.sha256(DATA).hexdigest()
    return {'digest': digest}

@app.get('/membuf')
async def _membuf(): return membuf()  # inline on the event loop, like /cpu

@app.get('/memobj')
async def _memobj(): return memobj()
