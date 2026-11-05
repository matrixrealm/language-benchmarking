"""Write LaTeX tables and a numbers.json for the paper from the raw runs in rerun/reports/data.
  python paper/make_tables.py [--data rerun/reports/data]
Only runs with valid=True are used. A cell passes only if every valid repeat passes ("k/n" is shown).
CPU cores = rate x median CPU-seconds per successful request (an estimate, only meaningful for passing cells)."""
import argparse, glob, json, pathlib, statistics as st
ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = pathlib.Path(__file__).parent / 'tables'
BASE = ('aiohttp', 'fastapi', 'django', 'gil-ceiling', 'threads-cost')

NAME = {'go': 'Go', 'java': 'Java (virtual threads)', 'java-platform': 'Java (200 platform threads)', 'python': 'Python aiohttp',
        'fastapi': 'FastAPI (uvloop, inline)', 'django': 'Django (uvloop, inline)',
        'aiohttp-gil': 'aiohttp, GIL', 'aiohttp-t-gilon': 'aiohttp, 3.14t with GIL forced on', 'aiohttp-nogil': 'aiohttp, 3.14t GIL off',
        'fastapi-gil': 'FastAPI, GIL, asyncio, 4 threads', 'fastapi-gil-uv': 'FastAPI, GIL, uvloop, 4 threads',
        'django-gil': 'Django, GIL, asyncio, 4 threads', 'django-gil-uv': 'Django, GIL, uvloop, 4 threads',
        'java-platform-2000': 'Java (2000 platform threads)'}
INLINE = {'fastapi': 'FastAPI, inline on the event loop', 'fastapi-gil-uv': 'FastAPI, 4-thread pool',
          'django': 'Django, inline on the event loop', 'django-gil-uv': 'Django, 4-thread pool'}

def load(data, batches):
    cells, hosts = {}, {}
    for f in glob.glob(str(pathlib.Path(data) / '*' / '*' / 'report.json')):
        p = pathlib.Path(f); batch = p.parent.parent.name
        if batch not in batches: continue
        r = json.loads(p.read_text())
        if not r.get('valid'): cells.setdefault((r['language'], r['endpoint'], r['rate']), {'runs': [], 'invalid': 0})['invalid'] += 1; continue
        c = cells.setdefault((r['language'], r['endpoint'], r['rate']), {'runs': [], 'invalid': 0}); c['runs'].append(r)
        m = p.parent / 'metadata.json'
        if m.exists(): hosts.setdefault(batch, set()).add(json.loads(m.read_text()).get('host', {}).get('cpu_name', '?'))
    return cells, hosts

def stat(c):
    R = c['runs']
    if not R: return None
    p99 = [r['latency_ms']['p(99)'] for r in R]
    cpu = [r['cpu_ms_per_success'] for r in R if r.get('cpu_ms_per_success')]
    mem = [r['container_memory_median_mib'] for r in R if r.get('container_memory_median_mib')]
    return {'n': len(R), 'k': sum(bool(r['slo_passed']) for r in R), 'p99': st.median(p99), 'p99lo': min(p99), 'p99hi': max(p99),
            'cpu': st.median(cpu) if cpu else None, 'mem': st.median(mem) if mem else None,
            'memlo': min(mem) if mem else None, 'memhi': max(mem) if mem else None,
            'fail': st.median(r['failure_rate'] for r in R), 'invalid': c['invalid']}

def cp_interval(k, n, alpha=0.05):
    # Clopper-Pearson exact interval for k successes in n trials, by bisection on the binomial tail
    from math import comb
    def tail_ge(p, k): return sum(comb(n, i) * p**i * (1 - p)**(n - i) for i in range(k, n + 1))
    def bisect(f, lo=0.0, hi=1.0):
        for _ in range(60):
            mid = (lo + hi) / 2
            if f(mid): hi = mid
            else: lo = mid
        return (lo + hi) / 2
    lo = 0.0 if k == 0 else bisect(lambda p: tail_ge(p, k) >= alpha / 2)
    hi = 1.0 if k == n else bisect(lambda p: 1 - tail_ge(p, k + 1) <= alpha / 2)
    return lo, hi

