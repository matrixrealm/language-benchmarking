"""Host Python 3.10+, Docker Desktop (Linux containers) or Docker Engine."""
import argparse, csv, hashlib, json, os, pathlib, platform, statistics, subprocess, sys, threading, time, uuid
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import analysis
from candidates import CANDIDATES, env_args, image
from calibration import ROOT, capacity_problem, load_calibration, peak_rates

CRITERIA = ROOT / 'criteria.json'
SMOKE_LIMIT_RPS = 300  # without results/calibration.json only runs this small are allowed
SAMPLE_FIELDS = ['time', 'phase', 'memory_bytes', 'rss_bytes', 'usage_usec', 'nr_throttled', 'throttled_usec', 'oom', 'oom_kill', 'os_threads']

def docker(*args, check=True):
    return subprocess.run(['docker', *map(str, args)], capture_output=True, text=True, check=check).stdout.strip()

def snapshot(name):
    """docker-exec snapshot inside the candidate. Charged to the candidate's cgroup, so it is used
    only for --sampler exec (legacy) and --sampler none (two snapshots bracketing the measured run)."""
    command = 'cat /sys/fs/cgroup/memory.current; cat /sys/fs/cgroup/cpu.stat; echo MEMORY_EVENTS; cat /sys/fs/cgroup/memory.events; echo PROCESS; cat /proc/1/status'
    raw = docker('exec', name, 'sh', '-c', command)
    first, *lines = raw.splitlines(); out = {'memory_bytes': int(first)}
    section = 'cpu'
    for line in lines:
        if line == 'MEMORY_EVENTS': section = 'events'; continue
        if line == 'PROCESS': section = 'process'; continue
        fields = line.replace(':', '').split()
        if len(fields) < 2: continue
        if section == 'cpu' and fields[0] in ('usage_usec', 'nr_throttled', 'throttled_usec'): out[fields[0]] = int(fields[1])
        if section == 'events' and fields[0] in ('oom', 'oom_kill'): out[fields[0]] = int(fields[1])
        if section == 'process' and fields[0] == 'VmRSS': out['rss_bytes'] = int(fields[1]) * 1024
        if section == 'process' and fields[0] == 'Threads': out['os_threads'] = int(fields[1])
    out['time'] = time.time(); return out

def wait_ready(network):
    docker('run', '--rm', '--network', network, 'lb-python', 'python', '-c',
           "import time,urllib.request\nfor i in range(120):\n try:\n  urllib.request.urlopen('http://candidate:8080/health',timeout=1);break\n except Exception:time.sleep(.25)\nelse:raise SystemExit('readiness timeout')")

def load(network, out, args, criteria, duration=None):
    slo = criteria['slo']
    p99 = args.p99 if args.p99 is not None else slo.get({'cpu': 'cpu_p99_ms', 'pycpu': 'cpu_p99_ms', 'park': 'park_p99_ms'}.get(args.endpoint, 'p99_ms'), slo['p99_ms'])
    env = {'RATE': str(args.rate), 'PROFILE': args.profile if duration is None else 'steady',
           'ENDPOINT': args.endpoint, 'VUS': str(args.vus), 'MAX_VUS': str(args.max_vus),
           'P99_MS': str(p99), 'MAX_FAIL': str(slo['max_failure_rate']), 'CPU_DIGEST': hashlib.sha256(b'a' * 1048576).hexdigest()}
    if duration is not None or args.duration: env['DURATION'] = duration or args.duration
    cmd = ['docker', 'run', '--rm', '--network', network, '-v', f'{ROOT / "load"}:/scripts:ro', '-v', f'{out}:/results']
    if args.helper_cpuset: cmd += ['--cpuset-cpus', args.helper_cpuset]
    for k, v in env.items(): cmd += ['-e', f'{k}={v}']
    cmd += ['grafana/k6:1.3.0', 'run', '/scripts/test.js']
    with (out / 'load.log').open('w') as log:
        r = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT)
    return r.returncode

def host_info():
    info = {'platform': platform.platform(), 'processor': platform.processor(), 'cpu_count': os.cpu_count()}
    if platform.system() == 'Windows':
        try: info['cpu_name'] = subprocess.run(['powershell', '-NoProfile', '-Command', '(Get-CimInstance Win32_Processor).Name'], capture_output=True, text=True, timeout=20).stdout.strip()
        except Exception as e: info['cpu_name_error'] = str(e)
        wsl = pathlib.Path.home() / '.wslconfig'
        info['wslconfig'] = wsl.read_text() if wsl.exists() else None
    elif pathlib.Path('/proc/cpuinfo').exists():
        info['cpu_name'] = next((l.split(':', 1)[1].strip() for l in open('/proc/cpuinfo') if l.startswith('model name')), None)
    return info

