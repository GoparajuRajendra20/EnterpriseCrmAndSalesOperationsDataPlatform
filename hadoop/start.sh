#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
: "${JAVA_HOME:?Set JAVA_HOME}"
: "${HADOOP_HOME:?Set HADOOP_HOME to Hadoop 3.4.3}"
export HADOOP_CONF_DIR="$PWD/state/hadoop-conf"
export HADOOP_LOG_DIR="$PWD/state/hdfs/logs"
export HADOOP_PID_DIR="$PWD/state/hdfs/pids"
mkdir -p "$HADOOP_CONF_DIR" "$HADOOP_LOG_DIR" "$HADOOP_PID_DIR" state/hdfs/namenode state/hdfs/datanode
cp "$HADOOP_HOME/etc/hadoop/log4j.properties" "$HADOOP_CONF_DIR/"
cat > "$HADOOP_CONF_DIR/core-site.xml" <<EOF
<configuration>
<property><name>fs.defaultFS</name><value>hdfs://127.0.0.1:19000</value></property>
<property><name>hadoop.tmp.dir</name><value>$PWD/state/hdfs/tmp</value></property>
</configuration>
EOF
cat > "$HADOOP_CONF_DIR/hdfs-site.xml" <<EOF
<configuration>
<property><name>dfs.replication</name><value>1</value></property>
<property><name>dfs.namenode.name.dir</name><value>file://$PWD/state/hdfs/namenode</value></property>
<property><name>dfs.datanode.data.dir</name><value>file://$PWD/state/hdfs/datanode</value></property>
<property><name>dfs.namenode.rpc-address</name><value>127.0.0.1:19000</value></property>
<property><name>dfs.namenode.http-address</name><value>127.0.0.1:19870</value></property>
<property><name>dfs.datanode.address</name><value>127.0.0.1:19866</value></property>
<property><name>dfs.datanode.http.address</name><value>127.0.0.1:19864</value></property>
<property><name>dfs.datanode.ipc.address</name><value>127.0.0.1:19867</value></property>
<property><name>dfs.permissions.enabled</name><value>true</value></property>
</configuration>
EOF
if [ ! -f state/hdfs/namenode/current/VERSION ]; then "$HADOOP_HOME/bin/hdfs" namenode -format -nonInteractive; fi
"$HADOOP_HOME/bin/hdfs" --daemon start namenode
"$HADOOP_HOME/bin/hdfs" --daemon start datanode
for attempt in $(seq 1 30); do
  if "$HADOOP_HOME/bin/hdfs" dfsadmin -safemode get | grep -q OFF; then exit 0; fi
  sleep 1
done
exit 1
