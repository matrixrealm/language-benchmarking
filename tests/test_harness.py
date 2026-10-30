import importlib.util, json, pathlib, sys, unittest
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import analysis, calibration

def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / f'{name}.py')
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod

CRITERIA = json.loads((ROOT / 'criteria.json').read_text())

def rows(phase, start, seconds, mib, slope_per_s=0.0):
    return [{'time': float(start + i), 'phase': phase, 'memory_bytes': int((mib + slope_per_s * i) * analysis.MIB)} for i in range(seconds)]

class AnalysisTest(unittest.TestCase):
    def test_flat_memory_is_ok(self):
        r = analysis.leak_screen(rows('measured', 0, 3600, 100), CRITERIA)
        self.assertEqual(r['verdict'], 'ok'); self.assertAlmostEqual(r['slope_mib_per_hour'], 0, places=3)
    def test_growth_is_suspect(self):
        r = analysis.leak_screen(rows('measured', 0, 3600, 100, slope_per_s=0.01), CRITERIA)  # 36 MiB/h
        self.assertEqual(r['verdict'], 'suspect'); self.assertAlmostEqual(r['slope_mib_per_hour'], 36, delta=0.5)
    def test_short_window_is_insufficient(self):
        self.assertEqual(analysis.leak_screen(rows('measured', 0, 300, 100, 0.05), CRITERIA)['verdict'], 'insufficient_window')
    def test_recovery(self):
        data = rows('idle', 0, 120, 50) + rows('recovery', 1000, 300, 60)
        r = analysis.recovery(data, CRITERIA); self.assertEqual(r['verdict'], 'ok'); self.assertAlmostEqual(r['ratio'], 1.2)
        self.assertEqual(analysis.recovery(rows('idle', 0, 120, 50) + rows('recovery', 1000, 300, 90), CRITERIA)['verdict'], 'retained')
    def test_coverage_detects_gaps(self):
        full = rows('measured', 0, 100, 1); gappy = full[:40] + full[60:]
        self.assertAlmostEqual(analysis.sampling_coverage(full, 'measured'), 1.0); self.assertLess(analysis.sampling_coverage(gappy, 'measured'), 0.85)

class CalibrationTest(unittest.TestCase):
    CAL = {'headroom': 2.0, 'generator_max_rps': 6000, 'mock_max_rps': {'/delay': 4500, '/data': 3000}}
    def test_fanout_triples_partner_load(self):
        self.assertEqual(calibration.peak_rates('fanout', 'steady', 500), (500, 1500))
        self.assertIsNone(calibration.capacity_problem('fanout', 'steady', 500, self.CAL))   
    def test_over_capacity_rejected(self):
        self.assertIn('mock capacity', calibration.capacity_problem('fanout', 'steady', 1000, self.CAL))
        self.assertIn('generator capacity', calibration.capacity_problem('partner', 'spike', 500, self.CAL))
    def test_missing_calibration(self):
        self.assertIn('calibrate.py', calibration.capacity_problem('partner', 'steady', 10, None))

class MatrixTest(unittest.TestCase):
    def test_every_language_takes_every_position(self):
        m = load('matrix')
        o3=m.orders(['java','go','python'])
        for pos in range(3): self.assertEqual({o[pos] for o in o3[:3]}, {'java', 'go', 'python'})
        self.assertEqual(len({tuple(o) for o in o3}), 6)

class SummarizeTest(unittest.TestCase):
    @staticmethod
    def cell(lang, vals, slo=True): return {'language': lang, 'slo_all': slo, 'values': {'memory_mib': vals}}
    def test_clear_difference(self):
        s = load('summarize')
        self.assertIn('go lower by', s.compare(self.cell('go', [100, 102, 101]), self.cell('java', [150, 152, 151]), 'memory_mib', 10, 3))
    def test_overlap_or_small_gap_is_inconclusive(self):
        s = load('summarize')
        self.assertIn('inconclusive', s.compare(self.cell('go', [100, 120, 101]), self.cell('java', [110, 130, 125]), 'memory_mib', 10, 3))
        self.assertIn('inconclusive', s.compare(self.cell('go', [100, 101, 102]), self.cell('java', [105, 106, 107]), 'memory_mib', 10, 3))
    def test_noise_raises_threshold_and_slo_failure_is_capacity(self):
        s = load('summarize')
        self.assertIn('inconclusive', s.compare(self.cell('go', [100, 101, 102]), self.cell('java', [120, 121, 122]), 'memory_mib', 25, 3))
        self.assertIn('capacity limited', s.compare(self.cell('go', [1, 1, 1]), self.cell('java', [9, 9, 9], slo=False), 'memory_mib', 10, 3))
    def test_too_few_repeats(self):
        s = load('summarize'); self.assertIn('too few', s.compare(self.cell('go', [1]), self.cell('java', [9]), 'memory_mib', 10, 3))

if __name__ == '__main__': unittest.main()
