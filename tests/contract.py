import hashlib,json,sys,urllib.request
base=sys.argv[1] if len(sys.argv)>1 else 'http://localhost:8080'
expected={'park':{'value':42},'health':{'ok':True},'partner':{'value':42},'fanout':{'total':126},'payload':{'id':7,'bytes':32768},'pycpu':{'ok':True,'iters':None},'cpu':{'digest':hashlib.sha256(b'a'*1048576).hexdigest()}}
name=sys.argv[2] if len(sys.argv)>2 else ''
MEM_OK={'membuf':{'bytes':16777216,'sum':16*sum(range(256))},'memobj':{'records':50000,'sum':50000*12+8*sum(range(50000))+28*50000}}
for endpoint,exp in MEM_OK.items():
    if name.endswith(('-gil','-nogil','-gilon')):continue
    with urllib.request.urlopen(base+'/'+endpoint,timeout=60) as r:actual=json.load(r)
    assert actual==exp,(endpoint,actual,exp)
for endpoint,result in expected.items():
    if endpoint=='pycpu' and not name.endswith(('-gil','-nogil','-gilon')):continue
    with urllib.request.urlopen(base+'/'+endpoint,timeout=30) as r:
        actual=json.load(r)
    if endpoint=='pycpu':assert actual.get('ok') is True and actual.get('iters'),(endpoint,actual);continue
    assert actual==result,(endpoint,actual,result)
with urllib.request.urlopen(base+'/meta') as r:meta=json.load(r)
if name=='java':assert meta.get('virtual') is True,meta
if name=='java-platform':assert meta.get('virtual') is False and meta.get('threads')=='platform',meta
if meta.get('runtime')=='python':
    want=False if name.endswith('-nogil') else True
    assert meta.get('gil_enabled') is want,('GIL state mismatch',want,meta)
if name.endswith('-2w'):
    import time
    deadline=time.time()+15
    while True:
        pids={json.load(urllib.request.urlopen(base+'/meta')).get('pid') for _ in range(100)}
        if len(pids)==2 or time.time()>deadline:break
        time.sleep(.5)
    assert len(pids)==2,('expected 2 worker processes, saw',pids)
try:urllib.request.urlopen(base+'/missing')
except urllib.error.HTTPError as e:assert e.code==404
else:raise AssertionError('missing endpoint must be 404')
print('PASS: five workload contracts, metadata, unknown-route status',meta)
