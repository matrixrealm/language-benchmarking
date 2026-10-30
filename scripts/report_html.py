"""Build a self-contained, categorized results/report.html (inline SVG charts, no network) from results/*.
usage: python scripts/report_html.py [--out results/report.html]"""
import argparse, csv, json, pathlib, sys, time
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from calibration import ROOT

def collect(results):
    runs = []
    for d in sorted(results.iterdir()):
        rp = d / 'report.json'
        if not rp.exists(): continue
        r = json.loads(rp.read_text()); r.pop('metrics', None)
        series = []
        cp = d / 'resources.csv'
        if cp.exists():
            with cp.open() as f:
                rows = list(csv.DictReader(f))
            if rows:
                t0 = float(rows[0]['time'])
                series = [[round(float(x['time']) - t0, 1), round(int(x['memory_bytes']) / 1048576, 1), x['phase']] for x in rows[::4]]
        r['id'] = d.name; r['series'] = series
        runs.append(r)
    return runs

PAGE = r'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Language benchmark report</title><style>
:root{--bg:#fafaf9;--fg:#1c1917;--mut:#78716c;--card:#fff;--line:#e7e5e4;--ok:#16a34a;--bad:#dc2626;--okbg:#dcfce7;--badbg:#fee2e2;--warn:#ca8a04}
@media(prefers-color-scheme:dark){:root{--bg:#161412;--fg:#f5f5f4;--mut:#a8a29e;--card:#1f1c1a;--line:#3a3532;--ok:#4ade80;--bad:#f87171;--okbg:#14351f;--badbg:#4a1d1d}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,sans-serif}
header{padding:20px 16px 8px;max-width:1180px;margin:0 auto}h1{font-size:24px;margin:0 0 4px}
nav{position:sticky;top:0;background:var(--bg);border-bottom:1px solid var(--line);z-index:5;overflow-x:auto;white-space:nowrap}
nav div{max-width:1180px;margin:0 auto;padding:8px 16px}nav a{color:var(--fg);text-decoration:none;font-size:13px;padding:5px 10px;border:1px solid var(--line);border-radius:14px;margin-right:6px;background:var(--card)}
main{max-width:1180px;margin:0 auto;padding:8px 16px 64px}section{margin-top:36px}
h2{font-size:20px;margin:0 0 2px}h3{font-size:14px;margin:0 0 4px}p.n{color:var(--mut);margin:2px 0 12px;font-size:13px;max-width:80ch}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px;overflow-x:auto}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:12px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:12px 0}.kpi{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 12px}.kpi b{display:block;font-size:22px}.kpi span{color:var(--mut);font-size:12px}
table{border-collapse:collapse;font-size:12.5px;width:100%}th,td{padding:5px 8px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}th:first-child,td:first-child{text-align:left}
td.p{background:var(--okbg)}td.f{background:var(--badbg);font-weight:600}td.na{color:var(--mut)}
svg{width:100%;height:auto;display:block}text{fill:var(--fg);font-size:11px}.ax{stroke:var(--line)}.m{fill:var(--mut)}
.leg{margin:8px 0}.leg span{display:inline-flex;align-items:center;margin-right:14px;font-size:13px}.leg svg{width:26px;height:10px;margin-right:5px}
.note{border-left:4px solid var(--warn);padding:8px 12px;background:var(--card);border-radius:6px;margin:12px 0;font-size:14px}
select{font:inherit;padding:4px;background:var(--card);color:var(--fg);border:1px solid var(--line);border-radius:6px;max-width:100%}
</style></head><body>
<header><h1>Java / Go / Python benchmark report</h1><p class="n" id="meta"></p></header>
<nav><div><a href="#overview">1 Overview</a><a href="#scoreboard">2 Pass/fail scoreboard</a><a href="#latency">3 Latency</a><a href="#memory">4 Memory</a><a href="#cpu">5 CPU cost</a><a href="#reliab">6 Reliability</a><a href="#threads">7 Concurrency models</a><a href="#pystack">8 Python stacks</a><a href="#timeline">9 Memory timeline</a><a href="#cal">10 Calibration</a><a href="#sens">11 Latency targets</a><a href="#raw">12 Raw runs</a></div></nav>
<main>
<section id="overview"><h2>1. Overview</h2><p class="n">Each point below is the median of all valid runs for that candidate, endpoint and request rate. Short runs (3 min, 1 repeat for most cells) on one laptop: directional, not statistically final.</p>
<div class="note" id="caveat"></div><div class="kpis" id="kpis"></div><div class="leg" id="legall"></div></section>
<section id="scoreboard"><h2>2. Pass/fail scoreboard</h2><p class="n">Did the candidate meet the SLO (p99 latency, near-zero failures, no dropped requests)? Green = pass, red = fail, blank = not run. Number is p99 in ms.</p><div class="card" id="score"></div></section>
<section id="latency"><h2>3. Latency (p99)</h2><p class="n">99th percentile response time vs request rate, one chart per endpoint. Dashed line = the SLO limit. A red X means that run failed the SLO; its value is clipped to the top of the chart.</p><div class="grid" id="g-lat"></div></section>
<section id="memory"><h2>4. Memory</h2><p class="n">Median container memory during the measured window (MiB), per endpoint. Limit was 512 MiB per candidate.</p><div class="grid" id="g-mem"></div></section>
<section id="cpu"><h2>5. CPU cost</h2><p class="n">CPU milliseconds spent per successful request (lower = cheaper to run). Failed runs have no value.</p><div class="grid" id="g-cpu"></div></section>
<section id="reliab"><h2>6. Reliability</h2><p class="n">Failure rate and dropped requests. Every row is a run that failed the SLO; an empty table means everything passed.</p><div class="card" id="rel"></div></section>
<section id="threads"><h2>7. Concurrency models: Java virtual threads vs Java platform threads vs Go</h2><p class="n">Park endpoint holds each request about 1 s on a slow partner call, so rate = requests in flight. Fanout makes three parallel partner calls.</p><div class="grid" id="g-thr"></div></section>
<section id="pystack"><h2>8. Python stacks: aiohttp vs FastAPI vs Django (1 and 2 workers)</h2><p class="n">Tests the one-core limit. "-2w" means two uvicorn worker processes.</p><div class="grid" id="g-py"></div></section>
<section id="timeline"><h2>9. Memory timeline</h2><p class="n">Memory over one run, sampled outside the container. Pick a run. Bands: idle, warmup, measured, recovery.</p><select id="pick"></select><div class="card" style="margin-top:8px" id="tl"></div></section>
<section id="cal"><h2>10. Calibration (can the test rig itself keep up?)</h2><p class="n">Highest rate the mock partner and load generator held with no candidate involved. Candidate tests are only run where peak load x 2 stays under this.</p><div class="card" id="calc"></div></section>
<section id="sens"><h2>11. Response-time target sensitivity</h2><p class="n">What if the p99 target were stricter or looser? Each cell is the highest request rate (RPS) at which the candidate still met that p99 target with a failure rate under 0.1% and no dropped requests. "none" = it never met the target at any tested rate. Re-evaluated from the same runs, no new tests. The partner and fanout endpoints include a 100 ms partner wait, so a 100 ms target is impossible there (the floor is about 102 ms).</p><div class="card" id="sensc"></div></section>
<section id="raw"><h2>12. Raw runs</h2><div class="card"><table id="runs"></table></div></section>
</main><script>
const DATA=__DATA__;
const $=id=>document.getElementById(id),f=(x,d=1)=>x==null||isNaN(x)?'-':Number(x).toFixed(d);
const COL={go:'#0891b2',java:'#dc2626','java-platform':'#f97316',python:'#ca8a04',fastapi:'#16a34a','fastapi-2w':'#16a34a',django:'#8b5cf6','django-2w':'#8b5cf6','aiohttp-gil':'#92400e','aiohttp-nogil':'#0d9488','aiohttp-t-gilon':'#64748b','fastapi-gil':'#be185d','fastapi-nogil':'#16a34a','django-gil':'#4c1d95','django-nogil':'#a78bfa'};
const DASH={'aiohttp-nogil':'5 3','fastapi-nogil':'5 3','django-nogil':'5 3','aiohttp-t-gilon':'2 3','java-platform':'5 3','fastapi-2w':'5 3','django-2w':'5 3'};
const ORDER=['go','java','java-platform','python','fastapi','fastapi-2w','django','django-2w','aiohttp-gil','aiohttp-nogil','aiohttp-t-gilon','fastapi-gil','fastapi-nogil','django-gil','django-nogil'];
const SLO=DATA.criteria.slo,sloFor=e=>(e=='cpu'||e=='pycpu')?SLO.cpu_p99_ms:e=='park'?SLO.park_p99_ms:SLO.p99_ms;
const raw=DATA.runs.filter(r=>r.language&&!r.control&&r.valid&&r.profile=='steady');
// aggregate per candidate|endpoint|rate
const cells={};
raw.forEach(r=>{const k=r.language+'|'+r.endpoint+'|'+r.rate;(cells[k]=cells[k]||{language:r.language,endpoint:r.endpoint,rate:r.rate,runs:[]}).runs.push(r)});
const med=a=>{a=a.filter(x=>x!=null&&!isNaN(x)).sort((x,y)=>x-y);return a.length?(a.length%2?a[(a.length-1)/2]:(a[a.length/2-1]+a[a.length/2])/2):null};
Object.values(cells).forEach(c=>{const R=c.runs;c.n=R.length;c.pass=R.every(r=>r.slo_passed);
 c.p99=med(R.map(r=>r.latency_ms['p(99)']));c.mem=med(R.map(r=>r.container_memory_median_mib));c.peak=med(R.map(r=>r.container_memory_sampled_peak_mib));
 c.cpu=med(R.filter(r=>r.slo_passed).map(r=>r.cpu_ms_per_success));c.fail=med(R.map(r=>r.failure_rate||0));c.drop=med(R.map(r=>r.dropped_iterations||0));c.thr=med(R.map(r=>r.nr_throttled_delta||0))});
const all=Object.values(cells),cands=ORDER.filter(c=>all.some(x=>x.language==c)),eps=['partner','fanout','payload','cpu','pycpu','membuf','memobj','park'].filter(e=>all.some(x=>x.endpoint==e));
const cell=(l,e,r)=>cells[l+'|'+e+'|'+r];
$('meta').textContent=`${DATA.runs.length} runs on ${DATA.host||'unknown host'} - generated ${DATA.generated}. Candidates limited to 2 CPUs / 512 MiB.`;
$('caveat').innerHTML='Single laptop, shared load generator (about 2000 RPS ceiling), 3-minute runs. Partner is capped at 1000 RPS and fanout at 300 RPS by the test-rig headroom rule, not by the candidates.';
const nPass=all.filter(c=>c.pass).length;
$('kpis').innerHTML=[[all.length,'cells tested'],[nPass,'cells passed SLO'],[all.length-nPass,'cells failed SLO'],[cands.length,'candidates'],[DATA.runs.length,'total runs']].map(k=>`<div class="kpi"><b>${k[0]}</b><span>${k[1]}</span></div>`).join('');
function legend(list){return list.map(c=>`<span><svg viewBox="0 0 26 10"><line x1="0" x2="26" y1="5" y2="5" stroke="${COL[c]}" stroke-width="3" stroke-dasharray="${DASH[c]||''}"/></svg>${c}</span>`).join('')}
$('legall').innerHTML=legend(cands);
// scoreboard
(function(){let h='';eps.forEach(e=>{const rates=[...new Set(all.filter(x=>x.endpoint==e).map(x=>x.rate))].sort((a,b)=>a-b);
 h+=`<h3 style="margin-top:12px">${e} (SLO p99 ${sloFor(e)} ms)</h3><table><tr><th>Candidate</th>${rates.map(r=>`<th>${r} RPS</th>`).join('')}</tr>`;
 cands.filter(c=>all.some(x=>x.language==c&&x.endpoint==e)).forEach(c=>{h+=`<tr><td>${c}</td>`+rates.map(r=>{const x=cell(c,e,r);return x?`<td class="${x.pass?'p':'f'}">${x.pass?'pass':'FAIL'} <span class="m">${f(x.p99,x.p99<10?1:0)}</span></td>`:'<td class="na">-</td>'}).join('')+'</tr>'});
 h+='</table>'});$('score').innerHTML=h})();
// line chart: x = discrete rates, y = metric
function chart(box,title,unit,list,e,get,opt={}){
 const W=420,H=250,m={l:48,r:12,t:28,b:34};
 const cs=list.filter(c=>all.some(x=>x.language==c&&x.endpoint==e));if(!cs.length)return;
 const rates=[...new Set(all.filter(x=>x.endpoint==e&&cs.includes(x.language)).map(x=>x.rate))].sort((a,b)=>a-b);
 const pts=cs.map(c=>({c,p:rates.map((r,i)=>({i,x:cell(c,e,r)})).filter(o=>o.x&&get(o.x)!=null)}));
 let ymax=Math.max(...pts.flatMap(s=>s.p.filter(o=>!opt.clip||o.x.pass).map(o=>get(o.x))),opt.line||0,1e-9);
 if(opt.clip)ymax=Math.max(...pts.flatMap(s=>s.p.filter(o=>o.x.pass).map(o=>get(o.x))),opt.line*1.0||0,1e-9);
 ymax*=1.12;const X=i=>m.l+(W-m.l-m.r)*(rates.length==1?.5:i/(rates.length-1)),Y=v=>H-m.b-(H-m.t-m.b)*Math.min(v,ymax)/ymax;
 let s=`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${title} ${e}"><text x="${m.l}" y="14" style="font-weight:600">${title} - ${e} (${unit})</text>`;
 for(let i=0;i<=4;i++){const v=ymax*i/4;s+=`<line class="ax" x1="${m.l}" x2="${W-m.r}" y1="${Y(v)}" y2="${Y(v)}"/><text class="m" x="${m.l-4}" y="${Y(v)+3}" text-anchor="end">${f(v,ymax<10?1:0)}</text>`}
 rates.forEach((r,i)=>{s+=`<text class="m" x="${X(i)}" y="${H-16}" text-anchor="middle">${r}</text>`});
 s+=`<text class="m" x="${(m.l+W-m.r)/2}" y="${H-3}" text-anchor="middle">${e=='park'?'requests in flight (RPS x 1 s)':e=='cpu'?'requests per second':'requests per second'}</text>`;
 if(opt.line&&opt.line<ymax)s+=`<line x1="${m.l}" x2="${W-m.r}" y1="${Y(opt.line)}" y2="${Y(opt.line)}" stroke="var(--bad)" stroke-dasharray="4 3"/><text x="${W-m.r}" y="${Y(opt.line)-3}" text-anchor="end" style="fill:var(--bad)">SLO ${opt.line}</text>`;
 pts.forEach(s0=>{const ok=s0.p.filter(o=>!opt.clip||o.x.pass);
  s+=`<polyline fill="none" stroke="${COL[s0.c]}" stroke-width="2.2" stroke-dasharray="${DASH[s0.c]||''}" points="${ok.map(o=>X(o.i)+','+Y(get(o.x))).join(' ')}"/>`;
  s0.p.forEach(o=>{const v=get(o.x),x=X(o.i);
   if(opt.clip&&!o.x.pass)s+=`<text x="${x}" y="${m.t+8}" text-anchor="middle" style="fill:var(--bad);font-weight:700" ><title>${s0.c} @${rates[o.i]}: FAILED SLO (p99 ${f(o.x.p99,0)} ms, ${f(o.x.fail*100,1)}% failed)</title>X</text>`;
   else s+=`<circle cx="${x}" cy="${Y(v)}" r="3.5" fill="${COL[s0.c]}"><title>${s0.c} @${rates[o.i]}: ${f(v,v<10?2:1)} ${unit}</title></circle>`})});
 const el=document.createElement('div');el.className='card';el.innerHTML=s+'</svg>'+`<div class="leg">${legend(cs)}</div>`;$(box).appendChild(el)}
const cfg={lat:['p99 latency','ms',x=>x.p99,{clip:1}],mem:['Memory (median)','MiB',x=>x.mem,{}],cpu:['CPU per request','ms',x=>x.cpu,{}]};
function fill(box,list,which){which.forEach(w=>{eps.forEach(e=>{const c=cfg[w];const o=Object.assign({},c[3]);if(w=='lat')o.line=sloFor(e);chart(box,c[0],c[1],list,e,c[2],o)})})}
fill('g-lat',cands,['lat']);fill('g-mem',cands,['mem']);fill('g-cpu',cands,['cpu']);
// reliability
(function(){const bad=all.filter(c=>!c.pass).sort((a,b)=>a.endpoint.localeCompare(b.endpoint)||a.rate-b.rate||a.language.localeCompare(b.language));
 $('rel').innerHTML=bad.length?'<table><tr><th>Endpoint @ RPS</th><th>Candidate</th><th>Failure %</th><th>Dropped requests</th><th>p99 ms</th><th>Likely cause</th></tr>'+bad.map(c=>{const why=c.fail>0.5?'overloaded: timeouts / all requests failing':c.drop>0&&c.fail<=0.001?'could not keep arrival rate (queueing)':c.fail>0?'partial failures under load':'latency above SLO';
  return `<tr><td>${c.endpoint} @ ${c.rate}</td><td>${c.language}</td><td class="f">${f(c.fail*100,2)}</td><td>${f(c.drop,0)}</td><td>${f(c.p99,0)}</td><td style="text-align:left">${why}</td></tr>`}).join('')+'</table>':'All cells met the SLO.'})();
// focused groups
['park','fanout'].forEach(e=>{['lat','mem','cpu'].forEach(w=>{const c=cfg[w],o=Object.assign({},c[3]);if(w=='lat')o.line=sloFor(e);chart('g-thr',c[0],c[1],['java','java-platform','go'],e,c[2],o)})});
['partner','payload','cpu'].forEach(e=>{['lat','mem','cpu'].forEach(w=>{const c=cfg[w],o=Object.assign({},c[3]);if(w=='lat')o.line=sloFor(e);chart('g-py',c[0],c[1],['python','fastapi','fastapi-2w','django','django-2w'],e,c[2],o)})});
// timeline
(function(){const sr=DATA.runs.filter(r=>r.series&&r.series.length&&!r.control&&r.language);const sel=$('pick');
 sel.innerHTML=sr.map((r,i)=>`<option value="${i}">${r.language} ${r.endpoint}@${r.rate} (${r.cell_key&&r.cell_key.split('|')[0]||'smoke'})</option>`).join('');
 function draw(){const r=sr[sel.value];if(!r)return;const W=960,H=300,m={l:54,r:14,t:14,b:30},tmax=r.series.at(-1)[0],vmax=Math.max(...r.series.map(p=>p[1]))*1.15;
  const X=t=>m.l+(W-m.l-m.r)*t/tmax,Y=v=>H-m.b-(H-m.t-m.b)*v/vmax;let s=`<svg viewBox="0 0 ${W} ${H}">`;
  for(let i=0;i<=4;i++){const v=vmax*i/4;s+=`<line class="ax" x1="${m.l}" x2="${W-m.r}" y1="${Y(v)}" y2="${Y(v)}"/><text class="m" x="${m.l-5}" y="${Y(v)+3}" text-anchor="end">${f(v,0)} MiB</text>`}
  for(let i=0;i<=6;i++){const t=tmax*i/6;s+=`<text class="m" x="${X(t)}" y="${H-10}" text-anchor="middle">${f(t,0)}s</text>`}
  const sh={idle:.04,warmup:0,measured:.1,recovery:0},ref=r.series;let st=0;
  ref.forEach((p,i)=>{if(i==ref.length-1||ref[i+1][2]!=p[2]){const x0=X(ref[st][0]),x1=X(p[0]);s+=`<rect x="${x0}" y="${m.t}" width="${x1-x0}" height="${H-m.t-m.b}" fill="currentColor" opacity="${sh[p[2]]||0}"/><text class="m" x="${x0+3}" y="${m.t+10}">${p[2]}</text>`;st=i+1}});
  s+=`<polyline fill="none" stroke="${COL[r.language]}" stroke-width="2.2" points="${r.series.map(p=>X(p[0])+','+Y(p[1])).join(' ')}"/>`;$('tl').innerHTML=s+'</svg>'}
 sel.onchange=draw;draw()})();
// calibration
(function(){const c=DATA.calibration;if(!c){$('calc').textContent='No calibration.json found.';return}
 const rows=c.ladder,paths=[...new Set(rows.map(r=>r.path))],rates=[...new Set(rows.map(r=>r.rate))].sort((a,b)=>a-b);
 let h=`<p class="n">Headroom ${c.headroom}x. Generator max ${c.generator_max_rps} RPS. Mock max: ${Object.entries(c.mock_max_rps).map(([k,v])=>k+' '+v).join(', ')}.</p><table><tr><th>Path</th>${rates.map(r=>`<th>${r}</th>`).join('')}</tr>`;
 paths.forEach(p=>{h+=`<tr><td>${p}</td>`+rates.map(rt=>{const x=rows.find(r=>r.path==p&&r.rate==rt);return x?`<td class="${x.passed?'p':'f'}">${x.passed?'pass':'FAIL'}</td>`:'<td class="na">-</td>'}).join('')+'</tr>'});
 $('calc').innerHTML=h+'</table>'})();
// sensitivity to the p99 target
(function(){const T=[100,200,250,300,500];let h='';
 ['partner','fanout','payload','cpu','pycpu','membuf','memobj'].filter(e=>all.some(x=>x.endpoint==e)).forEach(e=>{
  h+=`<h3 style="margin-top:12px">${e}</h3><table><tr><th>Candidate</th>${T.map(t=>`<th>p99 &le; ${t} ms</th>`).join('')}</tr>`;
  cands.filter(c=>all.some(x=>x.language==c&&x.endpoint==e)).forEach(c=>{
   const cs=all.filter(x=>x.language==c&&x.endpoint==e);
   h+=`<tr><td>${c}</td>`+T.map(t=>{const ok=cs.filter(x=>x.fail<=0.001&&x.drop==0&&x.p99!=null&&x.p99<=t).map(x=>x.rate);
    return ok.length?`<td class="p">${Math.max(...ok)} RPS</td>`:'<td class="f">none</td>'}).join('')+'</tr>'});
  h+='</table>'});
 $('sensc').innerHTML=h})();
// raw
$('runs').innerHTML='<tr><th>Endpoint / RPS</th><th>Candidate</th><th>Tag</th><th>Mem MiB</th><th>Peak MiB</th><th>CPU ms/req</th><th>p50 ms</th><th>p99 ms</th><th>Fail %</th><th>Drops</th><th>Throttled</th><th>SLO</th><th>Valid</th></tr>'+
 DATA.runs.filter(r=>r.language&&!r.control).sort((a,b)=>a.endpoint.localeCompare(b.endpoint)||a.rate-b.rate||a.language.localeCompare(b.language)).map(r=>`<tr><td>${r.endpoint}/${r.profile}/${r.rate}</td><td>${r.language}</td><td>${(r.cell_key||'smoke').split('|')[0]||'smoke'}</td><td>${f(r.container_memory_median_mib)}</td><td>${f(r.container_memory_sampled_peak_mib)}</td><td>${f(r.cpu_ms_per_success,2)}</td><td>${f(r.latency_ms['p(50)'])}</td><td>${f(r.latency_ms['p(99)'])}</td><td>${f((r.failure_rate||0)*100,2)}</td><td>${r.dropped_iterations}</td><td>${r.nr_throttled_delta??'-'}</td><td class="${r.slo_passed?'p':'f'}">${r.slo_passed?'pass':'FAIL'}</td><td class="${r.valid?'p':'f'}">${r.valid?'yes':'NO'}</td></tr>`).join('');
</script></body></html>'''

def main():
    p = argparse.ArgumentParser(); p.add_argument('--out', default=str(ROOT / 'results' / 'report.html')); a = p.parse_args()
    results = ROOT / 'results'; runs = collect(results)
    cal = results / 'calibration.json'
    host = None
    for d in sorted(results.iterdir()):
        m = d / 'metadata.json'
        if m.exists():
            h = json.loads(m.read_text()).get('host', {}); host = f'{h.get("cpu_name")} ({h.get("cpu_count")} CPUs)'; break
    data = {'runs': runs, 'calibration': json.loads(cal.read_text()) if cal.exists() else None, 'host': host,
            'criteria': json.loads((ROOT / 'criteria.json').read_text()), 'generated': time.strftime('%Y-%m-%d %H:%M')}
    pathlib.Path(a.out).write_text(PAGE.replace('__DATA__', json.dumps(data).replace('</', '<\\/')), encoding='utf-8')
    print(f'{a.out}: {len(runs)} runs')

if __name__ == '__main__': main()
