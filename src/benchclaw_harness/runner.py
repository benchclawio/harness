from __future__ import annotations

import json
import platform
import shutil
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .analysis import analyze
from .common import artifact_record, iso_now, load_json, sha256_file, sha256_json, write_json
from .fixtures import ADAPTERS
from .redaction import sanitize_message
from .validation import read_events, verify_bundle


def _validate_config(config: dict[str, Any]) -> None:
    required = {
        "run_id",
        "publication_eligible",
        "source_revision",
        "region",
        "task_suite_path",
        "runs_per_task",
        "timeout_s",
        "seed",
        "model",
        "analysis",
        "subjects",
    }
    missing = required - config.keys()
    if missing:
        raise ValueError(f"missing config fields: {', '.join(sorted(missing))}")
    if config["publication_eligible"] is not False:
        raise ValueError("minimal fixture runner requires publication_eligible=false")
    if config["runs_per_task"] < 1:
        raise ValueError("runs_per_task must be positive")
    if len(config["subjects"]) < 2:
        raise ValueError("pilot requires at least two subjects")
    unknown = [s["adapter"] for s in config["subjects"] if s["adapter"] not in ADAPTERS]
    if unknown:
        raise ValueError(f"unknown adapters: {', '.join(unknown)}")


def _pair_key(suite_digest: str, task_id: str, run_index: int) -> str:
    return f"{suite_digest[:16]}:{task_id}:{run_index:04d}"


def _event_id(run_id: str, pair_key: str, subject_id: str) -> str:
    return f"evt:{sha256_json([run_id, pair_key, subject_id])[:40]}"


def run_fixture_pilot(config_path: Path, output: Path) -> dict[str, Any]:
    config_path = config_path.resolve()
    config = load_json(config_path)
    _validate_config(config)
    task_suite_path = (config_path.parent / config["task_suite_path"]).resolve()
    task_suite = load_json(task_suite_path)
    if not task_suite.get("tasks"):
        raise ValueError("task suite has no tasks")

    output.mkdir(parents=True, exist_ok=False)
    inputs = output / "inputs"
    inputs.mkdir()
    frozen_config = inputs / "config.json"
    frozen_tasks = inputs / "task-suite.json"
    shutil.copyfile(config_path, frozen_config)
    shutil.copyfile(task_suite_path, frozen_tasks)

    config_digest = sha256_file(frozen_config)
    task_digest = sha256_file(frozen_tasks)
    events_path = output / "events.jsonl"
    subjects = config["subjects"]

    with events_path.open("x", encoding="utf-8") as handle:
        for task_index, task in enumerate(task_suite["tasks"]):
            input_digest = sha256_json(task["input"])
            for run_index in range(config["runs_per_task"]):
                pair_key = _pair_key(task_digest, task["id"], run_index)
                start = (task_index * config["runs_per_task"] + run_index + config["seed"]) % len(subjects)
                ordered_subjects = subjects[start:] + subjects[:start]
                for order_index, subject in enumerate(ordered_subjects):
                    seed_material = f"{config['seed']}:{pair_key}:{subject['id']}"
                    adapter = ADAPTERS[subject["adapter"]]
                    try:
                        result = adapter(task, seed_material)
                    except Exception as exc:  # defensive boundary for future adapters
                        result = {
                            "status": "error",
                            "completed": False,
                            "metrics": {
                                "tokens_in": None,
                                "tokens_out": None,
                                "cost_usd": 0.0,
                                "wall_time_s": None,
                                "tool_calls": None,
                            },
                            "failure": {
                                "type": "unhandled_exception",
                                "stage": "adapter",
                                "message_sanitized": sanitize_message(type(exc).__name__),
                            },
                        }
                    event = {
                        "schema_version": "1.0.0",
                        "event_id": _event_id(config["run_id"], pair_key, subject["id"]),
                        "run_id": config["run_id"],
                        "recorded_at": iso_now(),
                        "publication_eligible": False,
                        "subject": {
                            "id": subject["id"],
                            "version": subject["version"],
                            "adapter": subject["adapter"],
                            "adapter_version": subject["adapter_version"],
                        },
                        "task": {
                            "suite_id": task_suite["suite_id"],
                            "suite_version": task_suite["suite_version"],
                            "id": task["id"],
                            "input_sha256": input_digest,
                        },
                        "pair": {
                            "key": pair_key,
                            "run_index": run_index,
                            "order_index": order_index,
                        },
                        "model": config["model"],
                        "environment": {
                            "harness_version": __version__,
                            "python_version": platform.python_version(),
                            "platform": f"{sys.platform}-{platform.machine()}",
                            "region": config["region"],
                        },
                        "parameters": {
                            "seed": config["seed"],
                            "timeout_s": config["timeout_s"],
                        },
                        "outcome": {
                            "status": result["status"],
                            "completed": result["completed"],
                        },
                        "metrics": result["metrics"],
                        "failure": result["failure"],
                        "provenance": {
                            "config_sha256": config_digest,
                            "task_suite_sha256": task_digest,
                            "source_revision": config["source_revision"],
                        },
                    }
                    handle.write(json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n")

    events = read_events(events_path)
    analysis_config = config["analysis"]
    analysis = analyze(
        events,
        seed=config["seed"],
        replicates=analysis_config["bootstrap_replicates"],
        confidence_level=analysis_config["confidence_level"],
    )
    analysis_path = output / "analysis.json"
    write_json(analysis_path, analysis)

    manifest = {
        "schema_version": "1.0.0",
        "run_id": config["run_id"],
        "created_at": iso_now(),
        "publication_eligible": False,
        "harness_version": __version__,
        "source_revision": config["source_revision"],
        "config": artifact_record(output, frozen_config),
        "task_suite": artifact_record(output, frozen_tasks),
        "analysis": {
            "seed": config["seed"],
            "bootstrap_replicates": analysis_config["bootstrap_replicates"],
            "confidence_level": analysis_config["confidence_level"],
            "estimator": analysis_config["estimator"],
        },
        "artifacts": [
            artifact_record(output, events_path),
            artifact_record(output, analysis_path),
        ],
    }
    write_json(output / "manifest.json", manifest)
    return verify_bundle(output)
