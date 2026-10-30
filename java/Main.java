import com.sun.net.httpserver.*;
import com.fasterxml.jackson.databind.*;
import java.net.*;import java.net.http.*;import java.time.*;import java.util.*;import java.util.concurrent.*;import java.security.*;
public class Main {
 // JAVA_THREADS=platform swaps virtual threads for classic platform threads so the two models can be compared
 // on the same code: requests run on a fixed THREAD_POOL (default 200, a Tomcat-like default) and fanout
 // sub-calls on a separate cached pool, which avoids pool-starvation deadlock between the two.
 static final boolean VIRTUAL=!"platform".equalsIgnoreCase(System.getenv().getOrDefault("JAVA_THREADS","virtual"));
 static final int POOL=Integer.parseInt(System.getenv().getOrDefault("THREAD_POOL","200"));
 static final int LIMIT=Integer.parseInt(System.getenv().getOrDefault("PARTNER_LIMIT","256"));
 static{System.setProperty("jdk.httpclient.connectionPoolSize",String.valueOf(LIMIT));}
 static final ObjectMapper JSON=new ObjectMapper();
 static final ExecutorService TASKS=VIRTUAL?Executors.newVirtualThreadPerTaskExecutor():Executors.newCachedThreadPool();
 static final ExecutorService REQUESTS=VIRTUAL?TASKS:Executors.newFixedThreadPool(POOL);
 static final Semaphore CONNECTIONS=new Semaphore(LIMIT);
 static final HttpClient CLIENT=HttpClient.newBuilder().version(HttpClient.Version.HTTP_1_1).connectTimeout(Duration.ofSeconds(3)).build();
 static final String BASE=System.getenv().getOrDefault("PARTNER_URL","http://mock:8080");
 static final byte[] DATA=new byte[1024*1024];
 static JsonNode fetch(String path)throws Exception {
  if(!CONNECTIONS.tryAcquire(3,TimeUnit.SECONDS))throw new TimeoutException();
  try{var r=CLIENT.send(HttpRequest.newBuilder(URI.create(BASE+path)).timeout(Duration.ofSeconds(3)).GET().build(),HttpResponse.BodyHandlers.ofByteArray());
   if(r.statusCode()!=200)throw new Exception("partner status");return JSON.readTree(r.body());
  }finally{CONNECTIONS.release();}
 }
 public static void main(String[] args)throws Exception{
  Arrays.fill(DATA,(byte)'a');var server=HttpServer.create(new InetSocketAddress(8080),0);
  server.setExecutor(REQUESTS);
  server.createContext("/",ex->{
   try{
    Object result;
    switch(ex.getRequestURI().getPath()){
     case "/health":result=Map.of("ok",true);break;
     case "/meta":result=Map.of("runtime","java","virtual",Thread.currentThread().isVirtual(),"threads",VIRTUAL?"virtual":"platform","pool",VIRTUAL?0:POOL,"partner_limit",LIMIT,"version",System.getProperty("java.version"),"max_heap_mib",Runtime.getRuntime().maxMemory()/1048576,"processors",Runtime.getRuntime().availableProcessors());break;
     case "/partner":result=fetch("/delay");break;
     case "/park":result=fetch("/park");break;
     case "/fanout":
      var futures=new ArrayList<Future<JsonNode>>();for(int i=0;i<3;i++)futures.add(TASKS.submit(()->fetch("/delay")));
      int total=0;for(var f:futures)total+=f.get().get("value").asInt();result=Map.of("total",total);break;
     case "/payload":var node=fetch("/data");result=Map.of("id",node.get("id").asInt(),"bytes",node.get("blob").asText().length());break;
     case "/cpu":var hash=MessageDigest.getInstance("SHA-256");byte[] digest=null;for(int i=0;i<100;i++)digest=hash.digest(DATA);result=Map.of("digest",HexFormat.of().formatHex(digest));break;
     case "/membuf":{int n=16*1024*1024;byte[] b=new byte[n];Arrays.fill(b,(byte)0xab);for(int i=0;i<n;i+=4096)b[i]=(byte)((i>>12)&0xFF);long s=0;for(int i=0;i<n;i+=4096)s+=b[i]&0xFF;result=Map.of("bytes",n,"sum",s);break;}
     case "/memobj":{int n=50000;var recs=new ArrayList<Object[]>();for(int i=0;i<n;i++){int[] t=new int[8];for(int k=0;k<8;k++)t[k]=i+k;recs.add(new Object[]{i,String.format("guest-%06d",i),t});}long s=0;for(var r:recs){s+=((String)r[1]).length();for(int v:(int[])r[2])s+=v;}result=Map.of("records",n,"sum",s);break;}
     default:ex.sendResponseHeaders(404,-1);ex.close();return;
    }
    byte[] body=JSON.writeValueAsBytes(result);ex.getResponseHeaders().set("Content-Type","application/json");ex.sendResponseHeaders(200,body.length);ex.getResponseBody().write(body);
   }catch(Exception e){try{ex.sendResponseHeaders(502,-1);}catch(Exception ignored){} }
   finally{ex.close();}
  });server.start();
 }
}
