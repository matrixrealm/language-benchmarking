# Benchmark test plan

## Objective and decision
Compare total candidate-container memory, end-to-end request latency and CPU
cost for the same successful workload. Weight partner, fanout and payload most
heavily for PMS/payment integration. No benchmark alone selects a language for a
ledger, tenant isolation or reservation correctness.

Default I/O SLO: p99 <250 ms, application failures <0.1%, zero dropped iterations.
CPU control uses a separate chosen target (example 2000 ms) and lower rates.
**Pre-registration:** all targets, endpoint weights, the inconclusive threshold and the
leak/recovery limits live in `criteria.json`. Edit and commit it before the first measured
run; every run stores its SHA-256 in metadata.json, so later edits are visible.
The CPU endpoint measures native SHA-256 plus event-loop blocking, not language speed.
Python runs one process, so it can use at most about one of the two CPU quota units; that is a
deployment-shape difference and must be stated next to any CPU or latency gap.
At a fixed offered RPS compare resources only if both candidates meet the SLO.
Otherwise report capacity limitations. Never hide failures or dropped arrivals.

## Environment and fairness

1. Run candidates one at a time on the same otherwise quiet host. Each receives
   2 CPU quota units, 512 MiB memory and 512 MiB total memory+swap (no swap).
2. For pilot runs k6 and mock run outside candidate limits but share the host.
   This runner is a **local pilot harness**: generator/mock can contend with it.
   For stronger isolation use --cpuset 0,1 on Linux and pin helper workloads to
   disjoint cores (requires additional Docker options), or place them on another
   host and adapt URLs/networking. CPU quota alone is not exclusive core pinning.
3. Validate mock+generator capacity independently at >2x intended maximum outbound
   request rate. Fanout triples partner requests. Watch helper CPU/network and
   generator VU exhaustion. Do not publish unexplained drops as server capacity.
   `scripts/calibrate.py` drives the mock directly (no candidate), writes
   results/calibration.json, and run.py/matrix.py refuse (or log as skipped) any run whose
   peak candidate or partner rate times the headroom exceeds it. Stress peaks at 8x and
   spike at 10x the base rate, so their base rate is capped by the same check. Without a
   calibration file only runs up to 300 RPS peak (smoke runs) are allowed.
   Headroom stays at 2x (decided). On the pilot host (Ryzen 7 8845HS, Docker Desktop, 16 CPUs)
   calibration sustained 3000 RPS on the mock's /delay and 6000 RPS on /data, and 4 mock
   workers did no better, so the k6 generator or Docker network path is the limit, not the
   mock. Consequence: **fanout at 1000 RPS (3000 partner RPS, 6000 with headroom) is skipped**
   and logged in results/matrix_skipped.log; fanout is measured at 50-500 RPS only. Report
   this as a helper-capacity limit, not a runtime result. Recalibrate on other hardware or
   with split generators before lifting it.
4. Record OS/CPU, Docker Desktop VM settings, image IDs/digests, runtime/library
   versions, command options, GC/environment settings. metadata.json captures
   Docker and image configuration; add hardware and runtime output to the report.
5. Baseline uses runtime defaults. JVM heap limits are not total container memory;
   record effective defaults before tuning. No profilers/race detectors in timed runs.
6. Contract validation must pass first. It asserts Java virtual threads and, for Python,
   `gil_enabled` true. /meta also reports Java max heap/processors, Go version,
   GOMAXPROCS, GOGC/GOMEMLIMIT and Python version; metadata.json stores that output, the
   host CPU name and (Windows) the .wslconfig limits.

## Execution stages

| Stage | Procedure | Harness support |
|---|---|---|
| Cold startup | 10 fresh-container starts; report median/range | `scripts/startup.py`: persistent prober container, no load; includes docker run create overhead, excludes helper startup. The per-run startup number in metadata.json remains an estimate |
| Idle | 2 minutes after contract checks | --idle 120 |
| Warmup | >=5 minutes per endpoint, extend until stable | --warmup 5m; inspect warmup output before accepting stability |
| Steady | 50,100,250,500,1000 offered RPS, 5 min each | default profile; --rate and --duration |
| Stress | Ramp from base rate toward 2x,4x,8x | --profile stress, four 2-minute ramps; not plateau capacity proof |
| Capacity confirmation | After finding knee, hold selected rates 5+ min | `matrix.py --pass coarse` then `--pass dense` (ladder rates around the knee, repeats); choose highest repeatedly meeting SLO |
| Noise floor | Same candidate, same cell, >=5 runs | `scripts/noise.py`; spread feeds the inconclusive threshold |
| Spike | 1m baseline, 1s rise to 10x, 1m high, 1s recovery, 2m baseline | --profile spike |
| Soak | 1 hour at sustainable fixed rate | --profile soak |
| Recovery | 5 minutes without traffic, no forced GC | --recovery 300 |

