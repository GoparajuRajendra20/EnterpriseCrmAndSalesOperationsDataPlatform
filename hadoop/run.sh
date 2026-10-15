#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
export HADOOP_CONF_DIR="$PWD/state/hadoop-conf"
: "${HADOOP_HOME:?Set HADOOP_HOME}"
"$HADOOP_HOME/bin/hdfs" dfs -mkdir -p /partner/raw
"$HADOOP_HOME/bin/hdfs" dfs -put -f data/raw/*.csv /partner/raw/
"$HADOOP_HOME/bin/hdfs" dfs -chmod -R 700 /partner
export RAW_DIR=hdfs://127.0.0.1:19000/partner/raw
export CURATED_DIR=hdfs://127.0.0.1:19000/partner/curated
.venv/bin/spark-submit ${JDBC_JAR:+--jars "$JDBC_JAR"} --master 'local[2]' pipeline.py
.venv/bin/spark-submit ${JDBC_JAR:+--jars "$JDBC_JAR"} --master 'local[2]' train.py
mkdir -p data/curated
for name in marketing compensation quality rep_compensation customer_experience crm budget_allocation lead_features lead_scores model_metrics lineage quarantine; do
  mkdir -p "data/curated/$name"
  find "data/curated/$name" -name 'part-*' -delete
  "$HADOOP_HOME/bin/hdfs" dfs -get -f "/partner/curated/$name/part-*" "data/curated/$name/"
done
.venv/bin/python scripts/export_reports.py
"$HADOOP_HOME/bin/hdfs" fsck /partner -files -blocks > state/hdfs/fsck.txt

"$HADOOP_HOME/bin/hdfs" dfs -chmod -R 700 /partner
