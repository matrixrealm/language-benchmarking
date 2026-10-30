# Validation record

Executed in the creation environment:

- Python syntax compilation: passed for service, mock, runner and tests.
- Python endpoint integration: /health, /partner, /fanout, /payload and /cpu
  returned exact expected values; /meta and unknown route 404 passed.
- Concurrent Python integration: 40 fanout requests with 20 client threads passed.
- Resource parser fixture: CPU, memory, RSS, OOM and thread unit check passed.
- k6 script JavaScript syntax check via Node: passed (not k6 runtime validation).
- Runner command-line help: passed.

Added when the plan-review fixes were implemented (unit and local checks only):

- tests/test_harness.py: memory slope, leak screen, recovery, sample coverage, capacity
  gating, Latin-square order, decision rule (13 tests, passing). tests/test_sampler.py passing.
- Python candidate + mock local integration (tests/local_check.py) passing, including the
  new Python `gil_enabled` assertion; Go `go vet` passing; k6 script syntax check passing.
- Dry-run of matrix.py cell order and resume keys.
- NOT executed: scripts/sampler.py (needs a real cgroup v2 host), calibrate.py, startup.py,
  noise.py, summarize.py against real results, the Java /meta change, the multi-worker
  (SO_REUSEPORT) mock on Linux, and any Docker or k6 run. Docker Desktop was not running.

Not executed here (original package):

- Java 25 compile and virtual-thread execution (only Java 17 available).
- Go compilation/execution (Go toolchain unavailable).
- Docker builds, cgroup sampler against a real container, k6 runtime and
  performance profiles (Docker unavailable).
- Windows PowerShell execution or filesystem installation.

Run setup.ps1 and the three quick validation commands in README.md first.
Dependency/image availability and Docker Desktop bind mounts must be verified
on the target machine. Smoke runs validate the harness, not comparative speed.

## Addendum
- Contract tests cover the new endpoints; membuf/memobj results must equal the expected sums. Runs where the load generator got no responses (failure rate 1, p99 0) are kept but flagged invalid (Django at 600+ RPS partner, 1000 partner, 2000 payload).
- Known limits: one repeat per cell, laptop host, leak screen not evaluated (needs a 30 min soak).
