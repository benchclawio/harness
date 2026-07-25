from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from .common import load_json, sha256_file
from .redaction import scan_public_value


FAILURE_TYPES = {
    "adapter_install_error",
    "subject_init_error",
    "authentication_error",
    "provider_error",
    "rate_limited",
    "timeout",
    "malformed_tool_call",
    "tool_error",
    "invalid_final_answer",
    "context_overflow",
    "loop_or_budget_exhausted",
    "unhandled_exception",
    "environment_error",
    "evaluator_error",
    "policy_blocked",
    "unknown",
}
OUTCOMES = {"success", "failure", "error", "timeout", "policy_blocked"}
SHA256 = re.compile(r"^[a-f0-9]{64}$")


def _keys(value: dict[str, Any], required: set[str], allowed: set[str], path: str) -> list[str]:
    errors = [f"{path}: missing {key}" for key in sorted(required - value.keys())]
    errors.extend(f"{path}: unexpected {key}" for key in sorted(value.keys() - allowed))
    return errors


def validate_event(event: Any, line_number: int | None = None) -> list[str]:
    prefix = f"event[{line_number}]" if line_number is not None else "event"
    if not isinstance(event, dict):
        return [f"{prefix}: expected object"]
    required = {
        "schema_version", "event_id", "run_id", "recorded_at", "publication_eligible",
        "subject", "task", "pair", "model", "environment", "parameters", "outcome",
        "metrics", "failure", "provenance",
    }
    allowed = required | {"supersedes_event_id"}
    errors = _keys(event, required, allowed, prefix)
    if event.get("schema_version") != "1.0.0":
        errors.append(f"{prefix}.schema_version: expected 1.0.0")
    if not isinstance(event.get("publication_eligible"), bool):
        errors.append(f"{prefix}.publication_eligible: expected boolean")
    for name in ["event_id", "run_id", "recorded_at"]:
        if not isinstance(event.get(name), str) or not event[name]:
            errors.append(f"{prefix}.{name}: expected non-empty string")
    if isinstance(event.get("event_id"), str) and not re.match(
        r"^[a-zA-Z0-9._:-]{8,160}$", event["event_id"]
    ):
        errors.append(f"{prefix}.event_id: invalid format")
    if isinstance(event.get("recorded_at"), str):
        try:
            datetime.fromisoformat(event["recorded_at"].replace("Z", "+00:00"))
        except ValueError:
            errors.append(f"{prefix}.recorded_at: invalid date-time")

    object_shapes = {
        "subject": ({"id", "version", "adapter", "adapter_version"}, set()),
        "task": ({"suite_id", "suite_version", "id", "input_sha256"}, set()),
        "pair": ({"key", "run_index", "order_index"}, set()),
        "model": ({"provider", "id", "temperature"}, set()),
        "environment": ({"harness_version", "python_version", "platform", "region"}, set()),
        "parameters": ({"seed", "timeout_s"}, set()),
        "outcome": ({"status", "completed"}, set()),
        "metrics": ({"tokens_in", "tokens_out", "cost_usd", "wall_time_s", "tool_calls"}, set()),
        "provenance": ({"config_sha256", "task_suite_sha256", "source_revision"}, set()),
    }
    for name, (shape_required, shape_optional) in object_shapes.items():
        value = event.get(name)
        if not isinstance(value, dict):
            errors.append(f"{prefix}.{name}: expected object")
            continue
        errors.extend(_keys(value, shape_required, shape_required | shape_optional, f"{prefix}.{name}"))

    for parent_name, field_names in {
        "subject": {"id", "version", "adapter", "adapter_version"},
        "task": {"suite_id", "suite_version", "id"},
        "environment": {"harness_version", "python_version", "platform", "region"},
        "provenance": {"source_revision"},
    }.items():
        parent = event.get(parent_name)
        if isinstance(parent, dict):
            for field_name in field_names:
                if not isinstance(parent.get(field_name), str) or not parent[field_name]:
                    errors.append(f"{prefix}.{parent_name}.{field_name}: expected non-empty string")

    pair = event.get("pair")
    if isinstance(pair, dict):
        if not isinstance(pair.get("key"), str) or not pair["key"]:
            errors.append(f"{prefix}.pair.key: expected non-empty string")
        for field_name in ["run_index", "order_index"]:
            value = pair.get(field_name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                errors.append(f"{prefix}.pair.{field_name}: expected non-negative integer")

    parameters = event.get("parameters")
    if isinstance(parameters, dict):
        if not isinstance(parameters.get("seed"), int) or isinstance(parameters.get("seed"), bool):
            errors.append(f"{prefix}.parameters.seed: expected integer")
        timeout = parameters.get("timeout_s")
        if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or timeout <= 0:
            errors.append(f"{prefix}.parameters.timeout_s: expected positive number")

    model = event.get("model")
    if isinstance(model, dict):
        for field_name in ["provider", "id"]:
            if not isinstance(model.get(field_name), str) or not model[field_name]:
                errors.append(f"{prefix}.model.{field_name}: expected non-empty string")
        if not isinstance(model.get("temperature"), (int, float)) or isinstance(
            model.get("temperature"), bool
        ):
            errors.append(f"{prefix}.model.temperature: expected number")

    outcome = event.get("outcome")
    if isinstance(outcome, dict):
        if outcome.get("status") not in OUTCOMES:
            errors.append(f"{prefix}.outcome.status: invalid")
        if not isinstance(outcome.get("completed"), bool):
            errors.append(f"{prefix}.outcome.completed: expected boolean")
        if outcome.get("completed") and outcome.get("status") != "success":
            errors.append(f"{prefix}.outcome: completed requires success status")
        if outcome.get("completed") and event.get("failure") is not None:
            errors.append(f"{prefix}.failure: completed event cannot have failure")

    metrics = event.get("metrics")
    if isinstance(metrics, dict):
        for field_name in ["tokens_in", "tokens_out", "tool_calls"]:
            value = metrics.get(field_name)
            if value is not None and (
                not isinstance(value, int) or isinstance(value, bool) or value < 0
            ):
                errors.append(f"{prefix}.metrics.{field_name}: expected non-negative integer or null")
        for field_name in ["cost_usd", "wall_time_s"]:
            value = metrics.get(field_name)
            if value is not None and (
                not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0
            ):
                errors.append(f"{prefix}.metrics.{field_name}: expected non-negative number or null")

    failure = event.get("failure")
    if failure is not None:
        if not isinstance(failure, dict):
            errors.append(f"{prefix}.failure: expected object or null")
        else:
            failure_keys = {"type", "stage", "message_sanitized"}
            errors.extend(_keys(failure, failure_keys, failure_keys, f"{prefix}.failure"))
            if failure.get("type") not in FAILURE_TYPES:
                errors.append(f"{prefix}.failure.type: invalid")
            if len(str(failure.get("message_sanitized", ""))) > 240:
                errors.append(f"{prefix}.failure.message_sanitized: too long")
    elif isinstance(outcome, dict) and not outcome.get("completed"):
        errors.append(f"{prefix}.failure: incomplete event requires failure")

    for path in [
        ("task", "input_sha256"),
        ("provenance", "config_sha256"),
        ("provenance", "task_suite_sha256"),
    ]:
        parent = event.get(path[0])
        value = parent.get(path[1]) if isinstance(parent, dict) else None
        if not isinstance(value, str) or not SHA256.match(value):
            errors.append(f"{prefix}.{path[0]}.{path[1]}: invalid sha256")

    errors.extend(f"{prefix} redaction {finding}" for finding in scan_public_value(event))
    return errors


def read_events(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            event = json.loads(line)
            errors = validate_event(event, line_number)
            if errors:
                raise ValueError("\n".join(errors))
            events.append(event)
    if not events:
        raise ValueError("events.jsonl is empty")
    ids = [event["event_id"] for event in events]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate event_id")
    return events


def verify_bundle(root: Path) -> dict[str, Any]:
    root = root.resolve()
    manifest_path = root / "manifest.json"
    manifest = load_json(manifest_path)
    if manifest.get("schema_version") != "1.0.0":
        raise ValueError("unsupported manifest schema")
    records = [manifest["config"], manifest["task_suite"], *manifest["artifacts"]]
    checked: list[str] = []
    for record in records:
        relative = Path(record["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"unsafe artifact path: {relative}")
        target = (root / relative).resolve()
        if root not in target.parents:
            raise ValueError(f"artifact escapes bundle: {relative}")
        if not target.is_file():
            raise ValueError(f"missing artifact: {relative}")
        if sha256_file(target) != record["sha256"]:
            raise ValueError(f"digest mismatch: {relative}")
        if target.stat().st_size != record["bytes"]:
            raise ValueError(f"size mismatch: {relative}")
        checked.append(relative.as_posix())
    events = read_events(root / "events.jsonl")
    analysis = load_json(root / "analysis.json")
    if analysis.get("run_id") != manifest.get("run_id"):
        raise ValueError("analysis and manifest run_id differ")
    if any(event["run_id"] != manifest["run_id"] for event in events):
        raise ValueError("event and manifest run_id differ")
    if any(event["publication_eligible"] != manifest["publication_eligible"] for event in events):
        raise ValueError("event and manifest publication eligibility differ")
    return {"run_id": manifest["run_id"], "events": len(events), "artifacts": checked}
