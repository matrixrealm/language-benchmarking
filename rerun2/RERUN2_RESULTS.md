# Rerun 2 results (GitHub Actions run #5, tag cloud1, 3 repeats, --fast)

Four batches, 96 runs, all valid except one (django-gil-uv partner 1000, repeat 0: no replies, marked invalid). Raw data: `rerun/reports/data/uv-*/` (gitignored).
Pass = failure rate <= 0.001, no dropped iterations, p99 within the SLO. "n/3" = repeats that passed.

## Read this first: the four jobs did not run on the same CPU

| Job | Runner CPU |
|---|---|
| uv-fastapi | **Intel Xeon 6975P-C** |
| uv-django, uv-cpu, uv-concurrency | AMD EPYC 7763 (same as cloud1) |

The Intel machine does the same pure-Python work in about 22 ms of CPU per request; the AMD machines need about 36 ms. So FastAPI and Django `pycpu` numbers from this run are **not comparable with each other**. Comparisons inside one job (FastAPI uvloop vs FastAPI plain asyncio, both in uv-fastapi) are valid. The same question for Django is valid too (both in uv-django).

To compare across machines use cores = rate x CPU-seconds per request. A GIL build cannot use more than 1 core on pure-Python work.

## Q1: pure-Python ceiling (`pycpu`)

| Candidate | Runner | 10 | 15 | 20 | 30 | 40 | CPU ms/req |
|---|---|---|---|---|---|---|---|
| FastAPI, uvloop + 4 threads | Intel | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 22 |
| FastAPI, plain asyncio + 4 threads | Intel | - | - | - | 3/3 | 3/3 | 22 |
| Django, uvloop + 4 threads | AMD | 3/3 | 3/3 | 3/3 | 0/3 | 0/3 | 35 to 37 |
| Django, plain asyncio + 4 threads | AMD | (cloud1: 3/3 to 20) | | | 0/3 | 0/3 | - |

- **uvloop made no measurable difference** to the ceiling in either framework (FastAPI: identical p99 of 23 to 25 ms; Django: both fail at 30).
- **FastAPI's ceiling was not found.** 40 RPS x 22 ms = 0.88 core, still under the 1-core GIL cap. It passed everything tested, so the honest statement is "above 40 RPS on the Intel runner".
- **Django's ceiling is between 20 and 30 RPS on AMD.** 30 x 36 ms = 1.08 cores, just over the cap, and the collapse matches the GIL cap. This is an inference from the arithmetic; no profiler was run.
- At 30 and 40 RPS Django failed with 5 s client timeouts and a handful of successes (0 to 841 of 5400+).

## Q2: hashing (`cpu`, releases the GIL)

All rates tested (30, 40, 50 RPS) were above what these builds handle on the AMD runner, so **no cell passed and the ceiling is not bracketed**.
- Inline on the event loop (`fastapi`, `django`, uvloop): 0 successes at every rate.
- 4-thread pool (`*-gil-uv`): some replies at 30 RPS (failure rate FastAPI 37%, Django 53%). At 40 and 50 FastAPI got none and Django only a few hundred.
So the thread pool is clearly better than running inline, but how much better needs lower rates (10 to 25).

## Q3: waiting calls (`partner` 1000 RPS, `park` 250 and 1000 in flight)

| Candidate | partner 1000 | park 250 | park 1000 | Memory (median) |
|---|---|---|---|---|
| FastAPI, uvloop | 3/3, p99 102 ms | 3/3 | 3/3 | 69 to 111 MiB |
| Django, uvloop | 0/3, 24% failures | 0/3, 26% failures | 0/3, 24% failures | 155 to 398 MiB |

- **FastAPI with uvloop passes everything**, at about 0.4 ms CPU per request.
- **Django with uvloop fails all of it**, even at 250 in flight, with 5 s timeouts. Its memory is far higher and reached the 512 MiB cap (peak 512 MiB at park 250), but there were no OOM kills and no CPU throttling.
- **Cause not established.** No `django` run without uvloop exists on these endpoints in the cloud data (the `concurrency` batch that contains `django-gil` was not run), so we cannot say whether this is uvloop, Django's async path, or the app's partner client settings. `candidate.log` is empty. Do not attribute it to uvloop in the article.

## What is still missing for a solid article

1. **Django waiting-call baseline without uvloop**: run the `concurrency` batch (`django-gil` on park and partner, plus Java classic threads at 2000).
2. **FastAPI ceiling**: `fastapi-gil-uv` and `fastapi-gil` at 50, 60 and 80 RPS on `pycpu`.
3. **Hashing at lower rates**: `cpu` at 10, 15, 20, 25 RPS for the pooled and inline builds.
4. **CPU-model control**: GitHub does not let us choose the runner CPU. Either record the model next to every cell (the report does), or repeat any cross-framework claim on a second run.
5. **Why Django fails at 250 in flight**: needs `candidate.log` to be non-empty (capture stderr) or a local reproduction.