Repeat each measured scenario >=3 times, rotating execution order. matrix.py uses a
Latin square (java,go,python / go,python,java / python,java,go), then the reverses for
repeats 4-6, so each runtime is first, middle and last equally often. The matrix resumes
(valid cells are skipped), logs failed cells and continues. The full steady matrix is about
216 runs at 17+ minutes each; run `--pass coarse` first and repeat densely only near the knee.
One hour is an initial leak screen, not proof of no leak. report.json `leak_screen` fits
the memory slope over the measured phase after the first 20% (verdict ok / suspect /
insufficient_window against criteria.json) and `recovery` compares the last minute of the
no-traffic phase with idle (ok / retained). Both are flags for investigation, not verdicts.
Extend to 4-24 hours when production needs justify it. Repeat cold-start measurements separately for
true startup claims: pre-pull images, keep build time excluded and use an
external persistent readiness prober to remove helper-container startup noise.

## Measurements

- Primary memory: cgroup v2 memory.current in bytes. Report measured median and
  sampled peak; report.json carries per-phase (idle, warmup, measured, recovery) stats.
  Sampling runs in a sidecar container (`scripts/sampler.py`, --pid host, host cgroup tree
  mounted read-only), outside the candidate cgroup, so it adds no CPU, memory or throttling to
  the candidate. `--sampler exec` is the legacy in-candidate sampler; `--sampler none` takes
  two snapshots only. Compare sidecar and none runs to bound any residual overhead. A run
  with under 95% of expected 1 Hz samples is invalid.
- Secondary memory: PID-1 RSS from /proc/1/status. These images launch the runtime
  directly as PID 1. Do not compare JVM heap to Python/Go whole-process memory.
- CPU: delta cpu.stat usage_usec; CPU ms/success = delta usage_usec /1000/successes.
  It includes CPU spent on failed work. Show failed requests with the quotient.
- Latency: k6 application_latency p50/p95/p99 (all request outcomes) with separate
  application_latency_success and application_latency_failure trends, all in report.json.
  Review the failure trend so fast failures cannot look favorable.
- Reliability: application_failures, http_req_failed, dropped_iterations, OOM kills,
  generator status and logs. Rejected/missing/invalid JSON responses are failures.
- Throttling: delta nr_throttled and throttled_usec. Quota throttling may explain
  tail latency. A crashed container or incomplete sampler invalidates the run.
- Optional diagnostics in separate instrumented runs: JVM JFR/GC logs, Go pprof/GC
  telemetry, Python allocation profiling; OS thread counts are not task counts.
- Disk: record full image byte sizes with `docker image inspect`; do not compare
  a Go binary with a Java JAR. Runtime data/log growth is a separate concern.

## Interpretation and reporting

Use one row per repetition, then report medians/ranges across runs; retain raw
JSON/CSV/logs. Never average percentiles to claim a pooled percentile.
`scripts/summarize.py` builds the table and applies the pre-registered rule: a runtime
difference is real only with >= min_repeats valid runs each, both meeting the SLO in every
run, a median gap above max(inconclusive_pct, control-run noise) and non-overlapping
min-max ranges. Everything else is reported as inconclusive or capacity limited. Weighted
wins use the endpoint weights in criteria.json. Report max sustainable throughput
separately from fixed-load efficiency. No forced GC in primary comparisons.
Memory retained after load can be allocator reuse, not necessarily a leak.

| Endpoint / profile / RPS | Runtime+stack | Successful RPS | Memory median/peak MiB | CPU ms/success | p50/p95/p99 ms | Error % | Drops | Throttling | Valid? |
|---|---|---|---|---|---|---|---|---|---|
| Fill from measured output | | | | | | | | | |

At 1000 RPS and 100 ms service time expect roughly 100 requests in flight,
not 1000. fanout creates three partner calls per in-flight request. Thousands
of waiting tasks require higher offered load or a separate controlled parking
experiment. This harness does not isolate per-task memory from service overhead.

## Official references

- Java virtual threads: https://openjdk.org/jeps/444
- k6 arrival rate: https://grafana.com/docs/k6/latest/using-k6/scenarios/executors/constant-arrival-rate/
- k6 dropped arrivals: https://grafana.com/docs/k6/latest/using-k6/scenarios/concepts/dropped-iterations/
- Docker resource limits: https://docs.docker.com/engine/containers/resource_constraints/
- Go GC guide: https://go.dev/doc/gc-guide
- Python asyncio: https://docs.python.org/3/library/asyncio.html

## Addendum: campaigns run after the pilot
p1/p2: higher traffic and concurrency-model tests (/park, fanout, payload, cpu). p3: GIL vs free-threaded Python (/pycpu rates 10-40, /cpu 20-50, partner 1000, payload 2000). p4: memory-heavy work (/membuf, /memobj at 10/20/40 RPS on Go, Java, Python, FastAPI, Django). p5: Django partner probe at 100/300/600 RPS. Response-time target sensitivity (100/200/250/300/500 ms p99) is computed from existing runs in report.html section 11. All are single-repeat `--fast` runs.
