"""Spark validation and analytics; local CSV output and optional PostgreSQL JDBC load."""
import os
from pathlib import Path
from pyspark.sql import SparkSession, functions as F

spark=SparkSession.builder.appName('PartnerRevenue').getOrCreate()
raw=os.getenv('RAW_DIR','data/raw').rstrip('/'); output=os.getenv('CURATED_DIR','data/curated').rstrip('/')
schemas={
 'partners':'partner_id INT, company STRING, commission_rate DECIMAL(8,4)',
 'campaigns':'campaign_id INT, channel STRING, spend DECIMAL(18,2)',
 'leads':'lead_id INT, company STRING, contact_email STRING, campaign_id INT, partner_id INT, rep_id INT, region STRING, created_date DATE, status STRING, employee_count INT',
 'reps':'rep_id INT, name STRING, monthly_quota DECIMAL(18,2), base_rate DECIMAL(8,4), accelerator_rate DECIMAL(8,4)',
 'customers':'customer_id INT, lead_id INT, region STRING, onboard_days INT',
 'tickets':'ticket_id INT, customer_id INT, opened_date DATE, resolution_hours INT, csat INT, category STRING',
 'sales':'sale_id INT, lead_id INT, sale_date DATE, gross_amount DECIMAL(18,2), refund_amount DECIMAL(18,2), booked_commission DECIMAL(18,2), paid_commission DECIMAL(18,2)'}
tables={name:spark.read.option('header',True).option('mode','FAILFAST').schema(schema).csv(raw+'/'+name+'.csv') for name,schema in schemas.items()}
for name,key in [('partners','partner_id'),('campaigns','campaign_id'),('leads','lead_id'),('reps','rep_id'),('customers','customer_id'),('tickets','ticket_id')]:
    d=tables[name]
    if d.filter(F.col(key).isNull()).count() or d.count()!=d.select(key).distinct().count():
        raise ValueError('Invalid primary key: '+name)
for name,field,parent in [('leads','partner_id','partners'),('leads','campaign_id','campaigns'),('sales','lead_id','leads'),('leads','rep_id','reps'),('customers','lead_id','leads'),('tickets','customer_id','customers')]:
    if tables[name].join(tables[parent].select(field),field,'left_anti').count():
        raise ValueError('Invalid foreign key: '+name+'.'+field)
# Governance checks beyond financial records; invalid dimension contracts fail before publishing.
checks={
 'partners': 'commission_rate IS NULL OR commission_rate < 0 OR commission_rate > 1',
 'campaigns': 'spend IS NULL OR spend <= 0 OR channel IS NULL',
 'leads': "created_date IS NULL OR status IS NULL OR status NOT IN ('Open','Won') OR employee_count IS NULL OR employee_count <= 0 OR region IS NULL OR region NOT IN ('Americas','EMEA','APAC')",
 'reps': 'monthly_quota IS NULL OR monthly_quota <= 0 OR base_rate IS NULL OR accelerator_rate IS NULL OR base_rate < 0 OR accelerator_rate < base_rate OR accelerator_rate > 1',
 'customers': 'onboard_days IS NULL OR onboard_days < 0 OR region IS NULL',
 'tickets': 'opened_date IS NULL OR resolution_hours IS NULL OR resolution_hours < 0 OR csat IS NULL OR csat < 1 OR csat > 5'}
for name,condition in checks.items():
    if tables[name].filter(condition).count():raise ValueError('Invalid data contract: '+name)
s=tables['sales']; financial=(F.col('sale_id').isNotNull() & F.col('gross_amount').isNotNull() & F.col('refund_amount').isNotNull() & F.col('paid_commission').isNotNull() & F.col('booked_commission').isNotNull() & F.col('sale_date').isNotNull() & (F.col('gross_amount')>=0) & (F.col('refund_amount')>=0) & (F.col('refund_amount')<=F.col('gross_amount')) & (F.col('paid_commission')>=0) & (F.col('booked_commission')>=0))
invalid=s.filter(~F.coalesce(financial,F.lit(False)))
valid=s.filter(financial)
# Identical replayed rows collapse safely; conflicting duplicate IDs fail the run.
unique=valid.dropDuplicates()
if unique.count()!=unique.select('sale_id').distinct().count():
    raise ValueError('Conflicting sale IDs')
invalid.write.mode('overwrite').option('header',True).csv(output+'/quarantine')
quality=spark.createDataFrame([(s.count(),invalid.count(),valid.count()-unique.count(),unique.count())],
    'raw_sales long, invalid_sales long, replay_duplicates long, accepted_sales long')
