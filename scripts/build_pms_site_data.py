"""Generate results/pms-language-guide/js/bench.js (aggregated test evidence) from results/*/report.json.
usage: python scripts/build_pms_site_data.py"""
import json, pathlib, statistics, sys
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from calibration import ROOT

def med(v):
    v = [x for x in v if x is not None]
    return statistics.median(v) if v else None

def main():
    groups = {}
    for p in sorted((ROOT / 'results').glob('*/report.json')):
        r = json.loads(p.read_text()); r.pop('metrics', None)
        if not r.get('language') or r.get('control') or r.get('profile') != 'steady' or not r.get('cell_key'): continue   # skip untagged quick smoke runs
        if not (r.get('valid') or (r.get('failure_rate') or 0) >= 0.99): continue   # total no-reply runs count as failures
        groups.setdefault((r['language'], r['endpoint'], r['rate']), []).append(r)
    cells = []
    for (c, e, rate), rs in sorted(groups.items()):
        ok = [x for x in rs if x['slo_passed']]
        total_fail = all((x.get('failure_rate') or 0) >= 0.99 for x in rs)
        cells.append({'c': c, 'e': e, 'r': rate, 'pass': all(x['slo_passed'] for x in rs), 'n': len(rs),
                      'p99': None if total_fail else med([x['latency_ms']['p(99)'] for x in rs]),
                      'mem': med([x.get('container_memory_median_mib') for x in rs]),
                      'cpu': med([x.get('cpu_ms_per_success') for x in ok]),
                      'fail': med([x.get('failure_rate') or 0 for x in rs])})
    out = ROOT / 'results' / 'pms-language-guide' / 'js' / 'bench.js'
    out.write_text('window.BENCH=' + json.dumps({'cells': cells, 'runs': sum(len(v) for v in groups.values()),
        'slo': json.loads((ROOT / 'criteria.json').read_text())['slo']}, separators=(',', ':')) + ';\n', encoding='utf-8')
    print(f'{out}: {len(cells)} cells')

if __name__ == '__main__': main()
