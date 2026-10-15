"""Train and evaluate the batch lead-conversion model, then persist its scores."""

import json
import os

# Spark 3.5 still imports distutils, which Python removed in 3.12.
# Initializing setuptools supplies that compatibility module on newer Python.
import setuptools  # noqa: F401

# isort: split
from pyspark.ml import Pipeline
from pyspark.ml.classification import LogisticRegression
from pyspark.ml.evaluation import BinaryClassificationEvaluator
from pyspark.ml.feature import OneHotEncoder, StringIndexer, VectorAssembler
from pyspark.ml.functions import vector_to_array
from pyspark.sql import SparkSession
from pyspark.sql import functions as F

TRAIN_END = "2025-08-01"
HOLDOUT_START = "2025-09-01"
FEATURE_SCHEMA = (
    "lead_id INT, campaign_id INT, partner_id INT, employee_count INT, "
    "created_date DATE, created_month INT, label INT"
)


def build_estimator():
    """Treat IDs as categories; their numeric order has no business meaning."""
    stages = [
        StringIndexer(
            inputCol=column, outputCol=column + "_index", handleInvalid="keep"
        )
        for column in ["campaign_id", "partner_id"]
    ]
    stages.extend(
        [
            OneHotEncoder(
                inputCols=["campaign_id_index", "partner_id_index"],
                outputCols=["campaign_vec", "partner_vec"],
            ),
            VectorAssembler(
                inputCols=[
                    "campaign_vec",
                    "partner_vec",
                    "employee_count",
                    "created_month",
                ],
                outputCol="features",
            ),
            LogisticRegression(maxIter=30, regParam=0.1),
        ]
    )
    return Pipeline(stages=stages)


def train_and_score(spark, output):
    leads = (
        spark.read.option("header", True)
        .schema(FEATURE_SCHEMA)
        .csv(output + "/lead_features")
    )
    # A random split would mix future observations into the evaluation period.
    # The gap also lets the assumed 30-day conversion labels mature.
    training = leads.filter(F.col("created_date") < TRAIN_END)
    holdout = leads.filter(F.col("created_date") >= HOLDOUT_START)
    training_count = training.count()
    holdout_count = holdout.count()
    if not training_count or not holdout_count:
        raise ValueError("Insufficient temporal coverage")

    model = build_estimator().fit(training)
    predictions = model.transform(holdout)
    metrics = {
        "holdout_auc": BinaryClassificationEvaluator().evaluate(predictions),
        "training_prevalence": training.agg(F.avg("label")).first()[0],
        "train_rows": training_count,
        "test_rows": holdout_count,
        "baseline_auc": 0.5,
        "train_end_exclusive": TRAIN_END,
        "holdout_start": HOLDOUT_START,
        "limitation": "Synthetic labels encode campaign probabilities; no real-world effectiveness claim.",
    }
    spark.createDataFrame([(json.dumps(metrics),)], "metrics_json string").coalesce(
        1
    ).write.mode("overwrite").json(output + "/model_metrics")
    model.write().overwrite().save(output + "/lead_model")
    scores = model.transform(leads).select(
        "lead_id", vector_to_array("probability")[1].alias("conversion_probability")
    )
    scores.write.mode("overwrite").option("header", True).csv(output + "/lead_scores")
    if os.getenv("JDBC_URL"):
        scores.write.jdbc(
            os.environ["JDBC_URL"],
            "staging.lead_scores",
            mode="overwrite",
            properties={
                "user": os.environ["DB_USER"],
                "password": os.environ["DB_PASSWORD"],
                "driver": "org.postgresql.Driver",
            },
        )
    return metrics


def main():
    spark = SparkSession.builder.appName("LeadConversion").getOrCreate()
    try:
        output = os.getenv("CURATED_DIR", "data/curated").rstrip("/")
        print(json.dumps(train_and_score(spark, output)))
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