---

# Run #6 follow-up (workflow run 41553969798, 96 runs, commit 5183212)

Raw data: `rerun2/reports/data/` (gitignored). Runner CPUs per job: concurrency = Intel Xeon 6973P-C; uv-cpu-low-fastapi = AMD EPYC 9V74; uv-cpu-low-django and uv-fastapi-high = AMD EPYC 7763. Compare only within a job.

## Hashing (`/cpu`): thread pool vs inline, uvloop in both
| Candidate | 10 | 15 | 20 | 25 | CPU ms/req |
|---|---|---|---|---|---|
| FastAPI inline (AMD 9V74) | 3/3 | 3/3 | 0/3 (100% fail) | 0/3 | 58 to 59 |
| FastAPI 4-thread pool (AMD 9V74) | 3/3 | 3/3 | 3/3 | 3/3 | 59 to 62 |
| Django inline (AMD 7763) | 3/3 | 0/3 (p99 2638 ms) | 0/3 | 0/3 | 68 |
| Django 4-thread pool (AMD 7763) | 3/3 | 3/3 | 3/3 | 3/3 | 68 to 70 |
Inline ceiling is about 15 RPS (one core / about 60 ms); the pool passes every rate up to 25 and, with run #5 (failures at 30), has its ceiling between 25 and 30 RPS, consistent with two cores. The upper bound is not tighter than that.

## FastAPI `pycpu` ceiling (AMD 7763)
Both `fastapi-gil` (asyncio) and `fastapi-gil-uv` failed every request at 50, 60 and 80 RPS. With about 36 ms per request on this CPU, 50 RPS needs about 1.8 cores, well over the GIL's one core. Run #5 passed up to 40 RPS on an Intel runner (22 ms per request, 0.88 core). The data fit a ceiling of about one core divided by CPU cost per request, but the two sides were measured on different CPUs, so the exact FastAPI ceiling on one CPU model is still not bracketed.

## Waiting calls
- FastAPI (asyncio and uvloop, Intel 6973P-C): park 250 and 1000 and partner 1000 all 3/3; memory 70 to 113 MiB.
- Java with a 2000-thread pool: park 250 passes 3/3 (468 MiB); park 1000 fails (no replies, 501 MiB, near the 512 MiB cap). Java with 200 threads passes partner 1000 (242 MiB).
- **Django (gil image) fails waiting calls with plain asyncio too**: park 250 0/3 (31% failures, 401 MiB), partner 300 0/2, partner 1000 and park 1000 invalid in all repeats. So uvloop is not the cause. The laptop pilot shows the same pattern (django-gil passes at 100 RPS, fails at 300, memory about 440 MiB), while the standard `django` candidate passed partner 500 there. The cause is unexplained and the code of `gil/app_django.py` matches the FastAPI client logic, so **do not report Django's waiting-call performance until it is understood.**

## Django waiting-call anomaly: cause found (local diagnosis, 2026-11-03)
- **Evidence in run #6 data:** `resources.csv` of `django-gil` on `/park` shows 253 to 259 OS threads at 250 requests in flight (about 1020 median, 1290 max at 1000 in flight), against 3 threads for FastAPI. On `/partner` at 1000 RPS (about 100 in flight) it shows about 110 threads and 513 to 518 MiB resident, which is the 512 MiB limit.
- **Mechanism (read from Django 5.2.18 and asgiref 3.13.0 source):** `ASGIHandler` wraps every request in `ThreadSensitiveContext()` and sends `request_started` and `request_finished`; Django's own receivers on those signals are synchronous, so asgiref runs them with `sync_to_async` on a thread that belongs to that request. One thread per request in flight, about 1.5 to 2 MiB resident each.
- **Local control (Windows, Python 3.11, no CPU or memory limit, so a diagnosis, not a benchmark):** the app reports 252 threads at 250 in flight; with the two signals' receivers removed it reports 1 thread, and p99 went from 1.10 s to 1.05 s. Neither variant failed locally, because the host has no 2-CPU or 512 MiB limit.
- **Why the earlier laptop result fits:** the standard `django` candidate passed `/partner` at 500 RPS (about 50 in flight, about 50 threads); `django-gil` fails at 300 only inside the container limits.
- **Still to confirm in the benchmark:** batch `django-signals` runs `django-gil` against `django-gil-nosig` (receivers removed, switch `DJANGO_NO_SIGNALS=1`, default off) in the same job. Until it finishes this is a diagnosis supported by thread counts and a local control, not a benchmark result.
