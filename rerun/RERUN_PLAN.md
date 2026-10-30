# Rerun plan: cloud VM, 3 repeats

Purpose: turn the headline claims in the two articles from "one run on a laptop" into "3 of 3 runs on a fixed Linux VM, with ranges", so they hold up under editor and reader scrutiny.

This is a draft for you to edit. Items marked **CHECK** are things I could not confirm from the repo and you should verify before spending VM hours.

## 1. What the reruns must prove

Each claim below is used in the articles and depends on a small number of cells.

- **A. GIL ceiling (pure-Python CPU).** GIL on stops at about 10 RPS for all three stacks; GIL off reaches 30 for aiohttp and 15 for FastAPI and Django.
- **B. Control.** Free-threaded build with the GIL forced on behaves like the regular build (fails at 20).
- **C. Waiting calls.** Java virtual threads and Go hold 250 and 1,000 in flight; the 200-thread Java pool fails at 250.
- **D. Cost.** Memory per instance at 1,000 RPS on the partner endpoint: Go about 22 MiB, aiohttp about 35, FastAPI about 55, Java about 195.
- **E. Many small objects (Medium article only).** Go and Java pass at 10, 20, 40 RPS; Python stacks pass 10 and fail 20.
- **F. GIL does not matter for `hashlib` (optional).** GIL and free-threaded builds equal on `/cpu`.

## 2. Cells to run (3 repeats each)

Candidate names are the ones in `scripts/candidates.py`.

- **A+B, endpoint `pycpu`:**
  - aiohttp-gil, aiohttp-nogil, aiohttp-t-gilon at 10, 15, 20, 30, 40 RPS: 15 cells.
  - fastapi-gil, fastapi-nogil, django-gil, django-nogil at 10, 15, 20 RPS: 12 cells.
  - Subtotal: 27 cells, 81 runs.
- **C, endpoint `park`:** java, java-platform, go at 250 and 1000: 6 cells, 18 runs.
- **D, endpoint `partner`:** go, java, python, fastapi at 1000 RPS: 4 cells, 12 runs.
- **Core total: 37 cells, 111 runs.**
- **E, endpoint `memobj` (optional):** go, java, python, fastapi, django at 10 and 20 RPS: 10 cells, 30 runs.
- **F, endpoint `cpu` (optional):** aiohttp-gil and aiohttp-nogil at 30 and 40 RPS: 4 cells, 12 runs.
- **Optional total: 14 cells, 42 runs.**

Time at `--fast` (about 7 minutes per run): core about 13 hours, optional about 5 hours. At the default timings (about 17 minutes per run) the core set would be about 31 hours, so use `--fast` for the repeats and keep the same timings for every cell.

## 3. VM and environment

- **OS:** Linux (Ubuntu LTS), not Windows. The cgroup sampler needs a real cgroup v2 host, and `VALIDATION.md` says it was never executed on one. **CHECK:** run the sampler once on the VM before any real run.
- **Size:** dedicated (non-burstable) x86-64 instance, 8 vCPUs or more, 16 GiB RAM or more. Avoid burstable instance types, because credits make CPU throttling look like a runtime effect.
- **Isolation:** the harness gives each candidate 2 CPUs and 512 MiB, but k6 and the mock share the host. On the VM, pin the candidate with `--cpuset 0,1` and keep k6 and the mock on other cores. **CHECK:** `TEST_PLAN.md` says pinning the helper containers needs extra Docker options that are not yet in the harness; you may need a small change in `scripts/run.py`.
- **Alternative:** a second VM for k6 and the mock, in the same region. Cleaner, costs more, needs URL/network changes.
- **Docker:** Linux containers. Build images with the commands in the README (replace `setup.ps1`): `docker build -t lb-python python`, and the java, go, gil images, plus `docker pull grafana/k6:1.3.0`.
- **Pin versions:** record image digests and pin them. **CHECK:** make the `gil` and `nogil` images use the same CPython patch version (the laptop runs were 3.14.2 vs 3.14.3). This removes the main confounder the articles have to caveat.
- **Cost:** a dedicated 8 vCPU VM for about 20 hours is typically a small amount; check your provider's price before starting. Stop the VM between sessions.

## 4. Order of work

