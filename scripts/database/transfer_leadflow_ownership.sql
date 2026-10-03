\getenv bootstrap_user POSTGRES_BOOTSTRAP_USER
\getenv migrator_user POSTGRES_MIGRATOR_USER

SELECT set_config('leadflow.bootstrap_user', :'bootstrap_user', false) AS configured \gset
SELECT set_config('leadflow.migrator_user', :'migrator_user', false) AS configured \gset

BEGIN;
DO $$
BEGIN
    IF current_user <> current_setting('leadflow.bootstrap_user') OR
       NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = current_setting('leadflow.bootstrap_user') AND rolsuper) OR
       NOT EXISTS (
           SELECT 1 FROM pg_roles WHERE rolname = current_setting('leadflow.migrator_user')
             AND NOT rolsuper AND NOT rolcreatedb AND NOT rolcreaterole AND NOT rolreplication
       ) THEN
        RAISE EXCEPTION 'Selective ownership transfer preconditions are not satisfied';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_extension e JOIN pg_namespace n ON n.oid=e.extnamespace WHERE n.nspname='leadflow') THEN
        RAISE EXCEPTION 'Extension objects inside schema leadflow require manual review';
    END IF;
END $$;
SELECT format('ALTER SCHEMA leadflow OWNER TO %I', :'migrator_user') \gexec
SELECT format('ALTER %s %I.%I OWNER TO %I',
    CASE c.relkind WHEN 'S' THEN 'SEQUENCE' WHEN 'v' THEN 'VIEW' WHEN 'm' THEN 'MATERIALIZED VIEW' WHEN 'f' THEN 'FOREIGN TABLE' ELSE 'TABLE' END,
    n.nspname,c.relname,:'migrator_user')
FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
LEFT JOIN pg_depend d ON d.classid='pg_class'::regclass AND d.objid=c.oid AND d.deptype='e'
WHERE n.nspname='leadflow' AND c.relowner=(SELECT oid FROM pg_roles WHERE rolname=:'bootstrap_user')
  AND c.relkind IN ('r','p','S','v','m','f') AND d.objid IS NULL
  AND (c.relkind <> 'S' OR NOT EXISTS (
      SELECT 1 FROM pg_depend owned
      WHERE owned.classid='pg_class'::regclass AND owned.objid=c.oid
        AND owned.refclassid='pg_class'::regclass AND owned.deptype IN ('a','i')
  ))
ORDER BY c.relkind,c.relname \gexec
SELECT format('ALTER ROUTINE %s OWNER TO %I',p.oid::regprocedure,:'migrator_user')
FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
LEFT JOIN pg_depend d ON d.classid='pg_proc'::regclass AND d.objid=p.oid AND d.deptype='e'
WHERE n.nspname='leadflow' AND p.proowner=(SELECT oid FROM pg_roles WHERE rolname=:'bootstrap_user')
  AND d.objid IS NULL ORDER BY p.oid \gexec
SELECT format('ALTER %s %I.%I OWNER TO %I',CASE WHEN t.typtype='d' THEN 'DOMAIN' ELSE 'TYPE' END,
    n.nspname,t.typname,:'migrator_user')
FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace
LEFT JOIN pg_depend d ON d.classid='pg_type'::regclass AND d.objid=t.oid AND d.deptype='e'
WHERE n.nspname='leadflow' AND t.typowner=(SELECT oid FROM pg_roles WHERE rolname=:'bootstrap_user')
  AND t.typrelid=0 AND t.typtype IN ('c','d','e','r','m') AND d.objid IS NULL
ORDER BY t.oid \gexec
COMMIT;
