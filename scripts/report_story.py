"""Build results/presentation.html: the same runs as report.html, organised as a guided story for a mixed audience
(simple workloads first, harder ones later, each with low/medium/high traffic).
usage: python scripts/report_story.py [--out results/presentation.html]"""
import argparse, json, pathlib, sys, time
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from calibration import ROOT
from report_html import collect

PAGE = r'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Java, Go and Python benchmark story</title><style>
:root{--bg:#fafaf9;--fg:#1c1917;--mut:#78716c;--card:#fff;--line:#e7e5e4;--ok:#16a34a;--bad:#dc2626;--okbg:#dcfce7;--badbg:#fee2e2;--warn:#ca8a04;--warnbg:#fef9c3;--acc:#0e7490}
@media(prefers-color-scheme:dark){:root{--bg:#161412;--fg:#f5f5f4;--mut:#a8a29e;--card:#1f1c1a;--line:#3a3532;--ok:#4ade80;--bad:#f87171;--okbg:#14351f;--badbg:#4a1d1d;--warnbg:#3b3414;--acc:#22d3ee}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.55 system-ui,sans-serif}
header{padding:28px 16px 8px;max-width:1100px;margin:0 auto}h1{font-size:28px;margin:0 0 6px}header p{color:var(--mut);margin:0;max-width:75ch}
nav{position:sticky;top:0;background:var(--bg);border-bottom:1px solid var(--line);z-index:5;overflow-x:auto;white-space:nowrap}
nav div{max-width:1100px;margin:0 auto;padding:8px 16px}nav a{color:var(--fg);text-decoration:none;font-size:13px;padding:5px 10px;border:1px solid var(--line);border-radius:14px;margin-right:6px;background:var(--card)}
main{max-width:1100px;margin:0 auto;padding:8px 16px 80px}section{margin-top:44px}
h2{font-size:23px;margin:0 0 4px}h3{font-size:15px;margin:16px 0 6px}
.lvl{display:inline-block;background:var(--acc);color:#fff;border-radius:12px;font-size:12px;padding:1px 10px;margin-bottom:4px}
.cols{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:10px;margin:10px 0}
.box{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 14px}.box b{display:block;font-size:12px;color:var(--mut);text-transform:uppercase;letter-spacing:.04em;margin-bottom:2px}
.take{border-left:5px solid var(--acc);background:var(--card);border-radius:8px;padding:10px 14px;margin:12px 0}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px;overflow-x:auto}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:12px;margin-top:10px}
table{border-collapse:collapse;font-size:13.5px;width:100%}th,td{padding:5px 9px;border-bottom:1px solid var(--line);text-align:center;white-space:nowrap}th:first-child,td:first-child{text-align:left}
th small,td small{display:block;font-weight:400;color:var(--mut)}
td.p{background:var(--okbg)}td.f{background:var(--badbg);font-weight:600}td.h{background:var(--warnbg)}td.na{color:var(--mut)}td.p small,td.f small{color:var(--mut);font-weight:400}
.bar{display:grid;grid-template-columns:190px 1fr 140px;gap:8px;align-items:center;margin:4px 0;font-size:13.5px}.bar i{display:block;height:16px;border-radius:4px;min-width:2px}.bar .t{background:var(--line);border-radius:4px;position:relative;height:16px}
svg{width:100%;height:auto;display:block}text{fill:var(--fg);font-size:11px}.ax{stroke:var(--line)}.m{fill:var(--mut)}
.leg{margin:6px 0 0}.leg span{display:inline-flex;align-items:center;margin-right:12px;font-size:12.5px}.leg svg{width:26px;height:10px;margin-right:5px}
.steps{display:flex;gap:6px;flex-wrap:wrap;margin:8px 0}.steps div{flex:1;min-width:120px;background:var(--card);border:1px solid var(--line);border-radius:8px;padding:8px;font-size:13px}
.steps b{display:block;font-size:12px;color:var(--acc)}
@media(max-width:640px){.bar{grid-template-columns:1fr}}
</style></head><body>
<header><h1>Which language holds up best for a hotel system?</h1><p>Java, Go and Python (with its web frameworks) were put through the same tests, from an easy everyday job to a very demanding one. Read the sections from top to bottom: each one raises the difficulty. <span id="meta"></span></p></header>
<nav><div id="nav"></div></nav>
<main>
<section id="how"><h2>How to read this page</h2>
<div class="steps"><div><b>1 Warm up</b>Server starts and settles, results ignored.</div><div><b>2 Measure</b>A steady number of requests per second arrives for 3 minutes.</div><div><b>3 Check</b>Was every request answered quickly, with no errors?</div><div><b>4 Raise traffic</b>Repeat at a higher rate until it breaks.</div></div>
<div class="cols">
<div class="box"><b>What a test is</b>The system under test is a small web service in a box limited to <b style="display:inline;color:inherit;text-transform:none;font-size:inherit">2 CPU cores and 512 MB of memory</b>. A fake partner system (a channel manager or payment provider) answers after 100 ms.</div>
<div class="box"><b>Pass or fail</b>Pass = 99 of every 100 requests came back within the response-time limit for that job, fewer than 1 in 1000 failed, and none were turned away. Anything else is a fail.</div>
<div class="box"><b>Traffic</b>"Requests per second" (RPS). Each job is tried at low, medium and high traffic, labelled in the tables. Real hotel traffic is usually far below the "high" levels shown here.</div>
<div class="box"><b>Colours</b><span style="color:var(--ok)">Green</span> = pass, <span style="color:var(--bad)">red</span> = fail, blank = not tested. The small number is the response time (p99, in milliseconds; lower is better).</div>
</div>
<div class="take"><b>Honest limits.</b> One laptop, short 3-minute runs, mostly one repeat per cell. Treat the results as strong directional evidence, not final proof. The detailed charts are in <a href="report.html">report.html</a>.</div>
<h3>The contestants</h3><div class="card" id="who"></div></section>
<div id="story"></div>
<section id="score"><h2>The big picture</h2><p>For each job, the highest traffic each contestant handled (green = everything tested passed, amber = broke at higher traffic, red = failed even the lowest tested traffic). Number = highest passing RPS out of the highest tested.</p><div class="card" id="heat"></div></section>
<section id="sens"><h2>What if the response-time promise is stricter?</h2><p>The pass limit used above is 250 ms for most jobs. Here the same runs are re-judged against other limits. Each cell is the highest traffic that still met the limit. "none" = never met it. (Jobs that wait 100 ms for a partner can never beat about 102 ms.)</p><div class="card" id="sensc"></div></section>
</main><script>
const DATA=__DATA__;
const $=id=>document.getElementById(id),f=(x,d=1)=>x==null||isNaN(x)?'-':Number(x).toFixed(d);
const NAME={go:'Go',java:'Java (virtual threads)','java-platform':'Java (classic threads)',python:'Python (aiohttp, async)',fastapi:'FastAPI (1 process)','fastapi-2w':'FastAPI (2 processes)',django:'Django (1 process)','django-2w':'Django (2 processes)','aiohttp-gil':'Python, standard (with GIL)','aiohttp-nogil':'Python, free-threaded (no GIL)','aiohttp-t-gilon':'Control: free-threaded build, GIL forced on','fastapi-gil':'FastAPI, with GIL','fastapi-nogil':'FastAPI, no GIL','django-gil':'Django, with GIL','django-nogil':'Django, no GIL'};
const ABOUT={go:'Compiled language, lightweight "goroutines" for concurrency.',java:'Java 21+ with virtual threads: cheap threads that wait without blocking the machine.','java-platform':'Java with ordinary operating-system threads (200 in the pool) for comparison.',python:'Plain async Python (aiohttp): one process, one thread running the requests.',fastapi:'Popular Python API framework, one server process.','fastapi-2w':'FastAPI with two server processes, to get past Python single-core limits.',django:'Django (async views), one process.','django-2w':'Django with two processes.','aiohttp-gil':'Python 3.14 as most people run it. The GIL lets only one thread run Python code at a time.','aiohttp-nogil':'Python 3.14 free-threaded build: no GIL, several threads can run Python at once.','aiohttp-t-gilon':'Same build as no-GIL but with the GIL switched back on, to prove the gain comes from removing it.'};
['fastapi-gil','fastapi-nogil','django-gil','django-nogil'].forEach(k=>ABOUT[k]='Same idea as above for this framework.');
const COL={go:'#0891b2',java:'#dc2626','java-platform':'#f97316',python:'#ca8a04',fastapi:'#16a34a','fastapi-2w':'#16a34a',django:'#8b5cf6','django-2w':'#8b5cf6','aiohttp-gil':'#92400e','aiohttp-nogil':'#0d9488','aiohttp-t-gilon':'#64748b','fastapi-gil':'#be185d','fastapi-nogil':'#16a34a','django-gil':'#4c1d95','django-nogil':'#a78bfa'};
const DASH={'aiohttp-nogil':'5 3','fastapi-nogil':'5 3','django-nogil':'5 3','aiohttp-t-gilon':'2 3','java-platform':'5 3','fastapi-2w':'5 3','django-2w':'5 3'};
const ORDER=Object.keys(NAME),GIL=new Set(['aiohttp-gil','aiohttp-nogil','aiohttp-t-gilon','fastapi-gil','fastapi-nogil','django-gil','django-nogil']);
const SLO=DATA.criteria.slo,sloFor=e=>(e=='cpu'||e=='pycpu')?SLO.cpu_p99_ms:e=='park'?SLO.park_p99_ms:SLO.p99_ms;
const raw=DATA.runs.filter(r=>r.language&&!r.control&&(r.valid||r.failure_rate>=0.99)&&r.profile=='steady');
const cells={};raw.forEach(r=>{const k=r.language+'|'+r.endpoint+'|'+r.rate;(cells[k]=cells[k]||{language:r.language,endpoint:r.endpoint,rate:r.rate,runs:[]}).runs.push(r)});
const med=a=>{a=a.filter(x=>x!=null&&!isNaN(x)).sort((x,y)=>x-y);return a.length?(a.length%2?a[(a.length-1)/2]:(a[a.length/2-1]+a[a.length/2])/2):null};
Object.values(cells).forEach(c=>{const R=c.runs;c.pass=R.every(r=>r.slo_passed);c.p99=med(R.map(r=>r.latency_ms['p(99)']));c.mem=med(R.map(r=>r.container_memory_median_mib));
 c.cpu=med(R.filter(r=>r.slo_passed).map(r=>r.cpu_ms_per_success));c.fail=med(R.map(r=>r.failure_rate||0));c.drop=med(R.map(r=>r.dropped_iterations||0))});
const all=Object.values(cells),cell=(l,e,r)=>cells[l+'|'+e+'|'+r];
const has=(c,e)=>all.some(x=>x.language==c&&x.endpoint==e);
const ratesOf=(e,cs)=>[...new Set(all.filter(x=>x.endpoint==e&&cs.includes(x.language)).map(x=>x.rate))].sort((a,b)=>a-b);
const level=(i,n)=>n==1?'':n==2?(i?'high':'low'):(i/(n-1)<.34?'low':i/(n-1)<.67?'medium':'high');
const nm=c=>NAME[c]||c;
$('meta').textContent=`(${DATA.runs.length} test runs, ${DATA.host||'one laptop'}, generated ${DATA.generated}.)`;
$('who').innerHTML='<table>'+ORDER.filter(c=>all.some(x=>x.language==c)).map(c=>`<tr><td><span style="color:${COL[c]}">&#9632;</span> ${nm(c)}</td><td style="text-align:left;white-space:normal">${ABOUT[c]||''}</td></tr>`).join('')+'</table>';
const legend=l=>`<div class="leg">`+l.map(c=>`<span><svg viewBox="0 0 26 10"><line x1="0" x2="26" y1="5" y2="5" stroke="${COL[c]}" stroke-width="3" stroke-dasharray="${DASH[c]||''}"/></svg>${nm(c)}</span>`).join('')+`</div>`;
// highest passing rate per candidate
function cap(c,e){const xs=all.filter(x=>x.language==c&&x.endpoint==e).sort((a,b)=>a.rate-b.rate);if(!xs.length)return null;
 const ok=xs.filter(x=>x.pass);return {pass:ok.length?ok.at(-1).rate:0,max:xs.at(-1).rate,allpass:ok.length==xs.length}}
function ladder(e,cs){const rates=ratesOf(e,cs);if(!rates.length)return'';
 let h=`<h3>${e.toUpperCase()} &mdash; response-time limit ${sloFor(e)} ms</h3><div class="card"><table><tr><th>Contestant</th>`+rates.map((r,i)=>`<th>${r} RPS<small>${level(i,rates.length)}</small></th>`).join('')+'</tr>';
 cs.filter(c=>has(c,e)).forEach(c=>{h+=`<tr><td><span style="color:${COL[c]}">&#9632;</span> ${nm(c)}</td>`+rates.map(r=>{const x=cell(c,e,r);return x?`<td class="${x.pass?'p':'f'}">${x.pass?'pass':'FAIL'} <small>${x.p99>=5000||x.fail>=0.99?'no replies':f(x.p99,x.p99<10?1:0)+' ms'}</small></td>`:'<td class="na">-</td>'}).join('')+'</tr>'});
 return h+'</table></div>'}
function bars(e,cs){const list=cs.filter(c=>has(c,e)),mx=Math.max(...list.map(c=>cap(c,e).max));
 return `<h3>Highest traffic handled &mdash; ${e}</h3><div class="card">`+list.map(c=>{const k=cap(c,e),w=100*k.pass/mx,col=k.pass==0?'var(--bad)':k.allpass?'var(--ok)':'var(--warn)';
  return `<div class="bar"><span>${nm(c)}</span><span class="t"><i style="width:${w}%;background:${col}"></i></span><span>${k.pass?k.pass+' RPS':'failed even at '+Math.min(...all.filter(x=>x.language==c&&x.endpoint==e).map(x=>x.rate))+' RPS'}</span></div>`}).join('')+`<p style="margin:6px 0 0;color:var(--mut);font-size:12.5px">Bar full length = highest traffic tested for any contestant (${mx} RPS). Green = passed every level tested; amber = broke at a higher level.</p></div>`}
function chart(title,unit,cs,e,get,opt={}){
 const W=420,H=250,m={l:48,r:12,t:28,b:34},list=cs.filter(c=>has(c,e));if(!list.length)return'';const rates=ratesOf(e,list);
 const pts=list.map(c=>({c,p:rates.map((r,i)=>({i,x:cell(c,e,r)})).filter(o=>o.x&&get(o.x)!=null)}));
 let ymax=Math.max(...pts.flatMap(s=>s.p.filter(o=>!opt.clip||o.x.pass).map(o=>get(o.x))),opt.line||0,1e-9)*1.12;
 const X=i=>m.l+(W-m.l-m.r)*(rates.length==1?.5:i/(rates.length-1)),Y=v=>H-m.b-(H-m.t-m.b)*Math.min(v,ymax)/ymax;
 let s=`<svg viewBox="0 0 ${W} ${H}"><text x="${m.l}" y="14" style="font-weight:600">${title} (${unit})</text>`;
 for(let i=0;i<=4;i++){const v=ymax*i/4;s+=`<line class="ax" x1="${m.l}" x2="${W-m.r}" y1="${Y(v)}" y2="${Y(v)}"/><text class="m" x="${m.l-4}" y="${Y(v)+3}" text-anchor="end">${f(v,ymax<10?1:0)}</text>`}
 rates.forEach((r,i)=>{s+=`<text class="m" x="${X(i)}" y="${H-16}" text-anchor="middle">${r}</text>`});
 s+=`<text class="m" x="${(m.l+W-m.r)/2}" y="${H-3}" text-anchor="middle">requests per second</text>`;
 if(opt.line&&opt.line<ymax)s+=`<line x1="${m.l}" x2="${W-m.r}" y1="${Y(opt.line)}" y2="${Y(opt.line)}" stroke="var(--bad)" stroke-dasharray="4 3"/><text x="${W-m.r}" y="${Y(opt.line)-3}" text-anchor="end" style="fill:var(--bad)">limit ${opt.line}</text>`;
 pts.forEach(q=>{const ok=q.p.filter(o=>!opt.clip||o.x.pass);
  s+=`<polyline fill="none" stroke="${COL[q.c]}" stroke-width="2.2" stroke-dasharray="${DASH[q.c]||''}" points="${ok.map(o=>X(o.i)+','+Y(get(o.x))).join(' ')}"/>`;
  q.p.forEach(o=>{if(opt.clip&&!o.x.pass)s+=`<text x="${X(o.i)}" y="${m.t+8}" text-anchor="middle" style="fill:var(--bad);font-weight:700"><title>${nm(q.c)} @${rates[o.i]}: failed</title>X</text>`;
   else s+=`<circle cx="${X(o.i)}" cy="${Y(get(o.x))}" r="3.5" fill="${COL[q.c]}"><title>${nm(q.c)} @${rates[o.i]}: ${f(get(o.x),2)} ${unit}</title></circle>`})});
 return `<div class="card">${s}</svg>${legend(list)}</div>`}
const SEC=[
{id:'l1',lvl:'Level 1',title:'Everyday job: ask one partner system a question',eps:['partner'],pool:'core',
 what:'Each request makes one call to a slow outside system (100 ms) and returns the answer.',ex:'Checking a room rate or availability with a channel manager; looking up a guest in a loyalty system.',why:'This is the bread and butter of a hotel system: mostly waiting, very little computing.'},
{id:'l2',lvl:'Level 2',title:'Fan-out: one request triggers three partner calls',eps:['fanout'],pool:'core',
 what:'Each request calls three partner systems at the same time and combines the answers.',ex:'A search that asks three booking channels for rates and merges them into one list.',why:'Fan-out multiplies the waiting. The server must keep many calls in flight without getting stuck.'},
{id:'l3',lvl:'Level 3',title:'Big replies: move about 1 MB per request',eps:['payload'],pool:'core',
 what:'Each request fetches a large (about 1 MB) answer from the partner and returns a summary.',ex:'Pulling a day\'s folio, a rate-plan file or a report from another system.',why:'Large messages stress memory and the network more than waiting does.'},
{id:'l4',lvl:'Level 4',title:'Thousands of requests waiting at the same time',eps:['park'],pool:'threads',
 what:'Each request is held for about one second by a slow partner, so traffic in requests per second is also the number of requests in flight.',ex:'An evening check-in surge or an availability storm after a rate change, when a partner is slow.',why:'This is where Java\'s virtual threads, Go\'s goroutines and old-style Java threads really differ.'},
{id:'l5',lvl:'Level 5',title:'Heavy work done on the server itself (local computation)',eps:['cpu'],pool:'core',
 what:'Each request does about 45 ms of real computing (hashing a lot of data) with no waiting. Two cores can only do about 44 of these per second.',ex:'Night audit steps, tax and rate calculation, report generation, encryption.',why:'This is where the "one core" limit of a single Python process shows up.'},
{id:'l6',lvl:'Level 6',title:'Memory-heavy work',eps:['membuf','memobj'],pool:'mem',
 what:'Two jobs: "membuf" allocates and fills a 16 MB block; "memobj" builds 50,000 small records (names and number lists) in memory. Every contestant does exactly the same work.',ex:'Loading a large reservation list or building an in-memory availability grid.',why:'Shows both how much memory each runtime needs and how fast it can create lots of objects.'},
{id:'l7',lvl:'Level 7',title:'Python deep dive: with and without the GIL',eps:['pycpu','cpu','partner','payload'],pool:'gil',
 what:'Python normally lets only one thread run Python code at a time (the GIL). Python 3.14 also ships a free-threaded build without it. The same three web stacks were run on both, plus a control (free-threaded build with the GIL turned back on). "pycpu" is pure-Python arithmetic, the work most affected by the GIL.',ex:'Any calculation-heavy Python code in a reservation or pricing engine.',why:'Tells you whether upgrading to free-threaded Python is a real way to use more than one core.'}];
const POOLS={core:['go','java','python','fastapi','fastapi-2w','django','django-2w'],threads:['java','java-platform','go'],mem:['go','java','python','fastapi','django'],gil:['aiohttp-gil','aiohttp-nogil','aiohttp-t-gilon','fastapi-gil','fastapi-nogil','django-gil','django-nogil']};
function verdict(e,cs){const list=cs.filter(c=>has(c,e)).map(c=>({c,k:cap(c,e)}));if(!list.length)return'';
 const full=list.filter(o=>o.k.allpass).map(o=>nm(o.c)),part=list.filter(o=>!o.k.allpass&&o.k.pass>0).map(o=>`${nm(o.c)} (up to ${o.k.pass} RPS)`),none=list.filter(o=>o.k.pass==0).map(o=>nm(o.c));
 return `<b>${e}:</b> `+(full.length?`passed every level: ${full.join(', ')}. `:'')+(part.length?`Broke at higher traffic: ${part.join(', ')}. `:'')+(none.length?`Failed even the lowest level: ${none.join(', ')}.`:'')}
function cost(e,cs){const list=cs.filter(c=>has(c,e));const rates=ratesOf(e,list);if(!rates.length)return'';
 const r=rates.find(r=>list.every(c=>cell(c,e,r)&&cell(c,e,r).pass))||null;if(!r)return'';
 return `<b>${e} at ${r} RPS (every contestant passed):</b> `+list.map(c=>{const x=cell(c,e,r);return `${nm(c)} ${f(x.mem,0)} MB, ${f(x.cpu,x.cpu<10?1:0)} ms CPU`}).join('; ')+'.'}
SEC.forEach(S=>{const cs=POOLS[S.pool],eps=S.eps.filter(e=>cs.some(c=>has(c,e)));if(!eps.length)return;
 const sec=document.createElement('section');sec.id=S.id;
 sec.innerHTML=`<span class="lvl">${S.lvl}</span><h2>${S.title}</h2><div class="cols"><div class="box"><b>What the test does</b>${S.what}</div><div class="box"><b>Hotel example</b>${S.ex}</div><div class="box"><b>Why it matters</b>${S.why}</div></div>`+
 eps.map(e=>ladder(e,cs)+bars(e,cs)).join('')+
 `<div class="take"><b>Result</b><br>${eps.map(e=>verdict(e,cs)).join('<br>')}</div>`+
 `<h3>Response time, memory and CPU cost as traffic grows</h3><div class="grid">`+eps.map(e=>chart('Response time p99','ms',cs,e,x=>x.p99,{clip:1,line:sloFor(e)})+chart('Memory used','MB',cs,e,x=>x.mem)+chart('CPU per request','ms',cs,e,x=>x.cpu)).join('')+`</div>`+
 (eps.map(e=>cost(e,cs)).filter(Boolean).length?`<div class="take"><b>What it costs to run</b><br>${eps.map(e=>cost(e,cs)).filter(Boolean).join('<br>')}</div>`:'');
 $('story').appendChild(sec)});
$('nav').innerHTML=[['how','How to read']].concat(SEC.filter(S=>$(S.id)).map(S=>[S.id,S.lvl])).concat([['score','Big picture'],['sens','Stricter limits']]).map(a=>`<a href="#${a[0]}">${a[1]}</a>`).join('');
// big picture heat table
(function(){const E=['partner','fanout','payload','park','cpu','membuf','memobj','pycpu'].filter(e=>all.some(x=>x.endpoint==e)),cs=ORDER.filter(c=>all.some(x=>x.language==c));
 const T={partner:'1 partner call',fanout:'3 partner calls',payload:'1 MB replies',park:'waiting 1 s',cpu:'heavy compute',membuf:'16 MB buffer',memobj:'50k records',pycpu:'pure-Python compute'};
 let h='<table><tr><th>Contestant</th>'+E.map(e=>`<th>${T[e]}<small>${e}</small></th>`).join('')+'</tr>';
 cs.forEach(c=>{h+=`<tr><td><span style="color:${COL[c]}">&#9632;</span> ${nm(c)}</td>`+E.map(e=>{const k=cap(c,e);if(!k)return'<td class="na">-</td>';return `<td class="${k.pass==0?'f':k.allpass?'p':'h'}">${k.pass||'none'}<small>of ${k.max}</small></td>`}).join('')+'</tr>'});
 $('heat').innerHTML=h+'</table><p style="color:var(--mut);font-size:13px;margin:8px 0 0">Different contestants were tested up to different traffic levels (the ladders differ by job), so compare within a column and read "of N" as how far that contestant was pushed.</p>'})();
// sensitivity
(function(){const T=[100,200,250,300,500];let h='';
 ['partner','fanout','payload','cpu','membuf','memobj'].filter(e=>all.some(x=>x.endpoint==e)).forEach(e=>{
  h+=`<h3>${e}</h3><table><tr><th>Contestant</th>${T.map(t=>`<th>&le; ${t} ms</th>`).join('')}</tr>`;
  POOLS.core.concat(['java-platform']).filter(c=>has(c,e)).forEach(c=>{const cs=all.filter(x=>x.language==c&&x.endpoint==e);
   h+=`<tr><td>${nm(c)}</td>`+T.map(t=>{const ok=cs.filter(x=>x.fail<=0.001&&x.drop==0&&x.p99!=null&&x.p99<=t).map(x=>x.rate);return ok.length?`<td class="p">${Math.max(...ok)} RPS</td>`:'<td class="f">none</td>'}).join('')+'</tr>'});
  h+='</table>'});$('sensc').innerHTML=h})();
</script></body></html>'''

def main():
    p = argparse.ArgumentParser(); p.add_argument('--out', default=str(ROOT / 'results' / 'presentation.html')); a = p.parse_args()
    results = ROOT / 'results'; runs = collect(results)
    for r in runs: r['series'] = []
    host = None
    for d in sorted(results.iterdir()):
        m = d / 'metadata.json'
        if m.exists():
            h = json.loads(m.read_text()).get('host', {}); host = f'{h.get("cpu_name")} ({h.get("cpu_count")} CPUs)'; break
    data = {'runs': runs, 'host': host, 'criteria': json.loads((ROOT / 'criteria.json').read_text()), 'generated': time.strftime('%Y-%m-%d %H:%M')}
    pathlib.Path(a.out).write_text(PAGE.replace('__DATA__', json.dumps(data).replace('</', '<\\/')), encoding='utf-8')
    print(f'{a.out}: {len(runs)} runs')

if __name__ == '__main__': main()