1. **Provision and set up the VM.** Install Docker, Python 3.10+, clone the repo, build images.
2. **Sanity check.** Run the three quick validation commands from the README; confirm the sampler works and `/meta` reports the expected versions (Java virtual threads, `gil_enabled` values).
3. **Calibrate.** `python scripts/calibrate.py`. Calibration is hardware-specific, and runs above the rig's capacity are refused or skipped. Check `results/matrix_skipped.log` afterwards.
4. **Noise floor.** `python scripts/noise.py --language go --endpoint partner --rate 250`. If repeated identical runs differ a lot, fix the host before continuing.
5. **Dry run.** Add `--dry-run` to each matrix command to see the cell order.
6. **Run the core cells**, in the order below (most important first, so you can stop early).
7. **Optional cells** if time and budget allow.
8. **Summarise and update the articles.**

## 5. Commands (draft, **CHECK** with `--dry-run` first)

Use a new tag so reruns resume separately from the laptop data.

```bash
# A + B: GIL ceiling and control
python scripts/matrix.py --pass full --group gil --candidates aiohttp-gil,aiohttp-nogil,aiohttp-t-gilon --endpoints pycpu --rates 10,15,20,30,40 --repeats 3 --fast --tag cloud1
python scripts/matrix.py --pass full --group gil --candidates fastapi-gil,fastapi-nogil,django-gil,django-nogil --endpoints pycpu --rates 10,15,20 --repeats 3 --fast --tag cloud1

# C: waiting calls
python scripts/matrix.py --pass full --group threads --candidates java,java-platform,go --endpoints park --rates 250,1000 --repeats 3 --fast --tag cloud1

# D: cost at 1000 RPS
python scripts/matrix.py --pass full --group core --candidates go,java,python,fastapi --endpoints partner --rates 1000 --repeats 3 --fast --tag cloud1
```

**CHECK:** `matrix.py` has a `--group` option with `core`, `gil`, `threads` and others defined in `scripts/candidates.py`; confirm that `--candidates` and `--endpoints` override the group's lists as intended, that `aiohttp-t-gilon` is accepted outside the default `gil` group, and what happens to `--rates` when different candidates need different ladders (hence the separate commands above).

Optional:

```bash
python scripts/matrix.py --pass full --group python --candidates go,java,python,fastapi,django --endpoints memobj --rates 10,20 --repeats 3 --fast --tag cloud1
python scripts/matrix.py --pass full --group gil --candidates aiohttp-gil,aiohttp-nogil --endpoints cpu --rates 30,40 --repeats 3 --fast --tag cloud1
```

## 6. How to report the results

- **Per cell:** show passes out of 3 (for example "3 of 3 passed at 30 RPS"), plus median p99 and its min to max range.
- **Ceiling:** define it as the highest rate where all 3 runs pass. If a rate has mixed results (for example 2 of 3), call it "unstable" and say so. Do not round it up.
- **Memory and CPU:** median and min to max across the 3 runs.
- **Invalid runs:** keep flagged-invalid runs in the data, but exclude them from claims and say how many there were.
- **Do not hide failures.** Failed runs have no CPU-per-request value, so report them by pass count.
- **Keep the laptop data** as a labelled second dataset. If laptop and VM disagree, that is itself worth a paragraph.
- **Host description:** VM type, vCPUs, kernel, Docker version, image digests, and the pinned CPython versions.

## 7. Article updates after the reruns

- Replace "one run per rate" with the repeat counts and ranges in both articles' "Notes and limits".
- Update every number that changed. Expect the exact knees (for example 30 vs 40 RPS) to move by one step.
- If the forced-GIL control only ran on aiohttp, either run it for FastAPI and Django (`fastapi` and `django` variants with `PYTHON_GIL=1`, which means adding two candidates to `candidates.py`) or keep the caveat.
- If the CPython patch versions are now identical, delete the patch-version caveat.
- Link the repository, with the results folder and the `cloud1` summary.

## 8. Risks

- **Noisy neighbours.** Shared cloud hosts vary. Use dedicated instances and run the noise-floor check.
- **Rig limits.** If calibration shows the generator tops out near your top rate, those cells are skipped, not failed. Plan for that before the long run.
- **Different knees.** The VM may place the ceilings differently from the laptop. That is fine, but the articles must use the VM numbers.
- **Time overrun.** Run the core list in the order above, and stop after A+B and C if needed. Those two carry the pitch article.
- **Employer and confidentiality.** Use a personal cloud account for this, not a work account.
