"""Run locally; returned secret is saved with mode 600, never committed."""
import argparse, json, os, secrets, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from auth import digest, PERMISSIONS
p=argparse.ArgumentParser();p.add_argument('name');p.add_argument('role',choices=PERMISSIONS);p.add_argument('--partner-id',type=int);p.add_argument('--config',default='state/users.json');p.add_argument('--token-file',required=True);a=p.parse_args()
if a.role=='partner' and (not a.partner_id or a.partner_id<1):p.error('partner requires a positive --partner-id')
f=Path(a.config);f.parent.mkdir(parents=True,exist_ok=True);config=json.loads(f.read_text()) if f.exists() else {'users':[]}
token=secrets.token_urlsafe(32);salt=secrets.token_hex(16)
config['users']=[u for u in config['users'] if u['name']!=a.name]+[dict(name=a.name,role=a.role,partner_id=a.partner_id,salt=salt,token_hash=digest(token,salt),active=True)]
f.write_text(json.dumps(config,indent=2));f.chmod(0o600)
t=Path(a.token_file);t.parent.mkdir(parents=True,exist_ok=True);t.write_text(token);t.chmod(0o600)
print('Provisioned '+a.name+' ('+a.role+'); token saved to '+str(t))
