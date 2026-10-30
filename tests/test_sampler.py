import importlib.util,pathlib,unittest
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('runner',pathlib.Path(__file__).resolve().parents[1]/'scripts/run.py')
runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
class SamplerTest(unittest.TestCase):
    def test_cgroup_and_process_fields(self):
        fixture='1048576\nusage_usec 2500\nnr_periods 10\nnr_throttled 3\nthrottled_usec 17\nMEMORY_EVENTS\noom 1\noom_kill 0\nPROCESS\nName:\tjava\nVmRSS:\t2048 kB\nThreads:\t12\n'
        with patch.object(runner,'docker',return_value=fixture):r=runner.snapshot('candidate')
        self.assertEqual(r['memory_bytes'],1048576)
        self.assertEqual(r['rss_bytes'],2097152)
        self.assertEqual(r['usage_usec'],2500)
        self.assertEqual(r['nr_throttled'],3)
        self.assertEqual(r['oom'],1)
        self.assertEqual(r['os_threads'],12)
if __name__=='__main__':unittest.main()
