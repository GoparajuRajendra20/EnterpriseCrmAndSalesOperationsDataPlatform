"""Time-split Spark ML classifier, holdout evaluation and probability scoring."""
import json, os
from pathlib import Path
from pyspark.sql import SparkSession, functions as F
from pyspark.ml import Pipeline
from pyspark.ml.feature import OneHotEncoder, VectorAssembler, StringIndexer
from pyspark.ml.classification import LogisticRegression
from pyspark.ml.evaluation import BinaryClassificationEvaluator
from pyspark.ml.functions import vector_to_array
spark=SparkSession.builder.appName('LeadConversion').getOrCreate()
root=os.getenv('CURATED_DIR','data/curated').rstrip('/')
df=spark.read.option('header',True).schema('lead_id INT, campaign_id INT, partner_id INT, employee_count INT, created_date DATE, created_month INT, label INT').csv(root+'/lead_features')
# Outcomes are assumed observed at 30 days. Temporal gap keeps training label windows before holdout.
train=df.filter("created_date < '2025-08-01'")
test=df.filter("created_date >= '2025-09-01'")
if train.count()==0 or test.count()==0: raise ValueError('Insufficient temporal coverage')
stages=[]
for col in ['campaign_id','partner_id']:
    stages.append(StringIndexer(inputCol=col,outputCol=col+'_index',handleInvalid='keep'))
stages.extend([OneHotEncoder(inputCols=['campaign_id_index','partner_id_index'],outputCols=['campaign_vec','partner_vec']),VectorAssembler(inputCols=['campaign_vec','partner_vec','employee_count','created_month'],outputCol='features'),LogisticRegression(maxIter=30,regParam=.1)])
model=Pipeline(stages=stages).fit(train)
pred=model.transform(test)
auc=BinaryClassificationEvaluator().evaluate(pred)
prevalence=train.agg(F.avg('label')).first()[0]
metrics={'holdout_auc':auc,'training_prevalence':prevalence,'train_rows':train.count(),'test_rows':test.count(),'baseline_auc':.5,'train_end_exclusive':'2025-08-01','holdout_start':'2025-09-01','limitation':'Synthetic labels encode campaign probabilities; no real-world effectiveness claim.'}
spark.createDataFrame([(json.dumps(metrics),)],'metrics_json string').coalesce(1).write.mode('overwrite').json(root+'/model_metrics')
model.write().overwrite().save(root+'/lead_model')
scores=model.transform(df).select('lead_id',vector_to_array('probability')[1].alias('conversion_probability'))
scores.write.mode('overwrite').option('header',True).csv(root+'/lead_scores')
if os.getenv('JDBC_URL'):
    scores.write.jdbc(os.environ['JDBC_URL'],'staging.lead_scores',mode='overwrite',properties={'user':os.environ['DB_USER'],'password':os.environ['DB_PASSWORD'],'driver':'org.postgresql.Driver'})
print(json.dumps(metrics));spark.stop()
