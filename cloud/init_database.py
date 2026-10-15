import secrets
import subprocess
from pathlib import Path

import psycopg
from psycopg import sql


def main():
    """Provision the cloud host database and owner-only service environment files."""
    project_directory = Path("/opt/partner")
    writer_password = secrets.token_urlsafe(32)
    reader_password = secrets.token_urlsafe(32)
    statements = (
        sql.SQL(
            "CREATE ROLE pipeline_writer LOGIN PASSWORD {}; CREATE ROLE api_reader LOGIN PASSWORD {}; CREATE ROLE analytics_reader NOLOGIN; GRANT analytics_reader TO api_reader; CREATE DATABASE partner_revenue OWNER pipeline_writer;"
        )
        .format(sql.Literal(writer_password), sql.Literal(reader_password))
        .as_string()
    )
    subprocess.run(
        ["sudo", "-u", "postgres", "psql", "-v", "ON_ERROR_STOP=1", "-d", "postgres"],
        input=statements,
        text=True,
        capture_output=True,
        check=True,
    )
    writer = f"postgresql://pipeline_writer:{writer_password}@127.0.0.1/partner_revenue"
    with psycopg.connect(writer) as conn:
        conn.execute((project_directory / "access.sql").read_text())
    (project_directory / "state/pipeline.env").write_text(
        f"export JAVA_HOME=/usr/lib/jvm/java-17-amazon-corretto\nexport HADOOP_HOME=/opt/hadoop-3.4.3\nexport SPARK_LOCAL_IP=127.0.0.1\nexport PYSPARK_PYTHON=/opt/partner/.venv/bin/python\nexport JDBC_URL=jdbc:postgresql://127.0.0.1:5432/partner_revenue\nexport DB_USER=pipeline_writer\nexport DB_PASSWORD={writer_password}\nexport WRITER_DATABASE_URL={writer}\n"
    )
    (project_directory / "state/api.env").write_text(
        f"DATABASE_URL=postgresql://api_reader:{reader_password}@127.0.0.1/partner_revenue\nPORT=9443\nTLS_CERT=/opt/partner/state/server.crt\nTLS_KEY=/opt/partner/state/server.key\n"
    )
    for environment_path in [
        project_directory / "state/pipeline.env",
        project_directory / "state/api.env",
    ]:
        environment_path.chmod(0o600)


if __name__ == "__main__":
    main()
