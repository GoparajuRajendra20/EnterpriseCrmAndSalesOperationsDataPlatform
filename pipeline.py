"""Validate source records and build the reporting tables consumed by the app.

The pipeline keeps raw ingestion, financial validation and report calculations
separate so a failed data contract is not hidden inside a reporting expression.
"""

import datetime
import json
import os

from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.window import Window

SOURCE_SCHEMAS = {
    "partners": "partner_id INT, company STRING, commission_rate DECIMAL(8,4)",
    "campaigns": "campaign_id INT, channel STRING, spend DECIMAL(18,2)",
    "leads": "lead_id INT, company STRING, contact_email STRING, campaign_id INT, partner_id INT, rep_id INT, region STRING, created_date DATE, status STRING, employee_count INT",
    "reps": "rep_id INT, name STRING, monthly_quota DECIMAL(18,2), base_rate DECIMAL(8,4), accelerator_rate DECIMAL(8,4)",
    "customers": "customer_id INT, lead_id INT, region STRING, onboard_days INT",
    "tickets": "ticket_id INT, customer_id INT, opened_date DATE, resolution_hours INT, csat INT, category STRING",
    "sales": "sale_id INT, lead_id INT, sale_date DATE, gross_amount DECIMAL(18,2), refund_amount DECIMAL(18,2), booked_commission DECIMAL(18,2), paid_commission DECIMAL(18,2)",
}


def read_sources(spark, raw):
    """Read explicit schemas so source inference cannot silently change financial types."""
    return {
        name: spark.read.option("header", True)
        .option("mode", "FAILFAST")
        .schema(schema)
        .csv(raw + "/" + name + ".csv")
        for name, schema in SOURCE_SCHEMAS.items()
    }


def validate_sources(tables):
    """Fail on broken keys or dimension contracts before calculating business metrics."""
    for name, key in [
        ("partners", "partner_id"),
        ("campaigns", "campaign_id"),
        ("leads", "lead_id"),
        ("reps", "rep_id"),
        ("customers", "customer_id"),
        ("tickets", "ticket_id"),
    ]:
        d = tables[name]
        if (
            d.filter(F.col(key).isNull()).count()
            or d.count() != d.select(key).distinct().count()
        ):
            raise ValueError("Invalid primary key: " + name)
    for name, field, parent in [
        ("leads", "partner_id", "partners"),
        ("leads", "campaign_id", "campaigns"),
        ("sales", "lead_id", "leads"),
        ("leads", "rep_id", "reps"),
        ("customers", "lead_id", "leads"),
        ("tickets", "customer_id", "customers"),
    ]:
        if tables[name].join(tables[parent].select(field), field, "left_anti").count():
            raise ValueError("Invalid foreign key: " + name + "." + field)
    # Governance checks beyond financial records; invalid dimension contracts fail before publishing.
    checks = {
        "partners": "commission_rate IS NULL OR commission_rate < 0 OR commission_rate > 1",
        "campaigns": "spend IS NULL OR spend <= 0 OR channel IS NULL",
        "leads": "created_date IS NULL OR status IS NULL OR status NOT IN ('Open','Won') OR employee_count IS NULL OR employee_count <= 0 OR region IS NULL OR region NOT IN ('Americas','EMEA','APAC')",
        "reps": "monthly_quota IS NULL OR monthly_quota <= 0 OR base_rate IS NULL OR accelerator_rate IS NULL OR base_rate < 0 OR accelerator_rate < base_rate OR accelerator_rate > 1",
        "customers": "onboard_days IS NULL OR onboard_days < 0 OR region IS NULL",
        "tickets": "opened_date IS NULL OR resolution_hours IS NULL OR resolution_hours < 0 OR csat IS NULL OR csat < 1 OR csat > 5",
    }
    for name, condition in checks.items():
        if tables[name].filter(condition).count():
            raise ValueError("Invalid data contract: " + name)


