"""Pure functions turning resources.csv rows into memory-phase statistics, leak slope and recovery."""
import statistics

MIB = 1048576

def in_phase(rows, phase):
    return [r for r in rows if r['phase'] == phase]

def phase_stats(rows, phase):
    xs = [r['memory_bytes'] for r in in_phase(rows, phase)]
    if not xs: return {'samples': 0, 'median_mib': None, 'peak_mib': None}
    return {'samples': len(xs), 'median_mib': statistics.median(xs) / MIB, 'peak_mib': max(xs) / MIB}

def slope_mib_per_hour(rows):
    """Least-squares slope of memory over time; None with fewer than 3 points or no time spread."""
    if len(rows) < 3: return None
    t0 = rows[0]['time']; xs = [r['time'] - t0 for r in rows]; ys = [r['memory_bytes'] / MIB for r in rows]
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    var = sum((x - mx) ** 2 for x in xs)
    if var == 0: return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / var * 3600

def leak_screen(rows, criteria, skip_fraction=0.2):
    """Slope over the measured phase after discarding the first fraction (still warming heaps).
    A screen only: 'suspect' means look closer, 'ok' is not proof of no leak."""
    measured = in_phase(rows, 'measured')
    window = (measured[-1]['time'] - measured[0]['time']) / 60 if len(measured) > 1 else 0
    tail = measured[int(len(measured) * skip_fraction):]
    slope = slope_mib_per_hour(tail)
    cfg = criteria['leak']
    if slope is None or window < cfg['min_window_minutes']:
        verdict = 'insufficient_window'
    else:
        verdict = 'suspect' if slope > cfg['max_slope_mib_per_hour'] else 'ok'
    return {'window_minutes': window, 'slope_mib_per_hour': slope, 'verdict': verdict}

def recovery(rows, criteria, tail_seconds=60):
    """Memory in the last minute of no-traffic recovery relative to the idle median.
    Retained memory can be allocator/heap reuse, so this flags rather than convicts."""
    idle = phase_stats(rows, 'idle')['median_mib']
    rec = in_phase(rows, 'recovery')
    if not idle or not rec: return {'idle_median_mib': idle, 'final_median_mib': None, 'ratio': None, 'verdict': 'no_data'}
    end = rec[-1]['time']
    final = statistics.median(r['memory_bytes'] for r in rec if r['time'] >= end - tail_seconds) / MIB
    ratio = final / idle
    return {'idle_median_mib': idle, 'final_median_mib': final, 'ratio': ratio,
            'verdict': 'retained' if ratio > criteria['recovery']['max_ratio_to_idle'] else 'ok'}

def sampling_coverage(rows, phase, interval=1.0):
    """Captured samples over the samples a gap-free phase of the same span would hold."""
    xs = in_phase(rows, phase)
    if len(xs) < 2: return 0.0
    return len(xs) / ((xs[-1]['time'] - xs[0]['time']) / interval + 1)
