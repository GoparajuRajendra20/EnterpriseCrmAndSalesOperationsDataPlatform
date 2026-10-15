import csv, tempfile, unittest, zipfile
from decimal import Decimal
from pathlib import Path
from xml.etree import ElementTree as E
import sys
BASE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(BASE))
from generate import generate

def read(path):
    with path.open(newline='') as f:return list(csv.DictReader(f))
class SyntheticDataTests(unittest.TestCase):
    def test_seeded_generation_and_global_support(self):
        with tempfile.TemporaryDirectory() as a,tempfile.TemporaryDirectory() as b:
            generate(a,1000);generate(b,1000)
            for f in Path(a).glob('*.csv'):self.assertEqual(f.read_bytes(),(Path(b)/f.name).read_bytes())
            leads=read(Path(a)/'leads.csv');sales=read(Path(a)/'sales.csv');customers=read(Path(a)/'customers.csv');tickets=read(Path(a)/'tickets.csv')
            lead_ids={r['lead_id'] for r in leads};self.assertTrue(all(r['lead_id'] in lead_ids for r in sales))
            regions={c['customer_id']:c['region'] for c in customers}
            self.assertEqual({regions[t['customer_id']] for t in tickets},{'Americas','EMEA','APAC'})
class BusinessReconciliationTests(unittest.TestCase):
    def test_marketing_finance_and_budget(self):
        raw=BASE/'data/raw';out=BASE/'data/curated'
        sales={r['sale_id']:r for r in read(raw/'sales.csv') if Decimal(r['gross_amount'])>=0}
        net=sum(Decimal(r['gross_amount'])-Decimal(r['refund_amount']) for r in sales.values())
        marketing=read(out/'marketing.csv');self.assertEqual(sum(Decimal(r['net_revenue']) for r in marketing),net)
        self.assertEqual(sum(int(r['won_sales']) for r in marketing),len(sales))
        self.assertEqual(sum(int(r['leads']) for r in marketing),len(read(raw/'leads.csv')))
        rates={r['partner_id']:Decimal(r['commission_rate']) for r in read(raw/'partners.csv')}
        leads={r['lead_id']:r for r in read(raw/'leads.csv')}
        expected={id:Decimal(0) for id in rates}
        for r in sales.values():
            partner=leads[r['lead_id']]['partner_id'];expected[partner]+=((Decimal(r['gross_amount'])-Decimal(r['refund_amount']))*rates[partner]).quantize(Decimal('.01'))
        for r in read(out/'compensation.csv'):self.assertEqual(Decimal(r['expected_commission']),expected[r['partner_id']])
        budget=read(out/'budget_allocation.csv')
        self.assertLessEqual(abs(sum(Decimal(r['proposed_budget']) for r in budget)-sum(Decimal(r['spend']) for r in budget)),Decimal('.02'))
    def test_sales_quota_tiers(self):
        for r in read(BASE/'data/curated/rep_compensation.csv'):
            net=Decimal(r['net_revenue']);quota=Decimal(r['monthly_quota'])
            expected=(min(net,quota)*Decimal(r['base_rate'])+max(net-quota,Decimal(0))*Decimal(r['accelerator_rate'])).quantize(Decimal('.01'))
            self.assertEqual(Decimal(r['expected_commission']),expected)
    def test_customer_metrics_span_regions(self):
        rows=read(BASE/'data/curated/customer_experience.csv')
        self.assertEqual({r['region'] for r in rows},{'Americas','EMEA','APAC'})
        self.assertTrue(all(int(r['tickets'])>0 for r in rows))
        self.assertTrue(all(1<=float(r['average_csat'])<=5 for r in rows))
    def test_tableau_package_sources_and_sheets(self):
        with zipfile.ZipFile(BASE/'tableau/PartnerRevenue.twbx') as z:
            root=E.fromstring(z.read('PartnerRevenue.twb'))
            self.assertEqual(len(root.findall('worksheets/worksheet')),8)
            self.assertEqual(len(root.findall('dashboards/dashboard')),1)
            for c in root.findall('datasources/datasource/connection'):
                self.assertIn('Data/'+c.attrib['filename'],z.namelist())
if __name__=='__main__':unittest.main()