def candidate_meta(network):
    raw = docker('run', '--rm', '--network', network, 'lb-python', 'python', '-c',
                 "import urllib.request;print(urllib.request.urlopen('http://candidate:8080/meta').read().decode())")
    return json.loads(raw)

def start_sidecar(network, cname, out, cpuset=''):
    """Sampler container outside the candidate's cgroup; see scripts/sampler.py."""
    cid = docker('inspect', '-f', '{{.Id}}', cname); pid = docker('inspect', '-f', '{{.State.Pid}}', cname)
    sidecar = network + '-sampler'
    docker('run', '-d', '--name', sidecar, '--network', 'none', '--pid', 'host', *(['--cpuset-cpus', cpuset] if cpuset else []),
           '-v', '/sys/fs/cgroup:/host-cgroup:ro', '-v', f'{ROOT / "scripts"}:/scripts:ro', '-v', f'{out}:/results',
           'lb-python', 'python', '/scripts/sampler.py', cid, pid, '/results', '1')
    for _ in range(60):
        if (out / 'sampler.ready').exists(): return sidecar
        if docker('inspect', '-f', '{{.State.Running}}', sidecar) != 'true':
            raise RuntimeError('sampler sidecar exited: ' + docker('logs', sidecar, check=False))
        time.sleep(.5)
    raise RuntimeError('sampler sidecar not ready: ' + docker('logs', sidecar, check=False))

def read_rows(path):
    with path.open() as f:
        return [{k: (float(v) if k == 'time' else (v if k == 'phase' else int(v))) for k, v in r.items() if v != ''} for r in csv.DictReader(f)]

def metric(metrics, name, key):
    return metrics.get(name, {}).get('values', {}).get(key)

