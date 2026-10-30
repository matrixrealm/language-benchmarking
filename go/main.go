package main
import("crypto/sha256";"encoding/hex";"encoding/json";"fmt";"io";"net/http";"os";"runtime";"strconv";"sync";"time";"context")
var input = make([]byte, 1024*1024)
var limit = func()int{if n,e:=strconv.Atoi(os.Getenv("PARTNER_LIMIT"));e==nil&&n>0{return n};return 256}()
var client = &http.Client{Timeout:3*time.Second, Transport:&http.Transport{MaxConnsPerHost:limit,MaxIdleConns:limit,MaxIdleConnsPerHost:limit,IdleConnTimeout:90*time.Second}}
func main(){
 for i:=range input {input[i]='a'}
 base:=os.Getenv("PARTNER_URL"); if base=="" {base="http://mock:8080"}
 fetch:=func(ctx context.Context,path string)(map[string]interface{},error){
  req,e:=http.NewRequestWithContext(ctx,"GET",base+path,nil);if e!=nil{return nil,e}
  r,e:=client.Do(req);if e!=nil{return nil,e};defer r.Body.Close()
  if r.StatusCode!=200{return nil,fmt.Errorf("partner status %d",r.StatusCode)}
  b,e:=io.ReadAll(r.Body);if e!=nil{return nil,e};var x map[string]interface{};e=json.Unmarshal(b,&x);return x,e
 }
 http.HandleFunc("/",func(w http.ResponseWriter,r *http.Request){
  var result interface{};var err error
  switch r.URL.Path {
  case "/health":result=map[string]interface{}{"ok":true}
  case "/meta":result=map[string]interface{}{"runtime":"go","concurrency":"goroutines","version":runtime.Version(),"gomaxprocs":runtime.GOMAXPROCS(0),"num_cpu":runtime.NumCPU(),"partner_limit":limit,"gogc":os.Getenv("GOGC"),"gomemlimit":os.Getenv("GOMEMLIMIT")}
  case "/partner":result,err=fetch(r.Context(),"/delay")
  case "/park":result,err=fetch(r.Context(),"/park")
  case "/fanout":
   var wg sync.WaitGroup; vals:=make([]float64,3);errs:=make([]error,3)
   for i:=0;i<3;i++ {wg.Add(1);go func(i int){defer wg.Done();x,e:=fetch(r.Context(),"/delay");errs[i]=e;if e==nil{vals[i]=x["value"].(float64)}}(i)};wg.Wait()
   for _,e:=range errs {if e!=nil{err=e}};result=map[string]interface{}{"total":vals[0]+vals[1]+vals[2]}
  case "/payload":var x map[string]interface{};x,err=fetch(r.Context(),"/data");if err==nil{result=map[string]interface{}{"id":x["id"],"bytes":len(x["blob"].(string))}}
  case "/membuf":n:=16*1024*1024;b:=make([]byte,n);for i:=range b{b[i]=0xab};for i:=0;i<n;i+=4096{b[i]=byte((i>>12)&0xFF)};var s int64;for i:=0;i<n;i+=4096{s+=int64(b[i])};result=map[string]interface{}{"bytes":n,"sum":s}
  case "/memobj":type rec struct{id int;name string;tags []int};n:=50000;recs:=make([]rec,0,n);for i:=0;i<n;i++{t:=make([]int,8);for k:=range t{t[k]=i+k};recs=append(recs,rec{i,fmt.Sprintf("guest-%06d",i),t})};var s int64;for _,r:=range recs{s+=int64(len(r.name));for _,v:=range r.tags{s+=int64(v)}};result=map[string]interface{}{"records":n,"sum":s}
  case "/cpu":var sum [32]byte;for i:=0;i<100;i++ {sum=sha256.Sum256(input)};result=map[string]interface{}{"digest":hex.EncodeToString(sum[:])}
  default:http.NotFound(w,r);return
  }
  w.Header().Set("Content-Type","application/json")
  if err!=nil {w.WriteHeader(502);result=map[string]interface{}{"error":"partner_failure"}}
  json.NewEncoder(w).Encode(result)
 })
 s:=&http.Server{Addr:":8080",ReadHeaderTimeout:5*time.Second};if e:=s.ListenAndServe();e!=nil{panic(e)}
}
