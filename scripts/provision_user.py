"""Create or rotate a user token without storing plaintext in identity config."""

import argparse
import json
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from auth import PERMISSIONS, digest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("name")
    parser.add_argument("role", choices=PERMISSIONS)
    parser.add_argument("--partner-id", type=int)
    parser.add_argument("--config", default="state/users.json")
    parser.add_argument("--token-file", required=True)
    args = parser.parse_args()
    if args.role == "partner" and (not args.partner_id or args.partner_id < 1):
        parser.error("partner requires a positive --partner-id")

    config_path = Path(args.config)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config = (
        json.loads(config_path.read_text()) if config_path.exists() else {"users": []}
    )
    token = secrets.token_urlsafe(32)
    salt = secrets.token_hex(16)
    identity = {
        "name": args.name,
        "role": args.role,
        "partner_id": args.partner_id,
        "salt": salt,
        "token_hash": digest(token, salt),
        "active": True,
    }
    # Replacing the named identity also revokes its previous token.
    config["users"] = [
        user for user in config["users"] if user["name"] != args.name
    ] + [identity]
    config_path.write_text(json.dumps(config, indent=2))
    config_path.chmod(0o600)

    # Keep the usable secret separate from the hashed configuration. Neither
    # file belongs in Git; the owner-only mode limits other local users.
    token_path = Path(args.token_file)
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(token)
    token_path.chmod(0o600)
    print(f"Provisioned {args.name} ({args.role}); token saved to {token_path}")


if __name__ == "__main__":
    main()
