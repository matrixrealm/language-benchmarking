# Other ways to evaluate Java, Go and Python for a hotel PMS

The harness here measures one thing well: resource cost and latency of a stateless service that
calls a slow partner. That is a narrow slice of what decides a PMS project. Below are the other
angles, ordered by how much they usually change the decision. Items marked **cheap** can be done
in a day or two with what is already in this repo.

## 1. Correctness under concurrency (decides more than speed does)
- **Double-booking race test (cheap):** N clients try to reserve the last room for the same night at
  once. Pass criterion: exactly one succeeds, zero oversell, repeated 1000 times. Run against each
  stack's idiomatic approach (DB unique/exclusion constraint, `SELECT ... FOR UPDATE`, optimistic version column).
- **Folio / ledger invariants:** property-based tests (debits equal credits, a folio balance equals the
  sum of its postings, night audit is idempotent when re-run). Compare how much code and how many bugs each stack needs.
- **Idempotent payment and webhook handling:** replay the same provider callback 50 times in parallel; exactly one posting.
- **Time and money handling:** time zones and DST at night audit, per-property currency rounding, tax rules.
  Count library gaps: `BigDecimal` and `java.time` versus Go's `decimal` and `time` versus Python's `Decimal` and `zoneinfo`.

## 2. A realistic workload instead of a synthetic one
- Add PostgreSQL with a small PMS schema (properties, room types, inventory per night, reservations, folios).
  Endpoints: availability search, create reservation, modify stay, check-in, post charge, night audit batch.
- Use the same schema, same queries and connection pool size for every candidate; then the runtime cost
  is the cost of the real work, and DB contention becomes visible.
- Use real framework stacks: Spring Boot, Go with chi/sqlc, Django REST or FastAPI + SQLAlchemy.
  Libraries, not languages, drive most of the CPU and memory that production sees.

## 3. Load shapes that match hotels
- **Open-model traffic** (arrivals independent of response time, which k6 `constant-arrival-rate` already does)
  plus a **closed-model** run (fixed concurrent users) to see back-pressure behaviour.
- Shapes: morning check-out and evening check-in surges, OTA availability storms after a rate change,
  the night-audit batch running while the front desk is busy.
- Scale reality check: estimate peak RPS per property and chain-wide (often tens to low hundreds). If every
  candidate meets the SLO at 5x that, the benchmark is a tie and other angles decide.

## 4. Failure and degradation behaviour
- **Slow or failing partner (cheap with the mock):** make `/delay` take 2 s, then return 5xx 20% of the time,
  then drop connections. Measure memory growth, queue build-up, timeouts, recovery time and retry amplification.
- **Overload:** push past capacity and check graceful rejection (429 or 503) against collapse.
- **Noisy tenant:** one tenant sends 50x traffic; does the others' p99 hold? Needs per-tenant limits in the app.
- **Restart behaviour:** kill the container mid-load; time to ready and any lost or duplicated work.

## 5. Concurrency model, deeper
- `/park` here is the first step: Java virtual threads versus classic threads versus goroutines at thousands
  of in-flight calls. Extend with: blocking JDBC on virtual threads (pinning with `synchronized`), CPU-bound
  work mixed into the same pool, and Go with a huge `GOMAXPROCS` mismatch.
- Python: async (FastAPI/Django ASGI), multi-process workers (done), a sync WSGI worker pool, and the free-threaded 3.14 build as a separate labelled experiment.
- Java variants labelled separately: heap and GC settings, class-data sharing for startup, GraalVM native image for memory and start time.

## 6. Operations and cost
- **Per-instance and per-month cost model:** measured memory and CPU, mapped to the smallest instance type that
  meets the SLO with headroom, times the number of instances for your peak. Usually dollars per month, which makes the runtime choice small next to engineers' time.
- Container size, cold start (measured here), GC pause behaviour, profiling and observability tooling,
  and how easy it is to debug a production incident in each language.
- Deployment realism: Kubernetes CPU limits and throttling (the harness records throttling), autoscaling response time.

## 7. People and delivery (often decisive)
- **Implementation bake-off:** give the same small spec (create reservation with availability check and
  idempotency, plus a folio posting) to engineers fluent in each stack; compare time to correct, lines of code,
  test count, and defects found by a shared test suite. One week of effort teaches more than a week of load testing.
- Hiring pool, onboarding time, ecosystem depth for hospitality standards (OpenTravel, HTNG, channel manager and
  payment SDKs), long-term maintenance, security patch cadence and supply-chain risk.

## 8. How to combine the evidence
1. Fix the SLO and the weights first (criteria.json).
2. Gate: a candidate that fails correctness (section 1) or the SLO at 5x peak is out.
3. Among survivors, weigh cost (6), integrations and hiring (7), then performance (this harness).
4. Re-run the shortlist on the realistic workload (2) before committing.
