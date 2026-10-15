"""Merge staged CRM leads while the API is stopped for maintenance."""

import csv
import json
import os
from pathlib import Path

base = Path(__file__).resolve().parents[1]
state = Path(os.getenv("STATE_DIR", str(base / "state")))
inbox = state / "lead_inbox.json"
# Stop the API during this maintenance command; cloud/refresh.sh manages the cloud service window.
if inbox.exists():
    rows = json.loads(inbox.read_text())
    f = base / "data/raw/leads.csv"
    with f.open(newline="") as src:
        reader = csv.DictReader(src)
        fields = reader.fieldnames
        existing = list(reader)
    ids = {int(r["lead_id"]) for r in existing}
    fresh = [r for r in rows if int(r["lead_id"]) not in ids]
    temp = f.with_suffix(".tmp")
    with temp.open("w", newline="") as dst:
        w = csv.DictWriter(dst, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        w.writerows(existing + fresh)
    temp.replace(f)
    print("Merged", len(fresh), "new CRM leads; inbox retained for audit/replay")
