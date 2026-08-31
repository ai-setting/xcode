"""
Trace scenario: request → handler → business-helper flow.

Models a realistic HTTP-request call chain:
  handle_request()
    -> parse_payload()
    -> validate_payload()
        -> check_schema()
    -> format_response()
        -> render_body()

This scenario is run by xcode_trace.py via `runpy.run_path`, which installs
its own sys.settrace hook. We just need to drive the call chain — no manual
tracer setup here. The CLI runner wraps this script, traces it, and saves
the result to .xcode/traces/<name>.json.
"""
from __future__ import annotations

import json


# ---- business helpers --------------------------------------------------

def check_schema(field: str) -> bool:
    """Validate a single field exists in the schema."""
    return field in {"user_id", "action", "payload"}


def validate_payload(payload: dict) -> dict:
    """Ensure payload has all required fields."""
    missing = [f for f in ("user_id", "action", "payload") if not check_schema(f)]
    if missing:
        raise ValueError(f"missing fields: {missing}")
    return {"ok": True, "fields": list(payload.keys())}


def parse_payload(raw: str) -> dict:
    """Parse raw text into a dict payload."""
    out = {}
    for chunk in raw.split(";"):
        if "=" in chunk:
            k, v = chunk.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def render_body(data: dict) -> str:
    """Render a JSON-ish response body."""
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


def format_response(payload: dict) -> str:
    """Compose the final HTTP-style response body."""
    validated = validate_payload(payload)
    body = render_body({"status": "ok", "data": validated})
    return body


def handle_request(raw: str) -> str:
    """Top-level entry: parse → validate → format → return."""
    payload = parse_payload(raw)
    return format_response(payload)


def main() -> int:
    body = handle_request("user_id=42; action=ping; payload=hi")
    print(f"[trace_request_flow] body = {body}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
