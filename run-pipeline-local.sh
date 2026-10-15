#!/bin/zsh
set -eu
cd "$(dirname "$0")"
TASK_ROOT="$(cd ../.. && pwd)"
export JAVA_HOME="$TASK_ROOT/work/runtime/jdk-17.0.20.1+1/Contents/Home"
export SPARK_LOCAL_IP=127.0.0.1
export PYSPARK_PYTHON="$PWD/.venv/bin/python"
exec .venv/bin/spark-submit --master 'local[2]' pipeline.py
