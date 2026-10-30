"""Aggregate results/*/report.json into the plan's table and apply the pre-registered decision rule.

One row per (endpoint, profile, rate, language) across repeats: medians and min-max ranges (never
averaged percentiles). A runtime comparison is 'real' only when both sides met the SLO in every
repeat, there are >= min_repeats valid runs each, the median gap exceeds max(inconclusive_pct,
control noise range) AND the min-max ranges do not overlap. Otherwise it is inconclusive."""
import argparse, collections, json, pathlib, statistics, sys
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from calibration import ROOT

METRICS = {'memory_mib': 'container_memory_median_mib', 'cpu_ms_per_success': 'cpu_ms_per_success'}

def p99(r): return (r.get('latency_ms') or {}).get('p(99)')

def load_reports(results):
    out = []
    for f in sorted(results.glob('*/report.json')):
        try: out.append(json.loads(f.read_text()))
        except ValueError: pass
    return out

def noise_pct(reports):
    """Largest relative min-max range among control groups, per metric (percent)."""
    groups = collections.defaultdict(list)
    for r in reports:
        if r.get('control') and r.get('valid'): groups[(r['language'], r['endpoint'], r['rate'])].append(r)
    noise = {}
    for name, key in METRICS.items():
        spreads = []
        for g in groups.values():
            xs = [r[key] for r in g if r.get(key) is not None]
            if len(xs) >= 3: spreads.append(100 * (max(xs) - min(xs)) / statistics.median(xs))
        noise[name] = max(spreads, default=0.0)
    noise['p99_ms'] = 0.0
    for g in groups.values():
        xs = [p99(r) for r in g if p99(r) is not None]
        if len(xs) >= 3: noise['p99_ms'] = max(noise['p99_ms'], 100 * (max(xs) - min(xs)) / statistics.median(xs))
    return noise

def compare(a, b, key, threshold, min_repeats):
    xa, xb = a['values'][key], b['values'][key]
    if min(len(xa), len(xb)) < min_repeats: return 'inconclusive (too few repeats)'
    if not (a['slo_all'] and b['slo_all']): return 'capacity limited (SLO not met in every repeat)'
    ma, mb = statistics.median(xa), statistics.median(xb)
    if min(ma, mb) <= 0: return 'inconclusive'
    gap = 100 * abs(ma - mb) / min(ma, mb)
    overlap = not (max(xa) < min(xb) or max(xb) < min(xa))
    if gap < threshold or overlap: return f'inconclusive ({gap:.1f}% gap, {"ranges overlap" if overlap else "below threshold"})'
    return f'{a["language"] if ma < mb else b["language"]} lower by {gap:.1f}%'

def main():
    p = argparse.ArgumentParser(); p.add_argument('--results', default=str(ROOT / 'results')); p.add_argument('--criteria', default=str(ROOT / 'criteria.json'))
    p.add_argument('--json', action='store_true')
    p.add_argument('--tag', default=None, help='only measured runs with this matrix.py --tag (control runs are always kept for the noise floor)')
    a = p.parse_args()
    criteria = json.loads(pathlib.Path(a.criteria).read_text()); reports = load_reports(pathlib.Path(a.results))
    if a.tag is not None: reports = [r for r in reports if r.get('control') or r.get('tag', '') == a.tag]
    noise = noise_pct(reports); base = criteria['inconclusive_pct']
    cells = collections.defaultdict(list)
    for r in reports:
        if r.get('control') or not r.get('language'): continue
        cells[(r['endpoint'], r['profile'], r['rate'], r['language'])].append(r)
    rows = {}
    for (endpoint, profile, rate, lang), rs in sorted(cells.items()):
        valid = [r for r in rs if r['valid']]
        def vals(f): return [x for x in (f(r) for r in valid) if x is not None]
        rows[(endpoint, profile, rate, lang)] = {
            'language': lang, 'runs': len(rs), 'valid_runs': len(valid), 'slo_all': bool(valid) and all(r['slo_passed'] for r in valid),
            'values': {'memory_mib': vals(lambda r: r['container_memory_median_mib']), 'cpu_ms_per_success': vals(lambda r: r['cpu_ms_per_success']), 'p99_ms': vals(p99)},
            'peak_mib': vals(lambda r: r['container_memory_sampled_peak_mib']), 'successes': vals(lambda r: r['successes']),
            'failure_rate': vals(lambda r: r['failure_rate']), 'drops': vals(lambda r: r['dropped_iterations']),
            'throttled_usec': vals(lambda r: r['throttled_usec_delta']),
            'leak': [r['leak_screen']['verdict'] for r in valid if r.get('leak_screen')], 'recovery': [r['recovery']['verdict'] for r in valid if r.get('recovery')]}
    def rng(xs, fmt='{:.1f}'): return f'{fmt.format(statistics.median(xs))} ({fmt.format(min(xs))}-{fmt.format(max(xs))})' if xs else '-'
    print('| Endpoint / profile / RPS | Runtime | Valid/runs | SLO every run | Memory MiB median (range) | Peak MiB | CPU ms/success | p99 ms | Fail rate | Drops | Throttled usec | Leak | Recovery |')
    print('|---|---|---|---|---|---|---|---|---|---|---|---|---|')
    for (endpoint, profile, rate, lang), r in rows.items():
        v = r['values']
        print(f'| {endpoint}/{profile}/{rate} | {lang} | {r["valid_runs"]}/{r["runs"]} | {"yes" if r["slo_all"] else "NO"} | {rng(v["memory_mib"])} | {rng(r["peak_mib"])} | {rng(v["cpu_ms_per_success"], "{:.3f}")} | {rng(v["p99_ms"])} | {rng(r["failure_rate"], "{:.4f}")} | {rng(r["drops"], "{:.0f}")} | {rng(r["throttled_usec"], "{:.0f}")} | {",".join(sorted(set(r["leak"]))) or "-"} | {",".join(sorted(set(r["recovery"]))) or "-"} |')
    print(f'\nControl-run noise (min-max range %, 0 = no control runs): {json.dumps({k: round(x, 1) for k, x in noise.items()})}')
    print('\n## Pairwise decisions (threshold = max(criteria inconclusive_pct, control noise))')
    weights = criteria['endpoint_weights']; wins = collections.Counter(); considered = collections.Counter()
    by_cell = collections.defaultdict(dict)
    for (endpoint, profile, rate, lang), r in rows.items(): by_cell[(endpoint, profile, rate)][lang] = r
    for (endpoint, profile, rate), langs in by_cell.items():
        names = sorted(langs)
        for i, x in enumerate(names):
            for y in names[i + 1:]:
                for key in ('memory_mib', 'cpu_ms_per_success', 'p99_ms'):
                    threshold = max(base, noise.get(key, 0.0))
                    verdict = compare(langs[x], langs[y], key, threshold, criteria['min_repeats'])
                    print(f'- {endpoint}/{profile}/{rate} {x} vs {y} [{key}]: {verdict}')
                    considered[endpoint] += 1
                    if ' lower by ' in verdict: wins[(endpoint, verdict.split()[0])] += weights.get(endpoint, 1)
    if wins:
        print('\n## Weighted wins (clear differences only, weights from criteria.json)')
        totals = collections.Counter()
        for (endpoint, lang), w in wins.items(): totals[lang] += w
        for lang, w in totals.most_common(): print(f'- {lang}: {w}')
    if a.json: print(json.dumps({'noise': noise}, indent=2))

if __name__ == '__main__': main()
