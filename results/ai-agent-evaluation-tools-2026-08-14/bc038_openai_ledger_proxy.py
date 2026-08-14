#!/usr/bin/env python3
"""Small local OpenAI proxy that records usage without recording prompts or secrets.

Run one instance per evaluator arm. The runner sets a case context before each evaluation;
every upstream response is then attributable to that case even when a framework makes more
than one model call. Request bodies are forwarded but never written to disk.
"""

from __future__ import annotations

import argparse
import json
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


def enforce_request_payload(payload: dict, model: str) -> tuple[dict, object, object]:
    """Return a copied payload with reproducibility controls enforced."""
    if payload.get("stream"):
        raise ValueError("streaming is disabled because usage must be complete")
    forwarded = dict(payload)
    original_model = forwarded.get("model")
    original_temperature = forwarded.get("temperature")
    forwarded["model"] = model
    forwarded["temperature"] = 0
    return forwarded, original_model, original_temperature


def ledger_record(
    *,
    arm: str,
    path: str,
    status: int,
    original_model: object,
    original_temperature: object,
    enforced_model: str,
    response_payload: dict,
    wall_time_s: float,
) -> dict:
    """Build the deliberately prompt-free, credential-free ledger row."""
    usage = response_payload.get("usage") or {}
    return {
        "arm": arm,
        "path": path,
        "status": status,
        "context_model_requested": original_model,
        "context_temperature_requested": original_temperature,
        "model_enforced": enforced_model,
        "temperature_enforced": 0,
        "response_model": response_payload.get("model"),
        "response_id": response_payload.get("id"),
        "system_fingerprint": response_payload.get("system_fingerprint"),
        "prompt_tokens": usage.get("prompt_tokens") or usage.get("input_tokens"),
        "completion_tokens": usage.get("completion_tokens") or usage.get("output_tokens"),
        "total_tokens": usage.get("total_tokens"),
        "wall_time_s": round(wall_time_s, 6),
    }


class State:
    def __init__(self, arm: str, upstream: str, ledger: Path, model: str):
        self.arm = arm
        self.upstream = upstream.rstrip("/")
        self.ledger = ledger
        self.model = model
        self.context = "unset"
        self.lock = threading.Lock()
        self.sequence = 0

    def set_context(self, value: str) -> None:
        with self.lock:
            self.context = value

    def append(self, record: dict) -> None:
        with self.lock:
            self.sequence += 1
            record["sequence"] = self.sequence
            record["context"] = self.context
            with self.ledger.open("a") as fh:
                fh.write(json.dumps(record, separators=(",", ":")) + "\n")


class Handler(BaseHTTPRequestHandler):
    server_version = "bc038-ledger/0.1"

    @property
    def state(self) -> State:
        return self.server.state  # type: ignore[attr-defined]

    def log_message(self, _format: str, *_args) -> None:
        return

    def send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        if self.path == "/__context":
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
            value = str(payload.get("context", "")).strip()
            if not value:
                self.send_json(400, {"error": "context is required"})
                return
            self.state.set_context(value)
            self.send_json(200, {"ok": True})
            return

        parsed_path = urlparse(self.path)
        if not parsed_path.path.startswith("/v1/"):
            self.send_json(404, {"error": "only /v1/* is proxied"})
            return

        length = int(self.headers.get("Content-Length", "0"))
        request_payload = json.loads(self.rfile.read(length) or b"{}")
        try:
            request_payload, original_model, original_temperature = enforce_request_payload(
                request_payload, self.state.model
            )
        except ValueError as exc:
            self.send_json(400, {"error": str(exc)})
            return
        body = json.dumps(request_payload).encode()

        authorization = self.headers.get("Authorization")
        if not authorization:
            self.send_json(401, {"error": "missing Authorization header"})
            return
        headers = {"Authorization": authorization, "Content-Type": "application/json"}
        for name in ("OpenAI-Organization", "OpenAI-Project", "OpenAI-Beta"):
            if self.headers.get(name):
                headers[name] = self.headers[name]

        upstream_url = self.state.upstream + parsed_path.path
        if parsed_path.query:
            upstream_url += "?" + parsed_path.query
        request = urllib.request.Request(upstream_url, data=body, headers=headers, method="POST")
        started = time.time()
        status = 0
        response_body = b""
        response_headers = {}
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                status = response.status
                response_body = response.read()
                response_headers = dict(response.headers.items())
        except urllib.error.HTTPError as exc:
            status = exc.code
            response_body = exc.read()
            response_headers = dict(exc.headers.items()) if exc.headers else {}

        response_payload = {}
        try:
            response_payload = json.loads(response_body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass
        self.state.append(
            ledger_record(
                arm=self.state.arm,
                path=parsed_path.path,
                status=status,
                original_model=original_model,
                original_temperature=original_temperature,
                enforced_model=self.state.model,
                response_payload=response_payload,
                wall_time_s=time.time() - started,
            )
        )

        self.send_response(status)
        self.send_header("Content-Type", response_headers.get("Content-Type", "application/json"))
        self.send_header("Content-Length", str(len(response_body)))
        if response_headers.get("x-request-id"):
            self.send_header("x-request-id", response_headers["x-request-id"])
        self.end_headers()
        self.wfile.write(response_body)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--arm", required=True)
    parser.add_argument("--ledger", required=True, type=Path)
    parser.add_argument("--model", required=True)
    parser.add_argument("--listen", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--upstream", default="https://api.openai.com")
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.listen, args.port), Handler)
    server.state = State(args.arm, args.upstream, args.ledger, args.model)  # type: ignore[attr-defined]
    server.serve_forever()


if __name__ == "__main__":
    main()
