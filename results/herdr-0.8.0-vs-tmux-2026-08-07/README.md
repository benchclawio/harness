# herdr 0.8.0 vs tmux 3.4 vs tmux 3.7b

Supporting evidence for <https://benchclaw.io/herdr-vs-tmux/>.

Every page comparing herdr and tmux argues from features. None publishes a measurement.
These are the measurements.

**Subjects:**
- `herdr` **0.8.0** — official `herdr-linux-x86_64` release binary,
  SHA-256 `b872ea7e40fa2cb17e857ac9b62b1bf26db7b403c622f5d2f3f5b35f6e9acd28`
- `tmux` **3.4** — Ubuntu 24.04 package `3.4-1ubuntu0.1` (the LTS default)
- `tmux` **3.7b** — built from the official release tarball,
  SHA-256 `87f2e99e3b685973f2ca002ffd6ed7e51a5744f7009daae5a15670b6d532db96`

**Host:** Hetzner CX23, 2 vCPU / 4 GB, Intel Xeon (Skylake), Ubuntu 24.04.4 LTS,
kernel 6.8.0-117-generic, Helsinki
**Date:** 2026-08-07
**Measurements:** 378 across three arms, single run, interleaved per metric
**Cost:** ~€0.01 of server time. No model calls, no API spend — nothing here involves an LLM.

## Why three arms

The obvious comparison is herdr against tmux. But "tmux" is ambiguous: the version most
people have (`3.4`, shipped in Ubuntu 24.04 LTS) was released 2024-02-13, and four releases
have landed since. Upstream optimised the exact paths this benchmark measures — `getpwuid`
caching taken off the startup path (issue 4973), and a fork race in pane creation
(issue 4719).

Benchmarking a current tool against a 2.5-year-old comparator systematically flatters the
tool under review. So both tmux versions run as separate arms, on the same box, in the same
interleaved run. That separates "herdr is faster" from "the tmux you have is old" — and the
distinction turns out to carry the entire result.

## Design

Six metrics, each measured independently and never combined into a score. Arms are
interleaved per metric so host drift hits all three equally.

| Metric | What it times | n per arm |
|---|---|---|
| `cli_overhead_ms` | one scripted CLI call against a running server | 30 |
| `create_ms` | create a session/workspace with a live shell | 30 |
| `roundtrip_ms` | send a command, poll until output is readable | 30 |
| `server_start_ms` | cold server start, after confirming it is down | 20 |
| `survive` | work survives an abruptly killed client | 10 |
| `rss_kb_total` | resident memory at 0/1/5/10/20/40 held sessions | 6 points |

Two isolation details that materially affect correctness:

- **Each tmux arm runs on its own `-L` socket.** Without separate sockets the two versions
  share one server and are not two arms at all.
- **RSS is attributed by PID tree from each arm's own server PID**, obtained from
  `display-message -p '#{pid}'` for tmux. Matching on process name would sum both tmux
  servers together — they are both called `tmux: server`.

Confidence intervals are bootstrap percentile intervals, 10,000 resamples, seed `20260807`,
on the difference of means. A difference is called only when its 95% CI excludes zero.

## Results

Times in milliseconds, mean (SD):

| Metric | herdr 0.8.0 | tmux 3.4 | tmux 3.7b |
|---|---|---|---|
| CLI invocation | 4.72 (1.18) | 5.82 (1.33) | **4.38 (0.97)** |
| Create session | 9.51 (3.09) | 14.58 (4.04) | **5.16 (1.15)** |
| Command round-trip | 14.55 (3.21) | 11.42 (2.84) | **7.85 (1.77)** |
| Server cold start | **20.18 (12.64)** | 38.78 (8.66) | 29.89 (5.70) |

herdr against **current** tmux (positive = herdr slower):

| Metric | Difference | 95% CI | Called |
|---|---|---|---|
| CLI invocation | +0.33 | −0.18 to +0.89 | not significant |
| Create session | +4.34 | +3.25 to +5.57 | tmux 3.7b faster |
| Command round-trip | +6.69 | +5.40 to +7.97 | tmux 3.7b faster |
| Server cold start | −9.70 | −15.69 to −3.89 | herdr faster |

tmux 3.7b against tmux 3.4 — the size of the version effect:

| Metric | Difference | 95% CI |
|---|---|---|
| CLI invocation | −1.44 | −2.06 to −0.89 |
| Create session | −9.42 | −10.98 to −8.04 |
| Command round-trip | −3.56 | −4.75 to −2.43 |
| Server cold start | −8.89 | −13.18 to −4.47 |

**Memory:**

| Arm | Baseline | Marginal per session |
|---|---|---|
| herdr 0.8.0 | 16,160 kB | 4,771 kB |
| tmux 3.4 | 10,656 kB | 5,670 kB |
| tmux 3.7b | 9,708 kB | 5,676 kB |

herdr's floor is higher, its marginal cost lower; they cross at **~7.1 sessions** against
tmux 3.7b.

**Survival: 10/10 on all three arms, 0 invalid.** No measured difference.

## The survival test was wrong the first time

The first run reported herdr surviving 9 of 10 client kills. That result is withdrawn — not
because of the value, but because the test did not do what it claimed.

A bare `herdr` attaches to the **focused** workspace. Each repetition created a fresh
workspace and never focused it, so the client being killed was rendering a *different*
workspace from the one running the marker loop. The tmux arm used
`attach-session -t <label>` and attached directly to the session under test. The two arms
were not running the same experiment, and herdr was running the easier one.

The corrected test focuses the workspace before attaching and gates every repetition on the
server snapshot confirming the client is on the target. A repetition that cannot be shown to
have exercised the condition is recorded **invalid**, not as a pass. Under the corrected
test all three arms are 10/10 with 0 invalid.

`superseded-first-run/` contains the original data and the corrected survival reproduction,
published because a withdrawn result should be inspectable.

## Files

| File | Contents |
|---|---|
| `bench3.py` | the harness — three arms, all six metrics |
| `analyze3.py` | bootstrap analysis, fixed seed, pairwise differences |
| `herdr-tmux-scored-raw-2026-08-07.jsonl` | every measurement, one record per line |
| `herdr-tmux-analysis-2026-08-07.json` | computed statistics |
| `herdr-tmux-smoke-raw-2026-08-07.jsonl` | 3-rep smoke run that validated the harness |
| `environment-2026-08-07.txt` | versions, checksums, kernel, CPU, memory |
| `agent-tooling-methodology-v0.1.0.md` | methodology addendum for this cluster |
| `superseded-first-run/` | the withdrawn first run and the corrected survival repro |

## Reproducing

```
python3 bench3.py results.jsonl 30
python3 analyze3.py results.jsonl analysis.json
```

Requires `herdr` at `~/.local/bin/herdr`, tmux at `/usr/bin/tmux`, and a second tmux build
at `/opt/tmux37b/bin/tmux`. Edit the constants at the top for other paths or versions.

## What this does not measure

Shell processes, not coding agents. Every claim herdr makes about agent-specific
awareness — state tracking, orchestration APIs — is outside this benchmark. So is
interactive latency under a real terminal, behaviour over a high-latency SSH link,
multi-user access, and plugin ecosystems. One host class, one CPU model, one day.
