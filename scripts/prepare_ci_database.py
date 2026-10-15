import os
from pathlib import Path
import psycopg
with psycopg.connect(os.environ['WRITER_DATABASE_URL']) as conn:
    conn.execute(Path('access.sql').read_text())
    conn.execute("CREATE ROLE api_reader LOGIN PASSWORD 'ci-reader-only'")
    conn.execute('GRANT analytics_reader TO api_reader')
