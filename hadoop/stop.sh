#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
export HADOOP_CONF_DIR="$PWD/state/hadoop-conf"
export HADOOP_PID_DIR="$PWD/state/hdfs/pids"
"$HADOOP_HOME/bin/hdfs" --daemon stop datanode
"$HADOOP_HOME/bin/hdfs" --daemon stop namenode
