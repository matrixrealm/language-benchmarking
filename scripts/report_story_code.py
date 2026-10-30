"""Build results/presentation_with_test_code_and_steps.html: results/presentation.html plus, for every level, the code that
generated the traffic, the fake partner it called, and the services under test (excerpts read live from the repo).
results/presentation.html and scripts/report_story.py are not modified.
usage: python scripts/report_story_code.py [--out results/presentation_with_test_code_and_steps.html]"""
import argparse, json, pathlib, sys, time
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from calibration import ROOT
from report_html import collect
import report_story

def ex(file, parts):
    """Excerpt(s) of a repo file: parts = [(substring, n_lines)] -> text with a file:line header per excerpt."""
    lines = (ROOT / file).read_text(encoding='utf-8').splitlines(); out = []
    for sub, n in parts:
        i = next((k for k, l in enumerate(lines) if sub in l), None)
        if i is None: raise SystemExit(f'anchor not found in {file}: {sub}')
        out.append(f'// {file}:{i + 1}-{i + n}\n' + '\n'.join(lines[i:i + n]))
    return '\n\n'.join(out)

def S(role, title, note, file, parts): return {'role': role, 'title': title, 'note': note, 'code': ex(file, parts)}
K6 = lambda note: S('traffic', 'k6 load script: the request that is repeated (load/test.js)', note, 'load/test.js', [('export default function', 8)])
MOCK_DELAY = S('partner', 'Fake partner: answers after 100 ms (python/mock.py)', 'Stands in for a channel manager or payment provider. It simply waits 100 ms and replies {"value": 42}.', 'python/mock.py', [('DELAY =', 1), ('async def delay', 3)])
CMD = lambda c: {'role': 'cmd', 'title': 'Command that ran the traffic levels', 'note': 'The matrix runner starts a fresh set of containers for every traffic level and records the result.', 'code': c}

