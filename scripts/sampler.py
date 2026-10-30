"""Out-of-candidate cgroup sampler. Runs in its own container with --pid host and the host cgroup
tree mounted read-only, so reading counters costs the candidate nothing (the earlier docker-exec
sampler forked sh/cat inside the candidate's cgroup every second and was charged to it).

usage: sampler.py <container-id> <host-pid> <results-dir> [interval-seconds]
Writes <results-dir>/resources.csv; reads the current phase from <results-dir>/phase and exits
when <results-dir>/stop appears."""
import csv, os, pathlib, sys, time

FIELDS = ['time', 'phase', 'memory_bytes', 'rss_bytes', 'usage_usec', 'nr_throttled', 'throttled_usec', 'oom', 'oom_kill', 'os_threads']

def find_cgroup(root, container_id, depth=4):
    """The container's cgroup directory is named <id> (cgroupfs) or docker-<id>.scope (systemd)."""
    for base, dirs, _ in os.walk(root):
        if base[len(root):].count('/') >= depth: dirs[:] = []
        for d in dirs:
            if d == container_id or (container_id in d and d.endswith('.scope')): return os.path.join(base, d)
    raise SystemExit(f'cgroup for {container_id} not found under {root}')

def kv(path, wanted):
    out = {}
    with open(path) as f:
        for line in f:
            k, _, v = line.partition(' ')
            if k in wanted: out[k] = int(v)
    return out

def read(cg, pid):
    row = {'memory_bytes': int(open(f'{cg}/memory.current').read())}
    row.update(kv(f'{cg}/cpu.stat', ('usage_usec', 'nr_throttled', 'throttled_usec')))
    row.update(kv(f'{cg}/memory.events', ('oom', 'oom_kill')))
    for line in open(f'/proc/{pid}/status'):
        if line.startswith('VmRSS:'): row['rss_bytes'] = int(line.split()[1]) * 1024
        elif line.startswith('Threads:'): row['os_threads'] = int(line.split()[1])
    return row

def main():
    container_id, pid, results = sys.argv[1], sys.argv[2], pathlib.Path(sys.argv[3])
    interval = float(sys.argv[4]) if len(sys.argv) > 4 else 1.0
    cg = find_cgroup('/host-cgroup', container_id)
    with (results / 'resources.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS); writer.writeheader(); f.flush()
        (results / 'sampler.ready').write_text(cg)
        nxt = time.monotonic()
        while not (results / 'stop').exists():
            try:
                phase = (results / 'phase').read_text().strip() if (results / 'phase').exists() else 'idle'
                row = read(cg, pid); row['time'] = time.time(); row['phase'] = phase
                writer.writerow(row); f.flush()
            except OSError as e:  # candidate gone or file mid-rotation: leave a gap, the host counts samples
                print('sample error:', e, file=sys.stderr, flush=True)
            nxt += interval
            time.sleep(max(0, nxt - time.monotonic()))

if __name__ == '__main__': main()
