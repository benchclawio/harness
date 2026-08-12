#!/usr/bin/env python3
"""bc-039 arm wiring: one Tracer per arm, plus the blocking positive-control gate.

VERIFIED against live backends on the study host 2026-08-12 (Langfuse server 4.10.0 /
SDK 4.14.4, Phoenix 20.1.0). An earlier draft of this file guessed a `client._otel_tracer`
attribute that does not exist; the real Langfuse v4 surface is `start_observation`, and child
spans are created from the parent observation rather than through an OTel context. That is
the kind of error the positive-control gate exists to catch before it reaches a number.

Each arm is instrumented the way its own documentation prescribes rather than forced into a
common shape — Langfuse through its native observation types, Phoenix through OpenTelemetry
with `phoenix.otel.register`. That is the realistic condition a reader faces, and it means a
capture difference may reflect the recommended integration rather than the storage backend.
The article must say so rather than implying we isolated the backend.

Imports are lazy and per-arm so `control` — and the offline test suite — run on a host with
none of these packages installed.
"""

from __future__ import annotations

import time
import uuid

LLM = "llm"
TOOL = "tool"
RETRIEVAL = "retrieval"

FLUSH_WINDOW_S = 30

# Langfuse models observation types natively. Using the idiomatic type per signal is how the
# tool is meant to be driven; forcing everything to a generic span would measure a
# configuration we invented rather than the one its users are told to write.
_LANGFUSE_TYPE = {LLM: "generation", TOOL: "tool", RETRIEVAL: "retriever"}


# ---------------------------------------------------------------------------
# control
# ---------------------------------------------------------------------------

class _NullSpan:
    def set_attribute(self, key, value):
        return None

    def record_error(self, exc):
        return None

    def end(self):
        return None


class ControlTracer:
    """No SDK, no exporter, no tracer provider. The mandatory overhead baseline."""

    name = "control"

    def start_span(self, name, kind, parent, attributes):
        return _NullSpan()

    def flush(self):
        return None


# ---------------------------------------------------------------------------
# Langfuse
# ---------------------------------------------------------------------------

class _LangfuseSpan:
    def __init__(self, observation):
        self._observation = observation
        self._pending = {}

    def set_attribute(self, key, value):
        # Buffered and flushed on end(): metadata is written as a whole object, so setting
        # it per attribute would overwrite the correlation key we depend on.
        self._pending[key] = value

    def record_error(self, exc):
        self._observation.update(level="ERROR", status_message=str(exc))

    def end(self):
        if self._pending:
            self._observation.update(metadata=self._pending)
        self._observation.end()


class LangfuseTracer:
    name = "langfuse"

    def __init__(self, client):
        self._client = client

    def start_span(self, name, kind, parent, attributes):
        as_type = _LANGFUSE_TYPE.get(kind, "span")
        metadata = dict(attributes)
        if parent is None:
            observation = self._client.start_observation(name=name, as_type=as_type, metadata=metadata)
        else:
            # Nesting is expressed through the parent observation, not an ambient context.
            observation = parent._observation.start_observation(
                name=name, as_type=as_type, metadata=metadata
            )
        span = _LangfuseSpan(observation)
        span._pending.update(metadata)
        return span

    def flush(self):
        self._client.flush()


def build_langfuse_tracer(host: str, public_key: str, secret_key: str) -> LangfuseTracer:
    from langfuse import Langfuse

    client = Langfuse(public_key=public_key, secret_key=secret_key, host=host)
    if not client.auth_check():
        raise RuntimeError("Langfuse auth_check failed")
    return LangfuseTracer(client)


# ---------------------------------------------------------------------------
# Phoenix (OpenTelemetry)
# ---------------------------------------------------------------------------

class _OtelSpan:
    def __init__(self, span):
        self._span = span

    def set_attribute(self, key, value):
        self._span.set_attribute(key, value)

    def record_error(self, exc):
        from opentelemetry.trace import Status, StatusCode

        self._span.record_exception(exc)
        self._span.set_status(Status(StatusCode.ERROR, str(exc)))

    def end(self):
        self._span.end()


class PhoenixTracer:
    name = "phoenix"

    def __init__(self, provider, tracer):
        self._provider = provider
        self._tracer = tracer

    def start_span(self, name, kind, parent, attributes):
        from opentelemetry import trace as otel_trace

        context = otel_trace.set_span_in_context(parent._span) if parent is not None else None
        span = self._tracer.start_span(name, context=context)
        for key, value in attributes.items():
            span.set_attribute(key, value)
        return _OtelSpan(span)

    def flush(self):
        self._provider.force_flush()


def build_phoenix_tracer(endpoint: str, project_name: str) -> PhoenixTracer:
    from phoenix.otel import register

    provider = register(
        project_name=project_name,
        endpoint=endpoint,
        batch=True,
        auto_instrument=False,
        set_global_tracer_provider=False,
    )
    return PhoenixTracer(provider, provider.get_tracer("benchclaw.bc039"))


# ---------------------------------------------------------------------------
# Positive control — a blocking gate, not a checklist item
# ---------------------------------------------------------------------------

def positive_control(tracer, read_back, flush_window_s: int = FLUSH_WINDOW_S) -> dict:
    """Emit one known probe span, flush, wait the declared window, and read it back.

    `read_back()` must query the tool's OWN API and return normalised records.

    The caller MUST refuse to run a measured window for any arm whose verdict is not
    `passed`. Zero spans from a misconfigured exporter is indistinguishable from total data
    loss at analysis time, and the two must never be confused.
    """
    probe_run_id = f"probe-{uuid.uuid4().hex}"
    attributes = {
        "benchclaw.run_id": probe_run_id,
        "benchclaw.step_index": 0,
        "benchclaw.scenario": "positive-control",
        "benchclaw.kind": LLM,
    }
    parent = tracer.start_span("benchclaw.positive_control", LLM, None, attributes)
    child_attributes = dict(attributes, **{"benchclaw.step_index": 1, "benchclaw.kind": TOOL})
    # A probe with a child also proves nesting survives, which a single flat span cannot.
    child = tracer.start_span("benchclaw.positive_control.child", TOOL, parent, child_attributes)
    child.end()
    parent.end()

    tracer.flush()
    time.sleep(flush_window_s)

    try:
        records = read_back()
    except Exception as exc:
        return {"arm": tracer.name, "passed": False, "probe_run_id": probe_run_id,
                "reason": f"read-back raised: {type(exc).__name__}: {exc}"}

    matching = [r for r in records if r.get("run_id") == probe_run_id]
    if not matching:
        return {"arm": tracer.name, "passed": False, "probe_run_id": probe_run_id,
                "reason": "probe span never arrived through the tool's own API",
                "records_seen": len(records)}

    nested = [r for r in matching if r.get("parent_step_index") == 0]
    return {
        "arm": tracer.name,
        "passed": len(matching) == 2 and len(nested) == 1,
        "probe_run_id": probe_run_id,
        "spans_returned": len(matching),
        "nesting_returned": len(nested),
        "reason": None if (len(matching) == 2 and len(nested) == 1)
        else f"expected 2 spans and 1 nested edge, got {len(matching)} and {len(nested)}",
        "flush_window_s": flush_window_s,
    }
