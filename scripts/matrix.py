"""Long-running sequential matrix; candidates never run concurrently.

Passes (see TEST_PLAN.md 'Execution stages'):
  full    every ladder rate, --repeats repeats (default 3)
  coarse  3 rates per endpoint, 1 repeat: finds roughly where each candidate stops meeting the SLO
  dense   ladder rates around that knee only, --repeats repeats (default 3)
Groups (--group): core (java, go, python), python (aiohttp, fastapi, django, 1 and 2 workers),
threads (java virtual, java platform, go on park/fanout). --candidates/--endpoints/--rates override.
Every run is resumable: a cell whose valid report already exists is skipped, a failed cell is
logged and the matrix continues. Cells whose peak load would exceed the calibrated mock/generator
capacity are skipped and logged rather than run. --fast shortens idle/warmup/measured/recovery."""
import argparse, json, pathlib, subprocess, sys
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from calibration import ROOT, CALIBRATION, capacity_problem, load_calibration
from candidates import CANDIDATES, GROUPS

RESULTS = ROOT / 'results'
LADDER = {'cpu': [1, 2, 5, 10, 20], 'pycpu': [10, 20, 30, 40, 50], 'membuf': [5, 10, 20, 40, 80], 'memobj': [5, 10, 20, 40, 80], 'park': [250, 500, 1000, 2000], 'default': [50, 100, 250, 500, 1000, 1500]}
COARSE = {'cpu': [2, 5, 10], 'pycpu': [10, 30, 50], 'membuf': [10, 20, 40], 'memobj': [10, 20, 40], 'park': [250, 1000, 2000], 'default': [100, 500, 1000]}
FAST = ['--idle', '30', '--warmup', '2m', '--duration', '3m', '--recovery', '60']

def ladder(table, endpoint): return table.get(endpoint, table['default'])

def orders(candidates):
    """Rotations of the candidate list, then their reverses: each candidate gets every position equally often."""
    n = len(candidates); rot = [candidates[i:] + candidates[:i] for i in range(n)]
    return rot + [list(reversed(r)) for r in rot]

def reports():
    for report in RESULTS.glob('*/report.json'):
        try: yield json.loads(report.read_text())
        except ValueError: continue

def completed_keys(tag):
    return {r['cell_key'] for r in reports() if r.get('cell_key') and r.get('valid') and r.get('tag', '') == tag}

def knee_rates(endpoint, candidates):
    """Ladder rates between 'every candidate passes' and 'some candidate fails', from existing results."""
    passed = {l: [] for l in candidates}; failed = []
    for r in reports():
        if r.get('endpoint') != endpoint or r.get('profile') != 'steady' or not r.get('valid') or r.get('control') or r.get('language') not in passed: continue
        (passed[r['language']] if r['slo_passed'] else failed).append(r['rate'])
    if not any(passed.values()) and not failed: return None
    rungs = ladder(LADDER, endpoint)
    all_pass = min((max(p) if p else 0) for p in passed.values())
    lo = all_pass if all_pass else rungs[0]; hi = min(failed) if failed else rungs[-1]
    return [r for r in rungs if lo <= r <= hi] or [rungs[0]]

def run_cell(cmd, key, retries, log):
    for attempt in range(retries + 1):
        if subprocess.run(cmd).returncode == 0: return True
        log.write(f'{key} attempt {attempt + 1} failed\n'); log.flush()
    return False

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--pass', dest='which', choices=['full', 'coarse', 'dense'], default='full')
    p.add_argument('--group', choices=sorted(GROUPS), default='core')
    p.add_argument('--candidates', default=''); p.add_argument('--endpoints', default='')
    p.add_argument('--rates', default='', help='explicit comma list of rates, overrides the ladder')
    p.add_argument('--repeats', type=int, default=None); p.add_argument('--retries', type=int, default=1)
    p.add_argument('--fast', action='store_true', help='idle 30s, warmup 2m, measured 3m, recovery 60s (about 7 min/run)')
    p.add_argument('--tag', default='', help='label stored with each run; resume only skips cells with the same tag')
    p.add_argument('--recalibrate', action='store_true'); p.add_argument('--force-rate', action='store_true')
    p.add_argument('--dry-run', action='store_true')
    p.add_argument('--cpuset', default='', help='pin each candidate to these host CPUs, e.g. 0,1')
    p.add_argument('--helper-cpuset', default='', help='pin mock, k6 and sampler to these other CPUs, e.g. 2,3 (also used by auto-calibration)')
    a = p.parse_args()
    group_candidates, group_endpoints = GROUPS[a.group]
    candidates = a.candidates.split(',') if a.candidates else group_candidates
    endpoints = a.endpoints.split(',') if a.endpoints else group_endpoints
    for c in candidates:
        if c not in CANDIDATES: p.error(f'unknown candidate {c}')
    repeats = a.repeats or (1 if a.which == 'coarse' else 3)
    if not a.dry_run and (a.recalibrate or not CALIBRATION.exists()):
        subprocess.run([sys.executable, str(ROOT / 'scripts' / 'calibrate.py'), *(['--helper-cpuset', a.helper_cpuset] if a.helper_cpuset else [])], check=True)
    calibration = load_calibration(); done = completed_keys(a.tag); runner = ROOT / 'scripts' / 'run.py'
    ordering = orders(candidates)
    RESULTS.mkdir(exist_ok=True); failures = skipped = ran = 0
    with (RESULTS / 'matrix_failures.log').open('a') as flog, (RESULTS / 'matrix_skipped.log').open('a') as slog:
        for repeat in range(repeats):
            order = ordering[repeat % len(ordering)]
            for endpoint in endpoints:
                if a.rates: rates = [int(x) for x in a.rates.split(',')]
                elif a.which == 'dense':
                    rates = knee_rates(endpoint, candidates)
                    if rates is None: print(f'dense: no results for {endpoint}, skipping'); continue
                else: rates = ladder(COARSE if a.which == 'coarse' else LADDER, endpoint)
                for rate in rates:
                    problem = None if (a.force_rate or (a.dry_run and calibration is None)) else capacity_problem(endpoint, 'steady', rate, calibration)
                    for candidate in order:
                        key = f'{a.tag}|{candidate}|{endpoint}|steady|{rate}|r{repeat}'
                        if problem: slog.write(f'{key}: {problem}\n'); skipped += 1; continue
                        if key in done: continue
                        cmd = [sys.executable, str(runner), '--language', candidate, '--endpoint', endpoint, '--rate', str(rate), '--cell-key', key, '--tag', a.tag]
                        if a.cpuset: cmd += ['--cpuset', a.cpuset]
                        if a.helper_cpuset: cmd += ['--helper-cpuset', a.helper_cpuset]
                        if a.fast: cmd += FAST
                        if a.force_rate: cmd.append('--force-rate')
                        if a.dry_run: print(key); continue
                        if run_cell(cmd, key, a.retries, flog): ran += 1
                        else: failures += 1
    print(f'ran={ran} skipped_for_capacity={skipped} failed={failures} (see results/matrix_failures.log, matrix_skipped.log)')
    sys.exit(1 if failures else 0)

if __name__ == '__main__': main()
