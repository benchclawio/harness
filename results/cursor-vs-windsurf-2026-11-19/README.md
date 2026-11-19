# Cursor vs Windsurf / Devin Desktop public-records audit

Captured November 19, 2026. This is a documentation audit, not a product benchmark.
Neither editor was installed; no coding tasks, agent runs, exploit tests, latency or task-cost measurements were performed.

## Files
- [source-records.json](source-records.json): sixteen public URLs, UTC capture times, HTTP status, final URL, selected excerpts and SHA-256 of each original response.
- [collect.mjs](collect.mjs): read-only collector, one public GET per URL, 25-second limit, stops at first error. No credentials, retries or paid API requests. An optional output path can be supplied. A new capture can differ because upstream documents change.
- [claim-audit.md](claim-audit.md): interpretations, limitations and ignored embedded instructions.

The JSON contains selected excerpts, not complete archived response bodies. Hashes identify the response that was read; a hash alone does not reconstruct it.