CODE = {
 'l1': [K6('Fires GET /partner at a fixed number of requests per second (constant arrival rate) and checks the reply is {"value": 42}.'),
        MOCK_DELAY,
        S('svc', 'Go (go/main.go)', 'Each request runs in its own goroutine; fetch() calls the partner and decodes the JSON.', 'go/main.go', [('fetch:=func', 6), ('case "/partner"', 1)]),
        S('svc', 'Java, virtual threads (java/Main.java)', 'One virtual thread per request; the blocking HTTP call parks that thread cheaply.', 'java/Main.java', [('static JsonNode fetch', 6), ('case "/partner"', 1)]),
        S('svc', 'Python, aiohttp (python/app.py)', 'One event loop; `await` hands control to other requests during the 100 ms wait.', 'python/app.py', [('async def handle', 7), ("elif path == '/partner'", 1)]),
        S('svc', 'FastAPI (fastapi/app.py)', 'Same idea through the FastAPI framework on uvicorn.', 'fastapi/app.py', [('async def fetch', 4), ("@app.get('/partner')", 3)]),
        S('svc', 'Django, async views (django/app.py)', 'Django on uvicorn with an async view.', 'django/app.py', [('async def fetch', 4), ("elif path == 'partner'", 1)]),
        CMD('python scripts/matrix.py --group core   --pass coarse --fast --tag p1 --endpoints partner,payload,cpu\npython scripts/matrix.py --group python --pass coarse --fast --tag p2 --endpoints partner --rates 500,1000')],
 'l2': [K6('Fires GET /fanout and checks the reply is {"total": 126} (three answers of 42 added together).'),
        MOCK_DELAY,
        S('svc', 'Go', 'Three goroutines call the partner at once; a WaitGroup waits for all three.', 'go/main.go', [('case "/fanout"', 4)]),
        S('svc', 'Java, virtual threads', 'Three tasks are submitted to the executor and their results added up.', 'java/Main.java', [('case "/fanout"', 3)]),
        S('svc', 'Python, aiohttp', 'asyncio.gather runs the three calls concurrently on the event loop.', 'python/app.py', [("elif path == '/fanout'", 1)]),
        S('svc', 'FastAPI', 'Same gather pattern.', 'fastapi/app.py', [("@app.get('/fanout')", 4)]),
        CMD('python scripts/matrix.py --group core    --pass coarse --fast --tag p1 --endpoints fanout --rates 50,150,300\npython scripts/matrix.py --group threads --pass coarse --fast --tag p2 --endpoints fanout --rates 150,300\npython scripts/matrix.py --group python  --pass coarse --fast --tag p2 --endpoints fanout --rates 300')],
 'l3': [K6('Fires GET /payload and checks the reply is {"id": 7, "bytes": 32768}.'),
        S('partner', 'Fake partner: returns a 32 KB JSON document (python/mock.py)', 'The partner replies at once with about 32 KB of JSON (no delay), so the work is receiving and parsing that body.', 'python/mock.py', [('DATA =', 1), ('async def data', 1)]),
        S('svc', 'Go', 'Reads the whole body, parses the JSON, reports the blob length.', 'go/main.go', [('case "/payload"', 1)]),
        S('svc', 'Java, virtual threads', 'Parses the JSON with Jackson.', 'java/Main.java', [('case "/payload"', 1)]),
        S('svc', 'Python, aiohttp', 'Awaits the body, parses JSON.', 'python/app.py', [("elif path == '/payload'", 2)]),
        S('svc', 'FastAPI', 'Same through FastAPI.', 'fastapi/app.py', [("@app.get('/payload')", 5)]),
        CMD('python scripts/matrix.py --group core   --pass coarse --fast --tag p1 --endpoints partner,payload,cpu\npython scripts/matrix.py --group core   --pass coarse --fast --tag p2 --endpoints payload --rates 1500,2000\npython scripts/matrix.py --group python --pass coarse --fast --tag p2 --endpoints payload --rates 1000,2000')],
 'l4': [K6('Fires GET /park. Each request is held about one second by the partner, so N requests per second means about N requests in flight at once.'),
        S('partner', 'Fake partner: holds the connection for 1 second (python/mock.py)', 'Same as the 100 ms partner but it waits PARK_MS (1000 ms) before replying.', 'python/mock.py', [('PARK_SECONDS', 4)]),
        S('svc', 'Java: virtual vs classic threads (java/Main.java)', 'The same code runs in two modes. Virtual: one cheap virtual thread per request. Classic (java-platform): a fixed pool of 200 operating-system threads, so 200 slow requests fill it and the rest queue.', 'java/Main.java', [('static final boolean VIRTUAL', 5), ('case "/park"', 1)]),
        S('svc', 'Go', 'net/http already starts one goroutine per request, so no special code is needed.', 'go/main.go', [('case "/park"', 1)]),
        S('cfg', 'How the two Java candidates differ (scripts/candidates.py)', 'Only the environment differs, not the code.', 'scripts/candidates.py', [("'java':", 2)]),
        CMD('python scripts/matrix.py --group threads --pass coarse --fast --tag p2 --endpoints park --rates 250,1000,2000')],
 'l5': [K6('Fires GET /cpu and checks the hash equals the expected SHA-256 value computed by the runner (CPU_DIGEST).'),
        S('svc', 'Go', 'Hashes the same 1 MiB buffer 100 times (about 45 ms of CPU).', 'go/main.go', [('var input', 1), ('case "/cpu"', 1)]),
        S('svc', 'Java', 'Same 100 SHA-256 rounds.', 'java/Main.java', [('case "/cpu"', 1)]),
        S('svc', 'Python, aiohttp', 'Runs directly on the event loop, so while it hashes no other request is served: this is the one-core effect.', 'python/app.py', [("elif path == '/cpu'", 3)]),
        S('svc', 'FastAPI', 'Also runs on the event loop, deliberately.', 'fastapi/app.py', [("@app.get('/cpu')", 5)]),
        S('svc', 'Python GIL study: work moved to a 4-thread pool (gil/app_aiohttp.py)', 'In the GIL experiment the hashing runs in a thread pool, so hashlib (which releases the GIL) can use several cores.', 'gil/app_aiohttp.py', [('def hashing', 3), ("elif path == '/cpu'", 2)]),
        CMD('python scripts/matrix.py --group core   --pass coarse --fast --tag p1 --endpoints partner,payload,cpu\npython scripts/matrix.py --group core   --pass coarse --fast --tag p2 --endpoints cpu --rates 20,30,40\npython scripts/matrix.py --group python --pass coarse --fast --tag p2 --endpoints cpu --rates 10,30')],
 'l6': [K6('Fires GET /membuf or GET /memobj and checks the reply against the expected sums (so nobody can skip the work).'),
        S('svc', 'Go: membuf and memobj', 'membuf allocates and writes a 16 MiB block. memobj builds 50,000 records with a name and eight numbers each.', 'go/main.go', [('case "/membuf"', 1), ('case "/memobj"', 1)]),
        S('svc', 'Java: membuf and memobj', 'Same work with a byte[] and an ArrayList of records.', 'java/Main.java', [('case "/membuf"', 1), ('case "/memobj"', 1)]),
        S('svc', 'Python, aiohttp (also used by FastAPI and Django)', 'Same work with a bytearray and a list of dicts. The FastAPI and Django apps contain the identical two functions.', 'python/app.py', [('def membuf', 9)]),
        CMD('python scripts/matrix.py --group mem --pass coarse --fast --tag p4 --endpoints membuf --rates 10,20,40\npython scripts/matrix.py --group mem --pass coarse --fast --tag p4 --endpoints memobj --rates 10,20,40')],
 'l7': [K6('Fires GET /pycpu (and /cpu, /partner, /payload) at each rate.'),
        S('svc', 'The pure-Python work (gil/app_aiohttp.py)', 'burn() is plain Python arithmetic, so it holds the GIL the whole time. It runs in a 4-thread pool.', 'gil/app_aiohttp.py', [('def burn', 5), ("elif path == '/pycpu'", 1), ('POOL =', 1)]),
        S('cfg', 'Two Python builds from one Dockerfile (gil/Dockerfile)', 'PYVER=3.14 builds the standard interpreter; PYVER=3.14t builds the free-threaded one. APP chooses aiohttp, FastAPI or Django.', 'gil/Dockerfile', [('ARG PYVER', 1), ('CMD', 1)]),
        S('cfg', 'The seven candidates (scripts/candidates.py)', 'PYTHON_GIL=0 turns the GIL off; the aiohttp-t-gilon control runs the free-threaded build with PYTHON_GIL=1 so the effect of removing the GIL is isolated.', 'scripts/candidates.py', [("'aiohttp-gil':", 7)]),
        CMD('python scripts/matrix.py --group gil --candidates aiohttp-gil,aiohttp-nogil,fastapi-gil,fastapi-nogil,django-gil,django-nogil --pass coarse --fast --tag p3 --endpoints pycpu --rates 10,15,20,25,30,40\npython scripts/matrix.py --group gil ... --endpoints cpu --rates 20,30,40,50\npython scripts/matrix.py --group gil ... --endpoints partner --rates 1000\npython scripts/matrix.py --group gil ... --endpoints payload --rates 2000')],
}
STEPS = [
 S('traffic', 'The whole k6 script (load/test.js)', 'k6 is the load generator. "constant-arrival-rate" sends a fixed number of new requests per second whatever the server does, which is how real users behave. Thresholds encode the pass/fail rules; a request only counts as good if the reply content is correct.', 'load/test.js', [('import http', 25)]),
 S('harness', 'Start the fake partner and the service under test (scripts/run.py)', 'Each run creates a private Docker network, starts the fake partner, then the candidate limited to 2 CPUs and 512 MiB with no swap.', 'scripts/run.py', [('docker(\'network\', \'create\'', 8)]),
 S('harness', 'Start k6 (scripts/run.py)', 'k6 runs in its own container on the same network and talks to the service at http://candidate:8080.', 'scripts/run.py', [('def load(', 13)]),
 S('harness', 'Phases and timings (scripts/matrix.py)', 'Every run: 30 s idle, 2 min warm-up (ignored), 3 min measured, 60 s recovery (the quick profile used here; the full profile is longer).', 'scripts/matrix.py', [('FAST =', 1)]),
 S('harness', 'The pass/fail rules (criteria.json)', 'Fixed before the first run. p99 means 99 of 100 requests were at least this fast.', 'criteria.json', [('"slo"', 1)]),
 S('harness', 'Recording CPU and memory from outside the service (scripts/run.py)', 'A separate sampler container reads the service container\'s CPU and memory counters once a second, so measuring does not slow the service.', 'scripts/run.py', [('def start_sidecar', 10)]),
]
CSS = '''.src{margin:8px 0}.src summary{cursor:pointer;font-weight:600;font-size:14px;padding:6px 10px;background:var(--card);border:1px solid var(--line);border-radius:8px}
.src[open] summary{border-bottom-left-radius:0;border-bottom-right-radius:0}.src .nt{color:var(--mut);font-size:13px;margin:0;padding:8px 12px;background:var(--card);border-left:1px solid var(--line);border-right:1px solid var(--line)}
.src pre{margin:0;padding:10px 12px;background:#1c1917;color:#e7e5e4;font:12.5px/1.45 ui-monospace,Consolas,monospace;overflow-x:auto;border:1px solid var(--line);border-radius:0 0 8px 8px;white-space:pre}
.role{display:inline-block;font-size:11px;border-radius:10px;padding:0 8px;margin-right:6px;color:#fff}.role.traffic{background:#0e7490}.role.partner{background:#a16207}.role.svc{background:#15803d}.role.cfg{background:#6d28d9}.role.cmd{background:#475569}.role.harness{background:#475569}
.flow{display:flex;gap:6px;align-items:stretch;flex-wrap:wrap;margin:10px 0}.flow div{flex:1;min-width:150px;background:var(--card);border:1px solid var(--line);border-radius:8px;padding:8px;font-size:13px}.flow b{display:block}.flow .ar{flex:0 0 auto;min-width:0;border:0;background:none;align-self:center;font-size:20px;padding:0}'''
ROLE = {'traffic': 'Traffic generator', 'partner': 'Fake partner', 'svc': 'Service under test', 'cfg': 'Setup', 'cmd': 'Run command', 'harness': 'Test harness'}
STEPS_HTML = '''<section id="steps"><h2>How a test runs, step by step</h2>
<p>Every number on this page comes from the same repeatable recipe. The code below is read directly from the project files.</p>
<div class="flow"><div><b>1. k6 (traffic generator)</b>Sends a fixed number of requests per second.</div><div class="ar">&rarr;</div><div><b>2. Service under test</b>Go, Java, Python, FastAPI or Django, limited to 2 CPUs and 512 MiB.</div><div class="ar">&rarr;</div><div><b>3. Fake partner</b>Replies after 100 ms (or 1 s, or with a 32 KB body).</div></div>
<div class="flow"><div><b>4. Sampler</b>Reads CPU and memory counters from outside.</div><div class="ar">&rarr;</div><div><b>5. Judge</b>Compares p99, error rate and dropped requests with the rules.</div><div class="ar">&rarr;</div><div><b>6. Report</b>Everything is saved as JSON and turned into these pages.</div></div>
<div id="stepcode"></div></section>
<div id="story"></div>'''

