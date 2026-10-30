import asyncio, hashlib, os, sys
from contextlib import asynccontextmanager
import aiohttp, fastapi, uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse
PARTNER = os.getenv('PARTNER_URL', 'http://mock:8080')
LIMIT = int(os.getenv('PARTNER_LIMIT', '256'))
DATA = b'a' * (1024 * 1024)

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

@asynccontextmanager
async def lifespan(app):
    # One client per worker process, created on that process's event loop.
    import anyio.to_thread
    anyio.to_thread.current_default_thread_limiter().total_tokens = THREADS
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
            'gil_enabled': GIL(), 'threads': THREADS}

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
def cpu(): return hashing()  # plain def: FastAPI runs it in its thread pool

@app.get('/pycpu')
def pycpu(): return burn()
