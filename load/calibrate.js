// Drives the partner mock directly (no candidate) to find what mock + generator can sustain.
import http from 'k6/http';
const rate=Number(__ENV.RATE||1000), path=__ENV.MOCK_PATH||'/delay';
const minBytes=path==='/data'?32768:0;
export const options={scenarios:{calibrate:{executor:'constant-arrival-rate',rate,timeUnit:'1s',duration:__ENV.DURATION||'30s',
  preAllocatedVUs:Number(__ENV.VUS||500),maxVUs:Number(__ENV.MAX_VUS||5000),gracefulStop:'10s'}},
  summaryTrendStats:['avg','p(50)','p(95)','p(99)','max'],
  thresholds:{http_req_failed:['rate<0.001'],http_req_duration:[`p(99)<${__ENV.P99_MS||150}`],dropped_iterations:['count==0']}};
export default function(){
 const r=http.get(`${__ENV.BASE_URL||'http://mock:8080'}${path}`,{timeout:'5s'});
 if(r.status!==200||r.body.length<minBytes)throw new Error('bad mock response '+r.status);
}
export function handleSummary(data){return {'/results/calibrate.json':JSON.stringify(data,null,2)};}