def build():
    P = report_story.PAGE
    def rep(a, b):
        nonlocal P
        assert a in P, a
        P = P.replace(a, b)
    rep('<title>Java, Go and Python benchmark story</title>', '<title>Benchmark story with test code and steps</title>')
    rep('</style>', CSS + '</style>')
    rep('<div id="story"></div>', STEPS_HTML)
    rep("[['how','How to read']]", "[['how','How to read'],['steps','How a test runs']]")
    rep('Big replies: move about 1 MB per request', 'Bigger replies: about 32 KB per partner call')
    rep('Each request fetches a large (about 1 MB) answer from the partner and returns a summary.', 'Each request fetches a larger (about 32 KB) answer from the partner, parses it and returns a summary.')
    rep('Large messages stress memory and the network more than waiting does.', 'Receiving and parsing bigger messages costs more CPU and memory than a tiny reply.')
    rep("payload:'1 MB replies'", "payload:'32 KB replies'")
    rep("$('story').appendChild(sec)});", "sec.appendChild(codePanel(S.id));$('story').appendChild(sec)});\n$('stepcode').appendChild(srcList(DATA.steps));")
    rep("const SEC=[", r'''const esc=s=>s.replace(/&/g,'&amp;').replace(/</g,'&lt;');
const ROLE=__ROLE__;
function srcList(items){const d=document.createElement('div');d.innerHTML=items.map(s=>`<details class="src"><summary><span class="role ${s.role}">${ROLE[s.role]}</span>${esc(s.title)}</summary><p class="nt">${esc(s.note)}</p><pre>${esc(s.code)}</pre></details>`).join('');return d}
function codePanel(id){const d=document.createElement('div');const items=DATA.code[id]||[];
 d.innerHTML='<h3>How this level was simulated (click to open the code)</h3>';d.appendChild(srcList(items));return d}
const SEC=[''')
    rep('Read the sections from top to bottom: each one raises the difficulty.', 'Read the sections from top to bottom: each one raises the difficulty, and each shows the exact code that created the traffic, the fake partner and the services.')
    return P.replace('__ROLE__', json.dumps(ROLE))

def main():
    p = argparse.ArgumentParser(); p.add_argument('--out', default=str(ROOT / 'results' / 'presentation_with_test_code_and_steps.html')); a = p.parse_args()
    results = ROOT / 'results'; runs = collect(results)
    for r in runs: r['series'] = []
    host = None
    for d in sorted(results.iterdir()):
        m = d / 'metadata.json'
        if m.exists():
            h = json.loads(m.read_text()).get('host', {}); host = f'{h.get("cpu_name")} ({h.get("cpu_count")} CPUs)'; break
    data = {'runs': runs, 'host': host, 'criteria': json.loads((ROOT / 'criteria.json').read_text()), 'generated': time.strftime('%Y-%m-%d %H:%M'), 'code': CODE, 'steps': STEPS}
    pathlib.Path(a.out).write_text(build().replace('__DATA__', json.dumps(data).replace('</', '<\\/')), encoding='utf-8')
    print(f'{a.out}: {len(runs)} runs, {sum(len(v) for v in CODE.values())} code blocks')

if __name__ == '__main__': main()