def main():
    a = argparse.ArgumentParser()
    a.add_argument('--language', choices=sorted(CANDIDATES), required=True, help='candidate name from scripts/candidates.py')
    a.add_argument('--endpoint', choices=['health', 'partner', 'fanout', 'payload', 'park', 'cpu', 'pycpu', 'membuf', 'memobj'], default='partner')
    a.add_argument('--profile', choices=['steady', 'stress', 'spike', 'soak'], default='steady')
    a.add_argument('--rate', type=int, default=100); a.add_argument('--duration', default='')
    a.add_argument('--warmup', default='5m'); a.add_argument('--idle', type=int, default=120); a.add_argument('--recovery', type=int, default=300)
    a.add_argument('--vus', type=int, default=300); a.add_argument('--max-vus', type=int, default=3000)
    a.add_argument('--p99', type=float, default=None, help='override criteria.json p99 (ms)'); a.add_argument('--cpuset', default='', help='pin the candidate to these host CPUs, e.g. 0,1')
    a.add_argument('--helper-cpuset', default='', help='pin the mock, k6 and sampler to these other host CPUs, e.g. 2,3')
    a.add_argument('--sampler', choices=['sidecar', 'exec', 'none'], default='sidecar',
                   help='sidecar: out-of-candidate 1 Hz sampler (default); exec: legacy docker-exec 1 Hz; none: two exec snapshots, for sampler-overhead A/B runs')
    a.add_argument('--criteria', default=str(CRITERIA)); a.add_argument('--cell-key', default='', help='set by matrix.py for resume')
    a.add_argument('--tag', default='', help='label stored in the report, set by matrix.py')
    a.add_argument('--control', action='store_true', help='mark as a noise-floor control run')
    a.add_argument('--force-rate', action='store_true', help='ignore the calibration capacity check')
    a.add_argument('--partner-limit', type=int, default=None, help='outbound in-flight call limit (default 256; the park endpoint uses 20000)')
    a.add_argument('--build', action='store_true'); args = a.parse_args()
    if args.rate < 1 or args.vus < 1 or args.max_vus < args.vus: a.error('invalid rate or VU limits')
    if args.endpoint == 'park':
        # park holds ~1 s per request, so ~rate tasks are in flight; the 256 outbound cap would hide the thread-model difference
        args.partner_limit = args.partner_limit or 20000
        args.vus = max(args.vus, int(args.rate * 1.5)); args.max_vus = max(args.max_vus, args.vus * 2)
    args.partner_limit = args.partner_limit or 256
    criteria_path = pathlib.Path(args.criteria); criteria = json.loads(criteria_path.read_text())
    peak, partner_peak = peak_rates(args.endpoint, args.profile, args.rate)
    calibration = load_calibration()
    if calibration is None: problem = None if max(peak, partner_peak) <= SMOKE_LIMIT_RPS else 'no results/calibration.json: run scripts/calibrate.py first'
    else: problem = capacity_problem(args.endpoint, args.profile, args.rate, calibration)
    if problem and not args.force_rate: a.error(problem + ' (use --force-rate to override)')
    if args.build:
        for d in {'python', CANDIDATES[args.language]['dir']}: docker('build', '-t', f'lb-{d}', ROOT / d)  # gil/nogil images: see gil/Dockerfile (--build-arg PYVER)
    run_id = time.strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:6]
    out = ROOT / 'results' / f'{run_id}-{args.language}-{args.endpoint}-{args.profile}'; out.mkdir(parents=True)
    out.chmod(0o777)  # k6 container user needs a writable bind mount on Linux.
    network = 'lb-' + uuid.uuid4().hex[:8]; name = network + '-candidate'; mock = network + '-mock'; sidecar = None
    stop = threading.Event(); rows = []; errors = []; phase = ['idle']

    def set_phase(p):
        phase[0] = p
        if args.sampler == 'sidecar': (out / 'phase').write_text(p)

    def exec_sample():
        with (out / 'resources.csv').open('w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=SAMPLE_FIELDS); writer.writeheader()
            while not stop.is_set():
                started = time.monotonic()
                try:
                    row = snapshot(name); row['phase'] = phase[0]; rows.append(row); writer.writerow(row); f.flush()
                except Exception as e: errors.append(str(e))
                stop.wait(max(0, 1 - (time.monotonic() - started)))

    docker('network', 'create', network)
    thread = None
    try:
        docker('run', '-d', '--name', mock, '--network', network, '--network-alias', 'mock', *(['--cpuset-cpus', args.helper_cpuset] if args.helper_cpuset else []), 'lb-python', 'python', 'mock.py')
        # Ensure helper image has been started once before the startup measurement.
        docker('run', '--rm', 'lb-python', 'python', '-c', 'print("ready")')
        cmd = ['run', '-d', '--name', name, '--network', network, '--network-alias', 'candidate', '--cpus', '2', '--memory', '512m', '--memory-swap', '512m',
               *env_args(args.language, {'PARTNER_LIMIT': args.partner_limit})]
        if args.cpuset: cmd += ['--cpuset-cpus', args.cpuset]
        started = time.perf_counter(); docker(*cmd, image(args.language)); wait_ready(network)
        startup = time.perf_counter() - started
        # Verification includes all endpoints, the virtual-thread assertion and the Python GIL assertion.
        verification = docker('run', '--rm', '--network', network, '-v', f'{ROOT / "tests"}:/tests:ro', 'lb-python', 'python', '/tests/contract.py', 'http://candidate:8080', args.language)
        metadata = {'arguments': vars(args), 'cell_key': args.cell_key, 'control': args.control,
                    'criteria_sha256': hashlib.sha256(criteria_path.read_bytes()).hexdigest(), 'criteria': criteria,
                    'calibration': calibration, 'host': host_info(), 'candidate_meta': candidate_meta(network),
                    'startup_seconds_including_readiness_probe_container': startup,
                    'contract': verification, 'docker_version': docker('version'), 'docker_info': docker('info'),
                    'candidate_inspect': json.loads(docker('inspect', name)),
                    'candidate_image': json.loads(docker('image', 'inspect', image(args.language))),
                    'mock_image': json.loads(docker('image', 'inspect', 'lb-python')),
                    'k6_image': docker('image', 'inspect', 'grafana/k6:1.3.0', check=False),
                    'k6_version': docker('run', '--rm', 'grafana/k6:1.3.0', 'version', check=False)}
        (out / 'metadata.json').write_text(json.dumps(metadata, indent=2))
        if args.sampler == 'sidecar': set_phase('idle'); sidecar = start_sidecar(network, name, out, args.helper_cpuset)
        elif args.sampler == 'exec': thread = threading.Thread(target=exec_sample); thread.start()
        time.sleep(args.idle)
        set_phase('warmup'); warm = out / 'warmup'; warm.mkdir(); warm.chmod(0o777)
        load(network, warm, args, criteria, args.warmup)
        if args.sampler != 'sidecar': before = snapshot(name)
        set_phase('measured'); rc = load(network, out, args, criteria)
        if args.sampler != 'sidecar': after = snapshot(name)
        set_phase('recovery'); time.sleep(args.recovery)
        if args.sampler == 'sidecar':
            (out / 'stop').write_text('1'); docker('wait', sidecar, check=False)
            rows = read_rows(out / 'resources.csv')
            measured = analysis.in_phase(rows, 'measured')
            if measured: before, after = measured[0], measured[-1]
            else: before = after = None
        stop.set()
        if thread: thread.join(); thread = None
        if not (out / 'summary.json').exists(): raise RuntimeError('k6 did not produce summary; inspect load.log')
        summary = json.loads((out / 'summary.json').read_text()); metrics = summary['metrics']
        successful = metrics.get('successful_requests', {}).get('values', {}).get('count', 0)
        measured = analysis.in_phase(rows, 'measured')
        sampled = args.sampler != 'none'
        coverage = analysis.sampling_coverage(rows, 'measured') if sampled else None
        stats = {p: analysis.phase_stats(rows, p) for p in ('idle', 'warmup', 'measured', 'recovery')} if sampled else {}
        slo = criteria['slo']
        dropped = metric(metrics, 'dropped_iterations', 'count') or 0
        fail_rate = metric(metrics, 'application_failures', 'rate')
        oom_delta = (after.get('oom_kill', 0) - before.get('oom_kill', 0)) if before else None
        sampling_valid = bool(before) and not errors and (coverage is None or coverage >= 0.95)
        report = {
            'cell_key': args.cell_key, 'tag': args.tag, 'control': args.control, 'sampler': args.sampler,
            'language': args.language, 'endpoint': args.endpoint, 'profile': args.profile, 'rate': args.rate,
            'load_exit_code': rc,
            'cpu_ms_per_success': ((after['usage_usec'] - before['usage_usec']) / 1000 / successful) if successful and before else None,
            'container_memory_median_mib': stats.get('measured', {}).get('median_mib') if sampled else None,
            'container_memory_sampled_peak_mib': stats.get('measured', {}).get('peak_mib') if sampled else None,
            'memory_by_phase': stats, 'sampling_coverage_measured': coverage,
            'leak_screen': analysis.leak_screen(rows, criteria) if sampled else None,
            'recovery': analysis.recovery(rows, criteria) if sampled else None,
            'oom_kills_delta': oom_delta,
            'throttled_usec_delta': (after.get('throttled_usec', 0) - before.get('throttled_usec', 0)) if before else None,
            'nr_throttled_delta': (after.get('nr_throttled', 0) - before.get('nr_throttled', 0)) if before else None,
            'successes': successful, 'failure_rate': fail_rate, 'dropped_iterations': dropped,
            'latency_ms': {k: metric(metrics, 'application_latency', k) for k in ('p(50)', 'p(95)', 'p(99)', 'max')},
            'latency_success_ms': {k: metric(metrics, 'application_latency_success', k) for k in ('p(50)', 'p(95)', 'p(99)', 'max')},
            'latency_failure_ms': {k: metric(metrics, 'application_latency_failure', k) for k in ('p(50)', 'p(95)', 'p(99)', 'max')},
            'sampling_errors': errors,
            'slo_passed': rc == 0 and (fail_rate or 0) < slo['max_failure_rate'] and dropped <= slo['max_dropped_iterations'],
            # k6 exits 99 when thresholds are crossed (an SLO result); any other non-zero code is a broken run.
            'resource_sampling_valid': sampling_valid,
            'valid': rc in (0, 99) and (oom_delta or 0) == 0 and (sampling_valid or args.sampler == 'none'),
            'metrics': metrics}
        (out / 'report.json').write_text(json.dumps(report, indent=2)); print(out); print(json.dumps({k: v for k, v in report.items() if k != 'metrics'}, indent=2))
    finally:
        stop.set()
        if thread: thread.join(timeout=15)
        if sidecar:
            (out / 'stop').write_text('1'); docker('rm', '-f', sidecar, check=False)
        (out / 'candidate.log').write_text(docker('logs', name, check=False))
        (out / 'mock.log').write_text(docker('logs', mock, check=False))
        docker('rm', '-f', name, mock, check=False); docker('network', 'rm', network, check=False)
if __name__ == '__main__': main()
