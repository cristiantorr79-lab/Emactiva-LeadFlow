\getenv bootstrap_user POSTGRES_BOOTSTRAP_USER
\getenv bootstrap_password POSTGRES_BOOTSTRAP_PASSWORD
\getenv migrator_user POSTGRES_MIGRATOR_USER
\getenv app_user POSTGRES_APP_USER
\getenv transition_user POSTGRES_TRANSITION_USER

SELECT set_config('leadflow.bootstrap_user', :'bootstrap_user', false) AS configured \gset
SELECT set_config('leadflow.migrator_user', :'migrator_user', false) AS configured \gset
SELECT set_config('leadflow.app_user', :'app_user', false) AS configured \gset
SELECT set_config('leadflow.transition_user', :'transition_user', false) AS configured \gset

BEGIN;
DO $$
DECLARE bootstrap_oid oid; migrator_oid oid; app_oid oid;
BEGIN
    SELECT oid INTO bootstrap_oid FROM pg_roles WHERE rolname = current_setting('leadflow.bootstrap_user');
    SELECT oid INTO migrator_oid FROM pg_roles WHERE rolname = current_setting('leadflow.migrator_user');
    SELECT oid INTO app_oid FROM pg_roles WHERE rolname = current_setting('leadflow.app_user');
    IF bootstrap_oid IS NULL OR migrator_oid IS NULL OR app_oid IS NULL THEN
        RAISE EXCEPTION 'Legacy repair requires bootstrap, historical migrator, and app roles';
    END IF;
    IF migrator_oid <> 10 OR NOT (SELECT rolsuper FROM pg_roles WHERE oid = migrator_oid) THEN
        RAISE EXCEPTION 'Historical migrator does not match supported bootstrap OID 10 topology';
    END IF;
    IF NOT (SELECT rolsuper FROM pg_roles WHERE oid = bootstrap_oid) OR bootstrap_oid = 10 THEN
        RAISE EXCEPTION 'Destination bootstrap must be a distinct superuser';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = current_setting('leadflow.transition_user')) THEN
        RAISE EXCEPTION 'Transition role already exists';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_shdepend WHERE refclassid = 'pg_authid'::regclass AND refobjid = bootstrap_oid AND deptype = 'o') THEN
        RAISE EXCEPTION 'Destination bootstrap has unexpected ownership';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_auth_members WHERE roleid IN (bootstrap_oid,migrator_oid,app_oid) OR member IN (bootstrap_oid,migrator_oid,app_oid)) THEN
        RAISE EXCEPTION 'Unexpected role membership prevents legacy repair';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = current_database() AND datdba = migrator_oid) OR
       NOT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'leadflow' AND nspowner = migrator_oid) THEN
        RAISE EXCEPTION 'Historical migrator does not own the expected database and leadflow schema';
    END IF;
    IF EXISTS (
        SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        LEFT JOIN pg_depend d ON d.classid = 'pg_class'::regclass AND d.objid = c.oid AND d.deptype = 'e'
        WHERE c.relowner = migrator_oid AND n.nspname <> 'leadflow' AND d.objid IS NULL
          AND n.nspname NOT LIKE 'pg_%' AND n.nspname <> 'information_schema'
    ) OR EXISTS (
        SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
        LEFT JOIN pg_depend d ON d.classid = 'pg_proc'::regclass AND d.objid = p.oid AND d.deptype = 'e'
        WHERE p.proowner = migrator_oid AND n.nspname <> 'leadflow' AND d.objid IS NULL
          AND n.nspname NOT LIKE 'pg_%' AND n.nspname <> 'information_schema'
    ) THEN
        RAISE EXCEPTION 'Historical migrator owns unsupported user objects outside schema leadflow';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_extension e JOIN pg_namespace n ON n.oid = e.extnamespace WHERE n.nspname = 'leadflow') THEN
        RAISE EXCEPTION 'Extension objects inside schema leadflow require manual review';
    END IF;
END $$;
SELECT format('ALTER ROLE %I RENAME TO %I', :'bootstrap_user', :'transition_user') \gexec
SELECT format('ALTER ROLE %I PASSWORD %L', :'transition_user', :'bootstrap_password') \gexec
COMMIT;
