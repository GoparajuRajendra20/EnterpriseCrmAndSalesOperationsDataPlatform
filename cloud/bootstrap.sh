#!/bin/bash
set -euxo pipefail
exec > >(tee /var/log/partner-bootstrap.log) 2>&1
# AL2023 x86_64. Private application/database/HDFS; access through IAM-authorized SSM tunnel.
dnf install -y java-17-amazon-corretto-headless python3.11 python3.11-pip postgresql15-server postgresql15 tar gzip unzip openssl
id platform || useradd --create-home platform
mkdir -p /opt/partner
for attempt in $(seq 1 180); do
  if aws s3 cp "s3://$ARTIFACT_BUCKET/project.zip" /tmp/project.zip --region "$AWS_REGION"; then break; fi
  sleep 10
done
test -s /tmp/project.zip
unzip -o /tmp/project.zip -d /opt/partner
cd /opt/partner
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt
curl -fL https://dlcdn.apache.org/hadoop/common/hadoop-3.4.3/hadoop-3.4.3.tar.gz -o /tmp/hadoop.tar.gz
curl -fL https://dlcdn.apache.org/hadoop/common/hadoop-3.4.3/hadoop-3.4.3.tar.gz.sha512 -o /tmp/hadoop.sha512
python3.11 - <<'VERIFY'
import hashlib,re
expected=re.search(r'\b[a-fA-F0-9]{128}\b',open('/tmp/hadoop.sha512').read()).group(0).lower()
h=hashlib.sha512()
with open('/tmp/hadoop.tar.gz','rb') as f:
    for chunk in iter(lambda:f.read(1048576),b''):h.update(chunk)
assert h.hexdigest()==expected
VERIFY
tar -xzf /tmp/hadoop.tar.gz -C /opt
curl -fL https://jdbc.postgresql.org/download/postgresql-42.7.8.jar -o /opt/partner/postgresql.jar
postgresql-setup --initdb
# Local password authentication; no database TCP listener outside this host.
sed -i -E 's/^(host[[:space:]].*)ident$/\1scram-sha-256/' /var/lib/pgsql/data/pg_hba.conf
systemctl enable --now postgresql
mkdir -p state
chown -R platform:platform /opt/partner
# Generates independent owner and reader credentials without printing them.
/opt/partner/.venv/bin/python cloud/init_database.py
openssl req -x509 -newkey rsa:3072 -nodes -days 365 -keyout state/server.key -out state/server.crt -subj '/CN=localhost' -addext 'subjectAltName=DNS:localhost,IP:127.0.0.1'
chmod 600 state/server.key
chown -R platform:platform state
cat > /etc/systemd/system/partner-api.service <<'UNIT'
[Unit]
Description=Partner Revenue authenticated HTTPS API
After=network.target postgresql.service
[Service]
User=platform
WorkingDirectory=/opt/partner
EnvironmentFile=/opt/partner/state/api.env
ExecStart=/opt/partner/.venv/bin/python server.py
Restart=on-failure
NoNewPrivileges=true
PrivateTmp=true
[Install]
WantedBy=multi-user.target
UNIT
cat > /etc/systemd/system/partner-hdfs.service <<'UNIT'
[Unit]
Description=Private single-node Hadoop HDFS
After=network.target
[Service]
Type=oneshot
RemainAfterExit=true
User=platform
WorkingDirectory=/opt/partner
Environment=JAVA_HOME=/usr/lib/jvm/java-17-amazon-corretto
Environment=HADOOP_HOME=/opt/hadoop-3.4.3
ExecStart=/opt/partner/hadoop/start.sh
ExecStop=/opt/partner/hadoop/stop.sh
[Install]
WantedBy=multi-user.target
UNIT
cat > /etc/systemd/system/partner-refresh.service <<'UNIT'
[Unit]
Description=Refresh validated analytics and ML reports
After=partner-hdfs.service postgresql.service
Requires=partner-hdfs.service postgresql.service
[Service]
Type=oneshot
User=root
WorkingDirectory=/opt/partner
ExecStart=/opt/partner/cloud/refresh.sh
UNIT
cat > /etc/systemd/system/partner-refresh.timer <<'UNIT'
[Unit]
Description=Daily analytics refresh
[Timer]
OnCalendar=*-*-* 02:00:00 UTC
Persistent=true
[Install]
WantedBy=timers.target
UNIT
systemctl daemon-reload
systemctl enable --now partner-hdfs.service
./cloud/refresh.sh
systemctl enable --now partner-api.service partner-refresh.timer
# Readiness is exposed privately and bootstrap status can be inspected through SSM.
touch state/cloud-ready
