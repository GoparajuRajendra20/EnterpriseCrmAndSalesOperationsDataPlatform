"""Atomically promote staging reports; preserve reader grants and compensation RLS."""
import os
import psycopg
NAMES=['marketing','compensation','rep_compensation','customer_experience','crm','quality','lead_features','budget_allocation','lead_scores']
with psycopg.connect(os.environ['WRITER_DATABASE_URL']) as conn:
    with conn.cursor() as c:
        for name in NAMES:
            # Fixed internal allowlist; never client-provided identifiers.
            c.execute(f'CREATE TABLE IF NOT EXISTS analytics.{name} (LIKE staging.{name} INCLUDING ALL)')
            c.execute(f'TRUNCATE analytics.{name}')
            c.execute(f'INSERT INTO analytics.{name} SELECT * FROM staging.{name}')
        c.execute('ALTER TABLE analytics.compensation ENABLE ROW LEVEL SECURITY')
        c.execute('DROP POLICY IF EXISTS partner_scope ON analytics.compensation')
        c.execute("""CREATE POLICY partner_scope ON analytics.compensation FOR SELECT TO analytics_reader
          USING (current_setting('app.role',true) IN ('admin','finance') OR
          (current_setting('app.role',true)='partner' AND partner_id::text=current_setting('app.partner_id',true)))""")
        c.execute('GRANT SELECT ON ALL TABLES IN SCHEMA analytics TO analytics_reader')
print('Promoted reports with row-level policy')
