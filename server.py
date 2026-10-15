"""Role-scoped API, CRM inbox and simulated commission approval ledger."""
import csv, json, os, secrets, ssl, threading, time
from datetime import datetime, timezone
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import psycopg
from auth import authenticate, allowed, scoped, REPORTS
BASE=Path(__file__).resolve().parent
STATE=Path(os.getenv('STATE_DIR',str(BASE/'state')));STATE.mkdir(parents=True,exist_ok=True)
LOCK=threading.RLock()

def atomic_json(path,value):
    tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(value,indent=2));tmp.chmod(0o600);tmp.replace(path)
def audit(user,action,status):
    with LOCK:
        with (STATE/'audit.jsonl').open('a') as f:f.write(json.dumps(dict(at=datetime.now(timezone.utc).isoformat(),user=user,action=action,status=status))+'\n')

def report(name,user):
    if os.getenv('DATABASE_URL'):
        with psycopg.connect(os.environ['DATABASE_URL']) as conn:
            # RLS defaults to denying partner rows until a context is explicitly set.
            conn.execute("SELECT set_config('app.role',%s,true), set_config('app.partner_id',%s,true)",(user['role'],str(user.get('partner_id') or '')))
            with conn.cursor() as cur:
                # name comes only from REPORTS, never interpolated user SQL.
                cur.execute('SELECT * FROM analytics.'+name+' LIMIT 1000')
                return scoped(user,[dict(zip([d.name for d in cur.description],r)) for r in cur.fetchall()])
    folder=BASE/'data'/'curated'/name;rows=[]
    for part in sorted(folder.glob('part-*.csv')):
        with part.open(newline='') as f:rows.extend(csv.DictReader(f))
    if not folder.exists():raise FileNotFoundError(name)
    return scoped(user,rows)[:1000]

