"""Build rerun/reports/cloud1-report.html from the GitHub Actions artifacts of the cloud1 rerun.

usage: python rerun/reports/build_report.py [--data rerun/reports/data] [--out rerun/reports/cloud1-report.html]
data/<batch>/ holds the unzipped results-<batch> artifact (run directories with report.json and resources.csv).
Self-contained output: inline CSS and SVG, no network."""
import argparse, collections, csv, html, json, pathlib, statistics, sys, time

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from loop_note import note as loop_note, tag as loop_tag
REPO = 'https://github.com/matrixrealm/language-benchmarking/actions/runs/'
RUNS = [  # (run, batches, github run id, duration)
    ('#1', 'noise (go partner 250, aiohttp-nogil pycpu 10: 5 runs each)', None, '1h 7m'),
    ('#2', 'threads-cost (30 runs)', '41124061232', '3h 29m'),
    ('#3', 'aiohttp (33), fastapi (27), django (27)', '41145820619', '3h 48m, jobs in parallel'),
    ('#4', 'gil-ceiling: aiohttp-gil and aiohttp-t-gilon at 30 and 40 RPS (12)', '41172232217', '1h 30m'),
]
SLO = {'pycpu': None, 'park': 1250, 'partner': 250}
COLORS = {'aiohttp-gil': '#2563eb', 'aiohttp-t-gilon': '#9333ea', 'aiohttp-nogil': '#ea580c',
          'fastapi-gil': '#2563eb', 'fastapi-t-gilon': '#9333ea', 'fastapi-nogil': '#ea580c',
          'django-gil': '#2563eb', 'django-t-gilon': '#9333ea', 'django-nogil': '#ea580c',
          'go': '#0d9488', 'java': '#dc2626', 'java-platform': '#a16207', 'python': '#2563eb', 'fastapi': '#9333ea'}

CLOUD1 = ('aiohttp', 'fastapi', 'django', 'gil-ceiling', 'threads-cost')  # rerun2 batches (uv-*, concurrency) are reported separately

def load(data):
    runs = []
    for batch in sorted(p for p in data.iterdir() if p.is_dir() and p.name in CLOUD1):
        for d in sorted(batch.iterdir()):
            rp = d / 'report.json'
            if not rp.exists(): continue
            r = json.loads(rp.read_text()); r.pop('metrics', None)
            r['batch'] = batch.name; r['dir'] = d.name
            r['cores'] = cores_used(d)
            runs.append(r)
    return runs

def cores_used(d):
    """Average cores used by the candidate container in the measured phase, from resources.csv."""
    cp = d / 'resources.csv'
    if not cp.exists(): return None
    rows = [x for x in csv.DictReader(cp.open()) if x['phase'] == 'measured']
    if len(rows) < 2: return None
    dt = float(rows[-1]['time']) - float(rows[0]['time'])
    return (int(rows[-1]['usage_usec']) - int(rows[0]['usage_usec'])) / 1e6 / dt if dt else None

def link(label, rid): return '<a href="%s%s">%s</a>' % (REPO, rid, label) if rid else label

def p99(r): return (r.get('latency_ms') or {}).get('p(99)')

def cells(runs):
    out = collections.defaultdict(list)
    for r in runs:
        if r.get('control') or not r.get('language'): continue
        out[(r['endpoint'], r['rate'], r['language'])].append(r)
    return out

def stat(rs, f):
    xs = [v for v in (f(r) for r in rs if r['valid']) if v is not None]
    return (statistics.median(xs), min(xs), max(xs)) if xs else None

def passes(rs): return sum(1 for r in rs if r['valid'] and r['slo_passed'])

def fmt(s, nd=1):
    if not s: return '-'
    m, lo, hi = s
    return f'{m:.{nd}f}' + ('' if abs(hi - lo) < 10 ** -nd else f' <span class="m">({lo:.{nd}f}-{hi:.{nd}f})</span>')

