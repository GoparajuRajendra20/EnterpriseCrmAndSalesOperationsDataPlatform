"""Opaque per-user tokens: salted PBKDF2 at rest, roles and partner scoping."""

import hashlib
import hmac

REPORTS = {
    "marketing",
    "budget_allocation",
    "compensation",
    "rep_compensation",
    "customer_experience",
    "crm",
    "quality",
    "lead_scores",
}
PERMISSIONS = {
    "admin": REPORTS | {"ingest", "approve", "payout", "audit"},
    "marketing": {"marketing", "budget_allocation", "crm", "lead_scores"},
    "finance": {"compensation", "rep_compensation", "approve", "payout"},
    "support": {"customer_experience"},
    "engineer": {"quality", "ingest"},
    "partner": {"compensation"},
}


def digest(token, salt):
    """Hash the token using a per-user salt; configuration never needs plaintext."""
    return hashlib.pbkdf2_hmac(
        "sha256", token.encode(), bytes.fromhex(salt), 210000
    ).hex()


def authenticate(header, config):
    """Resolve an active identity from an opaque bearer token."""
    if not header.startswith("Bearer "):
        return None
    token = header[7:]
    if len(token) > 256:
        return None
    for user in config["users"]:
        if user.get("active", True) and hmac.compare_digest(
            digest(token, user["salt"]), user["token_hash"]
        ):
            return user
    return None


def allowed(user, action):
    """Unknown roles deny access rather than inheriting a default permission."""
    return action in PERMISSIONS.get(user["role"], set())


def scoped(user, rows):
    """Enforce partner isolation in the service, not merely in the browser UI."""
    if user["role"] == "partner":
        return [r for r in rows if str(r.get("partner_id")) == str(user["partner_id"])]
    return rows
