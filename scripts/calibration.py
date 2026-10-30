"""Shared helpers: how much partner traffic an offered candidate rate produces."""
import json, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[1]
CALIBRATION = ROOT / 'results' / 'calibration.json'
PEAK_MULTIPLIER = {'steady': 1, 'soak': 1, 'stress': 8, 'spike': 10}
PARTNER_CALLS = {'health': 0, 'cpu': 0, 'pycpu': 0, 'membuf': 0, 'memobj': 0, 'partner': 1, 'payload': 1, 'fanout': 3, 'park': 1}
MOCK_PATH = {'partner': '/delay', 'fanout': '/delay', 'payload': '/data', 'park': '/park'}

def load_calibration():
    return json.loads(CALIBRATION.read_text()) if CALIBRATION.exists() else None

def peak_rates(endpoint, profile, rate):
    """(peak candidate RPS, peak partner RPS) for one run."""
    peak = rate * PEAK_MULTIPLIER[profile]
    return peak, peak * PARTNER_CALLS[endpoint]

def capacity_problem(endpoint, profile, rate, calibration):
    """Return a reason string if the run would exceed calibrated helper capacity, else None."""
    if calibration is None: return 'no results/calibration.json: run scripts/calibrate.py first'
    peak, partner = peak_rates(endpoint, profile, rate)
    headroom = calibration.get('headroom', 2.0)
    if peak * headroom > calibration['generator_max_rps']:
        return f'peak {peak} RPS x{headroom} exceeds generator capacity {calibration["generator_max_rps"]}'
    if partner:
        cap = calibration['mock_max_rps'].get(MOCK_PATH[endpoint])
        if cap is None: return f'calibration has no {MOCK_PATH[endpoint]} entry: rerun scripts/calibrate.py'
        if partner * headroom > cap:
            return f'peak partner load {partner} RPS x{headroom} exceeds mock capacity {cap} on {MOCK_PATH[endpoint]}'
    return None
