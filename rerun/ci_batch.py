"""The rerun batches from RERUN_PLAN.md, one per CI job. Each batch keeps a whole comparison on one VM.

  python rerun/ci_batch.py aiohttp --dry-run
Candidate pinned to host CPUs 0,1 and mock/k6/sampler to 2,3 (a 4 vCPU runner), 3 repeats, --fast timings.
Extra arguments are passed to matrix.py."""
import pathlib, subprocess, sys
ROOT = pathlib.Path(__file__).resolve().parents[1]

TAG = 'cloud1'
GIL_RATES = '10,15,20'
BATCHES = {
    # claims A+B: GIL ceiling with the forced-GIL control. aiohttp-nogil is also pushed to 30 and 40.
    'aiohttp': [['--candidates', 'aiohttp-gil,aiohttp-t-gilon', '--endpoints', 'pycpu', '--rates', GIL_RATES],
                ['--candidates', 'aiohttp-nogil', '--endpoints', 'pycpu', '--rates', '10,15,20,30,40']],
    'fastapi': [['--candidates', 'fastapi-gil,fastapi-nogil,fastapi-t-gilon', '--endpoints', 'pycpu', '--rates', GIL_RATES]],
    'django':  [['--candidates', 'django-gil,django-nogil,django-t-gilon', '--endpoints', 'pycpu', '--rates', GIL_RATES]],
    # claim A follow-up: cloud1 only ran the GIL builds to 20 RPS, so push them to the rates where aiohttp-nogil was tested
    'gil-ceiling': [['--candidates', 'aiohttp-gil,aiohttp-t-gilon', '--endpoints', 'pycpu', '--rates', '30,40']],
    # claim C (waiting calls) and D (memory cost at 1000 RPS)
    'threads-cost': [['--candidates', 'java,java-platform,go', '--endpoints', 'park', '--rates', '250,1000'],
                     ['--candidates', 'go,java,python,fastapi', '--endpoints', 'partner', '--rates', '1000']],
    # claim G (concurrency = rate x latency): the five-way comparison Go / Java virtual / Java classic / FastAPI / Django.
    # Go, java and java-platform on park, and go/java on partner 1000, already exist from threads-cost; this fills the rest.
    'concurrency': [['--candidates', 'fastapi-gil,django-gil', '--endpoints', 'park', '--rates', '250,1000'],
                    ['--candidates', 'fastapi-gil,django-gil,java-platform', '--endpoints', 'partner', '--rates', '1000'],
                    ['--candidates', 'django-gil', '--endpoints', 'partner', '--rates', '300'],
                    ['--candidates', 'java-platform-2000', '--endpoints', 'park', '--rates', '250,1000']],
    # rerun2 (RERUN2_PLAN.md): uvloop + 4-thread pool vs plain asyncio vs uvloop inline. Q1 pycpu ceiling, with the 30/40 baseline on the same VM.
    'uv-fastapi': [['--candidates', 'fastapi-gil-uv', '--endpoints', 'pycpu', '--rates', '10,15,20,30,40'],
                   ['--candidates', 'fastapi-gil', '--endpoints', 'pycpu', '--rates', '30,40']],
    'uv-django':  [['--candidates', 'django-gil-uv', '--endpoints', 'pycpu', '--rates', '10,15,20,30,40'],
                   ['--candidates', 'django-gil', '--endpoints', 'pycpu', '--rates', '30,40']],
    # Q2: hashing, pool vs inline, both with uvloop
    'uv-cpu': [['--candidates', 'fastapi,django,fastapi-gil-uv,django-gil-uv', '--endpoints', 'cpu', '--rates', '30,40,50']],
    # Q3: waiting calls
    'uv-concurrency': [['--candidates', 'fastapi-gil-uv,django-gil-uv', '--endpoints', 'partner', '--rates', '1000'],
                       ['--candidates', 'fastapi-gil-uv,django-gil-uv', '--endpoints', 'park', '--rates', '250,1000']],
    # rerun2 follow-ups (RERUN2_RESULTS.md): FastAPI ceiling was not reached at 40 RPS; cpu rates 30-50 were all above capacity.
    # Both FastAPI builds in one job so they share a runner CPU model.
    'uv-fastapi-high': [['--candidates', 'fastapi-gil-uv,fastapi-gil', '--endpoints', 'pycpu', '--rates', '50,60,80']],
    'uv-cpu-low-fastapi': [['--candidates', 'fastapi,fastapi-gil-uv', '--endpoints', 'cpu', '--rates', '10,15,20,25']],
    'uv-cpu-low-django': [['--candidates', 'django,django-gil-uv', '--endpoints', 'cpu', '--rates', '10,15,20,25']],
    # rerun3: FastAPI ceiling on ONE runner CPU (both builds, rates from passing to failing in one job)
    'fastapi-bracket': [['--candidates', 'fastapi-gil-uv,fastapi-gil', '--endpoints', 'pycpu', '--rates', '30,40,50,60']],
    # rerun3: 10 repeats of the headline cells so that intervals can be reported (REPEATS below)
    'rep-park-virtual': [['--candidates', 'go,java', '--endpoints', 'park', '--rates', '250,1000']],
    'rep-park-platform': [['--candidates', 'java-platform,java-platform-2000', '--endpoints', 'park', '--rates', '250,1000']],
    'rep-memory': [['--candidates', 'go,java,python,fastapi', '--endpoints', 'partner', '--rates', '1000']],
    # rerun3: does removing Django's per-request signal receivers (one thread per request) fix the waiting-call failures?
    'django-signals': [['--candidates', 'django-gil,django-gil-nosig', '--endpoints', 'park', '--rates', '250,1000'],
                       ['--candidates', 'django-gil,django-gil-nosig', '--endpoints', 'partner', '--rates', '300,1000']],
    # optional pool-size sweep (THREADS is passed through matrix.py --env if supported; see RERUN2_PLAN.md section 4)
    # optional E and F
    'optional': [['--candidates', 'go,java,python,fastapi,django', '--endpoints', 'memobj', '--rates', '10,20'],
                 ['--candidates', 'aiohttp-gil,aiohttp-nogil', '--endpoints', 'cpu', '--rates', '30,40']],
}
REPEATS = {'rep-park-virtual': '10', 'rep-park-platform': '10', 'rep-memory': '10'}  # default 3
BASE = ['--pass', 'full', '--group', 'gil', '--repeats', '3', '--fast', '--tag', TAG, '--cpuset', '0,1', '--helper-cpuset', '2,3']

def main():
    if len(sys.argv) < 2 or sys.argv[1] not in BATCHES: sys.exit(f'usage: ci_batch.py {{{"|".join(BATCHES)}}} [matrix.py args]')
    status = 0
    for args in BATCHES[sys.argv[1]]:
        status |= subprocess.run([sys.executable, str(ROOT / 'scripts' / 'matrix.py'), *BASE, *(['--repeats', REPEATS[sys.argv[1]]] if sys.argv[1] in REPEATS else []), *args, *sys.argv[2:]]).returncode
    sys.exit(status)

if __name__ == '__main__': main()
