# Findings (pilot host: 16-CPU Windows laptop, Docker Desktop, candidates limited to 2 CPUs / 512 MiB)

Single-repeat, 3-minute (--fast) runs. Directional, not statistically conclusive. Raw data: results/*/report.json, results/report.html.
Load-generator cap (~2000 RPS on /delay) and 2x headroom limit partner to 1000 RPS and fanout to 300 RPS.

## Results
- I/O-bound endpoints (partner, fanout, payload): Go, Java (virtual threads), Python/aiohttp and FastAPI all met the SLO up to the tested limit
  (partner 1000 RPS, fanout 300, payload 2000). Latency does not separate them.
- Cost separates them: memory Go ~6-23 MiB, Python ~30-40, FastAPI ~50-55, Java ~170-220. CPU ms/request: Go ~ Python < FastAPI < Java (~1.4x) < Django (~4x).
- CPU-bound endpoint (45 ms/request, 2 CPUs ~ 44 RPS ceiling): at 30 RPS single-process Python, FastAPI and Django FAIL (one core ~22 RPS);
  Go and Java pass at 40 RPS; 2-worker FastAPI/Django pass at 30. This is the "Python one-core" limit, confirmed.
- Django (async views) is the weakest: fails at partner 1000 and payload 1000 even with 2 workers; FastAPI 1 worker holds 1000 RPS but fails payload 2000; fastapi-2w passes.
- Virtual threads vs goroutines vs platform threads (/park, ~1 s held per call): Java virtual threads and Go passed 250 and 1000 in flight;
  Java with a 200-thread platform pool FAILED at 250 RPS (all requests failed/dropped). Go used 112 MiB at 1000 vs Java 221 MiB.
  2000 RPS was skipped by the capacity gate (calibrated /park 3000 / 2x headroom = 1500).
- Leak screen is "insufficient_window" for all runs (needs >=30 min soak); not evaluated.

## What this means for a hotel PMS
Any of Go, Java (21+ virtual threads) or async Python can meet a PMS-scale SLO; hotel traffic is far below these rates. Avoid Django-sync-style
single-process designs for CPU-heavy work and platform-thread pools sized below concurrency. Choose on correctness, team skills, ecosystem, and
cost (Go cheapest, Java ~10x memory), per PERSPECTIVES.md. Not yet done: repeats >=3, soak/leak, startup times, noise control, DB-backed workload.

---

# Update: GIL vs free-threaded Python, memory-heavy work, p99 targets (campaigns p3, p4)

Same host and method as above (single repeat, --fast timings). CPython 3.14.2 (GIL) vs 3.14.3 free-threaded (PYTHON_GIL=0), same asyncio stack,
CPU work runs in a 4-thread pool inside a 2-CPU container. Pass = failure rate <= 0.1%, no dropped iterations, p99 within the endpoint SLO.

## GIL vs no-GIL: pure-Python CPU work (/pycpu, about 45 ms of GIL-holding arithmetic per request)
Highest tested RPS that passed:

| Stack | GIL on | GIL off (free-threaded) |
|---|---|---|
| aiohttp | 10 (fails at 15) | 30 (fails at 40) |
| FastAPI | 10 (fails at 15) | 15 (fails at 20) |
| Django | 10 (p99 1.2 s, near the limit; fails at 15) | 15 (fails at 20) |

- The GIL is the one-core limit. With the GIL on, all three stacks fail at 15 RPS (about one core of work). Free-threaded aiohttp uses both cores and holds to 30 RPS with p99 about 74 ms.
- Control: the free-threaded build with the GIL forced back on (aiohttp-t-gilon) fails at 20 RPS like the regular build, so the gain comes from removing the GIL, not from the 3.14.3 build.
- FastAPI and Django gain little from free-threading (15 vs 10 RPS) and then fail with CPU throttling. Hypothesis, not tested: four busy worker threads starve the event-loop thread inside the 2-CPU quota.
- Free-threaded CPU cost per request is also lower at low load (about 54-62 ms vs 84-90 ms CPU per request at 10 RPS), because there is no GIL hand-off contention.

## GIL vs no-GIL: other endpoints
- /cpu (hashlib, releases the GIL): GIL and no-GIL are equal. Both pass to 30 RPS; aiohttp also passes at 40; FastAPI passes at 40 (p99 about 215-240 ms, near the limit); Django fails at 40. All fail at 50 (about 45 ms of CPU per request on 2 CPUs).
- /partner at 1000 RPS: aiohttp and FastAPI pass in both builds (p99 about 103 ms); no-GIL uses about 10-20 MiB more memory.
- Django /partner (p5 probe, 1 worker): passes at 100 RPS in both builds (p99 105 ms). At 300 RPS the GIL build fails (61-73% failures, memory hits the 512 MiB limit) while the free-threaded build passes (p99 165 ms, about 150 MiB). At 600 RPS both fail with no usable responses, and the earlier 1000 RPS partner and 2000 RPS payload runs also failed completely. Django async views are therefore far below aiohttp and FastAPI on I/O fan-in.
- /payload at 2000 RPS: aiohttp passes only without the GIL here (p99 4 ms vs the GIL build failing the SLO at p99 8 ms); FastAPI fails in both (about 5% failures).
- Memory: free-threaded builds use more memory (for example Django 107 vs 67 MiB at 20 RPS cpu).

## Memory-heavy work (p4): same job per request on every stack
membuf = allocate and touch a 16 MiB buffer; memobj = build 50,000 records (string + list of 8 ints).
- membuf (10-40 RPS): all five pass. Peak memory: Python 50, FastAPI 66, Django 66, Go 62-65, Java 228-244 MiB. p99 3-9 ms. Native memory fills are cheap everywhere.
- memobj: Go and Java pass at 10, 20 and 40 RPS (CPU per request: Go about 9 ms, Java about 16 ms; p99 Go 9 ms, Java 42-50 ms). Go peak memory about 30 MiB, Java 180-240 MiB.
- Python, FastAPI and Django cost 47-62 ms of CPU per request on memobj, about 5-7x Go. They pass at 10 RPS (p99 65-84 ms) and fail at 20 RPS (aiohttp 62% failures, Django 95% failures, FastAPI p99 3.7 s) and at 40 RPS (nearly all requests fail).
- Reading: building many small Python objects is the weak spot. It is GIL-bound and allocation-heavy.

## Response-time targets
report.html section 11 gives, for p99 targets of 100, 200, 250, 300 and 500 ms, the highest RPS each stack sustains. 250 ms is our own SLO choice, not an industry standard.

## Caveats
- Single repeat per cell: knees are accurate to the tested step only.
- Runs are on a laptop; cloud-VM reruns of the key cells are still recommended.
