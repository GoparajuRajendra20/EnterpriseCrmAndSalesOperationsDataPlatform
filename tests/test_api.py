import importlib.util, json, os, secrets, sys, tempfile, threading, unittest, urllib.request, urllib.error
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch
BASE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(BASE))
import server
from auth import digest

class AccessAndWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.state=Path(cls.tmp.name);server.STATE=cls.state
        cls.tokens={};users=[]
        for name,role,partner in [('admin','admin',None),('marketer','marketing',None),('partner1','partner',1),('partner2','partner',2),('finance1','finance',None),('finance2','finance',None),('engineer','engineer',None),('support','support',None)]:
            token=secrets.token_urlsafe(32);salt=secrets.token_hex(16);cls.tokens[name]=token;users.append(dict(name=name,role=role,partner_id=partner,salt=salt,token_hash=digest(token,salt)))
        config=cls.state/'users.json';config.write_text(json.dumps({'users':users}));os.environ['AUTH_CONFIG']=str(config);os.environ.pop('DATABASE_URL',None)
        cls.http=ThreadingHTTPServer(('127.0.0.1',0),server.Handler);cls.thread=threading.Thread(target=cls.http.serve_forever,daemon=True);cls.thread.start();cls.url='http://127.0.0.1:'+str(cls.http.server_port)
    @classmethod
    def tearDownClass(cls):cls.http.shutdown();cls.http.server_close();cls.thread.join();cls.tmp.cleanup();os.environ.pop('AUTH_CONFIG',None)
    def request(self,path,user=None,data=None):
        headers={'Authorization':'Bearer '+self.tokens[user]} if user else {}
        body=json.dumps(data).encode() if data is not None else None
        req=urllib.request.Request(self.url+path,data=body,headers=headers)
        try:
            with urllib.request.urlopen(req) as r:return r.status,json.load(r)
        except urllib.error.HTTPError as e:return e.code,json.load(e)
    def test_authentication_and_role_denial(self):
        self.assertEqual(self.request('/api/marketing')[0],401)
        self.assertEqual(self.request('/api/compensation','marketer')[0],403)
        self.assertEqual(self.request('/api/customer_experience','support')[0],200)
        self.assertEqual(self.request('/api/marketing','marketer')[0],200)
        self.assertEqual(self.request('/api/audit','partner1')[0],403)
    def test_partner_rows_are_isolated(self):
        for user,id in [('partner1',1),('partner2',2)]:
            status,rows=self.request('/api/compensation',user);self.assertEqual(status,200);self.assertEqual(len(rows),1);self.assertEqual(int(rows[0]['partner_id']),id)
    def test_ingestion_validation_and_replay(self):
        lead=dict(lead_id=900001,company='Test',contact_email='test@example.test',campaign_id=1,partner_id=1,rep_id=1,region='EMEA',created_date='2025-10-01',status='Open',employee_count=25)
        self.assertEqual(self.request('/api/leads','marketer',lead)[0],403)
        self.assertEqual(self.request('/api/leads','engineer',dict(lead,campaign_id=999))[0],400)
        self.assertEqual(self.request('/api/leads','engineer',lead)[0],201)
        self.assertEqual(self.request('/api/leads','engineer',lead)[0],409)
    def test_approval_separation_and_no_double_payout(self):
        # Controlled financial fixture verifies rules independently of random synthetic compensation.
        record={'partner_id':1,'commission_variance':'0','expected_commission':'100','paid_commission':'0'}
        def data(name,user):return [record]
        with patch.object(server,'report',side_effect=data):
            self.assertEqual(self.request('/api/payouts','finance2',{'partner_id':1})[0],400)
            self.assertEqual(self.request('/api/approvals','finance1',{'partner_id':1})[0],201)
            self.assertEqual(self.request('/api/payouts','finance1',{'partner_id':1})[0],400)
            self.assertEqual(self.request('/api/payouts','finance2',{'partner_id':1})[0],201)
            self.assertEqual(self.request('/api/payouts','finance2',{'partner_id':1})[0],400)
            record['expected_commission']='150';record['paid_commission']='0'
            status,approval=self.request('/api/approvals','finance1',{'partner_id':1});self.assertEqual(status,201);self.assertEqual(approval['amount'],'50')
            self.assertEqual(self.request('/api/payouts','finance2',{'partner_id':1})[0],201)
    def test_audit_excludes_tokens(self):
        status,data=self.request('/api/audit','admin');self.assertEqual(status,200)
        text=json.dumps(data)
        self.assertFalse(any(token in text for token in self.tokens.values()))
    def test_rejects_unknown_routes_and_malformed_payload(self):
        self.assertEqual(self.request('/api/anything','admin')[0],404)
        self.assertEqual(self.request('/api/leads','engineer',{'lead_id':-1})[0],400)
if __name__=='__main__':unittest.main()
