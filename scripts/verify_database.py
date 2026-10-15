"""Run after promotion against an isolated CI database, not production."""

import os

import psycopg

url = os.getenv(
    "READER_TEST_DATABASE_URL",
    "postgresql://api_reader:ci-reader-only@127.0.0.1/partner_revenue",
)
with psycopg.connect(url) as conn:
    assert conn.execute("SELECT count(*) FROM analytics.marketing").fetchone()[0] == 4
    assert (
        conn.execute("SELECT count(*) FROM analytics.compensation").fetchone()[0] == 0
    )
    conn.execute(
        "SELECT set_config('app.role','partner',true),set_config('app.partner_id','1',true)"
    )
    rows = conn.execute("SELECT partner_id FROM analytics.compensation").fetchall()
    assert rows == [(1,)]
    conn.execute("SELECT set_config('app.partner_id','2',true)")
    assert conn.execute("SELECT partner_id FROM analytics.compensation").fetchall() == [
        (2,)
    ]
    conn.execute("SELECT set_config('app.role','finance',true)")
    assert (
        conn.execute("SELECT count(*) FROM analytics.compensation").fetchone()[0] == 10
    )
    try:
        conn.execute("DELETE FROM analytics.marketing")
        raise AssertionError("Reader could write")
    except psycopg.errors.InsufficientPrivilege:
        conn.rollback()
print("Database integration: row isolation, finance scope and read-only grants passed")
