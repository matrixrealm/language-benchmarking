"""Noise-floor control: run the SAME candidate and cell N times and report the spread.
Differences between runtimes smaller than this spread (or criteria.json inconclusive_pct,
whichever is larger) must be reported as inconclusive; summarize.py applies that automatically."""
import argparse, json, pathlib, statistics, subprocess, sys
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from calibration import ROOT

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--language', default='go')
    p.add_argument('--endpoint', default='partner'); p.add_argument('--rate', type=int, default=250)
    p.add_argument('--runs', type=int, default=5)
    p.add_argument('--cpuset', default=''); p.add_argument('--helper-cpuset', default='')
    p.add_argument('--fast', action='store_true', help='same shortened timings as matrix.py --fast; use it so noise matches the measured runs')
    a = p.parse_args()
    for i in range(a.runs):
        key = f'noise|{a.language}|{a.endpoint}|{a.rate}|c{i}'
        cmd = [sys.executable, str(ROOT / 'scripts' / 'run.py'), '--language', a.language, '--endpoint', a.endpoint,
               '--rate', str(a.rate), '--cell-key', key, '--control']
        if a.cpuset: cmd += ['--cpuset', a.cpuset]
        if a.helper_cpuset: cmd += ['--helper-cpuset', a.helper_cpuset]
        if a.fast: cmd += ['--idle', '30', '--warmup', '2m', '--duration', '3m', '--recovery', '60']
        subprocess.run(cmd, check=True)
    reports = [json.loads(f.read_text()) for f in (ROOT / 'results').glob('*/report.json')]
    mine = [r for r in reports if r.get('control') and r['language'] == a.language and r['endpoint'] == a.endpoint and r['rate'] == a.rate and r['valid']]
    for metric in ('container_memory_median_mib', 'cpu_ms_per_success'):
        xs = [r[metric] for r in mine if r.get(metric) is not None]
        if len(xs) > 1: print(f'{metric}: median={statistics.median(xs):.3f} range%={100 * (max(xs) - min(xs)) / statistics.median(xs):.1f}')

if __name__ == '__main__': main()