def clean_sales(spark, sales):
    """Quarantine bad amounts; collapse identical replays but reject conflicting sale IDs."""
    financial = (
        F.col("sale_id").isNotNull()
        & F.col("gross_amount").isNotNull()
        & F.col("refund_amount").isNotNull()
        & F.col("paid_commission").isNotNull()
        & F.col("booked_commission").isNotNull()
        & F.col("sale_date").isNotNull()
        & (F.col("gross_amount") >= 0)
        & (F.col("refund_amount") >= 0)
        & (F.col("refund_amount") <= F.col("gross_amount"))
        & (F.col("paid_commission") >= 0)
        & (F.col("booked_commission") >= 0)
    )
    invalid = sales.filter(~F.coalesce(financial, F.lit(False)))
    valid = sales.filter(financial)
    # Identical replayed rows collapse safely; conflicting duplicate IDs fail the run.
    unique = valid.dropDuplicates()
    if unique.count() != unique.select("sale_id").distinct().count():
        raise ValueError("Conflicting sale IDs")
    quality = spark.createDataFrame(
        [
            (
                sales.count(),
                invalid.count(),
                valid.count() - unique.count(),
                unique.count(),
            )
        ],
        "raw_sales long, invalid_sales long, replay_duplicates long, accepted_sales long",
    )
    return unique, invalid, quality


def build_sales_facts(unique, tables):
    """Join each accepted sale to its acquisition context and commission agreement."""
    facts = unique.join(tables["leads"], "lead_id").join(
        tables["partners"], "partner_id"
    )
    if facts.filter(F.col("sale_date") < F.col("created_date")).count():
        raise ValueError("Sale before lead creation")
    facts = (
        facts.withColumn("net_revenue", F.col("gross_amount") - F.col("refund_amount"))
        .withColumn(
            "expected_commission",
            F.round(F.col("net_revenue") * F.col("commission_rate"), 2),
        )
        .withColumn(
            "commission_variance",
            F.col("booked_commission") - F.col("expected_commission"),
        )
    )
    return facts


def build_marketing_report(facts, tables):
    """Attribute accepted sales to the campaign recorded when the lead arrived."""
    campaign_sales = facts.groupBy("campaign_id").agg(
        F.sum("net_revenue").alias("net_revenue"), F.count("*").alias("won_sales")
    )
    lead_counts = (
        tables["leads"].groupBy("campaign_id").agg(F.count("*").alias("leads"))
    )
    marketing = (
        tables["campaigns"]
        .join(lead_counts, "campaign_id", "left")
        .join(campaign_sales, "campaign_id", "left")
        .fillna(0, subset=["leads", "won_sales", "net_revenue"])
        .withColumn(
            "conversion_rate",
            F.when(F.col("leads") > 0, F.col("won_sales") / F.col("leads")),
        )
        .withColumn(
            "revenue_to_spend",
            F.when(F.col("spend") > 0, F.col("net_revenue") / F.col("spend")),
        )
    )
    return marketing


def build_partner_compensation(facts):
    """Keep booked accruals and payments separate; their financial meanings differ."""
    comp = facts.groupBy("partner_id").agg(
        F.sum("net_revenue").alias("net_revenue"),
        F.sum("expected_commission").alias("expected_commission"),
        F.sum("paid_commission").alias("paid_commission"),
        F.sum("booked_commission").alias("booked_commission"),
        F.sum("commission_variance").alias("commission_variance"),
    )
    return comp


def build_lead_features(tables):
    """Use arrival-time attributes only; outcome is the training target."""
    # Only attributes known when the lead arrived; status is a label, never a feature.
    features = tables["leads"].select(
        "lead_id",
        "campaign_id",
        "partner_id",
        "employee_count",
        "created_date",
        F.month("created_date").alias("created_month"),
        F.when(F.col("status") == "Won", 1).otherwise(0).alias("label"),
    )
    return features


def build_rep_compensation(facts, tables):
    """Apply the accelerator only to the portion of monthly revenue above quota."""
    rep_month = (
        facts.withColumn("month", F.date_format("sale_date", "yyyy-MM"))
        .groupBy("rep_id", "month")
        .agg(F.sum("net_revenue").alias("net_revenue"))
        .join(tables["reps"], "rep_id")
        .withColumn("quota_attainment", F.col("net_revenue") / F.col("monthly_quota"))
        .withColumn(
            "expected_commission",
            F.round(
                F.least(F.col("net_revenue"), F.col("monthly_quota"))
                * F.col("base_rate")
                + F.greatest(F.col("net_revenue") - F.col("monthly_quota"), F.lit(0))
                * F.col("accelerator_rate"),
                2,
            ),
        )
    )
    return rep_month