def cell_txt(s, rate):
    if not s: return '--'
    if s['k'] == 0 and (s['p99'] >= 5000 or s['p99'] <= 0 or s['fail'] >= 0.99): return f"{s['k']}/{s['n']} (no replies)"
    t = f"{s['k']}/{s['n']}, {s['p99']:.0f}\\,ms"
    if s['cpu'] and s['k']: t += f", {rate * s['cpu'] / 1000:.2f}\\,c"
    return t

def table(name, caption, label, head, rows):
    cols = 'l' + 'c' * (len(head) - 1)
    body = '\n'.join(' & '.join(r) + r' \\' for r in rows)
    (OUT / f'{name}.tex').write_text(
        f"\\begin{{table}}[t]\n\\caption{{{caption}}}\n\\label{{{label}}}\n\\centering\\small\n\\begin{{tabular}}{{{cols}}}\n\\toprule\n"
        + ' & '.join(head) + " \\\\\n\\midrule\n" + body + "\n\\bottomrule\n\\end{tabular}\n\\end{table}\n", encoding='utf-8')

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--data', default=str(ROOT / 'rerun' / 'reports' / 'data'))
    ap.add_argument('--data2', default=str(ROOT / 'rerun2' / 'reports' / 'data'))
    ap.add_argument('--data3', default=str(ROOT / 'rerun3' / 'reports' / 'data')); a = ap.parse_args()
    OUT.mkdir(exist_ok=True)
    cells, hosts = load(a.data, BASE)
    S = {k: stat(v) for k, v in cells.items()}
    nums = {'hosts': {k: sorted(v) for k, v in hosts.items()}, 'runs_base': sum(len(c['runs']) for c in cells.values()),
            'invalid_base': sum(c['invalid'] for c in cells.values())}
    g = lambda l, e, r: S.get((l, e, r))
    # waiting calls
    rows = [[NAME[l]] + [cell_txt(g(l, 'park', r), r) for r in (250, 1000)] for l in ('go', 'java', 'java-platform')]
    table('park', 'Waiting calls (\\texttt{/park}, each request held about 1\\,s by the partner). Cells: repeats passing / valid repeats, median p99, CPU cores used (passing cells). SLO: p99 $\\le$ 1250\\,ms.',
          'tab:park', ['Candidate', '250 in flight', '1000 in flight'], rows)
    # memory at 1000 RPS
    rows = []
    for l in ('go', 'python', 'fastapi', 'java'):
        s = g(l, 'partner', 1000)
        if s: rows.append([NAME[l], f"{s['k']}/{s['n']}", f"{s['p99']:.0f}", f"{s['mem']:.0f} [{s['memlo']:.0f}--{s['memhi']:.0f}]", f"{s['cpu']:.2f}"])
    table('memory', 'One partner call per request at 1000\\,RPS in a 512\\,MiB container. Memory is the median over the measured phase, shown as median [min--max] across repeats.',
          'tab:memory', ['Candidate', 'Pass', 'p99 (ms)', 'Memory (MiB)', 'CPU (ms/req)'], rows)
    # GIL ceiling
    rates = (10, 15, 20, 30, 40)
    rows = [[NAME[l]] + [cell_txt(g(l, 'pycpu', r), r) for r in rates] for l in ('aiohttp-gil', 'aiohttp-t-gilon', 'aiohttp-nogil')]
    table('gil', 'Pure-Python CPU work (\\texttt{/pycpu}), one event loop plus a 4-thread pool. Cells as in Table~\\ref{tab:park}; SLO p99 $\\le$ 2000\\,ms.',
          'tab:gil', ['Candidate'] + [f'{r} RPS' for r in rates], rows)
    # frameworks, base cloud1 data
    rows = [[NAME[l]] + [cell_txt(g(l, 'pycpu', r), r) for r in (10, 15, 20)] for l in ('fastapi-gil', 'django-gil')]
    table('frameworks', 'FastAPI and Django on \\texttt{/pycpu} with plain asyncio and a 4-thread pool (GIL build).', 'tab:frameworks',
          ['Candidate', '10 RPS', '15 RPS', '20 RPS'], rows)
    # uv rerun
    uc, uh = load(a.data, tuple(b for b in map(lambda p: p.name, pathlib.Path(a.data).iterdir()) if b.startswith('uv-') or b == 'concurrency'))
    US = {k: stat(v) for k, v in uc.items()}
    nums['hosts_uv'] = {k: sorted(v) for k, v in uh.items()}
    nums['runs_uv'] = sum(len(c['runs']) for c in uc.values())
    ug = lambda l, e, r: US.get((l, e, r))
    r2 = (10, 15, 20, 30, 40, 50, 60, 80)
    present = [r for r in r2 if any(ug(l, 'pycpu', r) for l in ('fastapi-gil', 'fastapi-gil-uv', 'django-gil', 'django-gil-uv'))]
    rows = [[NAME[l]] + [cell_txt(ug(l, 'pycpu', r), r) for r in present] for l in ('fastapi-gil', 'fastapi-gil-uv', 'django-gil', 'django-gil-uv') if any(ug(l, 'pycpu', r) for r in present)]
    table('uvloop', 'Effect of uvloop on \\texttt{/pycpu} (GIL build, 4-thread pool). FastAPI and Django jobs ran on different runner CPUs, see Section~\\ref{sec:threats}.',
          'tab:uvloop', ['Candidate'] + [f'{r}' for r in present], rows)
    # run 6 (rerun2/reports/data)
    d2 = pathlib.Path(a.data2)
    if d2.is_dir():
        c2, h2 = load(a.data2, tuple(p.name for p in d2.iterdir() if p.is_dir()))
        S2 = {k: stat(v) for k, v in c2.items()}
        nums['hosts_run6'] = {k: sorted(v) for k, v in h2.items()}
        nums['runs_run6'] = sum(len(c['runs']) + c['invalid'] for c in c2.values())
        nums['invalid_run6'] = sum(c['invalid'] for c in c2.values())
        g2 = lambda l, e, r: S2.get((l, e, r))
        rates = (10, 15, 20, 25)
        rows = [[INLINE[l]] + [cell_txt(g2(l, 'cpu', r), r) for r in rates] for l in ('fastapi', 'fastapi-gil-uv', 'django', 'django-gil-uv')]
        table('hashing', 'Hashing (\\texttt{/cpu}, releases the GIL), uvloop in all rows. The FastAPI rows ran on an AMD EPYC 9V74 runner and the Django rows on an EPYC 7763 runner, so compare within a framework only. SLO: p99 $\\le$ 2000\\,ms.',
              'tab:hashing', ['Candidate'] + [f'{r} RPS' for r in rates], rows)
        rates = (50, 60, 80)
        rows = [[NAME[l]] + [cell_txt(g2(l, 'pycpu', r), r) for r in rates] for l in ('fastapi-gil', 'fastapi-gil-uv')]
        table('pycpuhigh', 'FastAPI on \\texttt{/pycpu} above 40\\,RPS (AMD EPYC 7763 runner, about 36\\,ms of CPU per request).', 'tab:pycpuhigh',
              ['Candidate'] + [f'{r} RPS' for r in rates], rows)
        rows = [[NAME[l], cell_txt(g2(l, 'partner', 1000), 1000), cell_txt(g2(l, 'park', 250), 250), cell_txt(g2(l, 'park', 1000), 1000)]
                for l in ('fastapi-gil', 'java-platform', 'java-platform-2000') if any(g2(l, e, r) for e, r in (('partner', 1000), ('park', 250), ('park', 1000)))]
        # java-platform only has partner 1000 in this batch
        def mem(l, e, r):
            s_ = g2(l, e, r); return f"{s_['mem']:.0f}" if s_ and s_['mem'] else '--'
        rows = [r_ + [' / '.join(mem(l, e, rt) for e, rt in (('partner', 1000), ('park', 250), ('park', 1000)))] for r_, l in zip(rows, ('fastapi-gil', 'java-platform', 'java-platform-2000'))]
        table('waiting2', 'Waiting-call sensitivity runs on an Intel Xeon 6973P-C runner. Columns: \\texttt{/partner} at 1000\\,RPS, then \\texttt{/park} with 250 and 1000 in flight; last column is median memory in MiB for the three. A cell without replies means the candidate returned no usable answers.',
              'tab:waiting2', ['Candidate', 'partner 1000', 'park 250', 'park 1000', 'Memory (MiB)'], rows)
    # run 7 (rerun3/reports/data): FastAPI bracket on one CPU model and 10-repeat headline cells
    d3 = pathlib.Path(a.data3)
    if d3.is_dir():
        c3, h3 = load(a.data3, tuple(p.name for p in d3.iterdir() if p.is_dir()))
        S3 = {k: stat(v) for k, v in c3.items()}
        nums['hosts_run7'] = {k: sorted(v) for k, v in h3.items()}
        g3 = lambda l, e, r: S3.get((l, e, r))
        rates = (30, 40, 50, 60)
        rows = [[NAME[l]] + [cell_txt(g3(l, 'pycpu', r), r) for r in rates] for l in ('fastapi-gil', 'fastapi-gil-uv')]
        table('bracket', 'FastAPI on \\texttt{/pycpu} bracketed on a single runner CPU (Intel Xeon Platinum 8573C, both builds in one job). About 29\\,ms of CPU per request, so one core allows about 34 RPS.', 'tab:bracket',
              ['Candidate'] + [f'{r} RPS' for r in rates], rows)
        def ci_txt(s_):
            lo, hi = cp_interval(s_['k'], s_['n']); return f"{s_['k']}/{s_['n']} [{lo*100:.0f}--{hi*100:.0f}\\%]"
        def rng(v, lo, hi, d=0): return f"{v:.{d}f} [{lo:.{d}f}--{hi:.{d}f}]" if v is not None else '--'
        rows = []
        for l, e, r in (('go', 'park', 250), ('go', 'park', 1000), ('java', 'park', 250), ('java', 'park', 1000), ('java-platform', 'park', 250), ('java-platform', 'park', 1000),
                        ('java-platform-2000', 'park', 250), ('java-platform-2000', 'park', 1000)):
            s_ = g3(l, e, r)
            if not s_: continue
            rows.append([NAME[l], str(r), ci_txt(s_), ('--' if s_['k'] == 0 else rng(s_['p99'], s_['p99lo'], s_['p99hi'])), rng(s_['mem'], s_['memlo'], s_['memhi'])])
        table('repeats_park', 'Waiting calls with 10 repeats per cell (invalid repeats are excluded from n). Pass column: passing/valid repeats with the exact 95\\% Clopper--Pearson interval for the pass probability. p99 and memory are median [min--max].',
              'tab:repeatspark', ['Candidate', 'In flight', 'Pass [95\% CI]', 'p99 (ms)', 'Memory (MiB)'], rows)
        rows = []
        for l in ('go', 'python', 'fastapi', 'java'):
            s_ = g3(l, 'partner', 1000)
            if s_: rows.append([NAME[l], ci_txt(s_), rng(s_['mem'], s_['memlo'], s_['memhi']), rng(s_['p99'], s_['p99lo'], s_['p99hi'])])
        table('repeats_memory', 'One partner call per request at 1000\\,RPS, 10 repeats per candidate. Memory and p99 are median [min--max] over repeats.',
              'tab:repeatsmem', ['Candidate', 'Pass [95\% CI]', 'Memory (MiB)', 'p99 (ms)'], rows)
    (OUT / 'numbers.json').write_text(json.dumps(nums, indent=1, default=str), encoding='utf-8')
    for t in sorted(OUT.glob('*.tex')): print(t.name)
    print(json.dumps(nums, indent=1)[:900])

if __name__ == '__main__': main()
