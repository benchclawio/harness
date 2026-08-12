#!/usr/bin/env python3
"""bc-039 export readers: pull raw records from each tool's OWN API and normalise them.

Every reader returns the same flat shape so `bc039_capture.compare` can be tool-agnostic:

    {"run_id": str, "step_index": int, "parent_step_index": int|None,
     "kind": str, "has_error": bool, "tokens_in": int|None, "tokens_out": int|None}

No dashboards, no vendor aggregation. Counted by us.

VERIFIED AGAINST LIVE BACKENDS 2026-08-12 on the study host (Langfuse 4.10.0 server /
SDK 4.14.4, Phoenix 20.1.0). Two findings that would each have produced a false result:

1. **Langfuse omits `metadata` from the default projection of
   `GET /api/public/v2/observations`.** The field comes back only when `fields=metadata` is
   passed. Our correlation key lives in metadata, so a reader written without that parameter
   sees zero correlatable spans and would report ~0% capture for a tool that in fact captured
   everything. Confirmed present and byte-intact once requested.

2. **The v1 `/api/public/observations` endpoint is unavailable on a v4 deployment**
   (`events_only mode`) and the SDK's `api.observations.get_many()` targets it, returning a
   thin, partly-empty record. The v2 endpoint is the only correct source here.

3. **`fields=metadata` and the default projection are mutually exclusive.** Requesting
   metadata returns `name`, `level` and `statusMessage` as `None`; requesting `fields=all`
   returns those but drops metadata. There is no single call that yields both. A reader that
   asks only for metadata therefore sees `level=None` on every record and scores **every
   injected error as uncaptured** — which in a first smoke run produced an apparent
   "Langfuse captured 0 of 2 errors, Phoenix captured 2 of 2". That was an artefact of this
   reader, not Langfuse behaviour, and it is corrected by joining two calls on observation id.

   This is worth reporting in the article as an API-ergonomics finding. It is emphatically
   **not** a data-loss finding, and must never be presented as one.

4. **The endpoint is cursor-paginated and silently ignores `page`.** Requesting `page=2..5`
   returns the identical first 100 rows each time, with an unchanged `meta.cursor`. A
   page-number reader therefore collects 100 unique records no matter how much data exists —
   against 400 issued spans that reads as 25% capture. A single `limit=500` call returned all
   402 records (400 scored + 2 probes), confirming nothing was dropped.

   Both (3) and (4) would have produced a severe, publishable-looking false accusation
   against Langfuse. Neither is a Langfuse defect. They are the reason the protocol requires
   reading raw records and counting them ourselves — and the reason a positive control that
   only checks "did anything arrive" is not sufficient on its own: both bugs pass a
   two-span probe and only appear at volume.
"""

from __future__ import annotations

import datetime as _dt

LLM = "llm"
TOOL = "tool"
RETRIEVAL = "retrieval"


def _as_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Langfuse
# ---------------------------------------------------------------------------

def _langfuse_pages(host, token, params, limit=100):
    """Iterate every observation in the window.

    CURSOR pagination, not page-number pagination. See finding (4) in the module docstring:
    `/api/public/v2/observations` ignores a `page` parameter entirely and returns the same
    first window every time. Pagination is driven by the opaque `meta.cursor` echoed back
    into the next request.
    """
    import json
    import urllib.parse
    import urllib.request

    cursor = None
    seen_cursors = set()
    for _ in range(500):  # defensive: never loop unbounded against a live API
        query_params = {**params, "limit": str(limit)}
        if cursor:
            query_params["cursor"] = cursor
        query = urllib.parse.urlencode(query_params)
        request = urllib.request.Request(
            f"{host}/api/public/v2/observations?{query}",
            headers={"Authorization": f"Basic {token}"},
        )
        with urllib.request.urlopen(request, timeout=90) as response:
            payload = json.loads(response.read().decode())
        batch = payload.get("data") or []
        yield from batch
        if len(batch) < limit:
            return
        cursor = (payload.get("meta") or {}).get("cursor")
        # A repeated or absent cursor means the server is not advancing. Stopping here is
        # what turns a silent truncation into a visible one.
        if not cursor or cursor in seen_cursors:
            return
        seen_cursors.add(cursor)


