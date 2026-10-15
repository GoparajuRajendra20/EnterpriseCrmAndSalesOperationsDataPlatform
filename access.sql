CREATE SCHEMA IF NOT EXISTS analytics;
CREATE SCHEMA IF NOT EXISTS staging;
DO $$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='analytics_reader') THEN CREATE ROLE analytics_reader NOLOGIN; END IF;
END $$;
GRANT USAGE ON SCHEMA analytics TO analytics_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA analytics TO analytics_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA analytics GRANT SELECT ON TABLES TO analytics_reader;
REVOKE ALL ON SCHEMA staging FROM PUBLIC;
-- API/Tableau login users get analytics_reader only. Spark uses the separate owner/writer login.
