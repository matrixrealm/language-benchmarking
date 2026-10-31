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
    # optional E and F
    'optional': [['--candidates', 'go,java,python,fastapi,django', '--endpoints', 'memobj', '--rates', '10,20'],
                 ['--candidates', 'aiohttp-gil,aiohttp-nogil', '--endpoints', 'cpu', '--rates', '30,40']],
}
BASE = ['--pass', 'full', '--group', 'gil', '--repeats', '3', '--fast', '--tag', TAG, '--cpuset', '0,1', '--helper-cpuset', '2,3']

def main():
    if len(sys.argv) < 2 or sys.argv[1] not in BATCHES: sys.exit(f'usage: ci_batch.py {{{"|".join(BATCHES)}}} [matrix.py args]')
    status = 0
    for args in BATCHES[sys.argv[1]]:
        status |= subprocess.run([sys.executable, str(ROOT / 'scripts' / 'matrix.py'), *BASE, *args, *sys.argv[2:]]).returncode
    sys.exit(status)

if __name__ == '__main__': main()