class Handler(BaseHTTPRequestHandler):
    def reply(self,status,payload):
        body=json.dumps(payload,default=str).encode();self.send_response(status)
        self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(body)
    def identity(self,action):
        try:config=json.loads(Path(os.getenv('AUTH_CONFIG',str(STATE/'users.json'))).read_text())
        except (OSError,ValueError):self.reply(503,{'error':'Authentication configuration unavailable'});return None
        user=authenticate(self.headers.get('Authorization',''),config)
        if not user:audit('anonymous',action,401);self.reply(401,{'error':'Invalid credentials'});return None
        if not allowed(user,action):audit(user['name'],action,403);self.reply(403,{'error':'Forbidden'});return None
        audit(user['name'],action,200);return user
    def do_GET(self):
        if self.path=='/health':self.reply(200,{'status':'ok','mode':'postgresql' if os.getenv('DATABASE_URL') else 'csv'});return
        if self.path=='/':
            body=(BASE/'index.html').read_bytes();self.send_response(200);self.send_header('Content-Type','text/html');self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(body);return
        name=self.path.removeprefix('/api/') if self.path.startswith('/api/') else ''
        if name not in REPORTS|{'audit'}:self.reply(404,{'error':'Not found'});return
        user=self.identity(name)
        if not user:return
        try:
            if name=='audit':
                f=STATE/'audit.jsonl';data=[json.loads(x) for x in f.read_text().splitlines()][-100:] if f.exists() else []
            else:data=report(name,user)
            self.reply(200,data)
        except Exception:self.reply(503,{'error':'Report unavailable'})
    def do_POST(self):
        action={'/api/leads':'ingest','/api/approvals':'approve','/api/payouts':'payout'}.get(self.path)
        if not action:self.reply(404,{'error':'Not found'});return
        user=self.identity(action)
        if not user:return
        try:
            size=int(self.headers.get('Content-Length','0'))
            if size<1 or size>16384:raise ValueError('Body must be 1..16384 bytes')
            data=json.loads(self.rfile.read(size))
            with LOCK:
                if action=='ingest':
                    # Staged inbox: downstream validation/merge is a separate step.
                    required={'lead_id','company','contact_email','campaign_id','partner_id','rep_id','region','created_date','status','employee_count'}
                    if set(data)!=required:raise ValueError('Unexpected or missing lead fields')
                    if any(type(data[k]) is not int or data[k]<1 for k in ['lead_id','campaign_id','partner_id','rep_id','employee_count']):raise ValueError('Identifiers/count must be positive integers')
                    if data['status'] not in ['Won','Open'] or data['region'] not in ['Americas','EMEA','APAC']:raise ValueError('Invalid status or region')
                    datetime.strptime(data['created_date'],'%Y-%m-%d')
                    if not isinstance(data['company'],str) or not data['company'].strip():raise ValueError('Company required')
                    if not isinstance(data['contact_email'],str) or not data['contact_email'].endswith('@example.test'):raise ValueError('Synthetic example.test contacts only')
                    for table,key in [('campaigns','campaign_id'),('partners','partner_id'),('reps','rep_id')]:
                        with (BASE/'data/raw'/(table+'.csv')).open() as f:ids={int(r[key]) for r in csv.DictReader(f)}
                        if data[key] not in ids:raise ValueError('Unknown '+key)
                    with (BASE/'data/raw/leads.csv').open() as f:existing={int(r['lead_id']) for r in csv.DictReader(f)}
                    inbox=STATE/'lead_inbox.json';rows=json.loads(inbox.read_text()) if inbox.exists() else []
                    if data['lead_id'] in existing or any(r['lead_id']==data['lead_id'] for r in rows):self.reply(409,{'error':'Lead already exists'});return
                    atomic_json(inbox,rows+[data]);result={'status':'staged','lead_id':data['lead_id']}
                else:
                    partner=data.get('partner_id')
                    if type(partner) is not int or partner<1:raise ValueError('Positive partner_id required')
                    records=report('compensation',{'role':'finance'})
                    record=next((r for r in records if int(r['partner_id'])==partner),None)
                    if not record:raise ValueError('Unknown partner')
                    ledger=STATE/'ledger.json';rows=json.loads(ledger.read_text()) if ledger.exists() else {}
                    from decimal import Decimal
                    import hashlib
                    fingerprint=hashlib.sha256(json.dumps({k:str(record[k]) for k in sorted(record)},sort_keys=True).encode()).hexdigest()
                    key=str(partner);previous=rows.get(key)
                    if action=='approve':
                        if Decimal(str(record['commission_variance']))!=0:raise ValueError('Reconcile commission variance before approval')
                        if previous and (previous['fingerprint']==fingerprint or previous['status']=='approved'):self.reply(409,{'error':'Already approved or awaiting payout'});return
                        settled=Decimal(previous.get('settled_total','0')) if previous else Decimal('0')
                        accrued=max(Decimal(str(record['expected_commission']))-Decimal(str(record['paid_commission'])),Decimal('0'))
                        payable=accrued-settled
                        if payable<=0:raise ValueError('No unpaid accrued commission')
                        result=dict(partner_id=partner,status='approved',approved_by=user['name'],fingerprint=fingerprint,amount=str(payable),settled_total=str(settled),approved_accrued=str(accrued))
                    else:
                        if not previous or previous['status']!='approved' or previous['fingerprint']!=fingerprint:raise ValueError('Current report must be approved first')
                        if previous['approved_by']==user['name']:raise ValueError('A different finance user must authorize payout')
                        result=dict(previous,status='simulated_paid',authorized_by=user['name'],settled_total=previous['approved_accrued'])
                    rows[key]=result;atomic_json(ledger,rows)
                audit(user['name'],action,201);self.reply(201,result)
        except (ValueError,TypeError,KeyError):self.reply(400,{'error':'Invalid request or disallowed state transition'})
        except Exception:self.reply(503,{'error':'Operation unavailable'})
    def log_message(self,*args):pass

if __name__=='__main__':
    server=ThreadingHTTPServer(('127.0.0.1',int(os.getenv('PORT','8000'))),Handler)
    cert=os.getenv('TLS_CERT');key=os.getenv('TLS_KEY')
    if cert and key:
        context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.minimum_version=ssl.TLSVersion.TLSv1_2;context.load_cert_chain(cert,key);server.socket=context.wrap_socket(server.socket,server_side=True)
    server.serve_forever()
