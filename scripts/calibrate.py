"""Find the highest rate the mock + k6 generator hold with zero drops and low latency.
No candidate is involved, so a failure here is helper capacity, not runtime capacity.
Writes results/calibration.json; run.py and matrix.py refuse runs whose peak rate x headroom
exceeds it (the plan requires helpers to handle >2x the intended maximum)."""
import argparse, json, pathlib, subprocess, sys, time, uuid
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from calibration import ROOT, CALIBRATION

def docker(*a, check=True):
    return subprocess.run(['docker', *map(str, a)], capture_output=True, text=True, check=check).stdout.strip()

def k6(network, out, env, cpuset=''):
    cmd = ['docker', 'run', '--rm', '--network', network, '-v', f'{ROOT / "load"}:/scripts:ro', '-v', f'{out}:/results', *(['--cpuset-cpus', cpuset] if cpuset else [])]
    for k, v in env.items(): cmd += ['-e', f'{k}={v}']
    return subprocess.run(cmd + ['grafana/k6:1.3.0', 'run', '/scripts/calibrate.js'], capture_output=True, text=True).returncode == 0

def main():
    a = argparse.ArgumentParser()
    a.add_argument('--rates', default='500,1000,2000,3000,4500,6000,9000', help='ascending ladder of requests/s to the mock')
    a.add_argument('--duration', default='30s'); a.add_argument('--p99', default='150')
    a.add_argument('--mock-workers', default='2'); a.add_argument('--headroom', type=float, default=2.0)
    a.add_argument('--max-vus', default='5000'); a.add_argument('--park-rates', default='250,500,1000,2000,3000', help='ladder for /park (each request holds ~1 s)')
    a.add_argument('--helper-cpuset', default='', help='pin the mock and k6 to these host CPUs; calibrate with the same pinning the runs use')
    args = a.parse_args()
    network = 'lb-cal-' + uuid.uuid4().hex[:8]; mock = network + '-mock'
    out = ROOT / 'results' / ('calibration-' + time.strftime('%Y%m%d-%H%M%S')); out.mkdir(parents=True); out.chmod(0o777)
    docker('network', 'create', network)
    result = {'headroom': args.headroom, 'mock_workers': args.mock_workers, 'helper_cpuset': args.helper_cpuset, 'mock_max_rps': {}, 'ladder': []}
    try:
        docker('run', '-d', '--name', mock, '--network', network, '--network-alias', 'mock', *(['--cpuset-cpus', args.helper_cpuset] if args.helper_cpuset else []), '-e', f'MOCK_WORKERS={args.mock_workers}', 'lb-python', 'python', 'mock.py')
        time.sleep(3)
        for path in ('/delay', '/data', '/park'):
            best = 0
            for rate in map(int, (args.park_rates if path == '/park' else args.rates).split(',')):
                env = {'RATE': rate, 'MOCK_PATH': path, 'DURATION': args.duration, 'P99_MS': args.p99, 'MAX_VUS': args.max_vus}
                if path == '/park': env.update({'P99_MS': 1300, 'VUS': int(rate * 1.5)})  # ~1 s per call => ~rate VUs held
                ok = k6(network, out, env, args.helper_cpuset)
                result['ladder'].append({'path': path, 'rate': rate, 'passed': ok}); print(path, rate, 'PASS' if ok else 'FAIL', flush=True)
                if not ok: break
                best = rate
            result['mock_max_rps'][path] = best
        # Both ladders go through the same k6 generator, so the better one bounds what k6 can offer.
        result['generator_max_rps'] = max(result['mock_max_rps']['/delay'], result['mock_max_rps']['/data'])
        result['mock_logs_tail'] = docker('logs', '--tail', '20', mock, check=False)
    finally:
        docker('rm', '-f', mock, check=False); docker('network', 'rm', network, check=False)
    CALIBRATION.write_text(json.dumps(result, indent=2)); print(json.dumps(result, indent=2))
    if min(result['mock_max_rps'].values()) == 0: sys.exit('calibration failed: even the lowest rate was not sustained')

if __name__ == '__main__': main()
