import secrets, subprocess
from pathlib import Path
import psycopg
from psycopg import sql
base=Path('/opt/partner');owner=secrets.token_urlsafe(32);reader=secrets.token_urlsafe(32)
statements=sql.SQL('CREATE ROLE pipeline_writer LOGIN PASSWORD {}; CREATE ROLE api_reader LOGIN PASSWORD {}; CREATE ROLE analytics_reader NOLOGIN; GRANT analytics_reader TO api_reader; CREATE DATABASE partner_revenue OWNER pipeline_writer;').format(sql.Literal(owner),sql.Literal(reader)).as_string()
subprocess.run(['sudo','-u','postgres','psql','-v','ON_ERROR_STOP=1','-d','postgres'],input=statements,text=True,capture_output=True,check=True)
writer=f'postgresql://pipeline_writer:{owner}@127.0.0.1/partner_revenue'
with psycopg.connect(writer) as conn:
    conn.execute((base/'access.sql').read_text())
(base/'state/pipeline.env').write_text(f'export JAVA_HOME=/usr/lib/jvm/java-17-amazon-corretto\nexport HADOOP_HOME=/opt/hadoop-3.4.3\nexport SPARK_LOCAL_IP=127.0.0.1\nexport PYSPARK_PYTHON=/opt/partner/.venv/bin/python\nexport JDBC_URL=jdbc:postgresql://127.0.0.1:5432/partner_revenue\nexport DB_USER=pipeline_writer\nexport DB_PASSWORD={owner}\nexport WRITER_DATABASE_URL={writer}\n')
(base/'state/api.env').write_text(f'DATABASE_URL=postgresql://api_reader:{reader}@127.0.0.1/partner_revenue\nPORT=9443\nTLS_CERT=/opt/partner/state/server.crt\nTLS_KEY=/opt/partner/state/server.key\n')
for f in [base/'state/pipeline.env',base/'state/api.env']:f.chmod(0o600)
