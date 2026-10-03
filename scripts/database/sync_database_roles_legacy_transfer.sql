\getenv bootstrap_user POSTGRES_BOOTSTRAP_USER
\getenv bootstrap_password POSTGRES_BOOTSTRAP_PASSWORD
\getenv migrator_user POSTGRES_MIGRATOR_USER
\getenv migrator_password POSTGRES_MIGRATOR_PASSWORD
\getenv app_user POSTGRES_APP_USER
\getenv app_password POSTGRES_APP_PASSWORD
\getenv transition_user POSTGRES_TRANSITION_USER

SELECT set_config('leadflow.bootstrap_user', :'bootstrap_user', false) AS configured \gset
SELECT set_config('leadflow.migrator_user', :'migrator_user', false) AS configured \gset
SELECT set_config('leadflow.transition_user', :'transition_user', false) AS configured \gset

BEGIN;
DO $$
BEGIN
    IF (SELECT oid FROM pg_roles WHERE rolname = current_setting('leadflow.migrator_user')) <> 10 OR
       current_user <> current_setting('leadflow.transition_user') OR
       EXISTS (SELECT 1 FROM pg_roles WHERE rolname = current_setting('leadflow.bootstrap_user')) THEN
        RAISE EXCEPTION 'Legacy transfer topology changed after preflight';
    END IF;
END $$;
SELECT format('ALTER ROLE %I RENAME TO %I', :'migrator_user', :'bootstrap_user') \gexec
SELECT format('ALTER ROLE %I LOGIN SUPERUSER CREATEDB CREATEROLE NOREPLICATION PASSWORD %L', :'bootstrap_user', :'bootstrap_password') \gexec
SELECT format('CREATE ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD %L', :'migrator_user', :'migrator_password') \gexec
SELECT format('ALTER ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD %L', :'app_user', :'app_password') \gexec

SELECT format('ALTER SCHEMA leadflow OWNER TO %I', :'migrator_user') \gexec
SELECT format('ALTER %s %I.%I OWNER TO %I',
    CASE c.relkind WHEN 'S' THEN 'SEQUENCE' WHEN 'v' THEN 'VIEW' WHEN 'm' THEN 'MATERIALIZED VIEW' WHEN 'f' THEN 'FOREIGN TABLE' ELSE 'TABLE' END,
    n.nspname, c.relname, :'migrator_user')
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
LEFT JOIN pg_depend d ON d.classid = 'pg_class'::regclass AND d.objid = c.oid AND d.deptype = 'e'
WHERE n.nspname = 'leadflow' AND c.relowner = (SELECT oid FROM pg_roles WHERE rolname = :'bootstrap_user')
  AND c.relkind IN ('r','p','S','v','m','f') AND d.objid IS NULL
  AND (c.relkind <> 'S' OR NOT EXISTS (
      SELECT 1 FROM pg_depend owned
      WHERE owned.classid = 'pg_class'::regclass AND owned.objid = c.oid
        AND owned.refclassid = 'pg_class'::regclass AND owned.deptype IN ('a','i')
  ))
ORDER BY c.relkind,c.relname \gexec
SELECT format('ALTER ROUTINE %s OWNER TO %I', p.oid::regprocedure, :'migrator_user')
FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
LEFT JOIN pg_depend d ON d.classid = 'pg_proc'::regclass AND d.objid = p.oid AND d.deptype = 'e'
WHERE n.nspname = 'leadflow' AND p.proowner = (SELECT oid FROM pg_roles WHERE rolname = :'bootstrap_user')
  AND d.objid IS NULL ORDER BY p.oid \gexec
SELECT format('ALTER %s %I.%I OWNER TO %I', CASE WHEN t.typtype = 'd' THEN 'DOMAIN' ELSE 'TYPE' END,
    n.nspname, t.typname, :'migrator_user')
FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
LEFT JOIN pg_depend d ON d.classid = 'pg_type'::regclass AND d.objid = t.oid AND d.deptype = 'e'
WHERE n.nspname = 'leadflow' AND t.typowner = (SELECT oid FROM pg_roles WHERE rolname = :'bootstrap_user')
  AND t.typrelid = 0 AND t.typtype IN ('c','d','e','r','m') AND d.objid IS NULL
ORDER BY t.oid \gexec

SELECT format('GRANT CONNECT ON DATABASE %I TO %I', current_database(), :'migrator_user') \gexec
SELECT format('GRANT CONNECT ON DATABASE %I TO %I', current_database(), :'app_user') \gexec
SELECT format('GRANT USAGE, CREATE ON SCHEMA leadflow TO %I', :'migrator_user') \gexec
SELECT format('GRANT USAGE ON SCHEMA leadflow TO %I', :'app_user') \gexec
SELECT format('REVOKE CREATE ON SCHEMA leadflow FROM %I', :'app_user') \gexec
COMMIT;
