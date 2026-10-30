"""Run the Python candidate and mock locally; no Docker required."""
import os,pathlib,subprocess,sys,time,urllib.request
root=pathlib.Path(__file__).resolve().parents[1]
children=[]
try:
    children.append(subprocess.Popen([sys.executable,'mock.py'],cwd=root/'python',env={**os.environ,'MOCK_WORKERS':'1'},stdout=subprocess.DEVNULL,stderr=subprocess.PIPE))
    env={**os.environ,'PARTNER_URL':'http://127.0.0.1:8080','MOCK_WORKERS':'1'}
    children.append(subprocess.Popen([sys.executable,'-c',"from app import app; from aiohttp import web; web.run_app(app,port=8081,access_log=None,print=None)"],cwd=root/'python',env=env,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE))
    for _ in range(50):
        try:
            urllib.request.urlopen('http://127.0.0.1:8080/health',timeout=1)
            urllib.request.urlopen('http://127.0.0.1:8081/health',timeout=1)
            break
        except OSError:time.sleep(.1)
    subprocess.run([sys.executable,str(root/'tests/contract.py'),'http://127.0.0.1:8081','python'],check=True)
    import concurrent.futures
    def fanout(_):
        import json
        with urllib.request.urlopen('http://127.0.0.1:8081/fanout',timeout=5) as r:assert json.load(r)=={'total':126}
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as pool:list(pool.map(fanout,range(40)))
    print('PASS: 40 concurrent fanout requests')
finally:
    for c in children:c.terminate()
    for c in children:
        try:c.wait(timeout=5)
        except subprocess.TimeoutExpired:c.kill();c.wait()
