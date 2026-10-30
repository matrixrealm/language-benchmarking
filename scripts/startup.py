"""Cold-start measurement: N fresh container starts of one candidate, no load.

A persistent prober container (started once, before any measured start) polls the candidate's
/health every few ms and prints UP/DOWN transitions. The host timestamps the moment the UP line
arrives, so helper-container startup is not inside the measurement (the old run.py number included
a throwaway readiness container). Time covers `docker run` -> first successful /health, i.e. image
already pulled, container create + runtime boot + listener ready."""
import argparse, json, pathlib, statistics, subprocess, sys, threading, time, uuid
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from calibration import ROOT
from candidates import CANDIDATES, env_args, image

PROBER = ("import sys,time,urllib.request\n"
          "up=False\n"
          "while True:\n"
          " try:\n"
          "  urllib.request.urlopen('http://candidate:8080/health',timeout=.25).read();now=True\n"
          " except Exception:now=False\n"
          " if now!=up:print('UP' if now else 'DOWN',flush=True);up=now\n"
          " time.sleep(.003)\n")

def docker(*a, check=True):
    return subprocess.run(['docker', *map(str, a)], capture_output=True, text=True, check=check).stdout.strip()

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--language', choices=sorted(CANDIDATES), required=True)
    p.add_argument('--starts', type=int, default=10); p.add_argument('--timeout', type=float, default=60)
    p.add_argument('--cpuset', default='')
    a = p.parse_args()
    network = 'lb-st-' + uuid.uuid4().hex[:8]; mock = network + '-mock'; prober = network + '-prober'; name = network + '-candidate'
    out = ROOT / 'results' / f'startup-{time.strftime("%Y%m%d-%H%M%S")}-{a.language}'; out.mkdir(parents=True)
    docker('network', 'create', network)
    up = threading.Event(); lines = []
    try:
        docker('run', '-d', '--name', mock, '--network', network, '--network-alias', 'mock', 'lb-python', 'python', 'mock.py')
        docker('run', '-d', '--name', prober, '--network', network, 'lb-python', 'python', '-u', '-c', PROBER)
        proc = subprocess.Popen(['docker', 'logs', '-f', prober], stdout=subprocess.PIPE, text=True, bufsize=1)
        def watch():
            for line in proc.stdout:
                lines.append((time.perf_counter(), line.strip()))
                if line.strip() == 'UP': up.set()
        threading.Thread(target=watch, daemon=True).start()
        time.sleep(2)
        times = []
        for i in range(a.starts):
            up.clear(); lines.clear()
            cmd = ['run', '-d', '--name', name, '--network', network, '--network-alias', 'candidate', '--cpus', '2', '--memory', '512m', '--memory-swap', '512m', *env_args(a.language)]
            if a.cpuset: cmd += ['--cpuset-cpus', a.cpuset]
            t0 = time.perf_counter(); docker(*cmd, image(a.language))
            if not up.wait(a.timeout): raise RuntimeError(f'start {i}: candidate not up within {a.timeout}s')
            t_up = next(t for t, l in lines if l == 'UP')
            times.append(t_up - t0)
            print(f'start {i + 1}/{a.starts}: {times[-1]:.3f}s', flush=True)
            docker('rm', '-f', name)
            time.sleep(1)  # let the prober observe DOWN before the next start
        result = {'language': a.language, 'starts': a.starts, 'seconds': times, 'median': statistics.median(times), 'min': min(times), 'max': max(times),
                  'method': 'persistent prober, 3 ms poll; includes docker run create/start overhead, excludes helper startup'}
        (out / 'startup.json').write_text(json.dumps(result, indent=2)); print(json.dumps(result, indent=2))
    finally:
        docker('rm', '-f', name, prober, mock, check=False); docker('network', 'rm', network, check=False)

if __name__ == '__main__': main()
