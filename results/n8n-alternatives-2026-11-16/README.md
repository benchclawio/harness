# n8n alternatives: public-records audit, 2026-11-16

Evidence for BenchClaw's n8n alternatives guide. This is a documentary comparison, not a
benchmark: no product was installed and no agent was run. No model API was called for the
product comparison. No performance, completion-rate or reliability conclusion is implied.

## Files

- `records.json`: dated repository metadata, GitHub latest-release designation, licence
  excerpts, up to ten public security advisories per repository, and bounded first-party
  page excerpts. Source URLs, HTTP status, final URLs and original body hashes are retained.
  Release-note bodies are omitted, licence text is capped at 3,400 characters, and the first
  ten page excerpts are retained. Full primary sources remain linked.
- `collect.mjs`: zero-dependency Node collector with an output-path option. It makes one
  request per specified endpoint, without retrying failed pages. Results change over time.

The original collection used a base run followed by an extra sunset/README phase. Those
sources are all in the published collector's default list now. To collect current data,
use Node 24 or newer, invoke `collect.mjs`, and pass `--output=records-current.json` to
avoid replacing the historical snapshot. It contacts public vendor and GitHub endpoints,
needs no API key, and does not contact a paid service. Its output has fuller excerpts than
the bounded publication projection. Underlying source licences and copyrights remain with
their respective owners.

## Main observations

- n8n's September 25 announcement describes first-class Agents, distinct from the AI Agent
  workflow node. Current docs call Agents preview, available on all Cloud plans and
  self-hosted from 2.32.3. Capabilities are documented, not experimentally verified here.
- n8n uses SUL/Enterprise terms; Activepieces has an MIT core and commercial exclusions;
  Windmill distinguishes source licences from the supplied Community Edition binary;
  Dify's Apache derivative adds multi-tenant and frontend-branding conditions.
- Flowise's official sunset notice gives August 31, 2026 EOL. GitHub reports it archived.
  Remaining Apache-licensed code is distinct from a maintained upstream project.
- Make product/pricing pages returned HTTP 403. No retry or tariff/capability verdict.
- GitHub's latest-release endpoint is not a claim that no newer branch release exists.
  n8n advisories list multiple patched branches.

The advisory checks are a bounded sample, not total counts, complete incident histories,
or security certifications. Repository and homepage checks establish observed maintenance
signals, not an exhaustive corporate-ownership investigation.

## Search provenance

One separately approved DataForSEO US/English/desktop live-advanced SERP for
`n8n alternatives`, 2026-11-16 18:59 UTC, cost $0.00215. It returned nine organic results,
an AI Overview, six PAA questions and eight related searches. The AI Overview included
Flowise despite its official sunset. Full paid search data stays in the editorial
workspace; this bundle does not republish the full Google or competitor page content.
