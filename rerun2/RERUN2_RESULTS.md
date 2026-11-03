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