def read_langfuse(host: str, public_key: str, secret_key: str, window_minutes: int = 240) -> list[dict]:
    """Read observations from Langfuse's public v2 API.

    TWO CALLS, JOINED ON OBSERVATION ID — and this is not an optimisation, it is required for
    correctness. See finding (3) in the module docstring: `fields=metadata` and the default
    projection are mutually exclusive on this endpoint. A single call cannot see both the
    correlation key and the observation level, and a reader that asks only for metadata reads
    `level` as `None` for every record, which scores every error as uncaptured.

    Nesting is reported as `parentObservationId`, an opaque id, so parents are resolved
    through our own step indices — a captured-but-reparented span is then detectable rather
    than silently accepted.
    """
    import base64

    now = _dt.datetime.now(_dt.timezone.utc)
    window = {
        "fromStartTime": (now - _dt.timedelta(minutes=window_minutes)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "toStartTime": (now + _dt.timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    token = base64.b64encode(f"{public_key}:{secret_key}".encode()).decode()

    # Pass 1: correlation key and usage. Core fields come back null here.
    meta_by_id = {}
    for item in _langfuse_pages(host, token, {**window, "fields": "metadata,usage"}):
        metadata = item.get("metadata") or {}
        step_index = _as_int(metadata.get("benchclaw.step_index"))
        if step_index is None:
            continue
        meta_by_id[item["id"]] = (metadata, step_index, item.get("usage") or {})

    # Pass 2: core fields — level, statusMessage, parentObservationId. No metadata here.
    core_by_id = {}
    for item in _langfuse_pages(host, token, dict(window)):
        core_by_id[item["id"]] = item

    step_of = {oid: meta_by_id[oid][1] for oid in meta_by_id}

    records = []
    for observation_id, (metadata, step_index, usage) in meta_by_id.items():
        core = core_by_id.get(observation_id, {})
        parent_id = core.get("parentObservationId")
        records.append(
            {
                "run_id": metadata.get("benchclaw.run_id"),
                "step_index": step_index,
                "parent_step_index": step_of.get(parent_id),
                "kind": metadata.get("benchclaw.kind"),
                "has_error": (core.get("level") == "ERROR") or bool(core.get("statusMessage")),
                "tokens_in": _as_int(usage.get("input") if usage else None),
                "tokens_out": _as_int(usage.get("output") if usage else None),
                "core_fields_joined": observation_id in core_by_id,
            }
        )
    return records


# ---------------------------------------------------------------------------
# Phoenix
# ---------------------------------------------------------------------------

def read_phoenix(base_url: str, project: str) -> list[dict]:
    """Read spans from Phoenix's own client API.

    `get_spans_dataframe` returns our custom attributes nested under an
    `attributes.benchclaw` column rather than flattened, which is why this reads the dict
    instead of looking for `attributes.benchclaw.run_id`.
    """
    from phoenix.client import Client

    client = Client(base_url=base_url)
    frame = client.spans.get_spans_dataframe(project_identifier=project)
    if len(frame) == 0:
        return []

    rows = frame.to_dict(orient="records")

    by_span_id = {}
    for row in rows:
        attributes = row.get("attributes.benchclaw") or {}
        if not isinstance(attributes, dict):
            continue
        step_index = _as_int(attributes.get("step_index"))
        if step_index is None:
            continue
        by_span_id[row.get("context.span_id")] = (row, attributes, step_index)

    records = []
    for row, attributes, step_index in by_span_id.values():
        parent_id = row.get("parent_id")
        parent_step = by_span_id[parent_id][2] if parent_id in by_span_id else None
        records.append(
            {
                "run_id": attributes.get("run_id"),
                "step_index": step_index,
                "parent_step_index": parent_step,
                "kind": attributes.get("kind"),
                "has_error": str(row.get("status_code") or "").upper() == "ERROR",
                "tokens_in": _as_int(attributes.get("tokens_in")),
                "tokens_out": _as_int(attributes.get("tokens_out")),
            }
        )
    return records
