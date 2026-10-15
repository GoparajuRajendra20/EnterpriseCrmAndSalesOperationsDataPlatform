"""Serve reporting data and small, role-scoped CRM/finance workflows."""

import csv
import json
import logging
import os
import ssl
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import psycopg

from auth import REPORTS, allowed, authenticate, scoped
from workflows import (
    WorkflowConflict,
    approve_partner,
    read_ids,
    simulate_payout,
    validate_lead,
)

BASE = Path(__file__).resolve().parent
STATE = Path(os.getenv("STATE_DIR", str(BASE / "state")))
STATE.mkdir(parents=True, exist_ok=True)
LOCK = threading.RLock()
REPORT_ROW_LIMIT = 1000
MAX_REQUEST_BYTES = 16 * 1024
WRITE_ACTIONS = {
    "/api/leads": "ingest",
    "/api/approvals": "approve",
    "/api/payouts": "payout",
}
logger = logging.getLogger(__name__)


def atomic_json(path: Path, value) -> None:
    """Replace a complete document so readers never see half-written JSON."""
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2))
    temporary.chmod(0o600)
    temporary.replace(path)


def read_json(path: Path, default):
    return json.loads(path.read_text()) if path.exists() else default


def audit(user: str, action: str, status: int) -> None:
    event = {
        "at": datetime.now(timezone.utc).isoformat(),
        "user": user,
        "action": action,
        "status": status,
    }
    # Tokens and request bodies deliberately stay out of the audit trail.
    with LOCK:
        with (STATE / "audit.jsonl").open("a") as destination:
            destination.write(json.dumps(event) + "\n")


def report(name: str, user: dict) -> list[dict]:
    """Apply the same partner scope to database and CSV-backed reports."""
    if name not in REPORTS:
        raise ValueError("Unknown report")
    if os.getenv("DATABASE_URL"):
        with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
            # Context lasts for this transaction, preventing scope from leaking
            # into another request if connection reuse is introduced later.
            connection.execute(
                "SELECT set_config('app.role',%s,true), set_config('app.partner_id',%s,true)",
                (user["role"], str(user.get("partner_id") or "")),
            )
            with connection.cursor() as cursor:
                # name is an internal allowlist value, never arbitrary SQL input.
                cursor.execute(
                    f"SELECT * FROM analytics.{name} LIMIT {REPORT_ROW_LIMIT}"
                )
                fields = [column.name for column in cursor.description]
                rows = [dict(zip(fields, row)) for row in cursor.fetchall()]
                return scoped(user, rows)

    folder = BASE / "data" / "curated" / name
    if not folder.exists():
        raise FileNotFoundError(name)
    rows = []
    for part in sorted(folder.glob("part-*.csv")):
        with part.open(newline="") as source:
            rows.extend(csv.DictReader(source))
    # Scope before limiting, otherwise a partner's row could be cut off.
    return scoped(user, rows)[:REPORT_ROW_LIMIT]


def stage_lead(lead: dict) -> dict:
    raw_directory = BASE / "data" / "raw"
    validate_lead(lead, raw_directory)
    inbox = STATE / "lead_inbox.json"
    staged = read_json(inbox, [])
    existing_ids = read_ids(raw_directory / "leads.csv", "lead_id")
    if lead["lead_id"] in existing_ids or any(
        row["lead_id"] == lead["lead_id"] for row in staged
    ):
        raise WorkflowConflict("Lead already exists")
    # Stage first. The scheduled batch owns merging and refreshing reports.
    atomic_json(inbox, staged + [lead])
    return {"status": "staged", "lead_id": lead["lead_id"]}


