"""Build the presentation-style pages for the cloud1 rerun (3 repeats on a GitHub Actions runner), written to results/.
Reuses the page and the test-code excerpts of scripts/report_story.py and scripts/report_story_code.py without modifying them.
  python rerun/reports/build_story.py [--data rerun/reports/data] [--outdir results]
writes results/cloud1-presentation.html and results/cloud1-presentation_with_test_code_and_steps.html"""
import argparse, json, pathlib, sys, time
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import report_story, report_story_code
from report_html import collect

CLOUD1 = ('aiohttp', 'fastapi', 'django', 'gil-ceiling', 'threads-cost')  # rerun2 batches are not part of these pages
HOST = 'free GitHub Actions runner: 4 vCPU AMD EPYC 7763, 16 GB'
RUNNER_CMD = {'l1': 'python rerun/ci_batch.py threads-cost', 'l4': 'python rerun/ci_batch.py threads-cost',
              'l7': 'python rerun/ci_batch.py aiohttp\npython rerun/ci_batch.py fastapi\npython rerun/ci_batch.py django\npython rerun/ci_batch.py gil-ceiling'}
NOTE = ('Each batch is one GitHub Actions job (.github/workflows/rerun.yml). rerun/ci_batch.py calls scripts/matrix.py with '
        '--repeats 3 --fast --tag cloud1, the candidate on CPUs 0,1 and the fake partner, k6 and sampler on CPUs 2,3.')

def patch(page, pairs):
    for a, b in pairs:
        assert a in page, a
        page = page.replace(a, b)
    return page

JS = [  # a cell passes only if all repeats pass; show how many did
    ("c.pass=R.every(r=>r.slo_passed);", "c.pass=R.every(r=>r.slo_passed);c.np=R.filter(r=>r.slo_passed).length;c.n=R.length;"),
    ("f(x.p99,x.p99<10?1:0)+' ms'}</small>", "f(x.p99,x.p99<10?1:0)+' ms'} &middot; ${x.np}/${x.n}</small>"),
]
TEXT = [
    ('<title>Java, Go and Python benchmark story</title>', '<title>Cloud rerun: Java, Go and Python benchmark story</title>'),
    ('<b>Honest limits.</b> One laptop, short 3-minute runs, mostly one repeat per cell. Treat the results as strong directional evidence, not final proof. The detailed charts are in <a href="report.html">report.html</a>.',
     '<b>Honest limits.</b> A free, shared 4-vCPU GitHub Actions runner, 3-minute measured runs, 3 repeats per cell. A cell is green only if all 3 repeats pass; the small text is the median response time and how many repeats passed (for example 2/3). '
     'Only the waiting-call, memory and Python GIL experiments were rerun, so the other levels from the laptop pilot are not on this page. Detailed analysis: <a href="../rerun/reports/cloud1-report.html">cloud1-report.html</a>. The laptop version is <a href="presentation.html">presentation.html</a>.'),
]

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--data', default=str(ROOT / 'rerun' / 'reports' / 'data'))
    p.add_argument('--outdir', default=str(ROOT / 'results'))
    a = p.parse_args()
    runs = []
    for d in sorted(pathlib.Path(a.data).iterdir()):
        if d.is_dir() and d.name in CLOUD1: runs += collect(d)
    for r in runs: r['series'] = []
    data = {'runs': runs, 'host': HOST, 'criteria': json.loads((ROOT / 'criteria.json').read_text()), 'generated': time.strftime('%Y-%m-%d %H:%M')}
    report_story.PAGE = patch(report_story.PAGE, JS)
    for k, c in RUNNER_CMD.items():
        for s in report_story_code.CODE[k]:
            if s['role'] == 'cmd': s.update(title='Commands that ran the cloud batches', note=NOTE, code=c)
    out = pathlib.Path(a.outdir); out.mkdir(exist_ok=True)
    plain = patch(report_story.PAGE, TEXT)
    code = report_story_code.build()
    code = patch(code, [(a_, b_) for a_, b_ in TEXT if a_ in code] + [('<title>Benchmark story with test code and steps</title>', '<title>Cloud rerun: benchmark story with test code and steps</title>')])
    for name, page, extra in (('cloud1-presentation.html', plain, {}),
                              ('cloud1-presentation_with_test_code_and_steps.html', code, {'code': report_story_code.CODE, 'steps': report_story_code.STEPS})):
        (out / name).write_text(page.replace('__DATA__', json.dumps({**data, **extra}).replace('</', '<\\/')), encoding='utf-8')
        print(out / name, len(runs), 'runs')

if __name__ == '__main__': main()