def build_customer_experience(tables):
    """Aggregate customers before joining ticket metrics to avoid ticket-count bias."""
    customer_base = (
        tables["customers"]
        .groupBy("region")
        .agg(
            F.countDistinct("customer_id").alias("customers"),
            F.avg("onboard_days").alias("average_onboard_days"),
        )
    )
    ticket_stats = (
        tables["tickets"]
        .join(tables["customers"].select("customer_id", "region"), "customer_id")
        .groupBy("region")
        .agg(
            F.count("ticket_id").alias("tickets"),
            F.avg("csat").alias("average_csat"),
            F.avg("resolution_hours").alias("average_resolution_hours"),
            F.sum(F.when(F.col("resolution_hours") > 48, 1).otherwise(0)).alias(
                "sla_breaches"
            ),
        )
    )
    customer_experience = customer_base.join(ticket_stats, "region", "left").fillna(
        0, subset=["tickets", "sla_breaches"]
    )
    return customer_experience


def build_budget_scenario(marketing):
    """Redistribute the existing budget using descriptive revenue-to-spend weights."""
    # Descriptive heuristic only: no causal lift or profit claim.
    allocation = marketing.withColumn(
        "allocation_weight", F.col("net_revenue") / F.col("spend")
    )
    allocation = allocation.withColumn(
        "proposed_budget",
        F.round(
            F.sum("spend").over(Window.partitionBy())
            * F.col("allocation_weight")
            / F.sum("allocation_weight").over(Window.partitionBy()),
            2,
        ),
    )
    return allocation


def write_reports(reports, output):
    """Write snapshots; database readers see new data only after explicit promotion."""
    for name, df in reports.items():
        df.write.mode("overwrite").option("header", True).csv(output + "/" + name)
        if os.getenv("JDBC_URL"):
            # Staging is separate from reader grants/RLS. Promotion is an explicit DB transaction.
            df.write.jdbc(
                os.environ["JDBC_URL"],
                "staging." + name,
                mode="overwrite",
                properties={
                    "user": os.environ["DB_USER"],
                    "password": os.environ["DB_PASSWORD"],
                    "driver": "org.postgresql.Driver",
                },
            )


def run_pipeline(spark, raw, output):
    tables = read_sources(spark, raw)
    validate_sources(tables)
    accepted, rejected, quality = clean_sales(spark, tables["sales"])
    facts = build_sales_facts(accepted, tables)
    marketing = build_marketing_report(facts, tables)
    reports = {
        "marketing": marketing,
        "compensation": build_partner_compensation(facts),
        "lead_features": build_lead_features(tables),
        "quality": quality,
        "rep_compensation": build_rep_compensation(facts, tables),
        "customer_experience": build_customer_experience(tables),
        "crm": tables["leads"]
        .groupBy("region", "status")
        .agg(F.count("*").alias("leads")),
        "budget_allocation": build_budget_scenario(marketing),
    }
    # Preserve invalid source rows separately rather than silently dropping them.
    rejected.write.mode("overwrite").option("header", True).csv(output + "/quarantine")
    write_reports(reports, output)
    metadata = {
        "generated_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "source": raw,
        "destination": output,
        "reports": list(reports),
        "synthetic": True,
        "attribution": "single acquisition campaign",
        "currency": "USD",
    }
    spark.createDataFrame([(json.dumps(metadata),)], "metadata_json string").coalesce(
        1
    ).write.mode("overwrite").json(output + "/lineage")


def main():
    raw = os.getenv("RAW_DIR", "data/raw").rstrip("/")
    output = os.getenv("CURATED_DIR", "data/curated").rstrip("/")
    spark = SparkSession.builder.appName("PartnerRevenue").getOrCreate()
    try:
        run_pipeline(spark, raw, output)
    finally:
        # Release the local JVM even when validation rejects a batch.
        spark.stop()


if __name__ == "__main__":
    main()