def row(cs, endpoint, rate, lang, cols):
    rs = cs.get((endpoint, rate, lang))
    if not rs: return ''
    ok = passes(rs); n = len(rs)
    cls = 'p' if ok == n else 'f'
    cells_ = ''.join(f'<td>{fmt(stat(rs, f), nd)}</td>' for f, nd in cols)
    return f'<tr><td>{endpoint} @ {rate} RPS</td><td>{html.escape(lang + loop_tag(lang))}</td><td class="{cls}">{ok}/{n}</td>{cells_}</tr>'

def table(cs, keys, head, cols):
    body = ''.join(row(cs, e, r, l, cols) for e, r, l in keys)
    return f'<div class="card"><table><tr><th>Cell</th><th>Runtime</th><th>SLO passes</th>{head}</tr>{body}</table></div>'

# ---------- charts (inline SVG) ----------
def line_chart(cs, endpoint, langs, rates, ymax, title, ylabel='p99 ms'):
    W, H, L, B, T, R = 520, 260, 46, 34, 14, 14
    pw, ph = W - L - R, H - T - B
    xs = {r: L + pw * i / max(1, len(rates) - 1) for i, r in enumerate(rates)}
    y = lambda v: T + ph * (1 - min(v, ymax) / ymax)
    g = [f'<line class="ax" x1="{L}" y1="{y(t)}" x2="{W-R}" y2="{y(t)}"/><text class="m" x="{L-6}" y="{y(t)+4}" text-anchor="end">{t:g}</text>'
         for t in [ymax * i / 4 for i in range(5)]]
    g += [f'<text class="m" x="{x}" y="{H-12}" text-anchor="middle">{r}</text>' for r, x in xs.items()]
    g.append(f'<text class="m" x="{L+pw/2}" y="{H-1}" text-anchor="middle">requests per second</text>')
    for lang in langs:
        pts = []
        for rate in rates:
            rs = cs.get((endpoint, rate, lang))
            if not rs: continue
            s = stat(rs, p99)
            if not s: continue
            failed = passes(rs) < len(rs)
            pts.append((xs[rate], y(s[0]), failed, s[0]))
        c = COLORS.get(lang, '#555')
        if len(pts) > 1: g.append(f'<polyline fill="none" stroke="{c}" stroke-width="2" points="{" ".join(f"{a:.1f},{b:.1f}" for a, b, *_ in pts)}"/>')
        for a, b, failed, v in pts:
            if failed:
                g.append(f'<path d="M{a-5:.1f},{b-5:.1f}l10,10m0,-10l-10,10" stroke="#dc2626" stroke-width="2.5"><title>{lang}: failed SLO, p99 {v:.0f} ms</title></path>')
            else:
                g.append(f'<circle cx="{a:.1f}" cy="{b:.1f}" r="4" fill="{c}"><title>{lang}: p99 {v:.1f} ms</title></circle>')
    leg = ''.join(f'<span><svg viewBox="0 0 26 10"><line x1="0" y1="5" x2="26" y2="5" stroke="{COLORS.get(l, "#555")}" stroke-width="3"/></svg>{html.escape(l + loop_tag(l))}</span>' for l in langs)
    return f'<div class="card"><h3>{title}</h3><svg viewBox="0 0 {W} {H}">{"".join(g)}</svg><div class="leg">{leg}<span style="color:#dc2626">&times; failed the SLO (clipped to the top of the chart)</span></div></div>'