def process_commission(action: str, data: dict, user: dict) -> dict:
    partner_id = data.get("partner_id")
    if type(partner_id) is not int or partner_id < 1:
        raise ValueError("Positive partner_id required")
    records = report("compensation", {"role": "finance"})
    record = next(
        (row for row in records if int(row["partner_id"]) == partner_id), None
    )
    if record is None:
        raise ValueError("Unknown partner")
    ledger_path = STATE / "ledger.json"
    ledger = read_json(ledger_path, {})
    previous = ledger.get(str(partner_id))
    if action == "approve":
        result = approve_partner(record, previous, user)
    else:
        result = simulate_payout(record, previous, user)
    ledger[str(partner_id)] = result
    atomic_json(ledger_path, ledger)
    return result


class Handler(BaseHTTPRequestHandler):
    def reply(self, status: int, payload) -> None:
        body = json.dumps(payload, default=str).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def identity(self, action: str) -> dict | None:
        """Resolve identity and permission before accessing application data."""
        try:
            path = Path(os.getenv("AUTH_CONFIG", str(STATE / "users.json")))
            config = json.loads(path.read_text())
        except (OSError, ValueError):
            self.reply(503, {"error": "Authentication configuration unavailable"})
            return None
        user = authenticate(self.headers.get("Authorization", ""), config)
        if not user:
            audit("anonymous", action, 401)
            self.reply(401, {"error": "Invalid credentials"})
            return None
        if not allowed(user, action):
            audit(user["name"], action, 403)
            self.reply(403, {"error": "Forbidden"})
            return None
        audit(user["name"], action, 200)
        return user

    def do_GET(self):
        if self.path == "/health":
            self.reply(
                200,
                {
                    "status": "ok",
                    "mode": "postgresql" if os.getenv("DATABASE_URL") else "csv",
                },
            )
            return
        if self.path == "/":
            body = (BASE / "index.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return
        name = self.path.removeprefix("/api/") if self.path.startswith("/api/") else ""
        if name not in REPORTS | {"audit"}:
            self.reply(404, {"error": "Not found"})
            return
        user = self.identity(name)
        if user is None:
            return
        try:
            if name == "audit":
                path = STATE / "audit.jsonl"
                data = (
                    [json.loads(line) for line in path.read_text().splitlines()][-100:]
                    if path.exists()
                    else []
                )
            else:
                data = report(name, user)
            self.reply(200, data)
        except (OSError, ValueError, psycopg.Error):
            logger.warning("Report unavailable: %s", name)
            self.reply(503, {"error": "Report unavailable"})

    def read_request(self) -> dict:
        size = int(self.headers.get("Content-Length", "0"))
        if not 1 <= size <= MAX_REQUEST_BYTES:
            raise ValueError("Request body exceeds allowed size")
        payload = json.loads(self.rfile.read(size))
        if not isinstance(payload, dict):
            raise ValueError("Expected a JSON object")
        return payload

    def do_POST(self):
        action = WRITE_ACTIONS.get(self.path)
        if action is None:
            self.reply(404, {"error": "Not found"})
            return
        user = self.identity(action)
        if user is None:
            return
        try:
            payload = self.read_request()
            # The file-backed demo has one process. A multiworker deployment
            # needs database transactions instead of this in-process lock.
            with LOCK:
                result = (
                    stage_lead(payload)
                    if action == "ingest"
                    else process_commission(action, payload, user)
                )
                audit(user["name"], action, 201)
            self.reply(201, result)
        except WorkflowConflict as error:
            self.reply(409, {"error": str(error)})
        except (ValueError, TypeError, KeyError):
            self.reply(400, {"error": "Invalid request or disallowed state transition"})
        except (OSError, ArithmeticError, psycopg.Error):
            logger.warning("Write operation unavailable: %s", action)
            self.reply(503, {"error": "Operation unavailable"})

    def log_message(self, *_args):
        # Access decisions are recorded by audit(); do not log bearer headers.
        pass


def main():
    server = ThreadingHTTPServer(("127.0.0.1", int(os.getenv("PORT", "8000"))), Handler)
    certificate = os.getenv("TLS_CERT")
    private_key = os.getenv("TLS_KEY")
    if certificate and private_key:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(certificate, private_key)
        server.socket = context.wrap_socket(server.socket, server_side=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