facts=unique.join(tables['leads'],'lead_id').join(tables['partners'],'partner_id')
if facts.filter(F.col('sale_date')<F.col('created_date')).count(): raise ValueError('Sale before lead creation')
facts=facts.withColumn('net_revenue',F.col('gross_amount')-F.col('refund_amount')).withColumn('expected_commission',F.round(F.col('net_revenue')*F.col('commission_rate'),2)).withColumn('commission_variance',F.col('booked_commission')-F.col('expected_commission'))
campaign_sales=facts.groupBy('campaign_id').agg(F.sum('net_revenue').alias('net_revenue'),F.count('*').alias('won_sales'))
lead_counts=tables['leads'].groupBy('campaign_id').agg(F.count('*').alias('leads'))
marketing=tables['campaigns'].join(lead_counts,'campaign_id','left').join(campaign_sales,'campaign_id','left').fillna(0,subset=['leads','won_sales','net_revenue']).withColumn('conversion_rate',F.when(F.col('leads')>0,F.col('won_sales')/F.col('leads'))).withColumn('revenue_to_spend',F.when(F.col('spend')>0,F.col('net_revenue')/F.col('spend')))
comp=facts.groupBy('partner_id').agg(F.sum('net_revenue').alias('net_revenue'),F.sum('expected_commission').alias('expected_commission'),F.sum('paid_commission').alias('paid_commission'),F.sum('booked_commission').alias('booked_commission'),F.sum('commission_variance').alias('commission_variance'))
# Only attributes known when the lead arrived; status is a label, never a feature.
features=tables['leads'].select('lead_id','campaign_id','partner_id','employee_count','created_date',F.month('created_date').alias('created_month'),F.when(F.col('status')=='Won',1).otherwise(0).alias('label'))
rep_month=facts.withColumn('month',F.date_format('sale_date','yyyy-MM')).groupBy('rep_id','month').agg(F.sum('net_revenue').alias('net_revenue')).join(tables['reps'],'rep_id').withColumn('quota_attainment',F.col('net_revenue')/F.col('monthly_quota')).withColumn('expected_commission',F.round(F.least(F.col('net_revenue'),F.col('monthly_quota'))*F.col('base_rate')+F.greatest(F.col('net_revenue')-F.col('monthly_quota'),F.lit(0))*F.col('accelerator_rate'),2))
customer_base=tables['customers'].groupBy('region').agg(F.countDistinct('customer_id').alias('customers'),F.avg('onboard_days').alias('average_onboard_days'))
ticket_stats=tables['tickets'].join(tables['customers'].select('customer_id','region'),'customer_id').groupBy('region').agg(F.count('ticket_id').alias('tickets'),F.avg('csat').alias('average_csat'),F.avg('resolution_hours').alias('average_resolution_hours'),F.sum(F.when(F.col('resolution_hours')>48,1).otherwise(0)).alias('sla_breaches'))
customer_experience=customer_base.join(ticket_stats,'region','left').fillna(0,subset=['tickets','sla_breaches'])
crm=tables['leads'].groupBy('region','status').agg(F.count('*').alias('leads'))
# Descriptive heuristic only: no causal lift or profit claim.
allocation=marketing.withColumn('allocation_weight',F.col('net_revenue')/F.col('spend'))
from pyspark.sql.window import Window
allocation=allocation.withColumn('proposed_budget',F.round(F.sum('spend').over(Window.partitionBy())*F.col('allocation_weight')/F.sum('allocation_weight').over(Window.partitionBy()),2))
reports=dict(marketing=marketing,compensation=comp,lead_features=features,quality=quality,rep_compensation=rep_month,customer_experience=customer_experience,crm=crm,budget_allocation=allocation)
for name,df in reports.items():
    df.write.mode('overwrite').option('header',True).csv(output+'/'+name)
    if os.getenv('JDBC_URL'):
        # Staging is separate from reader grants/RLS. Promotion is an explicit DB transaction.
        df.write.jdbc(os.environ['JDBC_URL'],'staging.'+name,mode='overwrite',properties={'user':os.environ['DB_USER'],'password':os.environ['DB_PASSWORD'],'driver':'org.postgresql.Driver'})
import json, datetime
metadata={'generated_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'source':raw,'destination':output,'reports':list(reports),'synthetic':True,'attribution':'single acquisition campaign','currency':'USD'}
spark.createDataFrame([(json.dumps(metadata),)],'metadata_json string').coalesce(1).write.mode('overwrite').json(output+'/lineage')
spark.stop()