def bar_chart(cs, endpoint, rate, langs, key, title, unit, nd=0):
    items = []
    for lang in langs:
        rs = cs.get((endpoint, rate, lang))
        s = stat(rs, key) if rs else None
        if s: items.append((lang, s, passes(rs) == len(rs)))
    if not items: return ''
    vmax = max(s[2] for _, s, _ in items) * 1.12 or 1
    W, L, rowh = 600, 200, 30
    H = rowh * len(items) + 12
    g = []
    for i, (lang, (m, lo, hi), ok) in enumerate(items):
        yy = 6 + i * rowh; bw = (W - L - 64) * m / vmax
        c = COLORS.get(lang, '#555') if ok else '#dc2626'
        g.append(f'<text x="{L-8}" y="{yy+17}" text-anchor="end">{html.escape(lang + loop_tag(lang))}</text><rect x="{L}" y="{yy+4}" width="{bw:.1f}" height="18" rx="3" fill="{c}"><title>{lang}: median {m:.{nd}f} {unit}, range {lo:.{nd}f}-{hi:.{nd}f}</title></rect>')
        xr0, xr1 = L + (W - L - 64) * lo / vmax, L + (W - L - 64) * hi / vmax
        g.append(f'<line x1="{xr0:.1f}" y1="{yy+13}" x2="{xr1:.1f}" y2="{yy+13}" stroke="#1c1917" stroke-width="1.5"/>')
        g.append(f'<text class="m" x="{L+bw+6:.1f}" y="{yy+17}">{m:.{nd}f} {unit}</text>')
    return f'<div class="card"><h3>{title}</h3><svg viewBox="0 0 {W} {H}">{"".join(g)}</svg></div>'

