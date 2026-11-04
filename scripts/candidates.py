"""Candidate registry: name -> image, build directory and container environment.
Several candidates can share one image and differ only in environment (workers, thread model)."""
import pathlib
ROOT = pathlib.Path(__file__).resolve().parents[1]

CANDIDATES = {
    'java':          {'dir': 'java',    'env': {}},                                                  # virtual threads (default)
    'java-platform': {'dir': 'java',    'env': {'JAVA_THREADS': 'platform', 'THREAD_POOL': '200'}},  # same code, classic threads
    'java-platform-2000': {'dir': 'java', 'env': {'JAVA_THREADS': 'platform', 'THREAD_POOL': '2000'}},  # sensitivity: classic threads, pool larger than the tested concurrency
    'go':            {'dir': 'go',      'env': {}},
    'python':        {'dir': 'python',  'env': {}},                                                  # aiohttp, 1 process
    'fastapi':       {'dir': 'fastapi', 'env': {'WORKERS': '1'}},
    'fastapi-2w':    {'dir': 'fastapi', 'env': {'WORKERS': '2'}},
    'django':        {'dir': 'django',  'env': {'WORKERS': '1'}},
    'django-2w':     {'dir': 'django',  'env': {'WORKERS': '2'}},
    # GIL vs free-threaded study: same code and asyncio stack, CPU work runs in a 4-thread pool. 'gil' = CPython 3.14 default build, 'nogil' = 3.14t with PYTHON_GIL=0.
    'aiohttp-gil':    {'dir': 'gil', 'image': 'lb-gil',   'env': {'APP': 'aiohttp'}},
    'aiohttp-nogil':  {'dir': 'gil', 'image': 'lb-nogil', 'env': {'APP': 'aiohttp', 'PYTHON_GIL': '0'}},
    'fastapi-gil':    {'dir': 'gil', 'image': 'lb-gil',   'env': {'APP': 'fastapi'}},
    'fastapi-nogil':  {'dir': 'gil', 'image': 'lb-nogil', 'env': {'APP': 'fastapi', 'PYTHON_GIL': '0'}},
    'aiohttp-t-gilon': {'dir': 'gil', 'image': 'lb-nogil', 'env': {'APP': 'aiohttp', 'PYTHON_GIL': '1'}},  # control: free-threaded build, GIL forced back on
    'fastapi-t-gilon': {'dir': 'gil', 'image': 'lb-nogil', 'env': {'APP': 'fastapi', 'PYTHON_GIL': '1'}},
    'django-t-gilon': {'dir': 'gil', 'image': 'lb-nogil', 'env': {'APP': 'django', 'PYTHON_GIL': '1'}},
    'django-gil':     {'dir': 'gil', 'image': 'lb-gil',   'env': {'APP': 'django'}},
    # rerun2: GIL build, uvloop + httptools, 4-thread pool (image lb-gil-uv from rerun2/Dockerfile.gil-uv)
    'fastapi-gil-uv': {'dir': 'gil', 'image': 'lb-gil-uv', 'env': {'APP': 'fastapi', 'THREADS': '4'}},
    'django-gil-uv':  {'dir': 'gil', 'image': 'lb-gil-uv', 'env': {'APP': 'django', 'THREADS': '4'}},
    'django-nogil':   {'dir': 'gil', 'image': 'lb-nogil', 'env': {'APP': 'django', 'PYTHON_GIL': '0'}},
    # rerun3: django-gil with Django's request_started/request_finished receivers removed (see RERUN2_RESULTS.md, thread per request)
    'django-gil-nosig': {'dir': 'gil', 'image': 'lb-gil', 'env': {'APP': 'django', 'DJANGO_NO_SIGNALS': '1'}},
}
# Named comparison sets for matrix.py --group: (candidates, default endpoints)
GROUPS = {
    'core':   (['java', 'go', 'python'], ['health', 'partner', 'fanout', 'payload', 'cpu']),
    'python': (['python', 'fastapi', 'fastapi-2w', 'django', 'django-2w'], ['partner', 'fanout', 'payload', 'cpu']),
    'gil':    (['aiohttp-gil', 'aiohttp-nogil', 'fastapi-gil', 'fastapi-nogil', 'django-gil', 'django-nogil'], ['pycpu', 'cpu', 'partner', 'payload']),
    'mem':    (['java', 'go', 'python', 'fastapi', 'django'], ['membuf', 'memobj']),
    'threads': (['java', 'java-platform', 'go'], ['park', 'fanout']),
    # concurrency = rate x latency: Go, Java virtual, Java classic (200 and 2000 threads), FastAPI and Django on the pinned GIL build
    'uv':     (['fastapi-gil-uv', 'django-gil-uv', 'fastapi-gil', 'django-gil', 'fastapi', 'django'], ['pycpu', 'cpu', 'partner', 'park']),
    'concurrency': (['go', 'java', 'java-platform', 'java-platform-2000', 'fastapi-gil', 'django-gil'], ['park', 'partner']),
}
PYTHON_FAMILY = {'python', 'fastapi', 'fastapi-2w', 'django', 'django-2w'} | {c for c in CANDIDATES if c.endswith(('-gil', '-nogil', '-gilon', '-gil-uv', '-nosig'))}

def image(name): return CANDIDATES[name].get('image', 'lb-' + CANDIDATES[name]['dir'])
def build_dirs(): return sorted({c['dir'] for c in CANDIDATES.values()})
def env_args(name, extra=None):
    out = []
    for k, v in {**CANDIDATES[name]['env'], **(extra or {})}.items(): out += ['-e', f'{k}={v}']
    return out
