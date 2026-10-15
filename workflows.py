"""Business rules for CRM onboarding and the simulated partner payout ledger.

Keeping these rules outside the HTTP handler makes them usable from a batch job
or a different interface without reimplementing the financial checks.
"""

import csv
import hashlib
import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path

LEAD_FIELDS = {
    "lead_id",
    "company",
    "contact_email",
    "campaign_id",
    "partner_id",
    "rep_id",
    "region",
    "created_date",
    "status",
    "employee_count",
}
REGIONS = {"Americas", "EMEA", "APAC"}


class WorkflowConflict(ValueError):
    """The request conflicts with an existing lead or approval."""


def read_ids(path: Path, field: str) -> set[int]:
    with path.open(newline="") as source:
        return {int(row[field]) for row in csv.DictReader(source)}


def validate_lead(lead: dict, raw_directory: Path) -> None:
    """Reject malformed records before they enter the batch ingestion inbox."""
    if not isinstance(lead, dict) or set(lead) != LEAD_FIELDS:
        raise ValueError("Unexpected or missing lead fields")
    for field in ["lead_id", "campaign_id", "partner_id", "rep_id", "employee_count"]:
        # bool is a subclass of int in Python; True must not become a valid ID.
        if type(lead[field]) is not int or lead[field] < 1:
            raise ValueError("Identifiers and employee count must be positive integers")
    if lead["status"] not in {"Won", "Open"} or lead["region"] not in REGIONS:
        raise ValueError("Invalid status or region")
    datetime.strptime(lead["created_date"], "%Y-%m-%d")
    if not isinstance(lead["company"], str) or not lead["company"].strip():
        raise ValueError("Company required")
    email = lead["contact_email"]
    if not isinstance(email, str) or not email.endswith("@example.test"):
        raise ValueError("Use a synthetic example.test contact address")
    for table, key in [
        ("campaigns", "campaign_id"),
        ("partners", "partner_id"),
        ("reps", "rep_id"),
    ]:
        if lead[key] not in read_ids(raw_directory / f"{table}.csv", key):
            raise ValueError(f"Unknown {key}")


def report_fingerprint(record: dict) -> str:
    """Bind approval to the exact report values the reviewer saw."""
    canonical = {field: str(record[field]) for field in sorted(record)}
    return hashlib.sha256(json.dumps(canonical, sort_keys=True).encode()).hexdigest()


def approve_partner(record: dict, previous: dict | None, user: dict) -> dict:
    """Approve only reconciled commission that has not already been settled."""
    if Decimal(str(record["commission_variance"])) != 0:
        raise ValueError("Reconcile commission variance before approval")
    fingerprint = report_fingerprint(record)
    if previous and (
        previous["fingerprint"] == fingerprint or previous["status"] == "approved"
    ):
        raise WorkflowConflict("Already approved or awaiting payout")

    settled = Decimal(previous.get("settled_total", "0")) if previous else Decimal("0")
    expected = Decimal(str(record["expected_commission"]))
    already_paid = Decimal(str(record["paid_commission"]))
    unpaid_accrual = max(expected - already_paid, Decimal("0"))
    # The source snapshot and this simulation have separate settlement records.
    # Subtract both, or a refreshed report could offer the same money twice.
    payable = unpaid_accrual - settled
    if payable <= 0:
        raise ValueError("No unpaid accrued commission")
    return {
        "partner_id": int(record["partner_id"]),
        "status": "approved",
        "approved_by": user["name"],
        "fingerprint": fingerprint,
        "amount": str(payable),
        "settled_total": str(settled),
        "approved_accrued": str(unpaid_accrual),
    }


def simulate_payout(record: dict, previous: dict | None, user: dict) -> dict:
    """Require a second reviewer and reject approval of an outdated snapshot."""
    if not previous or previous["status"] != "approved":
        raise ValueError("The current report must be approved first")
    if previous["fingerprint"] != report_fingerprint(record):
        raise ValueError("The report changed after approval")
    if previous["approved_by"] == user["name"]:
        raise ValueError("A different finance user must authorize payout")
    # This is a ledger event only. No payment provider or bank is called.
    return dict(
        previous,
        status="simulated_paid",
        authorized_by=user["name"],
        settled_total=previous["approved_accrued"],
    )
