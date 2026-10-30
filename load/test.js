import http from 'k6/http';
import { Counter, Rate, Trend } from 'k6/metrics';
const successes=new Counter('successful_requests');
const failures=new Rate('application_failures');
const latency=new Trend('application_latency',true);
const latencyOk=new Trend('application_latency_success',true);
const latencyBad=new Trend('application_latency_failure',true);
const rate=Number(__ENV.RATE || 100), profile=__ENV.PROFILE || 'steady';
const vus=Number(__ENV.VUS || 300), max=Number(__ENV.MAX_VUS || 3000);
const common={timeUnit:'1s',preAllocatedVUs:vus,maxVUs:max,gracefulStop:'10s'};
let scenario;
if(profile==='stress') scenario={...common,executor:'ramping-arrival-rate',startRate:rate,stages:[1,2,4,8].map(m=>({duration:__ENV.STEP_DURATION||'2m',target:rate*m}))};
else if(profile==='spike') scenario={...common,executor:'ramping-arrival-rate',startRate:rate,stages:[{duration:'1m',target:rate},{duration:'1s',target:rate*10},{duration:'1m',target:rate*10},{duration:'1s',target:rate},{duration:'2m',target:rate}]};
else scenario={...common,executor:'constant-arrival-rate',rate,duration:__ENV.DURATION||(profile==='soak'?'1h':'5m')};
export const options={scenarios:{workload:scenario},summaryTrendStats:['avg','p(50)','p(95)','p(99)','max'],thresholds:{application_failures:[`rate<${__ENV.MAX_FAIL||0.001}`],application_latency:[`p(99)<${__ENV.P99_MS||250}`],dropped_iterations:['count==0']}};
const expected={health:{ok:true},partner:{value:42},park:{value:42},fanout:{total:126},payload:{id:7,bytes:32768},pycpu:{ok:true},membuf:{bytes:16777216,sum:522240},memobj:{records:50000,sum:10001800000}};
export default function(){
 const endpoint=__ENV.ENDPOINT||'partner';
 const r=http.get(`${__ENV.BASE_URL||'http://candidate:8080'}/${endpoint}`,{timeout:'5s'});
 let good=r.status===200;
 try{let x=r.json();if(endpoint==='cpu')good=good&&x.digest===__ENV.CPU_DIGEST;else for(const [k,v]of Object.entries(expected[endpoint]))good=good&&x[k]===v;}catch(e){good=false;}
 failures.add(!good);latency.add(r.timings.duration);
 if(good){successes.add(1);latencyOk.add(r.timings.duration);}else latencyBad.add(r.timings.duration);
}
export function handleSummary(data){return {'/results/summary.json':JSON.stringify(data,null,2)};}