PAGE = r'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Cloud rerun report</title><style>
:root{--bg:#fafaf9;--fg:#1c1917;--mut:#78716c;--card:#fff;--line:#e7e5e4;--ok:#16a34a;--bad:#dc2626;--okbg:#dcfce7;--badbg:#fee2e2;--warn:#ca8a04}
@media(prefers-color-scheme:dark){:root{--bg:#161412;--fg:#f5f5f4;--mut:#a8a29e;--card:#1f1c1a;--line:#3a3532;--ok:#4ade80;--bad:#f87171;--okbg:#14351f;--badbg:#4a1d1d}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,sans-serif}
header{padding:20px 16px 8px;max-width:1180px;margin:0 auto}h1{font-size:24px;margin:0 0 4px}
nav{position:sticky;top:0;background:var(--bg);border-bottom:1px solid var(--line);z-index:5;overflow-x:auto;white-space:nowrap}
nav div{max-width:1180px;margin:0 auto;padding:8px 16px}nav a{color:var(--fg);text-decoration:none;font-size:13px;padding:5px 10px;border:1px solid var(--line);border-radius:14px;margin-right:6px;background:var(--card)}
main{max-width:1180px;margin:0 auto;padding:8px 16px 64px}section{margin-top:36px}
h2{font-size:20px;margin:0 0 2px}h3{font-size:14px;margin:0 0 4px}p.n{color:var(--mut);margin:2px 0 12px;font-size:13px;max-width:80ch}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px;overflow-x:auto}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:12px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:12px 0}.kpi{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 12px}.kpi b{display:block;font-size:22px}.kpi span{color:var(--mut);font-size:12px}
table{border-collapse:collapse;font-size:12.5px;width:100%}th,td{padding:5px 8px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}th:first-child,td:first-child,th:nth-child(2),td:nth-child(2){text-align:left}
td.p{background:var(--okbg)}td.f{background:var(--badbg);font-weight:600}.m{color:var(--mut)}
svg{width:100%;height:auto;display:block}svg text{fill:var(--fg);font-size:11px}svg .m{fill:var(--mut)}.ax{stroke:var(--line)}
.leg{margin:8px 0}.leg span{display:inline-flex;align-items:center;margin-right:14px;font-size:13px}.leg svg{width:26px;height:10px;margin-right:5px}
.note{border-left:4px solid var(--warn);padding:8px 12px;background:var(--card);border-radius:6px;margin:12px 0;font-size:14px}
.verdict{border:1px solid var(--line);border-radius:10px;background:var(--card);padding:12px 14px;margin:10px 0}.verdict h3{font-size:15px;margin:0 0 4px}
.tag{display:inline-block;font-size:12px;font-weight:600;padding:2px 8px;border-radius:10px;margin-right:6px}.tag.yes{background:var(--okbg);color:var(--ok)}.tag.no{background:var(--badbg);color:var(--bad)}.tag.part{background:#fef9c3;color:#854d0e}
a{color:inherit}
</style></head><body>
<header><h1>Cloud rerun report: Python GIL study and threads cost</h1><p class="n">__SUB__</p></header>
<div class="note" style="max-width:1100px;margin:12px auto"><b>Note:</b> Python 3.14 made the free-threaded build officially supported (PEP 779), but it is still a separate build (3.14t) rather than the default. The standard python is still a GIL build.</div>
<nav><div><a href="#overview">1 Overview</a><a href="#verdicts">2 Claims</a><a href="#a">3 GIL ceiling</a><a href="#b">4 Forced-GIL control</a><a href="#c">5 Waiting calls</a><a href="#d">6 Memory at 1000 RPS</a><a href="#collapse">7 The 40 RPS collapse</a><a href="#method">8 Method</a><a href="#raw">9 Raw runs</a></div></nav>
<main>__BODY__</main></body></html>'''

def build(runs):
    cs = cells(runs)
    valid = [r for r in runs if not r.get('control') and r['valid']]
    n_pass = sum(1 for r in valid if r['slo_passed'])
    g = lambda *a: cs.get(a)
    def med(e, rate, l, f): s = stat(g(e, rate, l) or [], f); return s[0] if s else None
    mem = lambda r: r['container_memory_median_mib']
    cpu = lambda r: r['cpu_ms_per_success']
    cols_mem = [(mem, 1), (cpu, 2), (p99, 1)]
    head3 = '<th>Memory MiB</th><th>CPU ms/request</th><th>p99 ms</th>'
    parts = []
    parts.append(f'''<section id="overview"><h2>1. Overview</h2>
<p class="n">Every cell was run 3 times on a free GitHub-hosted runner (ubuntu-24.04, 4 vCPU). A cell is one candidate on one endpoint at one request rate. Values are medians with the min-max range across repeats in grey. "SLO passes" counts repeats that met the pre-registered SLO (criteria.json), so 3/3 means every repeat passed.</p>
<div class="kpis"><div class="kpi"><b>{len(valid)}</b><span>valid measured runs</span></div><div class="kpi"><b>{len(cs)}</b><span>cells (3 repeats each)</span></div>
<div class="kpi"><b>{n_pass}</b><span>runs that met the SLO</span></div><div class="kpi"><b>{len(valid)-n_pass}</b><span>runs that failed the SLO</span></div>
<div class="kpi"><b>4</b><span>workflow runs, about 16 runner hours of job time</span></div></div>
<div class="card"><table><tr><th>Workflow run</th><th>Batches</th><th>Duration</th></tr>{"".join(f'<tr><td>{link(r, rid)}</td><td>{html.escape(b)}</td><td>{d}</td></tr>' for r, b, rid, d in RUNS)}</table></div></section>''')

    parts.append(loop_note('note'))
    a_gil30, a_no30 = med('pycpu', 30, 'aiohttp-gil', p99), med('pycpu', 30, 'aiohttp-nogil', p99)
    parts.append(f'''<section id="verdicts"><h2>2. What the data supports</h2>
<div class="verdict"><h3><span class="tag no">A not supported</span>The GIL caps CPU-bound Python; the free-threaded build lifts the cap</h3>
On <code>/pycpu</code> the GIL build, the free-threaded build and the forced-GIL control all passed at 10 to 30 RPS and all collapsed at 40 RPS. The 30 RPS latency and CPU figures of the GIL builds ({a_gil30:.0f} ms p99) and the free-threaded build ({a_no30:.0f} ms) are not directly comparable: the GIL builds' 30 RPS runs (run #4) landed on a faster CPU model (AMD EPYC 9V74) than the free-threaded build's (run #3, EPYC 7763). Where all builds shared one CPU model (20 RPS) CPU per request was within about 3% (33.7, 34.8 and 34.8 ms). The GIL cap is visible in CPU use: the GIL builds never exceed 1.0 core, while the free-threaded build does spread across cores (about 1.27 at 30 RPS and 2.0 at 40 RPS). But it did not turn the extra cores into higher throughput: its ceiling was the same as the GIL build's, and at 40 RPS it did worse (0 successes against a handful).</div>
<div class="verdict"><h3><span class="tag yes">B supported</span>Forced-GIL control</h3>
The free-threaded build with the GIL forced back on (<code>-t-gilon</code>) matches the free-threaded build on memory and CPU cost, and matches the GIL build on latency. The extra memory and CPU belong to the build, not to the GIL setting.</div>
<div class="verdict"><h3><span class="tag yes">C supported</span>Waiting calls: virtual threads and Go versus a 200-thread pool</h3>
Go and Java virtual threads passed <code>/park</code> at 250 and 1000 RPS in every repeat. The 200-thread Java pool failed every request at both rates, in every repeat.</div>
<div class="verdict"><h3><span class="tag yes">D supported</span>Memory cost at 1000 RPS on <code>/partner</code></h3>
Go {med('partner',1000,'go',mem):.0f} MiB, python (aiohttp) {med('partner',1000,'python',mem):.0f} MiB, fastapi {med('partner',1000,'fastapi',mem):.0f} MiB, Java {med('partner',1000,'java',mem):.0f} MiB, all passing the SLO in every repeat. Java is about 9 times Go. The earlier plan figure of about 195 MiB for Java is out of date.</div>
<div class="note">Not run yet: E (memobj) and F (hashlib control on <code>/cpu</code>), both optional.</div></section>''')

    pyc = lambda fw: [f'{fw}-gil', f'{fw}-t-gilon', f'{fw}-nogil']
    keys_a = [('pycpu', rt, l) for rt in (10, 15, 20, 30, 40) for l in pyc('aiohttp')]
    parts.append(f'''<section id="a"><h2>3. GIL ceiling on <code>/pycpu</code></h2>
<p class="n">Each request burns about 35 ms of pure-Python CPU in a 4-thread pool; the container has 2 CPUs. Under the GIL one core is usable, so about 29 to 35 RPS is the ceiling. A free-threaded build could use both cores. Aiohttp-gil and aiohttp-t-gilon were run at 10 to 20 RPS in run #3 and at 30 and 40 RPS in run #4; aiohttp-nogil ran 10 to 40 RPS in run #3.</p>
<div class="grid">{line_chart(cs, 'pycpu', pyc('aiohttp'), [10, 15, 20, 30, 40], 120, 'aiohttp: p99 latency by rate')}
{line_chart(cs, 'pycpu', pyc('fastapi'), [10, 15, 20], 60, 'fastapi: p99 latency by rate')}
{line_chart(cs, 'pycpu', pyc('django'), [10, 15, 20], 60, 'django: p99 latency by rate')}</div>
{table(cs, keys_a, head3, cols_mem)}
<p class="n">FastAPI and Django were only run to 20 RPS, so they show the build comparison (claim B) but no ceiling.</p></section>''')

    keys_b = [('pycpu', 20, l) for fw in ('aiohttp', 'fastapi', 'django') for l in pyc(fw)]
    parts.append(f'''<section id="b"><h2>4. Forced-GIL control</h2>
<p class="n">At 20 RPS (all three frameworks). GIL build = stock CPython 3.14.3. Free-threaded = 3.14.3t. Forced-GIL control = the free-threaded build with PYTHON_GIL=1.</p>
<div class="grid">{bar_chart(cs, 'pycpu', 20, [l for fw in ('aiohttp', 'fastapi', 'django') for l in pyc(fw)], mem, 'Memory at 20 RPS', 'MiB')}
{bar_chart(cs, 'pycpu', 20, [l for fw in ('aiohttp', 'fastapi', 'django') for l in pyc(fw)], cpu, 'CPU per request at 20 RPS', 'ms', 1)}</div>
{table(cs, keys_b, head3, cols_mem)}
<p class="n">Free-threaded memory is 27% higher for aiohttp and FastAPI and 40 to 47% higher for Django. The forced-GIL control sits with the free-threaded build, not with the GIL build.</p></section>''')

    park = [l for l in ('go', 'java', 'java-platform')]
    keys_c = [('park', rt, l) for rt in (250, 1000) for l in park]
    parts.append(f'''<section id="c"><h2>5. Waiting calls (<code>/park</code>)</h2>
<p class="n">Each request waits about 1 s on a slow partner call, so the rate equals the number of requests in flight. The SLO is a p99 of 1250 ms. The java-platform candidate is the same code on a 200-thread pool.</p>
<div class="grid">{bar_chart(cs, 'park', 250, park, mem, 'Memory at 250 in flight', 'MiB')}{bar_chart(cs, 'park', 1000, park, mem, 'Memory at 1000 in flight', 'MiB')}</div>
{table(cs, keys_c, head3, cols_mem)}
<p class="n">A p99 of 0.0 for java-platform means no request completed, so there is no latency to report. At 250 RPS it dropped about 914 iterations and at 1000 RPS about 72,000, with a failure rate of 1.0 in every repeat.</p></section>''')

    pl = ['go', 'python', 'fastapi', 'java']
    keys_d = [('partner', 1000, l) for l in pl]
    parts.append(f'''<section id="d"><h2>6. Memory at 1000 RPS on <code>/partner</code></h2>
<p class="n">Each request makes one 100 ms call to the mock partner, so the floor for p99 is about 100 ms. The SLO is a p99 of 250 ms. Black whiskers show the min-max range across the 3 repeats.</p>
<div class="grid">{bar_chart(cs, 'partner', 1000, pl, mem, 'Memory (median of the measured window)', 'MiB', 1)}{bar_chart(cs, 'partner', 1000, pl, cpu, 'CPU per request', 'ms', 3)}</div>
{table(cs, keys_d, head3, cols_mem)}</section>''')

    fails = [r for r in runs if r.get('endpoint') == 'pycpu' and r.get('rate') == 40 and not r.get('control')]
    frows = ''.join(f'<tr><td>{html.escape(r["language"] + loop_tag(r["language"]))}</td><td>{r["successes"]}</td><td>{r["failure_rate"]:.4f}</td><td>{(p99(r) or 0):.0f}</td><td>{(r["cores"] or 0):.2f}</td><td>{r["oom_kills_delta"]}</td><td>{r["throttled_usec_delta"]/1e6:.2f}</td></tr>' for r in sorted(fails, key=lambda r: (r['language'], r['dir'])))
    parts.append(f'''<section id="collapse"><h2>7. The 40 RPS collapse</h2>
<p class="n">At 40 RPS every runtime failed all three repeats. The 5-second client timeout is what p99 shows, so this is not a latency measurement. The GIL builds ran at the 1.0-core GIL cap and the free-threaded build at the full 2.0 cores. None was OOM-killed, and the cgroup throttled none by more than half a second. The GIL builds completed a handful of requests (2 to 57); the free-threaded build completed none.</p>
<div class="card"><table><tr><th>Runtime</th><th>Successes</th><th>Failure rate</th><th>p99 ms</th><th>Cores used</th><th>OOM kills</th><th>Throttled s</th></tr>{frows}</table></div>
<div class="note">Interpretation, not directly measured: the server cannot clear 40 RPS, so requests queue past the client timeout while the server keeps working on abandoned ones, which drives useful throughput to zero. The candidate log is empty, so this cannot be confirmed from the log. At 30 RPS all runtimes passed, so the usable ceiling lies between 30 and 40 RPS for every build tested (for the GIL builds that is the 1-core limit, since 0.86 cores were in use at 30 RPS). A 35 RPS cell would narrow it.</div></section>''')

    parts.append('''<section id="method"><h2>8. Method and limits</h2><div class="card"><table>
<tr><td>Runner</td><td>GitHub-hosted ubuntu-24.04, 4 vCPU (AMD EPYC 7763), 16 GB, Docker 28.0.4, cgroup v2</td></tr>
<tr><td>CPU pinning</td><td>Candidate on CPUs 0,1 (2 CPUs, 512 MiB, no swap); mock partner, k6 and the sampler on CPUs 2,3</td></tr>
<tr><td>Python</td><td>CPython 3.14.3 (GIL build) and 3.14.3t (free-threaded), same asyncio stack for both</td></tr>
<tr><td>Timings</td><td>--fast: 2 min warmup, 3 min measured, 60 s recovery; 3 repeats per cell, tag cloud1</td></tr>
<tr><td>Load</td><td>k6 1.3.0, constant arrival rate (open model)</td></tr>
<tr><td>SLO</td><td>p99 250 ms (park 1250 ms), failure rate at most 0.1%, no dropped iterations</td></tr>
<tr><td>Noise floor</td><td>Run #1 (5 repeats each, go partner 250 and aiohttp-nogil pycpu 10): memory 0.9%, CPU 3.2%, p99 0.5% min-max range. That artifact was not re-fetched for this report.</td></tr>
<tr><td>Limits</td><td>One runner per batch, so cross-batch comparisons carry VM-to-VM noise. The leak screen reports insufficient_window on the short runs. CPU ms per request is blank-equivalent when a run has almost no successes.</td></tr></table></div></section>''')

    allr = sorted((r for r in runs if not r.get('control')), key=lambda r: (r['endpoint'], r['language'], r['rate'], r['dir']))
    rr = ''.join(f'<tr><td>{r["batch"]}</td><td>{r["endpoint"]}</td><td>{html.escape(r["language"] + loop_tag(r["language"]))}</td><td>{r["rate"]}</td><td class="{"p" if r["slo_passed"] else "f"}">{"pass" if r["slo_passed"] else "FAIL"}</td><td>{r["container_memory_median_mib"]:.1f}</td><td>{(r["cpu_ms_per_success"] or 0):.2f}</td><td>{(p99(r) or 0):.1f}</td><td>{r["failure_rate"]:.4f}</td><td>{r["dropped_iterations"]}</td><td class="m">{r["dir"]}</td></tr>' for r in allr)
    parts.append(f'<section id="raw"><h2>9. Raw runs</h2><div class="card"><table><tr><th>Batch</th><th>Endpoint</th><th>Runtime</th><th>RPS</th><th>SLO</th><th>Mem MiB</th><th>CPU ms</th><th>p99 ms</th><th>Fail rate</th><th>Drops</th><th>Run directory</th></tr>{rr}</table></div></section>')
    return PAGE.replace('__BODY__', ''.join(parts)).replace('__SUB__', f'Generated {time.strftime("%Y-%m-%d %H:%M")} from the artifacts of GitHub Actions runs #2 to #4 (tag cloud1). Source: rerun/reports/build_report.py.')

def main():
    p = argparse.ArgumentParser(); p.add_argument('--data', default=str(HERE / 'data')); p.add_argument('--out', default=str(HERE / 'cloud1-report.html'))
    a = p.parse_args()
    runs = load(pathlib.Path(a.data))
    pathlib.Path(a.out).write_text(build(runs), encoding='utf-8')
    print(f'{len(runs)} runs -> {a.out}')

if __name__ == '__main__': main()
