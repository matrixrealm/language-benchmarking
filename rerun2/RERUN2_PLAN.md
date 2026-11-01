# Rerun 2 plan: uvloop + 4-thread pool, local and cloud

Status: plan only. No code has been changed and nothing has been run. Items marked **CHECK** are things I could not confirm from the repo and should be verified before spending runner hours.

## 1. Why this rerun

The cloud1 GIL study ran FastAPI and Django on plain asyncio (`--loop asyncio --http h11`) with a 4-thread pool for the CPU endpoints. The standard `fastapi` and `django` candidates use uvloop, but run the CPU endpoints inline on the event loop and have no `pycpu` endpoint. So there is no run that combines **uvloop with a 4-thread pool**, which is what a production FastAPI or Django service would most likely look like. The article needs to say whether uvloop changes the conclusions.

Scope: Python with the **GIL on** (the stock 3.14.3 build) for **FastAPI and Django**. The free-threaded build is out of scope for this rerun.

## 2. Questions the runs answer

- **Q1.** With uvloop and a 4-thread pool, where does the pure-Python CPU ceiling (`pycpu`) sit for FastAPI and Django on the GIL build? Compare against the existing plain-asyncio results.
- **Q2.** For hashing (`/cpu`, which releases the GIL), does the 4-thread pool beat running it inline on the loop, with uvloop in both cases?
- **Q3.** Do the waiting-call results (`partner` at 1000 RPS; `park` at 250 and 1000 in flight) change with uvloop? This feeds the five-way concurrency article.
- **Q4 (local vs cloud).** Why did the laptop show about 83 to 90 ms of CPU per `pycpu` request with the GIL on, against about 29 to 36 ms on the cloud runner? See section 6.

## 3. Candidates

Existing, no change:
- `fastapi-gil`, `django-gil`: plain asyncio, 4 threads, GIL on (cloud1 baseline).
- `fastapi`, `django`: uvloop, 1 process, CPU work inline (no pool).

New (names are a suggestion):
- `fastapi-gil-uv`: FastAPI, GIL on, `--loop uvloop --http httptools`, `THREADS=4`.
- `django-gil-uv`: Django, GIL on, same settings.
No free-threaded (`-nogil`) variants are planned.

Labels on the reports: `FastAPI, with GIL - uvloop, 4 threads` (the existing `- uvloop` and `- asyncio` tags stay as they are).

## 4. Cells (3 repeats each, `--fast`, about 7 minutes per run)

- **Q1, `pycpu`:** `fastapi-gil-uv`, `django-gil-uv` at 10, 15, 20, 30, 40 RPS: 10 cells, 30 runs.
- **Q1 baseline on the same runner:** `fastapi-gil`, `django-gil` at 30 and 40 RPS (cloud1 only went to 20): 4 cells, 12 runs.
- **Q2, `cpu` (hashing):** `fastapi`, `django` (inline), `fastapi-gil-uv`, `django-gil-uv` (pool) at 30, 40, 50 RPS: 12 cells, 36 runs.
- **Q3, `partner`:** `fastapi-gil-uv`, `django-gil-uv` at 1000 RPS: 2 cells, 6 runs.
- **Q3, `park`:** the same two at 250 and 1000 in flight: 4 cells, 12 runs.
- **Core total: 32 cells, 96 runs, about 11 hours.**
- **Optional, pool size sweep:** `fastapi-gil-uv`, `django-gil-uv` on `pycpu` at 20 RPS with `THREADS` of 1, 2 and 8 (alongside the default 4): 6 cells, 18 runs. This tests whether 4 threads on 2 CPUs hurts through contention.

## 5. Code changes needed (not yet made)

- **Image:** extend `rerun/Dockerfile.gil` (or add `rerun2/Dockerfile.gil-uv`) to install `uvloop` and `httptools`, and let the start command take `LOOP` and `HTTP` settings (defaults `asyncio` and `h11`, so existing candidates are unchanged). Build as `lb-gil-uv` from the same pinned CPython patch (GIL build only). Add them to `rerun/build_images.py`.
- **Candidates:** add the new entries and a group to `scripts/candidates.py`, each with `THREADS=4` set explicitly.
- **Metadata:** make the Django app report its loop in `/meta` (FastAPI already does), so the run metadata records which loop was used. This closes the gap noted on the reports.
- **Contract test:** `tests/contract.py` decides GIL-family behaviour with `name.endswith(('-gil','-nogil','-gilon'))`, which would not match `-gil-uv`. Update it, and assert the reported loop is `uvloop` for the `-uv` candidates.
- **Labels and notes:** extend `scripts/loop_note.py` (`TAGS` and the note text) and the generators that use it.
- **Batches:** add batches to `rerun/ci_batch.py` and the workflow inputs, for example `uv-fastapi`, `uv-django` and `uv-concurrency`, each under about 5 hours so they fit one runner job. The `cpu` baseline cells for `fastapi` and `django` go with `uv-cpu`.
- **Reports:** reuse the cloud report builder with a new data folder under `rerun2/reports`, with a section per question.

## 6. Local vs cloud (Q4)

The same cells should run on both so the difference can be studied.
- **Same images:** rebuild the laptop images from the same Dockerfiles with the pinned CPython patch. The earlier laptop runs mixed 3.14.2 and 3.14.3.
- **Same pinning:** on the laptop use `--cpuset 0,1 --helper-cpuset 2,3` if Docker Desktop's VM honours it. **CHECK:** whether the Windows sampler supports it.
- **Probe first:** run one `pycpu` cell (GIL on, 10 RPS, 3 repeats) on both machines, compare CPU ms per request, and only then decide whether the long local runs are worth it. A large gap would point at the laptop environment, not the code.
- **Local subset:** run the Q1 cells (`pycpu` at 10, 15, 20) and the Q2 cells at 30 and 40, tag `local2`, so the article can show the laptop next to the runner.
- **Close other apps** on the laptop, and report the host and power mode.

## 7. Commands (draft; run `--dry-run` first)

Cloud, once the batches exist:

```bash
python rerun/ci_batch.py uv-fastapi --dry-run
python rerun/ci_batch.py uv-fastapi
```

Local, with the new group and a separate tag:

```bash
python scripts/matrix.py --pass full --group uv --candidates fastapi-gil-uv,django-gil-uv --endpoints pycpu --rates 10,15,20 --repeats 3 --fast --tag local2 --dry-run
```

## 8. Reporting rules

- Same rules as `RERUN_PLAN.md` section 6: passes out of 3, median with range, no hiding failures.
- Compare the four Python setups for each framework side by side, always labelled with loop, thread count and GIL state: plain asyncio and 4 threads (cloud1), uvloop and 4 threads (new), uvloop and inline (existing).
- Never mix cells from different runners in one chart without saying so. Where possible run the baseline in the same batch.
- Compare **CPU ms per request**, which does not depend on thread count, alongside the ceilings.
- State clearly that production setups often use several worker processes; this rerun does not change the 1-process scope.

## 9. Open questions for you

- Is the pool-size sweep worth about 2 hours, or is the default 4 enough?
- How much laptop time can you give to the local runs?
