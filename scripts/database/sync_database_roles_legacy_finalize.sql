\getenv bootstrap_user POSTGRES_BOOTSTRAP_USER
\getenv migrator_user POSTGRES_MIGRATOR_USER
\getenv app_user POSTGRES_APP_USER
\getenv transition_user POSTGRES_TRANSITION_USER

SELECT set_config('leadflow.bootstrap_user', :'bootstrap_user', false) AS configured \gset
SELECT set_config('leadflow.migrator_user', :'migrator_user', false) AS configured \gset
SELECT set_config('leadflow.app_user', :'app_user', false) AS configured \gset
SELECT set_config('leadflow.transition_user', :'transition_user', false) AS configured \gset

DO $$
DECLARE transition_oid oid;
BEGIN
    IF current_user <> current_setting('leadflow.bootstrap_user') OR
       (SELECT oid FROM pg_roles WHERE rolname = current_setting('leadflow.bootstrap_user')) <> 10 THEN
        RAISE EXCEPTION 'Legacy finalization must run as the OID 10 bootstrap';
    END IF;
    IF EXISTS (
        SELECT 1 FROM pg_roles
        WHERE rolname IN (current_setting('leadflow.migrator_user'),current_setting('leadflow.app_user'))
          AND (rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication)
    ) THEN
        RAISE EXCEPTION 'Operational roles retain administrative attributes';
    END IF;
    SELECT oid INTO transition_oid FROM pg_roles WHERE rolname = current_setting('leadflow.transition_user');
    IF transition_oid IS NULL OR
       EXISTS (SELECT 1 FROM pg_shdepend WHERE refclassid = 'pg_authid'::regclass AND refobjid = transition_oid AND deptype = 'o') OR
       EXISTS (SELECT 1 FROM pg_auth_members WHERE roleid = transition_oid OR member = transition_oid) THEN
        RAISE EXCEPTION 'Transition role is not empty and cannot be dropped safely';
    END IF;
END $$;
SELECT format('DROP ROLE %I', :'transition_user') \gexec
